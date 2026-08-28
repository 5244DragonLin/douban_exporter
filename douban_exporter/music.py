# -*- coding: utf-8 -*-
import os, re, sys, json, time, random, logging, argparse, csv, html
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin
from bs4 import BeautifulSoup, NavigableString
from tqdm import tqdm
import urllib.request
import urllib.parse
import ssl
import http.cookiejar
from collections import Counter

from .core import (
    sanitize_filename,
    index_path,
    load_index,
    save_index,
    seed_ids_from_json,
    parse_rating_from_class,
    rating_to_stars,
    rating_to_label,
    randomized_delay,
    make_ssl_context,
    make_opener,
    load_cookie_file,
    fetch,
    random_delay,
    _save_checkpoint,
    load_existing_data,
    save_data,
    _load_config,
    _normalize_config,
    _setup_logging,
    _urllib_opener,
    _http_get,
    _clean_html_text,
    DEFAULT_OUTPUT_DIR,
    CONFIG_FILE,
    logger,
    DEFAULT_OUTPUT,
    DEFAULT_DELAY,
    MAX_RETRIES,
    RETRY_DELAY,
    ITEMS_PER_PAGE,
    HEADERS,
)

MUSIC_STATUS_LABELS = {
    "collect": "听过",
    "wish": "想听",
    "do": "在听",
}


