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

COLLECT_TYPES = {
    "collect": {"label": "读过", "path": "/people/{uid}/collect"},
    "wish":    {"label": "想读", "path": "/people/{uid}/wish"},
    "do":      {"label": "在读", "path": "/people/{uid}/do"},
}


def parse_pub(pub_str):
    """
    解析 pub 字段，格式示例：
    有译者: "（日）堀纟子 / 吕艳 / 浙江文艺出版社 / 2024-5-1 / 45.00"
    无译者: "阿西阿呷 / 太白文艺出版社 / 2026-3-19 / 49.80"
    返回: (author, translator, publisher, pub_date, price)
    """
    parts = [p.strip() for p in pub_str.strip().split("/")]

    author = parts[0] if len(parts) > 0 else ""

    publisher_keywords = ['出版社', '出版', '书店', '书房']
    date_pattern = re.compile(r'\d{4}[-/年]\d{1,2}')
    price_pattern = re.compile(r'^[\d.,]+元?$')

    translator = ""
    publisher = ""
    pub_date = ""
    price = ""

    if len(parts) >= 3:
        part2 = parts[1].strip()
        if (part2 and
                not any(kw in part2 for kw in publisher_keywords) and
                not date_pattern.match(part2) and
                not price_pattern.match(part2) and
                len(part2) < 20):
            translator = part2
            publisher = parts[2] if len(parts) > 2 else ""
            pub_date = parts[3] if len(parts) > 3 else ""
            price = parts[4] if len(parts) > 4 else ""
        else:
            publisher = part2
            pub_date = parts[2] if len(parts) > 2 else ""
            price = parts[3] if len(parts) > 3 else ""

    return author, translator, publisher, pub_date, price


def parse_rating(rating_html):
    """从 rating span 中提取星级（1-5）。"""
    m = re.search(r'class="rating(\d)-t"', rating_html)
    return int(m.group(1)) if m else 0


def parse_date(date_str):
    """
    解析日期字段，格式示例：
    "2026-05-17\n 读过"
    返回: (add_date, status)
    """
    date_str = re.sub(r'\s+', ' ', date_str.strip())
    parts = date_str.split()
    add_date = parts[0] if parts else ""
    status_text = parts[1] if len(parts) > 1 else ""
    status_map = {"读过": "已读", "想读": "想读", "在读": "在读"}
    status = status_map.get(status_text, status_text)
    return add_date, status


def parse_item(item_html):
    """
    解析单个 subject-item 的 HTML，提取书籍信息。
    返回 dict 或 None。
    """
    try:
        book_url_match = re.search(r'href="https://book\.douban\.com/subject/(\d+)/"', item_html)
        book_id = book_url_match.group(1) if book_url_match else ""

        title_match = re.search(r'<h2[^>]*>.*?<a[^>]+title="([^"]+)"', item_html, re.DOTALL)
        title = title_match.group(1).strip() if title_match else ""

        tags = []
        tag_matches = re.findall(r'<span class="[^"]*tag[^"]*">([^<]+)</span>', item_html)
        for tag in tag_matches[:5]:
            tag = tag.strip()
            # 清理“标签: ”前缀，并将空格分隔的多个标签拆开
            if tag.startswith("标签:") or tag.startswith("标签："):
                tag = tag.split(":", 1)[-1].split("：", 1)[-1].strip()
            for sub in re.split(r"[\s,，、]+", tag):
                sub = sub.strip()
                if sub and sub not in tags:
                    tags.append(sub)
        tags_str = "，".join(tags)

        pub_match = re.search(r'<div class="pub">(.*?)</div>', item_html, re.DOTALL)
        pub_str = pub_match.group(1).strip() if pub_match else ""
        author, translator, publisher, pub_date, price = parse_pub(pub_str)

        rating_match = re.search(r'<div class="short-note">(.*?)</div>', item_html, re.DOTALL)
        my_rating = 0
        if rating_match:
            rating_html = rating_match.group(1)
            my_rating = parse_rating(rating_html)

        date_match = re.search(r'<span class="date">([^<]+)</span>', item_html)
        add_date, status = ("", "未知")
        if date_match:
            add_date, status = parse_date(date_match.group(1))

        comment_match = re.search(r'<p class="comment comment-item"[^>]*>(.*?)</p>', item_html, re.DOTALL)
        my_comment = comment_match.group(1).strip() if comment_match else ""

        douban_url = f"https://book.douban.com/subject/{book_id}/" if book_id else ""

        return {
            "豆瓣ID": book_id,
            "豆瓣链接": douban_url,
            "书名": title,
            "作者": author,
            "译者": translator,
            "出版社": publisher,
            "出版日期": pub_date,
            "我的评分": my_rating,
            "阅读日期": add_date,
            "状态": status,
            "我的评论": my_comment,
            "标签": tags_str,
        }
    except Exception as e:
        print(f" [错误] 解析书籍条目失败: {e}")
        return None


