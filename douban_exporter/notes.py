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

def _strip_tags(html_text):
    """去除 HTML 标签，返回纯文本（用于笔记正文 content 字段）。"""
    if not html_text:
        return ""
    s = re.sub(r"<style.*?</style>", "", html_text, flags=re.DOTALL)
    s = re.sub(r"<script.*?</script>", "", html_text, flags=re.DOTALL)
    s = re.sub(r"<[^>]+>", "", s)
    return s.strip()


def _strip_note_citation(body):
    """去掉豆瓣在正文末尾追加的"引自 XXX"章节引用尾注（保留笔记正文本身）。

    两种来源都会带：Rexxar API 的 content、话题页补全的正文（如"引自 浮　桥 / 058"）。
    """
    if not body:
        return body
    return re.sub(r"\s*引自\s+[^\n]*\Z", "", body).strip()


def _format_rating(rating):
    """评分格式化：value/10（count人评价）。rating 可能为 None 或空 dict。"""
    if not rating or not isinstance(rating, dict):
        return ""
    value = rating.get("value")
    count = rating.get("count")
    if value is None:
        return ""
    s = f"{value}/10"
    if count:
        s += f"（{count}人评价）"
    return s


def fetch_annotation_ids(opener, uid, max_pages=None, limit=None):
    """从网页版读书笔记列表页获取笔记 ID（去重）。

    页面每页约 5 条；新笔记链接为 /annotation/{9位ID}（不带 people 前缀），
    旧笔记为 /people/{uid}/annotation/{id}。统一取 .annotations-item 容器内的链接，
    避免误抓侧栏推荐区；自动翻页直到无新 ID（start 越界时页面渲染推荐区，靠去重自然截断）。
    max_pages 仅用于测试/限页；limit 达到后提前停止翻页（避免测试时干等全量翻完）。
    """
    ids = []
    seen = set()
    pages = max_pages or 10**9
    for page in range(1, pages + 1):
        start = (page - 1) * 5
        url = f"https://book.douban.com/people/{uid}/annotation" + (f"?start={start}" if start else "")
        html = fetch(url, opener)
        if not html:
            break
        soup = BeautifulSoup(html, "html.parser")
        items = soup.select(".annotations-item")
        # 从标题"我的笔记(N)"提取总数，用于兜底截断（防 start 越界后推荐区混入）
        total = None
        m = re.search(r"我的笔记[（(](\d+)[)）]", html)
        if m:
            total = int(m.group(1))
        if total is not None:
            pages = min(pages, (total + 4) // 5)
        found_new = 0
        # 页面按书聚合：每页约 5 本书，h3 的书名链接是老格式（书名级，不可当笔记），
        # 真正的笔记 ID 在每本书的 ul.rnotes 里（新格式 9 位）
        for a in soup.select(".annotations-item ul.rnotes a[href*='/annotation/']"):
            m = re.search(r"/annotation/(\d+)", a.get("href", ""))
            if not m:
                continue
            aid = m.group(1)
            if aid not in seen:
                seen.add(aid)
                ids.append(aid)
                found_new += 1
                if limit and len(ids) >= limit:
                    return ids  # 收集够了立即返回，不等本页/全部翻完
        # 翻页进度（每 10 页打印一次），避免长时间无输出被误认为卡死
        if page % 10 == 0:
            print(f"  翻页进度：第 {page}/{min(pages, 10**9)} 页，已收集 {len(ids)} 条笔记 ID")
        if found_new == 0 or len(items) < 5:
            break
        random_delay()
    return ids


def parse_annotation_books(opener, uid, page):
    """解析笔记列表页（按书聚合），保持豆瓣页面顺序。

    Args:
        page: 页码（1 起）。列表页每页约 5 本书（annotations-item），
            每本书内 ul.rnotes 列出该书全部笔记。
    Returns:
        list[dict]: [{"book_name", "book_old_id", "annotations": [{"chapter", "note_id"|None}]}]
        note_id: 新笔记为 9 位 ID（可走 Rexxar API）；旧笔记无 /annotation/ 链接（None）。
    """
    start = (page - 1) * 5
    url = f"https://book.douban.com/people/{uid}/annotation" + (f"?start={start}" if start else "")
    html = fetch(url, opener)
    if not html:
        return []
    soup = BeautifulSoup(html, "html.parser")
    books = []
    for item in soup.select(".annotations-item"):
        h3a = item.select_one("h3 a[href*='annotation']")
        if not h3a:
            continue
        book_name = (h3a.get("title") or h3a.get_text(strip=True) or "").strip()
        book_name = re.sub(r"\s*\(\d+\)\s*$", "", book_name).strip()
        m = re.search(r"/annotation/(\d+)", h3a.get("href", ""))
        book_old_id = m.group(1) if m else None
        annotations = []
        for li in item.select("ul.rnotes li"):
            a = li.select_one("h5 a")
            if not a:
                continue
            chapter = a.get_text(strip=True)
            m = re.search(r"/annotation/(\d+)", a.get("href", ""))
            annotations.append({"chapter": chapter, "note_id": m.group(1) if m else None})
        books.append({"book_name": book_name, "book_old_id": book_old_id, "annotations": annotations})
    return books


def _fetch_topic_full(opener, topic_url):
    """话题通道笔记的完整正文：topic 页 .rich-content.topic-richtext。

    书级页对长笔记只显示摘要（~100-200 字，以"..."截断），话题页才有完整正文。
    """
    html = fetch(topic_url.split("?")[0], opener)
    if not html:
        return None
    soup = BeautifulSoup(html, "html.parser")
    el = soup.select_one(".rich-content.topic-richtext")
    if not el:
        return None
    txt = el.get_text("\n", strip=True)
    return txt or None


def fetch_book_notes_web(opener, uid, book_old_id):
    """从网页版书级页"我对《XX》的笔记(N)"抓取该书的全部笔记。

    豆瓣笔记有两条通道，由每条笔记条目 h5 的链接格式天然区分（与标记时间无关）：
    - `/annotation/{9位}`：改版前独立笔记页通道 → note_id 非空，用 Rexxar API 补全完整正文
    - `/topic/{id}`：改版后话题通道 → note_id 为空，书级页正文可能截断，
      此时抓 topic 页 .rich-content.topic-richtext 补全完整正文
    每页约 10 条，自动翻页。

    Returns:
        list[dict]: [{"章节", "正文", "创建时间", "笔记ID", "note_id"|None}]
    """
    notes = []
    page = 0
    book_meta = {}
    while True:
        url = f"https://book.douban.com/people/{uid}/annotation/{book_old_id}/"
        if page:
            url += f"?start={page * 10}"
        html = fetch(url, opener)
        if not html:
            break
        soup = BeautifulSoup(html, "html.parser")
        # 书级页自带书籍信息（书名/作者/页数/出版社/出版年），零额外请求。
        # 页面可能有多个 div.info，取含"出版社"的那个。
        if not book_meta:
            info_el = None
            for el in soup.select("div.info"):
                if "出版社" in el.get_text():
                    info_el = el
                    break
            if info_el:
                meta = {}
                for li in info_el.select("li"):
                    key_el = li.select_one("span")
                    if not key_el:
                        continue
                    key = key_el.get_text(strip=True)
                    val = li.get_text(" ", strip=True).replace(key, "", 1).strip(" : ")
                    val = re.sub(r"\s+", " ", val).strip()
                    meta[key] = val
                # 评分：书级页只有星级图标（rating4-t = 4 星 → 8.0/10），无评价人数
                star_el = soup.select_one("span[class*=rating]")
                if star_el:
                    m_star = re.search(r"rating(\d+)-t", " ".join(star_el.get("class") or []))
                    if m_star:
                        stars = int(m_star.group(1))
                        meta["评分"] = f"{stars * 2}.0/10"
                book_meta = meta
        items = soup.select("li.item.rnote")
        got = 0
        for li in items:
            h5 = li.select_one("h5")
            abstract = li.select_one(".abstract")
            reply = li.select_one(".reply span")
            chapter = h5.get_text(strip=True) if h5 else ""
            body = abstract.get_text("\n", strip=True) if abstract else ""
            created = reply.get_text(strip=True) if reply else ""
            if not body:
                continue
            h5a = h5.select_one("a") if h5 else None
            href = h5a.get("href", "") if h5a else ""
            m = re.search(r"/annotation/(\d+)", href)
            note_id = m.group(1) if m else None
            # 话题通道且正文被截断 → 从 topic 页补全完整正文
            if not note_id and body.rstrip().endswith("..."):
                full = _fetch_topic_full(opener, href)
                if full:
                    body = full
            notes.append({
                "章节": chapter,
                "正文": body,
                "创建时间": created,
                "笔记ID": f"web-{book_old_id}-{created}",
                "note_id": note_id,  # 通道标识：独立笔记页 ID / None=话题通道
            })
            got += 1
        if got < 10:
            break
        page += 1
        random_delay()
    return notes, book_meta


def fetch_annotation_detail(opener, aid, ck=None, expected_uid=None, chapter=None):
    """调用 Rexxar 单条笔记接口，返回结构化字典。失败或归属不符返回 None。

    expected_uid: 期望的笔记作者数字 ID（user.id）。豆瓣改版后，老笔记 ID 会在
    新接口下解析成其他用户的笔记（串号），用 author.id 比对可过滤这类脏数据。
    chapter: 列表页已解析出的章节文本（API 的 chapter 字段常为空，以此兜底）。
    """
    url = f"https://m.douban.com/rexxar/api/v2/annotation/{aid}?for_mobile=1"
    if ck:
        url += f"&ck={urllib.parse.quote(ck)}"
    req = urllib.request.Request(url)
    req.add_header("User-Agent", HEADERS["User-Agent"])
    req.add_header("Referer", "https://m.douban.com/")
    req.add_header("Accept", "application/json")
    try:
        resp = opener.open(req, timeout=20)
        data = json.loads(resp.read().decode("utf-8", errors="replace"))
    except Exception as e:
        logger.warning("笔记 %s 详情获取失败: %s", aid, e)
        return None

    # 归属校验：防止老 ID 在新接口下串号成别人的笔记
    author = data.get("author") or {}
    author_id = str(author.get("id") or "")
    if expected_uid and author_id and author_id != str(expected_uid):
        logger.warning("笔记 %s 归属不符（作者 %s，非目标用户 %s），跳过", aid, author.get("name") or author_id, expected_uid)
        return None

    subject = data.get("subject") or {}
    subject_card = data.get("subject_card") or {}
    book_title = subject.get("title") or ""
    if not book_title:
        book_title = subject_card.get("abstract", "") or ""
    page_val = data.get("page")
    return {
        "笔记ID": str(data.get("id", aid)),
        "书名": book_title,
        "作者出版": subject_card.get("abstract", ""),
        "作者": " / ".join(subject.get("author") or []),
        "副标题": subject.get("book_subtitle") or "",
        "出版社": " / ".join(subject.get("press") or []),
        "出版年": " / ".join(subject.get("pubdate") or []),
        "页数": " / ".join(subject.get("pages") or []) if subject.get("pages") else "",
        "评分": _format_rating(subject.get("rating")),
        "标题": data.get("title", ""),
        "章节": data.get("chapter") or chapter or "",
        "页码": str(page_val) if page_val not in (None, 0, "0") else "",
        "摘要": data.get("abstract", ""),
        "正文": _strip_tags(data.get("content", "")),
        "创建时间": data.get("create_time", ""),
        "笔记链接": data.get("url", f"https://book.douban.com/annotation/{aid}/"),
    }


def _write_note_md(md_path, book_title, items, append=False):
    """将一组笔记（同一本书）写入 {书名}.md，遵循《书籍阅读笔记撰写指南》。

    - 一级标题 # 书名
    - 元数据行 > 作者：{作者出版串}（API 仅提供合并串，无出版社/出版年单列）
    - --- 分隔
    - 每条笔记：## 位置标识（页码>章节>标题/摘要）+ 引文正文
    items: list[dict]，字段见 fetch_annotation_detail 返回值
    append=True 时仅追加新笔记（不全量重写），用于增量。
    """
    # 位置标识：优先页码，其次章节，再其次标题/摘要前若干字
    def loc_of(it):
        page = (it.get("页码") or "").strip()
        if page and page != "0":
            return f"第{page}页"
        chap = (it.get("章节") or "").strip()
        if chap:
            return chap
        title = (it.get("标题") or "").strip()
        if title:
            return title
        abst = (it.get("摘要") or "").strip()
        if abst:
            return abst[:20]
        return "摘录"

    # 按位置排序：页码按数字，其余按原顺序（API 已按书中顺序返回，保持）
    def sort_key(it):
        page = (it.get("页码") or "").strip()
        if page and page.isdigit():
            return (0, int(page))
        return (1, 0)

    items_sorted = sorted(items, key=sort_key)

    blocks = []
    for it in items_sorted:
        loc = loc_of(it)
        body = (it.get("正文") or "").strip()
        if not body:
            body = (it.get("摘要") or "").strip()
        # 统一为 Markdown 段落分隔：所有换行都用空行（\n\n），不用单个换行
        body = re.sub(r"\n+", "\n\n", body).strip()
        blocks.append(f"## {loc}\n\n{body}")

    meta = ""
    if items_sorted:
        it0 = items_sorted[0]
        parts = []
        if it0.get("作者"):
            parts.append(f"作者：{it0['作者']}")
        if it0.get("副标题"):
            parts.append(f"副标题：{it0['副标题']}")
        if it0.get("出版社"):
            parts.append(f"出版社：{it0['出版社']}")
        if it0.get("出版年"):
            parts.append(f"出版年：{it0['出版年']}")
        if it0.get("评分"):
            parts.append(f"评分：{it0['评分']}")
        if parts:
            meta = "> " + " | ".join(parts) + "\n\n"
        else:
            # 回退：旧数据仅有合并串（如"黄晓阳 / 2011 / 重庆出版社"）
            author_pub = it0.get("作者出版", "")
            if author_pub:
                meta = f"> 作者：{author_pub}\n\n"

    if append and os.path.exists(md_path):
        # 增量追加：仅写新笔记块
        with open(md_path, "a", encoding="utf-8") as f:
            for b in blocks:
                f.write("\n\n" + b)
        return md_path

    # 全量（新建或覆盖）：完整结构
    content = f"# {book_title}\n\n{meta}---\n\n" + "\n\n".join(blocks) + "\n"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(content)
    return md_path


def notes_main(config=None):
    """读书笔记抓取主流程（notes 子命令）。

    输出固定为 Markdown：按书名生成 {书名}.md（遵循《书籍阅读笔记撰写指南》：
    一级标题 # 书名、元数据行、--- 分隔，每条笔记 ## 位置标识 + 引文）。
    同一本书的多条笔记聚合进同一文件；位置标识优先级：页码 > 章节 > 标题/摘要。
    增量去重基于隐藏索引文件 .douban_notes_index.json（按笔记 ID 去重，避免文件级误判）。
    """
    parser = argparse.ArgumentParser(description="豆瓣读书笔记（标注）抓取工具")
    parser.add_argument("--user", "-u", dest="user_id", default=None, help="豆瓣用户 ID")
    parser.add_argument("--output", "-o", dest="output", default=None, help="输出目录")
    parser.add_argument("--config", "-c", dest="config", default=None, help="YAML 配置文件路径")
    parser.add_argument("--format", "-f", dest="fmt", default=None, choices=["md"], help="输出格式（固定 md，兼容旧参数）")
    parser.add_argument("--mode", "-m", dest="mode", default=None, choices=["full", "incremental"], help="抓取模式: full=全量, incremental=增量（默认: 根据配置 notes.incremental 决定）")
    parser.add_argument("--limit", "-l", dest="limit", type=int, default=None, help="限制抓取笔记条数，用于测试")
    parser.add_argument("--max-pages", dest="max_pages", type=int, default=None, help="笔记列表最大翻页数")
    parser.add_argument("--cookie", dest="cookie", default=None, help="豆瓣登录 Cookie 字符串")
    parser.add_argument("--cookie-file", dest="cookie_file", default=None, help="从文件读取豆瓣 Cookie")
    args = parser.parse_args()

    if config is None:
        config = _load_config(args.config or CONFIG_FILE)
    user_cfg = config.get("user") or {}
    notes_cfg = config.get("notes") or {}

    user_id = args.user_id or user_cfg.get("id")
    if not user_id:
        print("[错误] 未指定豆瓣用户 ID（命令行 -u 或配置 user.id）")
        sys.exit(1)

    output_dir = os.path.abspath(args.output or notes_cfg.get("output") or config.get("notes_output") or DEFAULT_OUTPUT_DIR)
    max_pages = args.max_pages or notes_cfg.get("max_pages")
    if args.limit is None:
        args.limit = notes_cfg.get("limit")
    run_mode = args.mode or ("incremental" if notes_cfg.get("incremental") else "full")
    # limit 模式（测试用）强制全量：不走增量去重，即使 yaml 设置了 incremental 也不启用
    if args.limit:
        run_mode = "full"
        # limit 测试输出到 test_output/ 子目录，避免污染正式文件（正式文件供增量去重）
        output_dir = os.path.join(output_dir, "test_output")
    os.makedirs(output_dir, exist_ok=True)

    cookie_str = args.cookie or user_cfg.get("cookie") or os.environ.get("DOUBAN_COOKIE")
    if not cookie_str and (args.cookie_file or user_cfg.get("cookie_file")):
        cookie_str = load_cookie_file(args.cookie_file or user_cfg.get("cookie_file"))
    ck = None
    if cookie_str:
        m = re.search(r"(?:^|;\s*)ck=([^;]+)", cookie_str)
        ck = m.group(1) if m else None

    # 增量索引：统一走 .douban_notes_index.json，记录已抓笔记 ID，按笔记级去重
    existing_ids, _ = load_index(output_dir, "notes") if run_mode == "incremental" else (set(), 0)
    print(f"\n{'='*60}")
    print(f" 笔记  | 模式: {run_mode}")
    print(f" 输出: {output_dir}")
    print(f"{'='*60}")
    opener = make_opener(cookie_str)
    start_time = time.time()

    all_books = []
    total_notes = 0
    consecutive_old = 0
    bar = tqdm(total=None, desc="翻页", unit="页", leave=True, ncols=90)
    for page in range(1, (max_pages or 10**9) + 1):
        books = parse_annotation_books(opener, user_id, page)
        if not books:
            break

        # 增量模式早停：先检测本页是否全为已知，再决定是否加入 all_books
        page_all_known = False
        if run_mode == "incremental" and existing_ids:
            page_all_known = True
            for b in books:
                for a in b["annotations"]:
                    if a["note_id"] and str(a["note_id"]) not in existing_ids:
                        page_all_known = False
                        break
                    # 话题通道笔记（无 note_id），跳过不参与判定
                    # 主循环中的 existing_ids 检测会处理它们
                    elif not a["note_id"]:
                        continue
                if not page_all_known:
                    break

        if page_all_known:
            consecutive_old += 1
        else:
            consecutive_old = 0
            # 只有包含新内容的页面才加入书籍列表
            for b in books:
                all_books.append(b)
                total_notes += len(b["annotations"])

        bar.update(1)
        if args.limit and total_notes >= args.limit:
            break
        if len(books) < 5:
            break
        if consecutive_old >= 2:
            break
        random_delay()
    bar.close()
    # limit 截断（按书顺序，南货店→情人→…）
    if args.limit:
        limited = []
        count = 0
        for b in all_books:
            if count >= args.limit:
                break
            take = dict(b)
            need = args.limit - count
            take["annotations"] = b["annotations"][:need]
            limited.append(take)
            count += len(take["annotations"])
        all_books = limited
        total_notes = min(total_notes, args.limit)
        print(f"  限制抓取前 {args.limit} 条（{len(all_books)} 本书）")
    if total_notes == 0:
        if run_mode == "incremental":
            print(f"  笔记: 已有 {len(existing_ids)} 条，无新增，停止")
        else:
            print("  笔记: 无数据")
        return

    notes = []
    new_count = 0
    limit_stop = False
    written_files = []
    # 总进度条：列表阶段已知总条数，详情阶段逐条推进（替代原来的每本书一个进度条）
    total_bar = tqdm(total=total_notes, desc="笔记抓取", unit="条", leave=True, ncols=90)
    for book in all_books:
        book_name = book["book_name"]
        if not book.get("book_old_id"):
            continue
        # 总进度条描述位显示当前正在抓取的书名（进度数字仍是全量累计）
        total_bar.set_description(f"「{book_name}」")
        # 每本书都从书级页"我对《XX》的笔记(N)"抓取，条目自带通道标识
        web_notes, book_meta = fetch_book_notes_web(opener, user_id, book["book_old_id"])
        book_notes = []
        for w in web_notes:
            if args.limit and len(notes) >= args.limit:
                limit_stop = True
                break
            item = {
                "笔记ID": w["笔记ID"],
                "书名": book_name,
                "章节": w["章节"],
                "页码": "",
                "正文": _strip_note_citation(w["正文"]),
                "创建时间": w["创建时间"],
                "笔记链接": "",
                # 话题通道书级页自带的书籍信息（作者/出版社/出版年/页数，无副标题）
                "作者": book_meta.get("作者", ""),
                "副标题": "",
                "出版社": book_meta.get("出版社", ""),
                "出版年": book_meta.get("出版年", ""),
                "页数": book_meta.get("页数", ""),
                "评分": book_meta.get("评分", ""),
            }
            # 通道判断：h5 链接为 /annotation/{9位}（独立笔记页）→ API 补全完整正文；
            # /topic/ 等（话题通道）→ 网页仅提供摘要，用书级页正文
            if w["note_id"]:
                detail = fetch_annotation_detail(opener, w["note_id"], ck=ck, expected_uid=user_id, chapter=w["章节"])
                if detail:
                    item["正文"] = _strip_note_citation(detail["正文"])
                    item["笔记ID"] = detail["笔记ID"]
                    item["作者出版"] = detail["作者出版"]
                    item["笔记链接"] = detail["笔记链接"]
                    # 独立通道：API subject 有完整书信息（含副标题/评分/简介等）
                    for k in ("作者", "副标题", "出版社", "出版年", "页数", "评分"):
                        if detail.get(k):
                            item[k] = detail[k]
            if run_mode == "incremental" and str(item["笔记ID"]) in existing_ids:
                total_bar.update(1)
                continue
            notes.append(item)
            new_count += 1
            book_notes.append(item)
            total_bar.update(1)
            time.sleep(DEFAULT_DELAY[0])
        # 每本书抓完立即写盘：中断也不丢已抓内容（增量时对新文件追加）
        if book_notes:
            md_path = os.path.join(output_dir, f"{book_name}.md")
            is_new = not os.path.exists(md_path)
            _write_note_md(md_path, book_name, book_notes, append=(run_mode == "incremental" and not is_new))
            written_files.append(md_path)
            if run_mode == "incremental":
                existing_ids |= {str(n["笔记ID"]) for n in book_notes}
        if limit_stop:
            break
    # 抓完所有书后恢复通用描述，再关闭进度条
    total_bar.set_description("笔记抓取")
    total_bar.close()

    if limit_stop:
        print(f"  已达 limit 早停上限（{args.limit} 条），停止抓取")

    if not notes:
        if existing_ids:
            print(f"本次无新增，已抓取 {len(existing_ids)} 条")
        else:
            print("本次无新增数据，未生成文件。")
        return

    # 更新增量索引（书籍 Markdown 已在逐书抓取时写盘）
    try:
        if run_mode == "incremental":
            # existing_ids 在逐书写盘时已并入本次新增的笔记 ID
            all_ids = existing_ids
        else:
            # 全量：重新统计该用户所有已抓笔记 ID（合并本次新抓）
            all_ids = {str(n["笔记ID"]) for n in notes}
            prev_ids, _ = load_index(output_dir, "notes")
            all_ids |= prev_ids
        save_index(output_dir, "notes", all_ids)
    except Exception as e:
        logger.warning("增量索引写入失败: %s", e)

    print(f"\n{'='*60}")
    print(f" 笔记  | 新增 {new_count} 条，写入 {len(written_files)} 个文件，耗时 {time.time()-start_time:.1f}s")
    print(f"{'='*60}")