def music_main(config=None):
    """音乐记录导出主流程（music 子命令）。

    纯标准库 + Cookie 实现，无需 Playwright。支持三种状态：
    collect=听过、wish=想听、do=在听。
    每个状态保存 JSON 到 output_dir/douban_music_{status}.json。
    使用 Rexxar API（与 movies/games 一致），详情由列表接口一次返回。
    """
    parser = argparse.ArgumentParser(description="豆瓣音乐记录导出工具（听过/想听/在听）")
    parser.add_argument("--user", "-u", dest="user_id", default=None, help="豆瓣用户 ID")
    parser.add_argument("--output", "-o", dest="output", default=None, help="输出根目录")
    parser.add_argument("--config", "-c", dest="config", default=None, help="YAML 配置文件路径")
    parser.add_argument("--status", "-s", dest="status", default=None,
                        help="抓取状态: collect=听过/wish=想听/do=在听（可逗号分隔，默认三种全抓）")
    parser.add_argument("--limit", "-l", dest="limit", type=int, default=None, help="限制每状态抓取条数")
    parser.add_argument("--mode", "-m", dest="mode", default=None, choices=["full", "incremental"],
                        help="full=全量/incremental=增量")
    parser.add_argument("--cookie", dest="cookie", default=None, help="豆瓣登录 Cookie 字符串")
    parser.add_argument("--cookie-file", dest="cookie_file", default=None,
                        help="从文件读取豆瓣 Cookie")
    args = parser.parse_args()

    if config is None:
        config = _load_config(args.config or CONFIG_FILE)
    user_cfg = config.get("user") or {}
    music_cfg = config.get("music") or {}

    user_id = args.user_id or user_cfg.get("id")
    if not user_id:
        print("[错误] 未指定豆瓣用户 ID（命令行 -u 或配置 user.id）")
        sys.exit(1)

    output_dir = os.path.abspath(args.output or music_cfg.get("output") or os.path.join(os.getcwd(), "douban_music_output"))

    if args.status:
        raw = [s.strip() for s in args.status.split(",") if s.strip()]
        valid = {"collect", "wish", "do"}
        statuses = [s for s in raw if s in valid] or ["collect", "wish", "do"]
    else:
        statuses = music_cfg.get("statuses") or ["collect", "wish", "do"]

    run_mode = args.mode or ("incremental" if music_cfg.get("incremental") else "full")
    limit = args.limit if args.limit is not None else music_cfg.get("limit")
    if limit:
        run_mode = "full"

    cookie_str = args.cookie or user_cfg.get("cookie") or os.environ.get("DOUBAN_COOKIE")
    if not cookie_str and (args.cookie_file or user_cfg.get("cookie_file")):
        cookie_str = load_cookie_file(args.cookie_file or user_cfg.get("cookie_file"))
    opener = _urllib_opener(cookie_str)
    opener.addheaders = [(k, v) for k, v in opener.addheaders if k not in ("User-Agent", "Referer", "Accept")]
    opener.addheaders += [
        ("User-Agent", "Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Mobile/15E148 Safari/604.1"),
        ("Referer", "https://m.douban.com/"),
        ("Accept", "application/json"),
    ]
    ck = None
    if cookie_str:
        _m = re.search(r"(?:^|;\s*)ck=([^;]+)", cookie_str)
        ck = _m.group(1) if _m else None

    print(f"\n{'='*60}")
    print(f" 音乐  | 模式: {run_mode}  |  状态: {' / '.join(MUSIC_STATUS_LABELS.get(s, s) for s in statuses)}")
    print(f" 输出: {output_dir}")
    print(f"{'='*60}")

    all_collected = 0
    status_api_map = {"collect": "done", "wish": "mark", "do": "doing"}
    MAX_PAGES = 100

    for status in statuses:
        label = MUSIC_STATUS_LABELS.get(status, status)
        api_status = status_api_map.get(status, status)
        items_list = []
        seen_ids = set()
        start = 0
        page_no = 0
        total_expected = None
        limit_stop = False
        print(f"\n  {label}:")
        from tqdm import tqdm
        base_dir = os.path.join(output_dir, "test_output") if limit else output_dir
        json_path = os.path.join(base_dir, f"douban_music_{status}.json")
        # 统一增量索引：去重只看 .douban_music_index.json
        # （首次无索引但有数据文件时，从数据文件反推已抓 ID，避免整页重抓）
        existing_ids = set()
        existing_records = {}
        if os.path.exists(json_path):
            try:
                with open(json_path, "r", encoding="utf-8") as f:
                    for g in json.load(f):
                        existing_records[g.get("douban_id")] = g
            except Exception:
                existing_records = {}
        if run_mode == "incremental":
            existing_ids, _ = load_index(output_dir, "music")
            # 从所有状态的数据文件补充 ID，确保索引完整
            for _s in ["collect", "wish", "do"]:
                _p = os.path.join(output_dir, f"douban_music_{_s}.json")
                if os.path.exists(_p):
                    existing_ids |= seed_ids_from_json(_p, ["douban_id"])
        consecutive_old = 0
        bar = tqdm(total=None, desc=f"「{label}」", unit="条", leave=True, ncols=90)
        while True:
            api_url = (f"https://m.douban.com/rexxar/api/v2/user/{user_id}/interests"
                       f"?type=music&status={api_status}&for_mobile=1&ck={urllib.parse.quote(ck)}&start={start}&count=50")
            try:
                resp = opener.open(api_url, timeout=20)
                data = json.loads(resp.read().decode("utf-8", errors="replace"))
            except Exception as ex:
                tqdm.write(f" [警告] 第 {page_no+1} 页接口请求失败: {ex}，停止翻页")
                break
            if total_expected is None:
                total_expected = data.get("total")
                if total_expected:
                    bar.total = total_expected
                    bar.refresh()
            page_items = data.get("interests") or []
            if not page_items:
                break
            if all(it.get("status") != api_status for it in page_items):
                tqdm.write(f"  [提示] 接口未按 status={api_status} 过滤，「{label}」无数据")
                break
            prev_len = len(items_list)
            for it in page_items:
                iid = str(it.get("id") or "")
                if iid in seen_ids:
                    continue
                seen_ids.add(iid)
                subj = it.get("subject") or {}
                douban_id = str(subj.get("id") or it.get("subject_id") or "")
                if not douban_id:
                    continue
                rating_obj = it.get("rating") or {}
                items_list.append({
                    "interest_id": iid,
                    "status": it.get("status", ""),
                    "douban_id": douban_id,
                    "title": subj.get("title", ""),
                    "url": f"https://music.douban.com/subject/{douban_id}/",
                    "artist": subj.get("card_subtitle", ""),
                    "genres": subj.get("genres") or [],
                    "rating": rating_obj.get("star_count") or 0,
                    "date": (it.get("create_time") or "")[:10],
                    "comment": (it.get("comment") or "").strip(),
                })
            bar.update(len(items_list) - prev_len)
            # 每 50 条中间保存
            if not limit:
                _save_checkpoint(items_list, json_path)
            if limit and len(items_list) >= limit:
                items_list = items_list[:limit]
                limit_stop = True
                break
            # 增量模式早停：检查本页是否全部已有（基于统一索引）
            if run_mode == "incremental" and existing_ids:
                page_all_old = True
                for it in page_items:
                    douban_id = str(it.get("subject", {}).get("id") or it.get("subject_id") or "")
                    if douban_id and douban_id not in existing_ids:
                        page_all_old = False
                        break
                if page_all_old:
                    consecutive_old += 1
                else:
                    consecutive_old = 0
                if consecutive_old >= 2:
                    bar.total = total_expected or len(items_list)
                    bar.n = bar.total
                    bar.refresh()
                    pass  # merged into result line
                    break
                # 优化：如果 total 与本地记录数一致，且第1页全旧，无需再翻第2页
                if consecutive_old == 1 and total_expected is not None and total_expected == len(existing_ids):
                    bar.total = total_expected
                    bar.n = total_expected
                    bar.refresh()
                    pass  # merged into result line
                    break
            if len(page_items) < 20:
                break
            if total_expected is not None and len(items_list) >= total_expected:
                break
            if page_no + 1 >= MAX_PAGES:
                break
            start += 20
            page_no += 1
            time.sleep(randomized_delay(0.5, 1.0))
        bar.close()
        if limit_stop:
            print(f"  已达 limit 上限（{limit} 条），停止")
        pass  # count shown in progress bar
        if not items_list:
            continue
        if run_mode == "incremental":
            new_items = [g for g in items_list if g.get("douban_id") not in existing_records]
            if existing_records:
                if not new_items:
                    print(f"  {label}: 已有 {len(existing_records)} 条，无新增，停止")
                    tmp_path = json_path + ".tmp"
                    if os.path.exists(tmp_path):
                        os.remove(tmp_path)
                    continue
                print(f"  {label}: 已有 {len(existing_records)} 条，新增 {len(new_items)} 条")
            merged = {g.get("douban_id"): g for g in items_list}
            merged.update(existing_records)
            items_list = list(merged.values())
        else:
            merged = {g.get("douban_id"): g for g in items_list}
            items_list = list(merged.values())

        os.makedirs(base_dir, exist_ok=True)
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(items_list, f, ensure_ascii=False, indent=2)
        # 清理中间保存的临时文件
        tmp_path = json_path + ".tmp"
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        fname = os.path.basename(json_path)
        print(f"  已生成 {fname}（{len(items_list)} 条）")
        all_collected += len(items_list)
        # 写盘后更新统一增量索引（测试 limit 模式不写，避免污染）
        if not limit:
            prev_ids, _ = load_index(output_dir, "music")
            # 从所有状态的数据文件补充 ID，确保索引完整
            for _s in ["collect", "wish", "do"]:
                _p = os.path.join(output_dir, f"douban_music_{_s}.json")
                if os.path.exists(_p):
                    prev_ids |= seed_ids_from_json(_p, ["douban_id"])
            all_ids = prev_ids | {g.get("douban_id") for g in items_list}
            save_index(output_dir, "music", all_ids, max_page=page_no)
        pass  # merged into result line

    print(f"\n{'='*60}")
    print(f" 音乐  | 完成，共处理 {all_collected} 条")
    print(f"{'='*60}")
