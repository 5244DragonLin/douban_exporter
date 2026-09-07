# -*- coding: utf-8 -*-
"""豆瓣数据导出工具 - 包入口：聚合子命令 + 按 features 自动路由。"""
import sys

from .books import books_main
from .reviews import reviews_main
from .notes import notes_main
from .movies import movies_main
from .games import games_main
from .music import music_main
from .stats import stats_main
from .core import _load_config, CONFIG_FILE

_SUBCOMMANDS = {
    "books": books_main,
    "reviews": reviews_main,
    "notes": notes_main,
    "movies": movies_main,
    "games": games_main,
    "music": music_main,
    "stats": stats_main,
}


def _auto_route_by_features(config_path=None):
    """根据 config.yaml 的 features 自动执行所有启用的功能：按固定顺序依次执行，不交互询问。

    Args:
        config_path: 配置文件路径，None 则使用默认 CONFIG_FILE
    """
    config = _load_config(config_path or CONFIG_FILE)
    feat = config.get("features") or {}
    enabled = [name for name in ("books", "reviews", "notes", "movies", "games", "music")
               if feat.get(name, True)]

    # 全部禁用
    if not enabled:
        print("[提示] 配置文件 features 将所有功能均设为 false（在 config.yaml 顶部 features 段设置）")
        print("      至少启用一个功能，或直接指定子命令: python cli.py books | reviews | notes | movies | games | music | stats")
        sys.exit(0)

    # 按顺序依次执行所有启用的功能（不交互询问）
    for name in enabled:
        print()
        _SUBCOMMANDS[name](config)


def main():
    if len(sys.argv) > 1 and sys.argv[1] in _SUBCOMMANDS:
        # 显式子命令（不受 features 限制，始终可运行）
        name = sys.argv.pop(1)
        _SUBCOMMANDS[name]()
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
    print("未识别的参数或子命令。可用子命令：")
    print("  " + " / ".join(_SUBCOMMANDS))
    print("或无参数运行（按 config.yaml 的 features 自动执行）。")
    print("书评抓取示例：python cli.py reviews -c config.yaml")
    print("统计报告示例：python cli.py stats -c config.yaml")
    sys.exit(2)
