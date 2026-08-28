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

DEFAULT_OUTPUT_DIR = "douban_reviews_output"
# 配置文件位于项目根目录（即本包所在目录的上一级）
CONFIG_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config.yaml")
logger = logging.getLogger("douban_exporter")
DEFAULT_OUTPUT = os.path.join(os.path.expanduser("~"), "douban_books.json")
DEFAULT_DELAY = (2.5, 4.5)  # 随机请求间隔（秒）
MAX_RETRIES = 3
RETRY_DELAY = 10  # 重试前等待秒数
ITEMS_PER_PAGE = 15

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Referer": "https://book.douban.com/",
}


def sanitize_filename(name):
    name = name.replace("《", "\x01L").replace("》", "\x01R")
    name = re.sub(r'[\\/:*?"<>|\r\n]', "_", name)
    name = name.replace("\x01L", "《").replace("\x01R", "》")
    name = name.strip(". ")
    return name or "unnamed"


def index_path(output_dir, kind):
    return os.path.join(output_dir, f".douban_{kind}_index.json")


def load_index(output_dir, kind):
    """返回 (已抓取ID集合, 翻页进度max_page)。文件不存在或损坏时返回 (set(), 0)。"""
    p = index_path(output_dir, kind)
    if not output_dir or not os.path.exists(p):
        return set(), 0
    try:
        with open(p, "r", encoding="utf-8") as f:
            d = json.load(f)
        ids = set(str(x) for x in d.get("ids", []))
        return ids, int(d.get("max_page", 0) or 0)
    except Exception:
        return set(), 0


def save_index(output_dir, kind, ids, max_page=0):
    """把已抓取 ID 集合与翻页进度写入隐藏索引文件。"""
    p = index_path(output_dir, kind)
    try:
        os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(
                {"ids": sorted(str(x) for x in ids), "max_page": int(max_page or 0)},
                f, ensure_ascii=False, indent=2,
            )
    except Exception:
        pass


def seed_ids_from_json(filepath, id_keys):
    """首次增量（索引尚不存在但已有数据文件）时，从数据文件反推已抓取 ID，避免整页重抓。"""
    if not filepath or not os.path.exists(filepath):
        return set()
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        ids = set()
        for item in data:
            for k in id_keys:
                v = item.get(k)
                if v:
                    ids.add(str(v))
                    break
        return ids
    except Exception:
        return set()


def parse_rating_from_class(class_str):
    match = re.search(r"allstar(\d)0", class_str or "")
    return int(match.group(1)) if match else 0


def rating_to_stars(rating):
    return "★" * rating + "☆" * (5 - rating)


def rating_to_label(rating):
    return {1: "很差", 2: "较差", 3: "还行", 4: "推荐", 5: "力荐"}.get(rating, "")


def randomized_delay(base, jitter):
    return base + random.uniform(0, jitter)


def make_ssl_context():
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def make_opener(cookie_str=None):
    """创建带 Cookie 的 Opener。

    Args:
        cookie_str: 可选，豆瓣登录 Cookie 字符串（如 "dbcl2=xxx; ck=xxx; bid=xxx"）。
                    传入后直接注入请求头；不传则匿名访问。
    """
    cj = http.cookiejar.CookieJar()
    ctx = make_ssl_context()
    opener = urllib.request.build_opener(
        urllib.request.HTTPSHandler(context=ctx),
        urllib.request.HTTPCookieProcessor(cj),
    )
    headers = [(k, v) for k, v in HEADERS.items()]
    if cookie_str:
        headers.append(("Cookie", cookie_str))
    opener.addheaders = headers
    return opener


def load_cookie_file(path):
    """从文件读取豆瓣 Cookie 字符串（文件内容即 Cookie，或包含 dbcl2= 的行；跳过 # 注释行）。"""
    if not path or not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.read().splitlines()
        if not lines:
            return None
        # 过滤空行与 # 注释行
        content_lines = [ln for ln in lines if ln.strip() and not ln.strip().startswith("#")]
        if not content_lines:
            return None
        # 兼容整段 cookie 或包含 dbcl2 的行
        for line in content_lines:
            if "dbcl2=" in line:
                return line.strip()
        return "\n".join(content_lines).strip()
    except Exception:
        return None


