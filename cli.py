# -*- coding: utf-8 -*-
"""豆瓣数据导出工具 - 命令行入口

用法：
    python cli.py <子命令> [参数]
    python -m douban_exporter <子命令> [参数]

子命令：books / reviews / notes / movies / games / music
"""
import sys
from douban_exporter import main

if __name__ == "__main__":
    main()
