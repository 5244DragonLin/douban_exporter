# -*- coding: utf-8 -*-
"""读书记录导出（books 子命令）：已读/想读/在读，走 Rexxar API，纯标准库 + Cookie。"""
import argparse
import os
import sys

from .core import CONFIG_FILE, _load_config
from .interests import export_interests, resolve_cookie

BOOK_LABELS = {
    "collect": "读过",
    "wish": "想读",
    "do": "在读",
}


def _build_book_record(it, subj, label):
    douban_id = str(subj.get("id") or it.get("subject_id") or "")
    authors = subj.get("author") or []
    return {
        "豆瓣ID": douban_id,
        "书名": subj.get("title", ""),
        "阅读日期": (it.get("create_time") or "")[:10],
        "状态": label,
        "标签": "",
        "作者": ", ".join(authors) if isinstance(authors, list) else str(authors),
        "译者": "",
        "出版社": subj.get("press", ""),
        "出版日期": subj.get("pubdate", ""),
        "我的评分": (it.get("rating") or {}).get("star_count") or 0,
        "我的评论": (it.get("comment") or "").strip(),
        "豆瓣链接": f"https://book.douban.com/subject/{douban_id}/",
    }


def books_main(config=None):
    parser = argparse.ArgumentParser(description="豆瓣读书数据抓取工具（已读/想读/在读）")
    parser.add_argument("--user", "-u", dest="user_id", default=None,
                        help="豆瓣用户 ID")
    parser.add_argument("--output", "-o", dest="output", default=None,
                        help="输出目录（默认: ~，文件名固定为 douban_books_{分类}.json）")
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
                        help="每分类最大页数（用于测试/调试，默认 100 页保护）")
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

    # 输出目录：命令行 -o > 配置 books.output > 默认 ~（books.output 为目录，文件名固定 douban_books_{分类}.json）
    if not args.output and books_cfg.get("output"):
        args.output = books_cfg["output"]
    if not args.output:
        args.output = os.path.expanduser("~")

    # 确认用户 ID（优先级：命令行 > YAML 配置 user.id > 交互输入）
    user_id = args.user_id or user_cfg.get("id")
    if not user_id:
        user_id = input("请输入豆瓣用户 ID: ").strip()
    if not user_id:
        print("[错误] 未提供用户 ID")
        sys.exit(1)

    run_mode = args.mode or ("incremental" if books_cfg.get("incremental") else "full")
    limit = args.limit if args.limit is not None else books_cfg.get("limit")
    # limit 模式（测试用）强制全量：不走增量去重，输出写入 test_output/ 子目录
    if limit:
        run_mode = "full"

    types_to_fetch = args.types or books_cfg.get("types") or ["collect", "wish", "do"]

    cookie_str = resolve_cookie(args.cookie, args.cookie_file, user_cfg)

    total, saved_files = export_interests(
        user_id, args.output, types_to_fetch, run_mode, limit,
        kind="books", api_type="book", title="书籍", labels=BOOK_LABELS,
        build_record=_build_book_record, dedup_key="豆瓣ID",
        max_pages=args.max_pages, no_delay=args.no_delay, cookie_str=cookie_str,
    )

    # 输出结果汇总
    print()
    for p, cnt in saved_files:
        print(f"  已生成 {os.path.relpath(p, args.output)}（{cnt} 条）")

    print(f"\n{'='*60}")
    print(f" 书籍  | 完成，共处理 {total} 条")
    print(f"{'='*60}")
