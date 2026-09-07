# -*- coding: utf-8 -*-
"""books / movies / games / music 共用的 Rexxar interests 导出管线。

四个子命令的抓取流程完全一致（移动端 opener、Rexxar 分页、limit/max-pages 早停、
增量去重与索引、checkpoint、合并写盘），差异仅在于：
- api_type（book/movie/game/music）与各状态中文标签
- 单条记录的字段映射（build_record 回调）
- 去重主键字段名（books 用「豆瓣ID」，其余用 douban_id）
"""
import json
import os
import re
import time
import urllib.parse

from tqdm import tqdm

from .core import (
    MAX_RETRIES,
    RETRY_DELAY,
    _save_checkpoint,
    load_cookie_file,
    load_index,
    make_opener,
    randomized_delay,
    save_index,
    seed_ids_from_json,
)

# 豆瓣新版无 wish 状态，「想看/想玩/想听/想读」实际记录为 mark（标记），wish 直接映射 mark
STATUS_API_MAP = {"collect": "done", "wish": "mark", "do": "doing"}
DEFAULT_MAX_PAGES = 100
PAGE_SIZE = 50  # Rexxar 接口实测支持 count=50，翻页步进必须与之一致，否则相邻页大量重复下载

MOBILE_UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) "
             "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Mobile/15E148 Safari/604.1")


def make_mobile_opener(cookie_str):
    """Rexxar 接口需移动端 UA + Referer，否则返回空/风控。"""
    opener = make_opener(cookie_str)
    opener.addheaders = [(k, v) for k, v in opener.addheaders if k not in ("User-Agent", "Referer", "Accept")]
    opener.addheaders += [
        ("User-Agent", MOBILE_UA),
        ("Referer", "https://m.douban.com/"),
        ("Accept", "application/json"),
    ]
    return opener


def resolve_cookie(args_cookie, args_cookie_file, user_cfg):
    """Cookie 优先级：命令行 > 配置 user.cookie > 环境变量 DOUBAN_COOKIE > cookie 文件。"""
    cookie_str = args_cookie or user_cfg.get("cookie") or os.environ.get("DOUBAN_COOKIE")
    if not cookie_str and (args_cookie_file or user_cfg.get("cookie_file")):
        cookie_str = load_cookie_file(args_cookie_file or user_cfg.get("cookie_file"))
    return cookie_str


def parse_ck(cookie_str):
    """从 Cookie 中解析 ck（Rexxar 接口必需），无 Cookie 时返回 None。"""
    if not cookie_str:
        return None
    m = re.search(r"(?:^|;\s*)ck=([^;]+)", cookie_str)
    return m.group(1) if m else None


def parse_status_list(raw):
    """解析状态列表：支持逗号分隔字符串或列表，非法值忽略；全非法/为空回退三种全抓。"""
    valid = {"collect", "wish", "do"}
    if isinstance(raw, str):
        raw = raw.split(",")
    parsed = [s.strip() for s in (raw or []) if isinstance(s, str) and s.strip() in valid]
    return parsed or ["collect", "wish", "do"]


