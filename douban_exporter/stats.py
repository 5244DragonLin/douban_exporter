# -*- coding: utf-8 -*-
"""豆瓣个人数据统计报告：读取读书/观影 JSON，生成 HTML 统计报告。

参考 zhihu_upvote_exporter/summary.py 的样式：
概览 / 年度趋势条形图（年折叠月展开）/ 评分分布 / 作者·导演·演员·出版社·类型·地区排行，
全部用纯标准库生成，无外部依赖。
"""
import os
import re
import sys
import json
import argparse
import base64
from collections import Counter, defaultdict
from datetime import datetime
from urllib.parse import quote

from .core import CONFIG_FILE, _load_config

# ============================================================
# 数据读取
# ============================================================

def _load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _parse_ym(date_str):
    """把 '2026-08-21' 之类解析为 (year, month)，失败返回 None"""
    if not date_str:
        return None
    m = re.match(r"^(\d{4})-(\d{2})", str(date_str).strip())
    if not m:
        return None
    return int(m.group(1)), int(m.group(2))


def _safe_rating(v, star_max=5):
    """评分转 1-5 星；0/空/异常视为未评分返回 0"""
    try:
        r = int(v)
    except (TypeError, ValueError):
        return 0
    if r < 1 or r > star_max:
        return 0
    return r


def _first_or_empty(items):
    """list 取第一项，标量原样返回，空则 ''"""
    if isinstance(items, list):
        return items[0].strip() if items and str(items[0]).strip() else ""
    if isinstance(items, str):
        return items.strip()
    return str(items).strip() if items else ""


# ============================================================
# 统计计算
# ============================================================

def _build_date_distribution(entries, date_key):
    """按 yyyy-mm 计数，返回 [(year, [(month, count)])] 按年倒序"""
    counter = Counter()
    for e in entries:
        ym = _parse_ym(e.get(date_key, ""))
        if ym:
            counter[f"{ym[0]}-{ym[1]:02d}"] += 1
    if not counter:
        return []
    groups = defaultdict(list)
    for month, count in sorted(counter.items(), key=lambda x: x[0]):
        groups[month[:4]].append((month, count))
    return sorted(groups.items(), key=lambda x: x[0], reverse=True)


def _build_rating_distribution(entries, rating_key, star_max=5):
    """1-5 星计数 + 未评分"""
    dist = Counter()
    unscored = 0
    scores = []
    for e in entries:
        r = _safe_rating(e.get(rating_key, 0), star_max)
        if r == 0:
            unscored += 1
        else:
            dist[r] += 1
            scores.append(r)
    avg = sum(scores) / len(scores) if scores else 0
    return dist, unscored, avg


def _build_rank(counter, top_n, min_count=1):
    return [(k, v) for k, v in counter.most_common(top_n) if v >= min_count]


def _count_field(entries, field, is_list=False):
    """统计某字段出现次数；is_list=True 时按列表元素展开（导演/演员/类型）"""
    c = Counter()
    for e in entries:
        v = e.get(field, "")
        if is_list:
            for item in v or []:
                item = str(item).strip()
                if item:
                    c[item] += 1
        else:
            item = _first_or_empty(v)
            if item:
                c[item] += 1
    return c


# ============================================================
# HTML 片段生成
# ============================================================

def _esc(text):
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _bar_row(label, count, max_count, label_w=90):
    """一条横向条形图"""
    width = count / max_count * 100 if max_count else 0
    return (
        f'<div class="bar-row"><div class="bar-label" style="width:{label_w}px">{_esc(label)}</div>'
        f'<div class="bar-num">{count}</div>'
        f'<div class="bar-track"><div class="bar-fill" style="width:{width:.1f}%"></div></div></div>'
    )