def parse_page(html):
    """解析整页 HTML，返回书籍条目列表。"""
    if not html:
        return []
    items = re.findall(r'<li[^>]+class="[^"]*subject-item[^"]*"[^>]*>(.*?)</li>', html, re.DOTALL)
    results = []
    for item_html in items:
        book = parse_item(item_html)
        if book and book.get("豆瓣ID"):
            results.append(book)
    return results


def get_total_count(html):
    """从页面 HTML 中提取总数（用于估算页数）。"""
    if not html:
        return 0
    m = re.search(r'<title>([^<]+)</title>', html)
    if not m:
        return 0
    m2 = re.search(r'\((\d+)\)', m.group(1))
    return int(m2.group(1)) if m2 else 0


def has_next_page(html):
    """检查页面是否还有下一页。"""
    if not html:
        return False
    return bool(re.search(r'class="[^"]*next[^"]*"', html))


def fetch_collection(opener, uid, collect_type, max_pages=None, known_ids=None, limit=None, checkpoint_path=None):
    """
    抓取指定分类的所有页面。

    Args:
        opener: urllib Opener
        uid: 豆瓣用户 ID
        collect_type: "collect" | "wish" | "do"
        max_pages: 最大抓取页数（None=不限制）
        known_ids: 已存在的 book_id 集合，用于增量去重
        limit: 每类抓取条数上限（None=不限制），达到即停止翻页

    Returns:
        list[dict]: 书籍条目列表
    """
    info = COLLECT_TYPES.get(collect_type, {})
    label = info.get("label", collect_type)
    path_template = info.get("path", "/people/{uid}/collect")
    path = path_template.format(uid=uid)

    results = []
    start = 0
    page = 1
    known_ids = known_ids or set()
    stop_reason = ""
    limit_stop = False
    page_all_known = False

    print(f"\n  {label}:")
    # 网页版不暴露总条数，tqdm 用 total=None 显示实时计数进度
    bar = tqdm(total=None, desc=f"「{label}」", unit="条", leave=True, ncols=90)

    while True:
        if max_pages and page > max_pages:
            stop_reason = "达到最大页数限制"
            break

        url = f"https://book.douban.com{path}?start={start}"
        if start > 0:
            random_delay()

        html = fetch(url, opener)
        if not html:
            stop_reason = "页面获取失败"
            break

        items = parse_page(html)
        if not items:
            stop_reason = "页面为空或解析失败"
            break

        # 增量去重：本页只要有一本「本地没有的书」就视为存在新增，继续翻页；
        # 仅当整页全部为已有书籍时才停止（避免老书被重新操作顶到列表最前时，
        # 其后的新书被误判为「已到边界」而漏抓）。与 movies/games/music 逻辑对齐。
        new_items = []
        page_all_known = True
        for item in items:
            bid = item.get("豆瓣ID", "")
            if bid in known_ids:
                continue
            page_all_known = False
            new_items.append(item)

        prev_len = len(results)
        results.extend(new_items)
        bar.update(len(results) - prev_len)

        # 每 50 条中间保存
        if checkpoint_path:
            _save_checkpoint(results, checkpoint_path)

        # limit 早停：达到上限即停，避免 limit 测试时仍全量翻页
        if limit and len(results) >= limit:
            results = results[:limit]
            stop_reason = f"达到 limit 早停上限（{limit} 条）"
            limit_stop = True
            break

        if page_all_known:
            stop_reason = "增量同步：整页均为已有书籍"
            break

        if not has_next_page(html):
            stop_reason = "已到最后一页"
            break

        start += ITEMS_PER_PAGE
        page += 1

    if not results:
        bar.clear()
    bar.close()
    if limit_stop:
        print(f"  已达 limit 上限（{limit} 条），停止")
    return results


