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
    __version__,
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

MOVIE_STATUS_LABELS = {
    "collect": "看过",
    "wish": "想看",
    "do": "在看",
}


def _parse_movie_grid(html_text):
    """解析观影列表单页（grid 视图），返回该页影片 dict 列表。"""
    soup = BeautifulSoup(html_text, "html.parser")
    items = soup.select(".grid-view .item")
    movies = []
    for item in items:
        try:
            movie = {}
            title_elem = item.select_one(".title a")
            if title_elem:
                movie["title"] = title_elem.get_text(strip=True)
                movie["url"] = title_elem.get("href", "")
            rating_elem = item.select_one(".rating")
            if rating_elem:
                rating_class = rating_elem.get("class", [])
                for c in rating_class:
                    if c.startswith("allstar"):
                        movie["rating"] = int(c.replace("allstar", "")[0])
                        break
            date_elem = item.select_one(".date")
            if date_elem:
                movie["date"] = date_elem.get_text(strip=True)
            comment_elem = item.select_one(".comment")
            if comment_elem:
                movie["comment"] = comment_elem.get_text(strip=True)
            if movie.get("url"):
                m = re.search(r"subject/(\d+)", movie["url"])
                if m:
                    movie["douban_id"] = m.group(1)
            if movie.get("title"):
                movies.append(movie)
        except Exception:
            continue
    return movies


