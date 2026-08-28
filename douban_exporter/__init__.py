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

from .books import books_main
from .reviews import reviews_main
from .notes import notes_main
from .movies import movies_main
from .games import games_main
from .music import music_main
from .stats import stats_main
from .core import (
    _load_config, CONFIG_FILE, logger,
)

def _auto_route_by_features(config_path=None):
    """根据 config.yaml 的 features 自动执行所有启用的功能：按配置顺序依次执行，不交互询问。

    Args:
        config_path: 配置文件路径，None 则使用默认 CONFIG_FILE
    """
    config = _load_config(config_path or CONFIG_FILE)
    feat = config.get("features") or {}
    books_on = feat.get("books", True)
    reviews_on = feat.get("reviews", True)
    notes_on = feat.get("notes", True)

    enabled = []
    if books_on:
        enabled.append(("books", "读书列表抓取（books）", books_main))
    if reviews_on:
        enabled.append(("reviews", "书评抓取（reviews）", reviews_main))
    if notes_on:
        enabled.append(("notes", "读书笔记抓取（notes）", notes_main))
    if feat.get("movies", True):
        enabled.append(("movies", "观影记录导出（movies）", movies_main))
    if feat.get("games", True):
        enabled.append(("games", "游戏记录导出（games）", games_main))
    if feat.get("music", True):
        enabled.append(("music", "音乐记录导出（music）", music_main))

    # 全部禁用
    if not enabled:
        print("[提示] 配置文件 features 将 books / reviews / notes / movies 均设为 false（在 config.yaml 顶部 features 段设置）")
        print("      至少启用一个功能，或直接指定子命令: python cli.py books | reviews | notes | movies")
        sys.exit(0)

    # 按顺序依次执行所有启用的功能（不交互询问）
    for key, label, fn in enabled:
        print()
        fn(config)


def main():
    pass  # 不再使用 logging
    # 子命令: books — 抓取已读/想读/在读列表（纯标准库实现，无需浏览器/登录）
    if len(sys.argv) > 1 and sys.argv[1] == "books":
        sys.argv.pop(1)
        books_main()
        return
    # 子命令: reviews — 抓取书评（纯标准库 + Cookie，无需 Playwright）
    if len(sys.argv) > 1 and sys.argv[1] == "reviews":
        sys.argv.pop(1)
        reviews_main()
        return
    # 子命令: notes — 抓取读书笔记（标注）
    if len(sys.argv) > 1 and sys.argv[1] == "notes":
        sys.argv.pop(1)
        notes_main()
        return
    # 子命令: movies — 观影记录导出（纯标准库，无需 Playwright）
    if len(sys.argv) > 1 and sys.argv[1] == "movies":
        sys.argv.pop(1)
        movies_main()
        return
    # 子命令: games — 游戏记录导出（纯标准库，无需 Playwright）
    if len(sys.argv) > 1 and sys.argv[1] == "games":
        sys.argv.pop(1)
        games_main()
        return
    # 子命令: music — 音乐记录导出（纯标准库，无需 Playwright）
    if len(sys.argv) > 1 and sys.argv[1] == "music":
        sys.argv.pop(1)
        music_main()
        return
    # 子命令: stats — 豆瓣个人数据统计报告（读书 + 观影，无需网络）
    if len(sys.argv) > 1 and sys.argv[1] == "stats":
        sys.argv.pop(1)
        stats_main()
        return

    # 纯无参运行：根据 features 自动路由到启用的功能（置顶开关的意义所在）
    if len(sys.argv) == 1:
        _auto_route_by_features()
        return

    # 带 -c / --config 参数：读取配置文件，按 features 自动执行所有启用的功能
    for i, arg in enumerate(sys.argv):
        if arg in ("-c", "--config") and i + 1 < len(sys.argv):
            _auto_route_by_features(sys.argv[i + 1])
            return
    if "-c" in sys.argv or "--config" in sys.argv:
        _auto_route_by_features()
        return

    # 未识别的子命令 / 参数：给出用法提示
    # （浏览器模式已移除，书评改用纯标准库 + Cookie 的 reviews 子命令抓取）
    print("未识别的参数或子命令。可用子命令：")
    print("  books / reviews / notes / movies / games / music / stats")
    print("或无参数运行（按 config.yaml 的 features 自动执行）。")
    print("书评抓取示例：python cli.py reviews -c config.yaml")
    print("统计报告示例：python cli.py stats -c config.yaml")
    sys.exit(2)