def export_interests(user_id, output_dir, statuses, run_mode, limit, *,
                     kind, api_type, title, labels, build_record, dedup_key,
                     max_pages=None, no_delay=False, cookie_str=None):
    """通用 interests 导出主流程。

    Args:
        kind: 输出文件名与索引的类型名（books/movies/games/music）
        api_type: Rexxar 接口 type 参数（book/movie/game/music）
        title: 汇总输出中的功能显示名（书籍/影视/游戏/音乐）
        labels: {status: 中文标签}
        build_record: (it, subj, label) -> dict，返回单条记录（须含 dedup_key 字段）
        dedup_key: 去重主键字段名（books 用「豆瓣ID」，其余用 douban_id）
        max_pages: 每状态最大翻页数（None 用 DEFAULT_MAX_PAGES 保护）
        no_delay: 禁用翻页间随机延迟（仅测试用）
        cookie_str: 登录 Cookie（可为空，匿名抓取）

    Returns:
        (总条数, [(输出文件路径, 条数)])
    """
    ck = parse_ck(cookie_str)
    opener = make_mobile_opener(cookie_str)

    print(f"\n{'='*60}")
    print(f" {title}  | 模式: {run_mode}  |  状态: {' / '.join(labels.get(s, s) for s in statuses)}")
    print(f" 输出: {output_dir}")
    print(f"{'='*60}")

    max_pages_limit = max_pages or DEFAULT_MAX_PAGES
    base_dir = os.path.join(output_dir, "test_output") if limit else output_dir

    # 统一增量索引：启动时读一次索引与各状态数据文件，运行中累加，
    # 避免每个状态重复读盘（首次无索引但有数据文件时，从数据文件反推已抓 ID）
    known_ids, _ = load_index(output_dir, kind)
    for _s in ("collect", "wish", "do"):
        _p = os.path.join(output_dir, f"douban_{kind}_{_s}.json")
        if os.path.exists(_p):
            known_ids |= seed_ids_from_json(_p, [dedup_key])

    total_collected = 0
    saved_files = []

    for status in statuses:
        label = labels.get(status, status)
        api_status = STATUS_API_MAP.get(status, status)
        json_path = os.path.join(base_dir, f"douban_{kind}_{status}.json")

        existing_records = {}
        if run_mode == "incremental" and os.path.exists(json_path):
            try:
                with open(json_path, "r", encoding="utf-8") as f:
                    for r in json.load(f):
                        existing_records[r.get(dedup_key)] = r
            except Exception:
                existing_records = {}

        records = []
        seen_ids = set()
        start = 0
        page_no = 0
        total_expected = None
        limit_stop = False
        max_pages_stop = False
        consecutive_old = 0
        last_saved = 0

        print(f"\n  {label}:")
        # 网页版不暴露总条数，接口首页返回 total 后进度条可显示百分比
        bar = tqdm(total=None, desc=f"「{label}」", unit="条", leave=True, ncols=90)
        while True:
            api_url = (f"https://m.douban.com/rexxar/api/v2/user/{user_id}/interests"
                       f"?type={api_type}&status={api_status}&for_mobile=1"
                       f"&ck={urllib.parse.quote(ck)}&start={start}&count={PAGE_SIZE}")
            data = None
            for attempt in range(MAX_RETRIES):
                try:
                    resp = opener.open(api_url, timeout=20)
                    data = json.loads(resp.read().decode("utf-8", errors="replace"))
                    break
                except Exception as ex:
                    tqdm.write(f" [警告] 第 {page_no+1} 页接口请求失败 (尝试 {attempt+1}/{MAX_RETRIES}): {ex}")
                    if attempt < MAX_RETRIES - 1:
                        time.sleep(RETRY_DELAY)
            if data is None:
                tqdm.write(f" [警告] 第 {page_no+1} 页接口请求失败，停止翻页")
                break
            if total_expected is None:
                total_expected = data.get("total")
                if total_expected:
                    bar.total = total_expected
                    bar.refresh()
            page_items = data.get("interests") or []
            if not page_items:
                break
            # 接口若忽略 status 参数（如 doing 不受支持），会返回混合数据；发现本页无目标状态即停止
            if all(it.get("status") != api_status for it in page_items):
                tqdm.write(f"  [提示] 接口未按 status={api_status} 过滤（该状态可能不受支持），「{label}」无数据")
                break
            prev_len = len(records)
            for it in page_items:
                iid = str(it.get("id") or "")
                if iid in seen_ids:
                    continue
                seen_ids.add(iid)
                record = build_record(it, it.get("subject") or {}, label)
                if record and record.get(dedup_key):
                    records.append(record)
            bar.update(len(records) - prev_len)
            # 每 50 条中间保存（limit 测试模式不写，避免污染正式文件）
            if not limit and len(records) - last_saved >= 50:
                _save_checkpoint(records, json_path)
                last_saved = len(records)
            # 早停：达到 limit 条即停
            if limit and len(records) >= limit:
                records = records[:limit]
                limit_stop = True
                break
            # 终止：本页不足一页 / 已达 total / 超页数保护
            if len(page_items) < PAGE_SIZE:
                break
            if total_expected is not None and len(records) >= total_expected:
                break
            if page_no + 1 >= max_pages_limit:
                max_pages_stop = True
                break
            # 增量模式早停：本页全部已有则连续计数，连续 2 页全旧即停（避免老条目
            # 被重新操作顶到列表最前时，其后新条目被误判为边界而漏抓）；
            # 若 total 与本地该状态条数一致且第 1 页全旧，无需再翻第 2 页
            if run_mode == "incremental" and known_ids:
                page_all_old = True
                for it in page_items:
                    sid = str((it.get("subject") or {}).get("id") or it.get("subject_id") or "")
                    if sid and sid not in known_ids:
                        page_all_old = False
                        break
                if page_all_old:
                    consecutive_old += 1
                else:
                    consecutive_old = 0
                if consecutive_old >= 2:
                    bar.total = total_expected or len(records)
                    bar.n = bar.total
                    bar.refresh()
                    break
                if consecutive_old == 1 and total_expected is not None and total_expected == len(existing_records):
                    bar.total = total_expected
                    bar.n = bar.total
                    bar.refresh()
                    break
            start += PAGE_SIZE
            page_no += 1
            if not no_delay:
                time.sleep(randomized_delay(0.5, 1.0))
        bar.close()
        if limit_stop:
            print(f"  已达 limit 上限（{limit} 条），停止")
        elif max_pages_stop:
            print(f"  已达最大翻页数 {max_pages_limit}，停止")
        if not records:
            continue

        if run_mode == "incremental":
            new_records = [r for r in records if r.get(dedup_key) not in existing_records]
            if existing_records:
                if not new_records:
                    print(f"  {label}: 已有 {len(existing_records)} 条，无新增，停止")
                    tmp_path = json_path + ".tmp"
                    if os.path.exists(tmp_path):
                        os.remove(tmp_path)
                    continue
                print(f"  {label}: 已有 {len(existing_records)} 条，新增 {len(new_records)} 条")
            # 合并：本次新抓数据覆盖旧记录（评分/短评可能已更新），未被重抓的旧条目保留
            merged = dict(existing_records)
        else:
            # 全量模式：文件内容完全由本次抓取重建
            merged = {}
        merged.update({r.get(dedup_key): r for r in records})
        records = list(merged.values())

        # 保存 json
        os.makedirs(base_dir, exist_ok=True)
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(records, f, ensure_ascii=False, indent=2)
        tmp_path = json_path + ".tmp"
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        print(f"  已生成 {os.path.basename(json_path)}（{len(records)} 条）")
        total_collected += len(records)
        saved_files.append((json_path, len(records)))

        # 写盘后更新统一增量索引（limit 测试模式不写，避免污染）
        if not limit:
            known_ids |= {r.get(dedup_key) for r in records}
            save_index(output_dir, kind, known_ids, max_page=page_no)

    return total_collected, saved_files