def fetch(url, opener, timeout=15):
    """带重试的页面抓取。"""
    req = urllib.request.Request(url)
    for attempt in range(MAX_RETRIES):
        try:
            resp = opener.open(req, timeout=timeout)
            return resp.read().decode("utf-8", errors="replace")
        except Exception as e:
            print(f" [警告] 获取 {url} 失败 (尝试 {attempt+1}/{MAX_RETRIES}): {e}")
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY)
            else:
                return None
    return None


def random_delay():
    """随机等待，模拟人类行为。"""
    time.sleep(random.uniform(*DEFAULT_DELAY))


def _save_checkpoint(results, json_path, every=50):
    """每 every 条中间保存一次到 .tmp 文件，防止中断丢数据，不影响正式文件。"""
    if len(results) % every == 0 and len(results) > 0:
        tmp_path = json_path + ".tmp"
        os.makedirs(os.path.dirname(os.path.abspath(tmp_path)), exist_ok=True)
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        return True
    return False


def load_existing_data(filepath, id_key="豆瓣ID"):
    """读取已有数据文件（CSV 或 JSON），返回 {id: row} 字典。

    id_key: 去重主键字段名（books 用「豆瓣ID」，notes 用「笔记ID」）。
    """
    if not os.path.exists(filepath):
        return {}
    existing = {}

    if filepath.endswith(".json"):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            for item in data:
                bid = item.get(id_key, "")
                if bid:
                    existing[str(bid)] = item
        except Exception as e:
            print(f"[警告] 读取已有 JSON 失败: {e}")
    else:
        try:
            with open(filepath, "r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    bid = row.get(id_key, "")
                    if bid:
                        existing[str(bid)] = row
        except Exception as e:
            print(f"[警告] 读取已有 CSV 失败: {e}")

    return existing


def save_data(books, filepath, mode="w", id_key="豆瓣ID"):
    """
    将书籍列表写入 JSON 文件。

    Args:
        books: list[dict]
        filepath: 输出路径
        mode: "w"（覆盖）或 "a"（追加）
    """
    if mode == "a":
        existing = load_existing_data(filepath, id_key=id_key)
        existing_bids = set(existing.keys())
        new_books = [b for b in books if str(b.get(id_key, "")) not in existing_bids]
        all_books = list(existing.values()) + new_books
    else:
        all_books = books

    # 确保输出目录存在
    os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)

    # 写入 JSON
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(all_books, f, ensure_ascii=False, indent=2)
    return len(all_books)


def _load_config(config_path):
    if not config_path or not os.path.exists(config_path):
        return {}
    try:
        import yaml
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
        logger.info(f"已加载配置文件: {config_path}")
        return _normalize_config(config or {})
    except Exception as e:
        logger.error(f"配置文件读取失败: {e}")
        sys.exit(1)


