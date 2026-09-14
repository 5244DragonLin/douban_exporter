# -*- coding: utf-8 -*-
"""共享库：HTTP 请求与 Cookie、HTML 清理、增量索引、配置文件加载与归一化。"""
import os, re, sys, json, time, random, logging, html
import urllib.request
import ssl
import http.cookiejar

DEFAULT_OUTPUT_DIR = "douban_reviews_output"
# 配置文件位于项目根目录（即本包所在目录的上一级）
CONFIG_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config.yaml")
logger = logging.getLogger("douban_exporter")
DEFAULT_DELAY = (2.5, 4.5)  # 随机请求间隔（秒）
MAX_RETRIES = 3
RETRY_DELAY = 10  # 重试前等待秒数

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


def rating_to_stars(rating):
    return "★" * rating + "☆" * (5 - rating)


def rating_to_label(rating):
    return {1: "很差", 2: "较差", 3: "还行", 4: "推荐", 5: "力荐"}.get(rating, "")


def randomized_delay(base, jitter):
    return base + random.uniform(0, jitter)


def make_ssl_context():
    return ssl.create_default_context()


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


def fetch(url, opener, timeout=20):
    """带重试的页面抓取，返回 HTML 文本或 None。"""
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


def _save_checkpoint(results, json_path):
    """把当前已抓结果保存到 .tmp 文件，防止中断丢数据，不影响正式文件。

    保存节奏由调用方控制（每新增 50 条调用一次），本函数只负责写盘。
    """
    if not results:
        return False
    tmp_path = json_path + ".tmp"
    os.makedirs(os.path.dirname(os.path.abspath(tmp_path)), exist_ok=True)
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    return True


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
    """将配置规范化为统一结构，兼容旧版扁平键与旧节名。

    推荐分层结构（键名遵循《爬虫项目指南》统一规范）：
      auth:
        cookie: "..."
        cookie_file: "..."
      user:
        id: "132021081"
      books:
        output_dir: "douban_books_output"
        types: [collect, wish, do]
      movies:
        output_dir: "douban_movies_output"
        statuses: [collect, wish, do]

    兼容项：旧 user.cookie / 顶层扁平键（user_id / cookie / books_output ...）、
    各功能节旧键 output（现 output_dir）。分层新键优先。
    """
    if not isinstance(cfg, dict):
        return {}

    # 功能开关（features）：控制各子命令是否启用，默认均启用（兼容旧配置）
    features = cfg.get("features") or {}
    if not isinstance(features, dict):
        features = {}
    for feat in ("books", "reviews", "notes", "movies", "games", "music"):
        val = features.get(feat, True)
        features[feat] = bool(val) if isinstance(val, bool) else (str(val).strip().lower() in ("1", "true", "yes", "on", "启用", "开启", "是"))
    cfg["features"] = features

    # 认证（auth 节）：兼容旧 user.cookie / 旧扁平键
    auth = cfg.get("auth") or {}
    if not isinstance(auth, dict):
        auth = {}
    user = cfg.get("user") or {}
    if not isinstance(user, dict):
        user = {}
    auth.setdefault("cookie", user.get("cookie") or cfg.get("cookie"))
    auth.setdefault("cookie_file", user.get("cookie_file") or cfg.get("cookie_file"))
    cfg["auth"] = auth
    # user 节仅保留业务字段（id），凭据统一走 auth
    cfg["user"] = {"id": user.get("id") or cfg.get("user_id")}

    # books 子命令
    books = cfg.get("books") or {}
    if not isinstance(books, dict):
        books = {}
    books.setdefault("output_dir", books.get("output") or cfg.get("books_output"))
    books.pop("output", None)
    books.setdefault("format", cfg.get("books_format"))
    books.setdefault("incremental", True)
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
    reviews.setdefault("output_dir", reviews.get("output") or cfg.get("reviews_output"))
    reviews.pop("output", None)
    reviews.setdefault("format", cfg.get("reviews_format"))
    reviews.setdefault("incremental", True)
    cfg["reviews"] = reviews

    # notes 子命令（读书笔记/标注抓取）—— 输出固定为 Markdown（每本书一个 {书名}.md）
    notes = cfg.get("notes") or {}
    if not isinstance(notes, dict):
        notes = {}
    notes.setdefault("output_dir", notes.get("output") or cfg.get("notes_output"))
    notes.pop("output", None)
    notes.setdefault("incremental", True)
    notes.setdefault("max_pages", None)
    cfg["notes"] = notes

    # movies / games / music 子命令：状态过滤配置键统一为 statuses（兼容旧写法 types）
    for key in ("movies", "games", "music"):
        sec = cfg.get(key) or {}
        if not isinstance(sec, dict):
            sec = {}
        sec.setdefault("output_dir", sec.get("output") or cfg.get(f"{key}_output"))
        sec.pop("output", None)
        sec.setdefault("incremental", True)
        sec.setdefault("limit", cfg.get("limit"))
        raw_statuses = sec.get("statuses", sec.get("types"))
        valid = {"collect", "wish", "do"}
        if isinstance(raw_statuses, (list, tuple)):
            parsed = [s for s in raw_statuses if s in valid]
        elif isinstance(raw_statuses, str):
            parsed = [s.strip() for s in raw_statuses.split(",") if s.strip() in valid]
        else:
            parsed = []
        sec["statuses"] = parsed or ["collect", "wish", "do"]
        sec.pop("types", None)
        cfg[key] = sec

    return cfg


def _clean_html_text(s):
    """清理 HTML 片段为纯文本。"""
    s = re.sub(r"<style.*?</style>", "", s, flags=re.DOTALL)
    s = re.sub(r"<script.*?</script>", "", s, flags=re.DOTALL)
    s = re.sub(r"<[^>]+>", "", s)
    s = html.unescape(s)
    return re.sub(r"\s+", " ", s).strip()