def _year_group_bars(date_dist, label_w=90):
    """年度折叠条形图：年汇总 + 点击展开月度明细"""
    if not date_dist:
        return '<p class="muted">暂无数据</p>'
    parts = []
    year_totals = [(y, sum(c for _, c in items)) for y, items in date_dist]
    year_max = max(c for _, c in year_totals) or 1
    for year, total in year_totals:
        month_rows = []
        if len(date_dist) > 1:  # 多个年份才需要展开
            m_items = [items for y2, items in date_dist if y2 == year][0]
            m_max = max(c for _, c in m_items) or 1
            for month, count in m_items:
                month_rows.append(
                    f'<div class="bar-row month-row"><div class="bar-label" style="width:{label_w}px">{month}</div>'
                    f'<div class="bar-num">{count}</div>'
                    f'<div class="bar-track"><div class="bar-fill" style="width:{count/m_max*100:.1f}%"></div></div></div>'
                )
        detail = f'<div class="month-bars">{"".join(month_rows)}</div>' if month_rows else ""
        parts.append(
            f'<details class="year-group"{"" if month_rows else " open"}>'
            f'<summary class="bar-row year-bar"><div class="bar-label" style="width:{label_w}px">{year}年</div>'
            f'<div class="bar-num">{total}</div>'
            f'<div class="bar-track"><div class="bar-fill" style="width:{total/year_max*100:.1f}%"></div></div></summary>'
            f'{detail}</details>'
        )
    return "\n".join(parts)


def _rank_table(rows, name_col):
    """排行表格：rows = [(名称, 次数)]"""
    lines = ['<table><thead><tr><th style="width:50px">#</th>'
             f'<th>{name_col}</th><th style="width:90px" class="num">数量</th></tr></thead><tbody>']
    for i, row in enumerate(rows, 1):
        name, cnt = row[0], row[1]
        lines.append(f'<tr><td>{i}</td><td>{_esc(name)}</td><td class="num">{cnt}</td></tr>')
    lines.append("</tbody></table>")
    return "\n".join(lines)


def _rating_distribution_html(dist, unscored, avg, label="评分"):
    """评分分布：条形图 + 均值说明"""
    if not dist:
        return '<p class="muted">暂无已评分数据</p>'
    max_count = max(dist.values())
    bars = "".join(_bar_row(f"{s}星", dist[s], max_count, label_w=60) for s in range(1, 6))
    note = (f'<p class="muted">平均 {avg:.2f} 星'
            + (f'，{unscored} 条未评分' if unscored else "")
            + "</p>")
    return bars + note


# ============================================================
# 报告主体
# ============================================================

def _wish_link(title, url):
    """想读/想看清单条目：有链接时书名可点击跳转豆瓣"""
    title = _esc(title)
    if url:
        return f'<a href="{_esc(url)}" target="_blank" rel="noopener">{title}</a>'
    return title


def _books_section(collect, wish):
    dist, unscored, avg = _build_rating_distribution(collect, "我的评分")
    date_dist = _build_date_distribution(collect, "阅读日期")
    author_counter = _count_field(collect, "作者")
    pub_counter = _count_field(collect, "出版社")
    year_counter = Counter()
    for e in collect:
        y = _first_or_empty(e.get("出版日期", ""))
        m = re.match(r"^(\d{4})", y)
        if m:
            year_counter[m.group(1)] += 1
    top_authors = _build_rank(author_counter, 10)
    top_pubs = _build_rank(pub_counter, 10)
    pub_year = _build_rank(year_counter, 10)
    five_star = dist.get(5, 0)

    h = ['<h2 id="sec-books">📚 读书</h2>']
    # 概览
    h.append('<div class="cards">'
             f'<div class="card"><div class="card-num">{len(collect)}</div><div class="card-label">已读</div></div>'
             f'<div class="card"><div class="card-num">{len(wish)}</div><div class="card-label">想读</div></div>'
             f'<div class="card"><div class="card-num">{avg:.2f}</div><div class="card-label">平均评分</div></div>'
             f'<div class="card"><div class="card-num">{five_star}</div><div class="card-label">五星本数</div></div>'
             f'<div class="card"><div class="card-num">{len(collect)+len(wish)}</div><div class="card-label">合计</div></div>'
             '</div>')
    # 年度趋势
    h.append('<h3>阅读趋势</h3>')
    h.append(_year_group_bars(date_dist))
    # 评分分布
    h.append('<h3>评分分布</h3>')
    h.append(_rating_distribution_html(dist, unscored, avg))
    # 排行
    h.append('<h3>作者排行 Top 10</h3>')
    h.append(_rank_table(top_authors, "作者") if top_authors else '<p class="muted">暂无数据</p>')
    h.append('<h3>出版社排行 Top 10</h3>')
    h.append(_rank_table(top_pubs, "出版社") if top_pubs else '<p class="muted">暂无数据</p>')
    h.append('<h3>出版年份分布 Top 10</h3>')
    h.append(_rank_table(pub_year, "出版年份") if pub_year else '<p class="muted">暂无数据</p>')
    # 想读清单（折叠）
    if wish:
        rows = [f"<li>{_wish_link(x.get('书名',''), x.get('豆瓣链接',''))}"
                f"<span class='muted'> — {_esc(_first_or_empty(x.get('作者')))}</span></li>"
                for x in wish if x.get("书名")]
        h.append(f'<details class="list-group"><summary class="list-summary">想读清单（{len(rows)} 本）</summary>'
                 f'<ul class="wish-list">{"".join(rows)}</ul></details>')
    return "\n".join(h)


