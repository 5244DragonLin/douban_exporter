# -*- coding: utf-8 -*-
"""观影记录导出（movies 子命令）：看过/想看/在看，走 Rexxar API，纯标准库 + Cookie。"""
import argparse
import os
import sys

from .core import CONFIG_FILE, _load_config
from .interests import export_interests, parse_status_list, resolve_cookie

MOVIE_STATUS_LABELS = {
    "collect": "看过",
    "wish": "想看",
    "do": "在看",
}


def _build_movie_record(it, subj, label):
    douban_id = str(subj.get("id") or it.get("subject_id") or "")
    card_parts = (subj.get("card_subtitle") or "").split(" / ")
    return {
        "interest_id": str(it.get("id") or ""),
        "status": it.get("status", ""),
        "douban_id": douban_id,
        "title": subj.get("title", ""),
        "url": f"https://movie.douban.com/subject/{douban_id}/",
        "year": str(subj.get("year", "")),
        "douban_rating": str((subj.get("rating") or {}).get("value", "")),
        "rating": (it.get("rating") or {}).get("star_count") or 0,
        "date": (it.get("create_time") or "")[:10],
        "comment": (it.get("comment") or "").strip(),
        # 详情字段：列表接口 subject 自带，一次请求拿全（无需逐部 enrich）
        "genres": subj.get("genres") or [],
        "directors": [d.get("name") for d in (subj.get("directors") or [])],
        "actors": [a.get("name") for a in (subj.get("actors") or [])][:6],
        "pubdate": " / ".join(subj.get("pubdate") or []),
        # card_subtitle 形如 "2022 / 美国 澳大利亚 / 剧情 惊悚 / 导演 / 演员"，第 2 段为国家
        "country": " / ".join(card_parts[1].split()) if len(card_parts) > 1 else "",
    }


def movies_main(config=None):
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

    # 状态集合：命令行 --status > 配置 movies.statuses
    statuses = parse_status_list(args.status if args.status else movies_cfg.get("statuses"))

    run_mode = args.mode or ("incremental" if movies_cfg.get("incremental") else "full")
    limit = args.limit if args.limit is not None else movies_cfg.get("limit")
    # limit 模式（测试用）强制全量：不走增量去重，即使 yaml 设置了 incremental 也不启用
    if limit:
        run_mode = "full"

    cookie_str = resolve_cookie(args.cookie, args.cookie_file, user_cfg)

    total, _ = export_interests(
        user_id, output_dir, statuses, run_mode, limit,
        kind="movies", api_type="movie", title="影视", labels=MOVIE_STATUS_LABELS,
        build_record=_build_movie_record, dedup_key="douban_id",
        cookie_str=cookie_str,
    )

    print(f"\n{'='*60}")
    print(f" 影视  | 完成，共处理 {total} 条")
    print(f"{'='*60}")
