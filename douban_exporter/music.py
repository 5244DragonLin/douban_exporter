# -*- coding: utf-8 -*-
"""音乐记录导出（music 子命令）：听过/想听/在听，走 Rexxar API，纯标准库 + Cookie。"""
import argparse
import os
import sys

from .core import CONFIG_FILE, _load_config
from .interests import export_interests, parse_status_list, resolve_cookie

MUSIC_STATUS_LABELS = {
    "collect": "听过",
    "wish": "想听",
    "do": "在听",
}


def _build_music_record(it, subj, label):
    douban_id = str(subj.get("id") or it.get("subject_id") or "")
    return {
        "interest_id": str(it.get("id") or ""),
        "status": it.get("status", ""),
        "douban_id": douban_id,
        "title": subj.get("title", ""),
        "url": f"https://music.douban.com/subject/{douban_id}/",
        "artist": subj.get("card_subtitle", ""),
        "genres": subj.get("genres") or [],
        "rating": (it.get("rating") or {}).get("star_count") or 0,
        "date": (it.get("create_time") or "")[:10],
        "comment": (it.get("comment") or "").strip(),
    }


def music_main(config=None):
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
    auth_cfg = config.get("auth") or {}
    user_cfg = config.get("user") or {}
    music_cfg = config.get("music") or {}

    user_id = args.user_id or user_cfg.get("id")
    if not user_id:
        print("[错误] 未指定豆瓣用户 ID（命令行 -u 或配置 user.id）")
        sys.exit(1)

    output_dir = os.path.abspath(args.output or music_cfg.get("output_dir") or os.path.join(os.getcwd(), "douban_music_output"))

    # 状态集合：命令行 --status > 配置 music.statuses
    statuses = parse_status_list(args.status if args.status else music_cfg.get("statuses"))

    run_mode = args.mode or ("incremental" if music_cfg.get("incremental") else "full")
    limit = args.limit if args.limit is not None else music_cfg.get("limit")
    if limit:
        run_mode = "full"

    cookie_str = resolve_cookie(args.cookie, args.cookie_file, auth_cfg)

    total, _ = export_interests(
        user_id, output_dir, statuses, run_mode, limit,
        kind="music", api_type="music", title="音乐", labels=MUSIC_STATUS_LABELS,
        build_record=_build_music_record, dedup_key="douban_id",
        cookie_str=cookie_str,
    )

    print(f"\n{'='*60}")
    print(f" 音乐  | 完成，共处理 {total} 条")
    print(f"{'='*60}")