def _movies_section(collect, wish):
    dist, unscored, avg = _build_rating_distribution(collect, "rating")
    date_dist = _build_date_distribution(collect, "date")
    genre_counter = _count_field(collect, "genres", is_list=True)
    director_counter = _count_field(collect, "directors", is_list=True)
    actor_counter = _count_field(collect, "actors", is_list=True)
    country_counter = _count_field(collect, "country")
    top_genres = _build_rank(genre_counter, 15)
    top_directors = _build_rank(director_counter, 10)
    top_actors = _build_rank(actor_counter, 15)
    top_countries = _build_rank(country_counter, 10)
    five_star = dist.get(5, 0)

    h = ['<h2 id="sec-movies">🎬 观影</h2>']
    h.append('<div class="cards">'
             f'<div class="card"><div class="card-num">{len(collect)}</div><div class="card-label">看过</div></div>'
             f'<div class="card"><div class="card-num">{len(wish)}</div><div class="card-label">想看</div></div>'
             f'<div class="card"><div class="card-num">{avg:.2f}</div><div class="card-label">平均评分</div></div>'
             f'<div class="card"><div class="card-num">{five_star}</div><div class="card-label">五星部数</div></div>'
             f'<div class="card"><div class="card-num">{len(collect)+len(wish)}</div><div class="card-label">合计</div></div>'
             '</div>')
    h.append('<h3>观影趋势</h3>')
    h.append(_year_group_bars(date_dist))
    h.append('<h3>评分分布</h3>')
    h.append(_rating_distribution_html(dist, unscored, avg))
    h.append('<h3>类型分布 Top 15</h3>')
    h.append(_rank_table(top_genres, "类型") if top_genres else '<p class="muted">暂无数据</p>')
    h.append('<h3>导演排行 Top 10</h3>')
    h.append(_rank_table(top_directors, "导演") if top_directors else '<p class="muted">暂无数据</p>')
    h.append('<h3>演员排行 Top 15</h3>')
    h.append(_rank_table(top_actors, "演员") if top_actors else '<p class="muted">暂无数据</p>')
    h.append('<h3>地区分布 Top 10</h3>')
    h.append(_rank_table(top_countries, "地区") if top_countries else '<p class="muted">暂无数据</p>')
    if wish:
        # 想看清单：按豆瓣评分倒序，方便挑片
        wish_sorted = sorted([x for x in wish if x.get("title")],
                             key=lambda x: float(x.get("douban_rating") or 0), reverse=True)
        rows = []
        for x in wish_sorted:
            dr = x.get("douban_rating") or "—"
            rows.append(f"<li>{_wish_link(x.get('title',''), x.get('url',''))}"
                        f"<span class='muted'> · 豆瓣 {dr} · {_esc(x.get('year',''))}</span></li>")
        h.append(f'<details class="list-group"><summary class="list-summary">想看清单（{len(rows)} 部，按豆瓣评分排序）</summary>'
                 f'<ul class="wish-list">{"".join(rows)}</ul></details>')
    return "\n".join(h)


# ============================================================
# 主入口
# ============================================================

