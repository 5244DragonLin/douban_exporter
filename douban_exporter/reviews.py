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

def generate_markdown(review, book_info):
    lines = []
    title = review.get("review_title") or review.get("book_name") or "无标题书评"
    lines.append(f"# {title}")
    lines.append("")
    meta_parts = []
    book_name = review.get("book_name", "")
    if book_name:
        meta_parts.append(f"《{book_name}》")
    for k, v in [("作者", book_info.get("author")), ("副标题", book_info.get("subtitle")),
                  ("出版社", book_info.get("publisher")), ("出版年", book_info.get("pub_year"))]:
        if v:
            meta_parts.append(f"{k}：{v}")
    rating = review.get("rating", 0)
    if rating > 0:
        meta_parts.append(f"评分：{rating_to_stars(rating)} {review.get('rating_label') or rating_to_label(rating)}")
    if review.get("review_date"):
        meta_parts.append(f"日期：{review['review_date']}")
    if review.get("useful_count", 0) > 0:
        meta_parts.append(f"有用：{review['useful_count']}")
    if meta_parts:
        lines.append("> " + " | ".join(meta_parts))
        lines.append("")
    if review.get("review_url"):
        lines.append(f"链接：[{review['review_url']}]({review['review_url']})")
        lines.append("")
    lines.append("---")
    lines.append("")
    if review.get("spoiler"):
        lines.append("> ⚠️ 这篇书评可能有关键情节透露")
        lines.append("")
    if review.get("content_html"):
        lines.append(html_to_markdown(review["content_html"]))
        lines.append("")
    elif review.get("content"):
        lines.append(review["content"])
        lines.append("")
    return "\n".join(lines)