def books_main(config=None):
    parser = argparse.ArgumentParser(description="豆瓣读书数据抓取工具（已读/想读/在读）")
    parser.add_argument("--user", "-u", dest="user_id", default=None,
                        help="豆瓣用户 ID")
    parser.add_argument("--output", "-o", dest="output", default=None,
                        help="输出目录（默认: ~，文件名固定为 douban_books，扩展名由 --format 决定）")
    parser.add_argument("--config", "-c", dest="config", default=None,
                        help="YAML 配置文件路径（默认自动加载脚本同目录 config.yaml）")
    parser.add_argument("--mode", "-m", dest="mode", default=None,
                        choices=["full", "incremental"],
                        help="抓取模式: full=全量, incremental=增量翻页（默认: 根据配置 books.incremental 决定）")
    parser.add_argument("--format", "-f", dest="fmt", default=None,
                        choices=["json"],
                        help="输出格式: json（固定，仅支持 json）")
    parser.add_argument("--type", "-t", dest="types", action="append",
                        choices=["collect", "wish", "do"],
                        help="指定抓取分类（可多次指定）；不指定则使用 config.yaml 的 books.types；若都未指定则抓取全部（collect=已读/wish=想读/do=在读）")
    parser.add_argument("--limit", "-l", dest="limit", type=int, default=None, help="限制每类抓取条数，用于测试")
    parser.add_argument("--max-pages", dest="max_pages", type=int, default=None,
                        help="每分类最大页数（用于测试/调试）")
    parser.add_argument("--no-delay", dest="no_delay", action="store_true",
                        help="禁用随机延迟（仅用于测试）")
    parser.add_argument("--cookie", dest="cookie", default=None,
                        help="豆瓣登录 Cookie 字符串（如 'dbcl2=xxx; ck=xxx'），不传则读取环境变量 DOUBAN_COOKIE")
    parser.add_argument("--cookie-file", dest="cookie_file", default=None,
                        help="从文件读取豆瓣 Cookie（文件内容或包含 dbcl2= 的行）")
    args = parser.parse_args()

    # 加载 YAML 配置：优先使用调用方传入的 config，否则自行加载（未指定 -c 时自动加载同目录 config.yaml）
    if config is None:
        config = _load_config(args.config or CONFIG_FILE)
    user_cfg = config.get("user") or {}
    books_cfg = config.get("books") or {}

    # 解析输出路径：命令行 -o > 配置 books.output > 默认

    # 解析输出路径：命令行 -o > 配置 books.output > 默认
    # books.output 为目录，文件名固定 douban_books，扩展名由 fmt 决定
    if not args.output and books_cfg.get("output"):
        args.output = books_cfg["output"]
    if not args.output:
        args.output = os.path.dirname(DEFAULT_OUTPUT)  # ~

    # books 固定输出 json（不需要 csv，格式选项仅保留 json）
    fmt = "json"

    # 构造输出文件：目录 + 固定文件名 douban_books.json
    output_path = os.path.join(args.output, "douban_books.json")

    # 确认用户 ID（优先级：命令行 > YAML 配置 user.id > 交互输入）
    user_id = args.user_id or user_cfg.get("id")
    if not user_id:
        user_id = input("请输入豆瓣用户 ID: ").strip()

    if not user_id:
        print("[错误] 未提供用户 ID")
        sys.exit(1)

    start_time = time.time()

    run_mode = args.mode or ("incremental" if books_cfg.get("incremental") else "full")
    if args.limit is None:
        args.limit = books_cfg.get("limit")
    if args.limit:
        run_mode = "full"

    types_to_fetch = args.types or books_cfg.get("types") or ["collect", "wish", "do"]

    print(f"\n{'='*60}")
    print(f" 书籍  | 模式: {run_mode}  |  分类: {', '.join(types_to_fetch)}")
    print(f" 输出: {args.output}")
    print(f"{'='*60}")

    global DEFAULT_DELAY
    if args.no_delay:
        DEFAULT_DELAY = (0.1, 0.2)

    cookie_str = args.cookie or user_cfg.get("cookie") or os.environ.get("DOUBAN_COOKIE")
    if not cookie_str and (args.cookie_file or user_cfg.get("cookie_file")):
        cookie_str = load_cookie_file(args.cookie_file or user_cfg.get("cookie_file"))

    # Rexxar API 所需的 opener 和 ck
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

    all_books = []
    saved_files = []

    def _per_type_path(ctype):
        """按分类生成独立的输出文件路径（已读/想读/在读分开存储）。
        limit 测试模式输出到 test_output/ 子目录，避免污染正式文件（正式文件供增量去重）。"""
        base = os.path.join(args.output, "test_output") if args.limit else args.output
        return os.path.join(base, f"douban_books_{ctype}.{fmt}")

    # 统一增量索引：所有类型的已抓 book id 汇总到 .douban_books_index.json
    status_api_map = {"collect": "done", "wish": "mark", "do": "doing"}
    MAX_PAGES = 100

    for ctype in types_to_fetch:
        label = COLLECT_TYPES.get(ctype, {}).get("label", ctype)
        api_status = status_api_map.get(ctype, ctype)
        base_dir = os.path.join(args.output, "test_output") if args.limit else args.output
        json_path = os.path.join(base_dir, f"douban_books_{ctype}.{fmt}")

        # 加载已有数据
        existing_ids = set()
        existing_records = {}
        if os.path.exists(json_path):
            try:
                with open(json_path, "r", encoding="utf-8") as f:
                    for b in json.load(f):
                        existing_records[b.get("豆瓣ID")] = b
            except Exception:
                existing_records = {}
        if run_mode == "incremental":
            existing_ids, _ = load_index(args.output, "books")
            for _s in ["collect", "wish", "do"]:
                _p = os.path.join(args.output, f"douban_books_{_s}.{fmt}")
                if os.path.exists(_p):
                    existing_ids |= seed_ids_from_json(_p, ["豆瓣ID"])

        print(f"\n  {label}:")
        books = []
        seen_ids = set()
        start = 0
        page_no = 0
        total_expected = None
        limit_stop = False
        consecutive_old = 0
        bar = tqdm(total=None, desc=f"「{label}」", unit="条", leave=True, ncols=90)
        while True:
            api_url = (f"https://m.douban.com/rexxar/api/v2/user/{user_id}/interests"
                       f"?type=book&status={api_status}&for_mobile=1&ck={urllib.parse.quote(ck)}&start={start}&count=50")
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
                tqdm.write(f"  [提示] 接口未按 status={api_status} 过滤，{label}无数据")
                break
            prev_len = len(books)
            for it in page_items:
                iid = str(it.get("id") or "")
                if iid in seen_ids:
                    continue
                seen_ids.add(iid)
                subj = it.get("subject") or {}
                douban_id = str(subj.get("id") or "")
                if not douban_id:
                    continue
                rating_obj = it.get("rating") or {}
                authors = subj.get("author") or []
                books.append({
                    "豆瓣ID": douban_id,
                    "书名": subj.get("title", ""),
                    "阅读日期": (it.get("create_time") or "")[:10],
                    "状态": label,
                    "标签": "",
                    "作者": ", ".join(authors) if isinstance(authors, list) else str(authors),
                    "译者": "",
                    "出版社": subj.get("press", ""),
                    "出版日期": subj.get("pubdate", ""),
                    "我的评分": rating_obj.get("star_count") or 0,
                    "我的评论": (it.get("comment") or "").strip(),
                    "豆瓣链接": f"https://book.douban.com/subject/{douban_id}/",
                })
            bar.update(len(books) - prev_len)
            # 每 50 条中间保存
            if not args.limit:
                _save_checkpoint(books, json_path)
            # 早停：达到 limit 条即停
            if args.limit and len(books) >= args.limit:
                books = books[:args.limit]
                limit_stop = True
                break
            # 终止：本页不足 20 条 / 已达 total / 超页数保护
            if len(page_items) < 20:
                break
            if total_expected is not None and len(books) >= total_expected:
                break
            if page_no + 1 >= MAX_PAGES:
                break
            # 增量模式早停
            if run_mode == "incremental" and existing_ids:
                page_all_old = True
                for it in page_items:
                    douban_id = str(it.get("subject", {}).get("id") or "")
                    if douban_id and douban_id not in existing_ids:
                        page_all_old = False
                        break
                if page_all_old:
                    consecutive_old += 1
                else:
                    consecutive_old = 0
                if consecutive_old >= 2:
                    bar.total = total_expected or len(books)
                    bar.n = bar.total
                    bar.refresh()
                    break
                if consecutive_old == 1 and total_expected is not None and total_expected == len(existing_ids):
                    bar.total = total_expected
                    bar.n = bar.total
                    bar.refresh()
                    break
            start += 20
            page_no += 1
            time.sleep(randomized_delay(0.5, 1.0))
        bar.close()
        if limit_stop:
            print(f"  已达 limit 上限（{args.limit} 条），停止")
        if not books:
            if not existing_records:
                print(f"  {label}: 无数据")
            else:
                print(f"  {label}: 已有 {len(existing_records)} 条，无新增，停止")
            continue

        # 增量模式：合并新旧数据
        if run_mode == "incremental":
            new_books = [b for b in books if b.get("豆瓣ID") not in existing_records]
            if existing_records:
                if not new_books:
                    print(f"  {label}: 已有 {len(existing_records)} 条，无新增，停止")
                    tmp_path = json_path + ".tmp"
                    if os.path.exists(tmp_path):
                        os.remove(tmp_path)
                    continue
                print(f"  {label}: 已有 {len(existing_records)} 条，新增 {len(new_books)} 条")
            merged = {b.get("豆瓣ID"): b for b in books}
            merged.update(existing_records)
            books = list(merged.values())
        else:
            merged = {b.get("豆瓣ID"): b for b in books}
            books = list(merged.values())

        # 保存 json
        os.makedirs(base_dir, exist_ok=True)
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(books, f, ensure_ascii=False, indent=2)
        tmp_path = json_path + ".tmp"
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        fname = os.path.basename(json_path)
        saved_files.append((json_path, len(books)))
        all_books.extend(books)

        # 更新索引
        if not args.limit:
            prev_ids, _ = load_index(args.output, "books")
            for _s in ["collect", "wish", "do"]:
                _p = os.path.join(args.output, f"douban_books_{_s}.{fmt}")
                if os.path.exists(_p):
                    prev_ids |= seed_ids_from_json(_p, ["豆瓣ID"])
            all_ids = prev_ids | {b.get("豆瓣ID") for b in books}
            save_index(args.output, "books", all_ids, max_page=page_no)

    # 输出结果汇总
    print()
    for p, cnt in saved_files:
        print(f"  已生成 {os.path.relpath(p, args.output)}（{cnt} 条）")

    print(f"\n{'='*60}")
    print(f" 书籍  | 完成，共处理 {len(all_books)} 条")
    print(f"{'='*60}")