_PAGE_CSS = """
body { margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Noto Sans SC", "PingFang SC", "Microsoft YaHei", sans-serif; font-size: 15px; line-height: 1.8; color: #1a1a1a; background: #fff; }
.layout { display: flex; align-items: flex-start; }
.sidebar { width: 170px; flex-shrink: 0; position: sticky; top: 0; height: 100vh; overflow-y: auto; padding: 28px 14px; box-sizing: border-box; border-right: 1px solid #eee; background: #fafafa; }
.sidebar h3 { font-size: 12px; color: #8590a6; letter-spacing: 2px; margin: 0 0 14px 6px; }
.sidebar a { display: block; padding: 7px 10px; margin: 2px 0; border-radius: 4px; color: #444; text-decoration: none; font-size: 14px; }
.sidebar a:hover { background: #eef3fb; color: #175199; }
.sidebar a.active { background: #0066cc; color: #fff; }
.sidebar a.active:hover { background: #0052a3; color: #fff; }
.main { flex: 1; min-width: 0; max-width: 1100px; margin: 0 auto; padding: 24px 28px 60px; }
h1 { text-align: center; font-size: 1.6em; }
h2 { border-bottom: 2px solid #0066cc; padding-bottom: 0.3em; margin-top: 2em; }
h3 { margin-top: 1.6em; }
.report-time { text-align: center; color: #8590a6; margin-bottom: 1.5em; }
.muted { color: #8590a6; }
.cards { display: flex; gap: 12px; flex-wrap: wrap; margin: 1em 0; }
.card { flex: 1; min-width: 100px; background: #f6f8fa; border-radius: 8px; padding: 14px 10px; text-align: center; }
.card-num { font-size: 1.5em; font-weight: 600; color: #0066cc; }
.card-label { font-size: 0.85em; color: #666; margin-top: 2px; }
table { width: 100%; border-collapse: collapse; margin: 0.8em 0; }
th, td { padding: 8px 12px; border-bottom: 1px solid #eee; text-align: left; }
th { background: #f6f8fa; font-weight: 600; }
th.num, td.num { text-align: right; }
tr:hover { background: #f9f9f9; }
.bar-row { display: flex; align-items: center; margin: 3px 0; height: 26px; }
.bar-label { flex-shrink: 0; font-size: 13px; color: #555; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.bar-num { width: 36px; flex-shrink: 0; text-align: right; font-size: 13px; color: #8590a6; margin-right: 8px; }
.bar-track { flex: 1; height: 16px; background: #f0f0f0; border-radius: 3px; overflow: hidden; }
.bar-fill { height: 100%; background: linear-gradient(90deg, #0066cc, #4d94ff); border-radius: 3px; min-width: 2px; }
.year-group { margin: 2px 0; }
.year-group > summary { list-style: none; cursor: pointer; }
.year-group > summary::-webkit-details-marker { display: none; }
.year-bar { font-weight: 600; }
.year-bar::before { content: "▸ "; display: inline-block; width: 16px; transition: transform 0.2s; color: #0066cc; flex-shrink: 0; }
.year-group[open] > .year-bar::before { content: "▾ "; }
.month-bars { margin-left: 16px; border-left: 2px solid #e8e8e8; padding-left: 12px; }
.month-row .bar-label { font-size: 12px; }
.list-group { margin: 1.2em 0 0; }
.list-summary { cursor: pointer; color: #175199; font-weight: 600; }
.list-summary::before { content: "▸ "; color: #0066cc; }
.list-group[open] > .list-summary::before { content: "▾ "; }
.wish-list { margin: 8px 0 12px; padding-left: 1.4em; line-height: 1.9; max-height: 400px; overflow-y: auto; }
a { color: #3377cc; text-decoration: none; }
"""