def _normalize_config(cfg):
    """将配置规范化为统一结构，兼容旧版扁平键：

    新版推荐分层结构：
      user:
        id: "132021081"
        cookie: "..."
        cookie_file: "..."
      books:
        output: "douban_books.csv"
        format: "csv"
      reviews:
        output: "douban_reviews_output"
        format: "both"

    旧版扁平键（user_id / cookie / books_output / reviews_output ...）
    仍可读取，分层键优先。
    """
    if not isinstance(cfg, dict):
        return {}

    # 功能开关（features）：控制各子命令是否启用，默认均启用（兼容旧配置）
    features = cfg.get("features") or {}
    if not isinstance(features, dict):
        features = {}
    for feat in ("books", "reviews", "notes", "movies"):
        val = features.get(feat, True)
        features[feat] = bool(val) if isinstance(val, bool) else (str(val).strip().lower() in ("1", "true", "yes", "on", "启用", "开启", "是"))
    cfg["features"] = features

    # 用户相关
    user = cfg.get("user") or {}
    if not isinstance(user, dict):
        user = {}
    user.setdefault("id", cfg.get("user_id"))
    user.setdefault("cookie", cfg.get("cookie"))
    user.setdefault("cookie_file", cfg.get("cookie_file"))
    cfg["user"] = user

    # books 子命令
    books = cfg.get("books") or {}
    if not isinstance(books, dict):
        books = {}
    books.setdefault("output", cfg.get("books_output"))
    books.setdefault("format", cfg.get("books_format"))
    # books.types: 指定抓取分类（collect=已读 / wish=想读 / do=在读），
    # 非法值会被忽略，为空则交由运行时决定（默认全部）。
    raw_types = books.get("types")
    if raw_types is not None:
        if isinstance(raw_types, (list, tuple)):
            valid = {"collect", "wish", "do"}
            parsed = [t for t in raw_types if t in valid]
            books["types"] = parsed
        else:
            books.pop("types", None)
    cfg["books"] = books

    # reviews 子命令
    reviews = cfg.get("reviews") or {}
    if not isinstance(reviews, dict):
        reviews = {}
    reviews.setdefault("output", cfg.get("reviews_output"))
    reviews.setdefault("format", cfg.get("reviews_format"))
    cfg["reviews"] = reviews

    # notes 子命令（读书笔记/标注抓取）—— 输出固定为 Markdown（每本书一个 {书名}.md）
    notes = cfg.get("notes") or {}
    if not isinstance(notes, dict):
        notes = {}
    notes.setdefault("output", cfg.get("notes_output"))
    # 兼容性读取：旧配置可能写 format: json/csv，notes 现已固定为 md，忽略该值
    notes.setdefault("incremental", False)
    notes.setdefault("max_pages", None)
    cfg["notes"] = notes

    # movies 子命令（观影记录导出，纯标准库 + Cookie，无需 Playwright）
    movies = cfg.get("movies") or {}
    if not isinstance(movies, dict):
        movies = {}
    movies.setdefault("output", cfg.get("movies_output"))
    movies.setdefault("incremental", False)     # 增量模式：已有 movies.json 去重
    movies.setdefault("limit", cfg.get("limit"))
    # movies.types: 抓取的观影状态列表
    #   collect=看过, wish=想看, do=在看；为空则默认三种全抓。
    raw_statuses = movies.get("types")
    if raw_statuses is not None:
        if isinstance(raw_statuses, (list, tuple)):
            valid = {"collect", "wish", "do"}
            parsed = [s for s in raw_statuses if s in valid]
            movies["types"] = parsed if parsed else ["collect", "wish", "do"]
        else:
            movies["types"] = ["collect", "wish", "do"]
    else:
        movies["types"] = ["collect", "wish", "do"]
    cfg["movies"] = movies

    # 顶层通用项（老式 reviews 配置兼容）
    cfg.setdefault("output", cfg.get("output"))
    cfg.setdefault("limit", cfg.get("limit"))
    cfg.setdefault("incremental", cfg.get("incremental", False))
    cfg.setdefault("visible", cfg.get("visible", False))
    cfg.setdefault("format", cfg.get("format"))
    return cfg


def _setup_logging():
    pass  # 已弃用，改为纯 print 输出


def _urllib_opener(cookie_str=None):
    """创建纯 urllib 的 opener，可选注入登录 Cookie。"""
    cj = http.cookiejar.CookieJar()
    ctx = make_ssl_context()
    opener = urllib.request.build_opener(
        urllib.request.HTTPSHandler(context=ctx),
        urllib.request.HTTPCookieProcessor(cj),
    )
    headers = [(k, v) for k, v in HEADERS.items()]
    if cookie_str:
        headers.append(("Cookie", cookie_str))
    opener.addheaders = headers
    return opener


def _http_get(url, opener, timeout=20):
    """带重试的 GET 抓取，返回 HTML 文本或 None。"""
    req = urllib.request.Request(url)
    for attempt in range(MAX_RETRIES):
        try:
            resp = opener.open(req, timeout=timeout)
            return resp.read().decode("utf-8", errors="replace")
        except Exception as e:
            print(f" [警告] 获取 {url} 失败 (尝试 {attempt+1}/{MAX_RETRIES}): {e}")
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY)
            else:
                return None


def _clean_html_text(s):
    """清理 HTML 片段为纯文本。"""
    s = re.sub(r"<style.*?</style>", "", s, flags=re.DOTALL)
    s = re.sub(r"<script.*?</script>", "", s, flags=re.DOTALL)
    s = re.sub(r"<[^>]+>", "", s)
    s = html.unescape(s)
    return re.sub(r"\s+", " ", s).strip()