def generate_html(review, book_info):
    title = review.get("review_title") or review.get("book_name") or "无标题书评"
    book_name = review.get("book_name", "")
    meta_parts = []
    if book_name:
        meta_parts.append(f"《{book_name}》")
    for k, v in [("作者", book_info.get("author")), ("副标题", book_info.get("subtitle")),
                  ("出版社", book_info.get("publisher")), ("出版年", book_info.get("pub_year"))]:
        if v:
            meta_parts.append(f"{k}：{v}")
    rating = review.get("rating", 0)
    if rating > 0:
        meta_parts.append(f"评分：{rating_to_stars(rating)} {review.get('rating_label') or rating_to_label(rating)}")
    if review.get("review_date"):
        meta_parts.append(f"日期：{review['review_date']}")
    if review.get("useful_count", 0) > 0:
        meta_parts.append(f"有用：{review['useful_count']}")
    meta_line = " | ".join(meta_parts)
    review_url = review.get("review_url", "")
    spoiler = review.get("spoiler")
    content_html = review.get("content_html") or ""
    if not content_html:
        # 兜底：无 HTML 正文时，把纯文本按空行拆成 <p> 段落，避免浏览器把换行折叠成一段
        plain = review.get("content", "") or ""
        _paras = [p.strip() for p in re.split(r"\n\s*\n", plain) if p.strip()]
        content_html = "\n".join(f"<p>{_clean_html_text(p)}</p>" for p in _paras)
    original_link_html = f'<p><a href="{review_url}">查看原文</a></p>' if review_url else ''
    spoiler_warn_html = '<div class="spoiler-warn">⚠️ 这篇书评可能有关键情节透露</div>' if spoiler else ''
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif; max-width: 800px; margin: 0 auto; padding: 2em 1em; line-height: 1.8; color: #333; }}
h1 {{ font-size: 1.6em; border-bottom: 2px solid #eee; padding-bottom: 0.4em; }}
.meta {{ color: #666; font-size: 0.9em; padding: 0.6em 1em; background: #f8f8f8; border-radius: 6px; margin-bottom: 1.5em; }}
.spoiler-warn {{ color: #e09020; background: #fff8e8; padding: 0.5em 1em; border-radius: 4px; margin-bottom: 1em; }}
.review-body {{ font-size: 1em; }}
.review-body p {{ margin: 0.8em 0; }}
.review-body h2 {{ font-size: 1.3em; margin: 1.3em 0 0.6em; border-bottom: 1px solid #eee; padding-bottom: 0.3em; }}
.review-body h3 {{ font-size: 1.15em; margin: 1.1em 0 0.5em; }}
.review-body h4 {{ font-size: 1.05em; margin: 1em 0 0.4em; }}
.review-body hr {{ border: none; border-top: 1px solid #eee; margin: 1.6em 0; }}
.review-body blockquote {{ margin: 1em 0; padding: 0.6em 1em; border-left: 4px solid #ddd; background: #f9f9f9; color: #555; }}
.review-body strong {{ font-weight: 600; }}
.review-body em {{ font-style: italic; }}
.review-body a {{ color: #3377cc; text-decoration: none; }}
.review-body img {{ max-width: 100%; height: auto; border-radius: 4px; }}
.footer {{ margin-top: 2em; padding-top: 1em; border-top: 1px solid #eee; font-size: 0.85em; color: #888; }}
</style></head>
<body>
<h1>{title}</h1>
<div class="meta">{meta_line}</div>
{original_link_html}
{spoiler_warn_html}
<div class="review-body">{content_html}</div>
<div class="footer">由 douban_exporter 导出</div>
</body>
</html>"""


def _extract_review_content(detail_html):
    """从书评详情页提取正文，返回 (content_html, content_text)。

    content_html 保留原始排版结构（h2/h3/h4 标题、blockquote 引用、strong 加粗、
    a 链接、img 图片、hr 分隔线等），供 HTML 与 Markdown 两种输出复用；
    content_text 为去标签纯文本，仅作为无 HTML 时的兜底。
    之前实现只抽取 <p>/<blockquote> 且强行剥离内联标签，导致标题、加粗、链接、
    引用结构全部丢失，本函数改为保留完整结构。
    """
    if not detail_html:
        return "", ""
    rc_idx = detail_html.find("review-content clearfix")
    if rc_idx == -1:
        return "", ""
    dstart = detail_html.rfind("<div", 0, rc_idx)
    if dstart == -1:
        return "", ""
    # 括号计数，定位 review-content 自身配对的闭合 </div>
    depth, j, closed = 0, dstart, -1
    while j < len(detail_html):
        if detail_html.startswith("<div", j):
            depth += 1
            j += 4
        elif detail_html.startswith("</div>", j):
            depth -= 1
            j += 6
            if depth == 0:
                closed = j
                break
        else:
            j += 1
    body = detail_html[dstart:closed] if closed != -1 else detail_html[dstart:]
    # 去掉最外层 <div ...> 与结尾 </div>，只保留内部节点
    m = re.match(r"^<div[^>]*>", body)
    if m:
        inner = body[m.end():]
        if inner.rstrip().endswith("</div>"):
            inner = inner[:inner.rstrip().rfind("</div>")]
    else:
        inner = body
    soup = BeautifulSoup(inner, "html.parser")
    # 拆解包裹 div：引言 div 直接展开为内部段落；分隔 div 转为 <hr>
    for d in soup.find_all("div", class_="introduction"):
        d.unwrap()
    for d in soup.find_all("div", class_="separator"):
        d.replace_with(soup.new_tag("hr"))
    # 清理无意义属性，仅保留链接/图片所需的 href/src/alt
    for tag in soup.find_all(True):
        allowed = ("href", "src", "alt") if tag.name in ("a", "img") else ()
        for k in list(tag.attrs):
            if k not in allowed:
                del tag[k]
    content_html = str(soup).strip()
    content_text = soup.get_text("\n").strip()
    return content_html, content_text


def html_to_markdown(html):
    """把保留结构的 content_html 转换为 Markdown，标题/引用/加粗/链接/图片均还原。"""
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")

    def _inline(node):
        out = []
        for c in node.children:
            if isinstance(c, NavigableString):
                out.append(str(c))
            else:
                out.append(_inline_tag(c))
        return "".join(out)

    def _inline_tag(tag):
        txt = _inline(tag)
        if tag.name in ("strong", "b"):
            return f"**{txt}**"
        if tag.name in ("em", "i"):
            return f"*{txt}*"
        if tag.name == "a":
            return f"[{txt}]({tag.get('href', '')})"
        if tag.name == "img":
            return f"![{tag.get('alt', '')}]({tag.get('src', '')})"
        if tag.name == "br":
            return "\n"
        return txt

    blocks = []
    for child in soup.children:
        if isinstance(child, NavigableString):
            if child.strip():
                blocks.append(("p", child.strip()))
            continue
        if not hasattr(child, "name"):
            continue
        name = child.name
        if name in ("h1", "h2", "h3", "h4", "h5", "h6"):
            blocks.append(("#" * int(name[1]) + " " + _inline(child).strip(), None))
        elif name == "p":
            blocks.append(("p", _inline(child).strip()))
        elif name == "blockquote":
            blocks.append(("blockquote", _inline(child).strip()))
        elif name == "hr":
            blocks.append(("hr", None))
        elif name == "div":
            inner = _inline(child).strip()
            if inner:
                blocks.append(("p", inner))
        else:
            inner = _inline(child).strip()
            if inner:
                blocks.append(("p", inner))

    md = []
    for kind, val in blocks:
        if kind == "hr":
            md.append("---")
        elif kind.startswith("#"):
            md.append(kind)
        elif kind == "blockquote":
            for line in val.split("\n"):
                md.append("> " + line)
        else:  # p
            if val:
                md.append(val)
    return "\n\n".join(md)


def reviews_main(config=None):
    parser = argparse.ArgumentParser(description="豆瓣读书书评抓取（纯标准库 + Cookie，无需 Playwright）")
    parser.add_argument("--user", "-u", dest="user_id", default=None,
                        help="豆瓣用户 ID")
    parser.add_argument("--output", "-o", dest="output", default=None,
                        help=f"输出目录（默认: {DEFAULT_OUTPUT_DIR}）")
    parser.add_argument("--config", "-c", dest="config", default=None,
                        help="YAML 配置文件路径（默认自动加载脚本同目录 config.yaml）")
    parser.add_argument("--limit", "-l", dest="limit", type=int, default=None,
                        help="限制抓取书评篇数（默认全部）")
    parser.add_argument("--format", "-f", dest="fmt", default=None,
                        choices=["md", "html", "both"],
                        help="输出格式: md / html / both（默认: both，或 config reviews.format）")
    parser.add_argument("--mode", "-m", dest="mode", default=None,
                        choices=["full", "incremental"],
                        help="抓取模式: full=全量, incremental=增量（默认: full，或 config reviews.incremental）")
    parser.add_argument("--cookie", dest="cookie", default=None,
                        help="豆瓣登录 Cookie 字符串（不传则读取配置或环境变量 DOUBAN_COOKIE）")
    parser.add_argument("--cookie-file", dest="cookie_file", default=None,
                        help="从文件读取豆瓣 Cookie（不传则读取配置 user.cookie_file）")
    args = parser.parse_args()

    # 加载 YAML 配置：优先使用调用方传入的 config，否则自行加载（未指定 -c 时自动加载同目录 config.yaml）
    if config is None:
        config = _load_config(args.config or CONFIG_FILE)
    user_cfg = config.get("user") or {}
    reviews_cfg = config.get("reviews") or {}

    # 用户 ID：命令行 > 配置 user.id > 交互
    user_id = args.user_id or user_cfg.get("id")
    if not user_id:
        user_id = input("请输入豆瓣用户 ID: ").strip()
    if not user_id:
        print("[错误] 未提供用户 ID")
        sys.exit(1)

    # 输出目录：命令行 > 配置 reviews.output > 默认
    output_dir = args.output or reviews_cfg.get("output") or DEFAULT_OUTPUT_DIR
    output_dir = os.path.abspath(output_dir)

    # 格式：命令行 --format > 配置 reviews.format > 默认 both；reviews 仅支持 md/html/both
    fmt = args.fmt or reviews_cfg.get("format") or "both"
    if fmt not in ("md", "html", "both"):
        print(f"[错误] 不支持的格式: {fmt}（可选: md / html / both）")
        sys.exit(1)

    # Cookie 优先级：命令行 --cookie > 配置 user.cookie > 环境变量 DOUBAN_COOKIE > --cookie-file / 配置 user.cookie_file
    cookie_str = args.cookie or user_cfg.get("cookie") or os.environ.get("DOUBAN_COOKIE")
    if not cookie_str and (args.cookie_file or user_cfg.get("cookie_file")):
        cookie_str = load_cookie_file(args.cookie_file or user_cfg.get("cookie_file"))

    # 限制篇数：命令行 > 配置 reviews.limit
    if args.limit is None and reviews_cfg.get("limit") is not None:
        args.limit = reviews_cfg["limit"]

    opener = _urllib_opener(cookie_str)
    list_url = f"https://www.douban.com/people/{user_id}/reviews"

    # 运行模式（提前计算，便于头部统一展示）
    run_mode = args.mode or ("incremental" if reviews_cfg.get("incremental") else "full")

    print(f"\n{'='*60}")
    print(f" 书评  | 模式: {run_mode}")
    print(f" 输出: {output_dir}")
    print(f"{'='*60}")

    # 第一步：抓列表页（含翻页），增量模式在翻页中早停
    review_items = []
    seen = set()
    page_num = 0
    existing_ids = set()
    consecutive_old = 0
    if run_mode == "incremental":
        existing_ids, _ = load_index(output_dir, "reviews")
    with tqdm(total=None, desc="书评列表", unit="页", ncols=90, leave=True) as pbar:
        while True:
            url = list_url if page_num == 0 else f"{list_url}?start={page_num * 10}"
            html_text = _http_get(url, opener)
            if not html_text:
                tqdm.write(f" [警告] 第 {page_num+1} 页抓取失败，停止翻页")
                break
            # 该页条目
            page_items = []
            for m in re.finditer(r'<h2><a href="(https://book\.douban\.com/review/\d+/)"[^>]*>([^<]+)</a></h2>', html_text):
                review_url = m.group(1)
                if review_url in seen:
                    continue
                rid = re.search(r"review/(\d+)/", review_url).group(1)
                # 从条目区块提取评分/日期/书籍
                idx = html_text.find(f"review_{rid}_short")
                seg = html_text[max(0, idx - 2000):idx + 600] if idx > 0 else ""
                rating_m = re.search(r'allstar(\d)[^"]*" title="([^"]*)"', seg)
                date_m = re.search(r'class="main-meta"[^>]*>([^<]+)</span>', seg)
                book_m = re.search(r'<a class="subject-img" href="(https://book\.douban\.com/subject/\d+/)">\s*<img[^>]*alt="([^"]+)"', seg)
                item = {
                    "review_url": review_url,
                    "rid": rid,
                    "review_title": _clean_html_text(m.group(2)),
                    "rating": int(rating_m.group(1)) if rating_m else 0,
                    "rating_label": rating_m.group(2) if rating_m else "",
                    "review_date": _clean_html_text(date_m.group(1)) if date_m else "",
                    "book_url": book_m.group(1) if book_m else "",
                    "book_name": book_m.group(2) if book_m else "",
                }
                page_items.append(item)
                seen.add(review_url)
            review_items.extend(page_items)
            pbar.update(1)

            # 增量模式早停：本页全为已知书评则停止翻页
            if run_mode == "incremental" and existing_ids and page_items:
                page_all_old = all(it["rid"] in existing_ids for it in page_items)
                if page_all_old:
                    consecutive_old += 1
                else:
                    consecutive_old = 0
                if consecutive_old >= 2:
                    break

            # 是否还有下一页
            if args.limit and len(review_items) >= args.limit:
                review_items = review_items[:args.limit]
                break
            # 翻页判定：本页一条都没解析到（已到末页或页面结构变化），或页面已无「下一页」链接即停止。
            # 不再用固定每页条数（如 15）判断——豆瓣书评列表每页 10 条，固定阈值会让首屏满页也被误判为「不足一页」而提前停止翻页。
            if len(page_items) == 0 or "<span class=\"next\">" not in html_text:
                break
            page_num += 1
            time.sleep(randomized_delay(1.5, 3.0))

    # 增量模式：从 review_items 中剔除已抓条目
    if run_mode == "incremental" and existing_ids:
        _before = len(review_items)
        review_items = [it for it in review_items if it["rid"] not in existing_ids]
        _skipped = _before - len(review_items)
        if _skipped:
            print(f"  书评: 已有 {len(existing_ids)} 篇，无新增，停止")
        if not review_items:
            return
    if not review_items:
        print("[错误] 未找到书评，请确认用户 ID 或 Cookie 是否有效")
        sys.exit(1)

    # 第二步：抓详情页正文
    print("  获取书评全文...")
    md_dir = os.path.join(output_dir, "md")
    html_dir = os.path.join(output_dir, "html")
    os.makedirs(md_dir, exist_ok=True)
    os.makedirs(html_dir, exist_ok=True)
    completed = failed = 0
    total = len(review_items)
    bar = tqdm(total=total, desc="书评全文", unit="篇", ncols=90, leave=True)
    for idx, review in enumerate(review_items, 1):
        try:
            detail = _http_get(review["review_url"], opener)
            if detail:
                h1 = re.search(r"<h1[^>]*>(.*?)</h1>", detail, re.DOTALL)
                if h1:
                    review["review_title"] = _clean_html_text(re.sub(r"<[^>]+>", "", h1.group(1)))
                author_m = re.search(r'data-author="([^"]+)"', detail)
                review["author"] = author_m.group(1) if author_m else ""
                # 正文：保留原始结构（标题/引用/加粗/链接/图片等），供 HTML/Markdown 复用
                content_html, content_text = _extract_review_content(detail)
                review["content_html"] = content_html
                review["content"] = content_text
            # 写文件
            book_info = {}
            if review.get("book_url"):
                book_info["book_url"] = review["book_url"]
            _base = sanitize_filename(f"《{review.get('book_name','未知')}》 - {review.get('review_title','')}")
            if fmt in ("md", "both"):
                md_path = os.path.join(md_dir, _base + ".md")
                with open(md_path, "w", encoding="utf-8") as f:
                    f.write(generate_markdown(review, book_info))
            if fmt in ("html", "both"):
                html_path = os.path.join(html_dir, _base + ".html")
                with open(html_path, "w", encoding="utf-8") as f:
                    f.write(generate_html(review, book_info))
            completed += 1
            bar.set_postfix(成功=completed, 失败=failed)
        except Exception as e:
            tqdm.write(f"  [{idx}/{total}] 《{review.get('book_name','未知')}》 处理失败: {e}")
            failed += 1
        bar.update(1)
        if idx < total:
            time.sleep(randomized_delay(2.0, 4.0))

    bar.close()
    print(f"\n 书评 | 完成，共处理 {total} 篇（成功 {completed} / 失败 {failed}）")

    # 更新增量索引（统一写 .douban_reviews_index.json，记录已抓取书评 id，供下次增量去重）
    try:
        prev_ids, _ = load_index(output_dir, "reviews")
        all_ids = prev_ids | {r.get("rid", "") for r in review_items if r.get("rid")}
        save_index(output_dir, "reviews", all_ids)
    except Exception:
        pass