_FAVICON_FALLBACK = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect width="64" height="64" rx="14" fill="#0066cc"/><rect x="12" y="16" width="16" height="32" rx="2" fill="#fff"/><line x1="20" y1="16" x2="20" y2="48" stroke="#0066cc" stroke-width="1.5"/><rect x="36" y="16" width="16" height="32" rx="2" fill="#fff"/></svg>"""


def _favicon_data_uri():
    """读取项目 assets/favicon.png 并转为 data URI；读取失败用内置 SVG 兜底"""
    png_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets", "favicon.png")
    try:
        with open(png_path, "rb") as f:
            data = base64.b64encode(f.read()).decode("ascii")
        return f"data:image/png;base64,{data}"
    except Exception:
        svg = _FAVICON_FALLBACK
        return "data:image/svg+xml," + quote(svg, safe="")


def _render_page(books_html, movies_html, gen_time, books_desc, movies_desc):
    """渲染单文件统计报告：侧边栏目录 + JS 切换读书/观影视图。

    Args:
        books_html: 读书板块内容 HTML
        movies_html: 观影板块内容 HTML
        gen_time: 生成时间字符串
        books_desc: 读书数据范围描述
        movies_desc: 观影数据范围描述
    """
    nav_items = (
        '<a href="#books" data-view="books" class="active">📚 读书</a>'
        '<a href="#movies" data-view="movies">🎬 观影</a>'
    )
    page = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>豆瓣个人数据统计报告</title>
<link rel="icon" href="{_favicon_data_uri()}">
<style>{_PAGE_CSS}</style>
</head>
<body>
<div class="layout">
<nav class="sidebar">
<h3>目录</h3>
{nav_items}
</nav>
<div class="main">
<h1>豆瓣个人数据统计报告</h1>
<p class="report-time"><strong>生成时间：{gen_time}</strong></p>
<div id="view-books" class="view">
<p class="report-time">{books_desc}</p>
{books_html}
</div>
<div id="view-movies" class="view" style="display:none">
<p class="report-time">{movies_desc}</p>
{movies_html}
</div>
</div>
</div>
<script>
function showView(name) {{
  document.querySelectorAll('.view').forEach(function (v) {{ v.style.display = 'none'; }});
  document.getElementById('view-' + name).style.display = 'block';
  document.querySelectorAll('.sidebar a').forEach(function (a) {{
    a.classList.toggle('active', a.getAttribute('data-view') === name);
  }});
}}
document.querySelectorAll('.sidebar a').forEach(function (a) {{
  a.addEventListener('click', function (e) {{ e.preventDefault(); showView(a.getAttribute('data-view')); }});
}});
var init = location.hash.slice(1);
if (init !== 'books' && init !== 'movies') init = 'books';
showView(init);
</script>
</body>
</html>"""
    return page


def stats_main(config=None):
    parser = argparse.ArgumentParser(description="豆瓣个人数据统计报告（读书 + 观影）")
    parser.add_argument("--output", "-o", dest="output", default=None,
                        help="输出目录（默认: 读书记录所在目录的上级目录，即豆瓣内容根目录）")
    parser.add_argument("--config", "-c", dest="config", default=None,
                        help="YAML 配置文件路径")
    parser.add_argument("--format", "-f", dest="fmt", default="html", choices=["html"],
                        help="输出格式（当前支持 html）")
    args = parser.parse_args()

    if config is None:
        config = _load_config(args.config or CONFIG_FILE)
    stats_cfg = config.get("stats") or {}

    # 输出目录：命令行 > 配置 > 默认（读书记录目录的上一级；未配置读书记录目录时用当前目录）
    if args.output:
        output_dir = os.path.abspath(args.output)
    elif stats_cfg.get("output"):
        output_dir = os.path.abspath(stats_cfg["output"])
    else:
        books_out = (config.get("books") or {}).get("output")
        output_dir = os.path.dirname(os.path.abspath(books_out)) if books_out else os.getcwd()
    os.makedirs(output_dir, exist_ok=True)

    # 数据目录：书籍/观影各自的输出目录
    books_dir = os.path.abspath((config.get("books") or {}).get("output")
                                or os.path.join(output_dir, "读书记录"))
    movies_dir = os.path.abspath((config.get("movies") or {}).get("output")
                                 or os.path.join(output_dir, "观影记录"))

    books_collect = _load_json(os.path.join(books_dir, "douban_books_collect.json"))
    books_wish = _load_json(os.path.join(books_dir, "douban_books_wish.json"))
    movies_collect = _load_json(os.path.join(movies_dir, "douban_movies_collect.json"))
    movies_wish = _load_json(os.path.join(movies_dir, "douban_movies_wish.json"))

    total_entries = len(books_collect) + len(movies_collect)
    if total_entries == 0:
        print("[错误] 未找到读书/观影数据，请先运行 books / movies 抓取")
        sys.exit(1)

    gen_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    books_html = _books_section(books_collect, books_wish)
    movies_html = _movies_section(movies_collect, movies_wish)

    page = _render_page(
        books_html, movies_html, gen_time,
        f"读书记录 {len(books_collect)} 条 · 想读 {len(books_wish)} 条",
        f"观影记录 {len(movies_collect)} 条 · 想看 {len(movies_wish)} 条")

    report_path = os.path.join(output_dir, "豆瓣统计报告.html")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(page)
    print(f"统计报告已生成：{report_path}")
    print(f"  读书：已读 {len(books_collect)} / 想读 {len(books_wish)}")
    print(f"  观影：看过 {len(movies_collect)} / 想看 {len(movies_wish)}")
    return report_path