def movies_main(config=None):
    """观影记录导出主流程（movies 子命令）。

    纯标准库 + Cookie 实现，无需 Playwright。支持三种观影状态：
    collect=看过、wish=想看、do=在看（由 config movies.types 或 --status 控制）。
    每个状态只保存 JSON 到 output_dir/douban_movies_{status}.json（供增量与后续分析复用）。
    """
    parser = argparse.ArgumentParser(description="豆瓣观影记录导出工具（看过/想看/在看）")
    parser.add_argument("--user", "-u", dest="user_id", default=None, help="豆瓣用户 ID")
    parser.add_argument("--output", "-o", dest="output", default=None, help="输出根目录")
    parser.add_argument("--config", "-c", dest="config", default=None, help="YAML 配置文件路径")
    parser.add_argument("--status", "-s", dest="status", default=None,
                        help="抓取状态: collect=看过/wish=想看/do=在看（可逗号分隔，默认三种全抓）")
    parser.add_argument("--limit", "-l", dest="limit", type=int, default=None, help="限制每状态抓取条数")
    parser.add_argument("--mode", "-m", dest="mode", default=None, choices=["full", "incremental"], help="full=全量/incremental=增量")
    parser.add_argument("--cookie", dest="cookie", default=None, help="豆瓣登录 Cookie 字符串")
    parser.add_argument("--cookie-file", dest="cookie_file", default=None,
                        help="从文件读取豆瓣 Cookie（文件内容或包含 dbcl2= 的行）")
    args = parser.parse_args()

    if config is None:
        config = _load_config(args.config or CONFIG_FILE)
    user_cfg = config.get("user") or {}
    movies_cfg = config.get("movies") or {}

    user_id = args.user_id or user_cfg.get("id")
    if not user_id:
        print("[错误] 未指定豆瓣用户 ID（命令行 -u 或配置 user.id）")
        sys.exit(1)

    output_dir = os.path.abspath(args.output or movies_cfg.get("output") or os.path.join(os.getcwd(), "douban_movies_output"))

    # 状态集合：命令行 --status > 配置 movies.types
    if args.status:
        raw = [s.strip() for s in args.status.split(",") if s.strip()]
        valid = {"collect", "wish", "do"}
        statuses = [s for s in raw if s in valid] or ["collect", "wish", "do"]
    else:
        statuses = movies_cfg.get("statuses") or ["collect", "wish", "do"]

    # 详情由列表接口 subject 内置（类型/导演/演员/评分/年份/上映日期/国家），无需逐部抓取
    run_mode = args.mode or ("incremental" if movies_cfg.get("incremental") else "full")
    limit = args.limit if args.limit is not None else movies_cfg.get("limit")
    # limit 模式（测试用）强制全量：不走增量去重，即使 yaml 设置了 incremental 也不启用
    if limit:
        run_mode = "full"

    cookie_str = args.cookie or user_cfg.get("cookie") or os.environ.get("DOUBAN_COOKIE")
    if not cookie_str and (args.cookie_file or user_cfg.get("cookie_file")):
        cookie_str = load_cookie_file(args.cookie_file or user_cfg.get("cookie_file"))
    opener = _urllib_opener(cookie_str)
    # Rexxar 接口需移动端 UA + Referer，否则返回空/风控
    opener.addheaders = [(k, v) for k, v in opener.addheaders if k not in ("User-Agent", "Referer", "Accept")]
    opener.addheaders += [
        ("User-Agent", "Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Mobile/15E148 Safari/604.1"),
        ("Referer", "https://m.douban.com/"),
        ("Accept", "application/json"),
    ]
    # 解析 ck（Rexxar 接口必需）
    ck = None
    if cookie_str:
        _m = re.search(r"(?:^|;\s*)ck=([^;]+)", cookie_str)
        ck = _m.group(1) if _m else None

    print(f"\n{'='*60}")
    print(f" 影视  | 模式: {run_mode}  |  状态: {' / '.join(MOVIE_STATUS_LABELS.get(s, s) for s in statuses)}")
    print(f" 输出: {output_dir}")
    print(f"{'='*60}")

    all_collected = 0
    # status 映射：config 状态 -> 接口 status 参数
    # 豆瓣新版无 wish 状态，「想看」实际记录为 mark（标记），wish 直接映射到 mark
    status_api_map = {"collect": "done", "wish": "mark", "do": "doing"}
    MAX_PAGES = 100

    for status in statuses:
        label = MOVIE_STATUS_LABELS.get(status, status)
        api_status = status_api_map.get(status, status)
        movies = []
        seen_ids = set()
        start = 0
        page_no = 0
        total_expected = None
        limit_stop = False
        max_pages_stop = False
        print(f"\n  {label}:")
        base_dir = os.path.join(output_dir, "test_output") if limit else output_dir
        json_path = os.path.join(base_dir, f"douban_movies_{status}.json")
        # 统一增量索引：去重只看 .douban_movies_index.json
        # （首次无索引但有数据文件时，从数据文件反推已抓 ID，避免整页重抓）
        existing_ids = set()
        existing_records = {}
        if os.path.exists(json_path):
            try:
                with open(json_path, "r", encoding="utf-8") as f:
                    for m in json.load(f):
                        existing_records[m.get("douban_id")] = m
            except Exception:
                existing_records = {}
        if run_mode == "incremental":
            existing_ids, _ = load_index(output_dir, "movies")
            # 从所有状态的数据文件补充 ID，确保索引完整
            for _s in ["collect", "wish", "do"]:
                _p = os.path.join(output_dir, f"douban_movies_{_s}.json")
                if os.path.exists(_p):
                    existing_ids |= seed_ids_from_json(_p, ["douban_id"])
        consecutive_old = 0
        bar = tqdm(total=None, desc=f"「{label}」", unit="条", leave=True, ncols=90)
        while True:
            api_url = (f"https://m.douban.com/rexxar/api/v2/user/{user_id}/interests"
                       f"?type=movie&status={api_status}&for_mobile=1&ck={urllib.parse.quote(ck)}&start={start}&count=50")
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
            # 接口若忽略 status 参数（如 doing 不受支持），会返回混合数据；发现本页无目标状态即停止
            if all(it.get("status") != api_status for it in page_items):
                tqdm.write(f"  [提示] 接口未按 status={api_status} 过滤（该状态可能不受支持），「{label}」无数据")
                break
            prev_len = len(movies)
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
                movies.append({
                    "interest_id": iid,
                    "status": it.get("status", ""),
                    "douban_id": douban_id,
                    "title": subj.get("title", ""),
                    "url": f"https://movie.douban.com/subject/{douban_id}/",
                    "year": str(subj.get("year", "")),
                    "douban_rating": str((subj.get("rating") or {}).get("value", "")),
                    "rating": rating_obj.get("star_count") or 0,
                    "date": (it.get("create_time") or "")[:10],
                    "comment": (it.get("comment") or "").strip(),
                    # 详情字段：列表接口 subject 自带，一次请求拿全（无需逐部 enrich）
                    "genres": subj.get("genres") or [],
                    "directors": [d.get("name") for d in (subj.get("directors") or [])],
                    "actors": [a.get("name") for a in (subj.get("actors") or [])][:6],
                    "pubdate": " / ".join(subj.get("pubdate") or []),
                    # card_subtitle 形如 "2022 / 美国 澳大利亚 / 剧情 惊悚 / 导演 / 演员"，第 2 段为国家
                    "country": " / ".join((subj.get("card_subtitle") or "").split(" / ")[1].split()) if len((subj.get("card_subtitle") or "").split(" / ")) > 1 else "",
                })
            # 进度：tqdm 滚动进度条（接口首页返回 total，可显示百分比）
            bar.update(len(movies) - prev_len)
            # 每 50 条中间保存
            if not limit:
                _save_checkpoint(movies, json_path)
            # 早停：达到 limit 条即停
            if limit and len(movies) >= limit:
                movies = movies[:limit]
                limit_stop = True
                break
            # 终止：本页不足 20 条 / 已达 total / 超页数保护
            if len(page_items) < 20:
                break
            if total_expected is not None and len(movies) >= total_expected:
                break
            if page_no + 1 >= MAX_PAGES:
                max_pages_stop = True
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
                    bar.total = total_expected or len(movies)
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
            start += 20
            page_no += 1
            time.sleep(randomized_delay(0.5, 1.0))
        bar.close()
        if limit_stop:
            print(f"  已达 limit 上限（{limit} 条），停止")
        elif max_pages_stop:
            print(f"  已达最大翻页数 {MAX_PAGES}，停止")
        pass  # count shown in progress bar
        if not movies:
            continue

        if run_mode == "incremental":
            new_movies = [m for m in movies if m.get("douban_id") not in existing_records]
            if existing_records:
                if not new_movies:
                    print(f"  {label}: 已有 {len(existing_records)} 条，无新增，停止")
                    # 清理中间保存的临时文件
                    tmp_path = json_path + ".tmp"
                    if os.path.exists(tmp_path):
                        os.remove(tmp_path)
                    continue
                print(f"  {label}: 已有 {len(existing_records)} 条，新增 {len(new_movies)} 条")
            merged = {m.get("douban_id"): m for m in movies}
            merged.update(existing_records)
            movies = list(merged.values())
        else:
            merged = {m.get("douban_id"): m for m in movies}
            movies = list(merged.values())


        # 保存 json（合并详情）
        os.makedirs(base_dir, exist_ok=True)
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(movies, f, ensure_ascii=False, indent=2)
        # 清理中间保存的临时文件
        tmp_path = json_path + ".tmp"
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        fname = os.path.basename(json_path)
        print(f"  已生成 {fname}（{len(movies)} 条）")
        all_collected += len(movies)
        # 写盘后更新统一增量索引（测试 limit 模式不写，避免污染）
        if not limit:
            prev_ids, _ = load_index(output_dir, "movies")
            # 从所有状态的数据文件补充 ID，确保索引完整
            for _s in ["collect", "wish", "do"]:
                _p = os.path.join(output_dir, f"douban_movies_{_s}.json")
                if os.path.exists(_p):
                    prev_ids |= seed_ids_from_json(_p, ["douban_id"])
            all_ids = prev_ids | {m.get("douban_id") for m in movies}
            save_index(output_dir, "movies", all_ids, max_page=page_no)
        pass  # merged into result line


    print(f"\n{'='*60}")
    print(f" 影视  | 完成，共处理 {all_collected} 条")
    print(f"{'='*60}")
