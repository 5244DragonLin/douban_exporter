# douban_exporter：豆瓣数据导出工具

基于 Python 标准库 + BeautifulSoup + Cookie 的豆瓣个人数据导出工具：自动化抓取读书记录、读书笔记、观影/游戏/音乐记录与书评全文，支持增量去重，导出 Markdown / HTML / JSON。

## 💡为什么需要这个工具？

- 豆瓣没有批量导出功能，手动复制粘贴每篇书评、逐页翻看书单、逐条摘录笔记，费时费力
- 担心账号被封或丢失、文章被下架，需要本地备份作为个人知识库
- 想回顾自己的阅读/观影史（年度趋势、评分分布、作者/导演排行），豆瓣不提供统计能力

**douban_exporter 解决这些问题**：统一用「标准库 + BeautifulSoup 解析 + Cookie」轻量抓取，自动遍历分页、完整保留富文本排版，增量模式只抓新增内容，无需浏览器、无需登录态持久化即可批量导出，并生成单文件 HTML 统计报告。

## ⭐亮点

- **多领域一站式**：读书记录、读书笔记、观影/游戏/音乐记录、书评全文、统计报告，一个工具全覆盖
- **统一增量索引**：所有子命令基于 `.douban_<类型>_index.json` 索引去重，首次自动从数据文件反推已抓 ID，第二次起仅抓新增
- **列表接口一次拿全**：Rexxar 接口单页即返回作者/出版社/评分/导演/演员等详情字段，无需逐条二次请求
- **书评富文本保留**：标题/引用/加粗/链接/图片结构完整导出为 Markdown 与 HTML，相邻引用块自动合并
- **读书笔记双通道**：自动适配独立笔记页与话题两条数据通道，长笔记自动补全，按书聚合输出 Markdown
- **统计报告**：`stats` 子命令读取本地 JSON 生成单文件 HTML 报告（趋势/评分分布/多维度排行/想读想看清单）
- **轻量零浏览器**：纯标准库 + BeautifulSoup，无需 Playwright、无需登录态持久化
- **测试友好**：`--limit` 强制输出到 `test_output/` 不污染正式数据，`--no-delay`、`--max-pages` 便于调试

## 📊能力矩阵

| 数据类型 | 全量同步 | 增量同步 | 输出格式 | 需登录/Cookie |
|---------|:---:|:---:|---------|:---:|
| 读书记录 | ✅ | ✅ | JSON | 可选（匿名可抓） |
| 观影记录 | ✅ | ✅ | JSON | 可选（匿名可抓） |
| 游戏记录 | ✅ | ✅ | JSON | 可选（匿名可抓） |
| 音乐记录 | ✅ | ✅ | JSON | 可选（匿名可抓） |
| 读书笔记 | ✅ | ✅ | Markdown | 可选（匿名可抓） |
| 书评全文 | ✅ | ✅ | Markdown, HTML | **建议必填**（匿名易折叠/截断） |
| 统计报告 | — | — | HTML | 否（读本地数据） |

## 🖥️效果预览

导出观影记录：

```text
$ python cli.py movies
============================================================
 影视  | 模式: full  |  状态: 看过 / 想看 / 在看
 输出: douban_movies_output
============================================================

  看过:
「看过」: 100%|████████████| 709/709 [01:12<00:00, 9.8条/s]
  已生成 douban_movies_collect.json（709 条）
```

导出的 JSON 单条记录（详情字段由列表接口一次返回）：

```json
{
  "interest_id": "4884305011",
  "status": "done",
  "douban_id": "37311135",
  "title": "飞驰人生3",
  "url": "https://movie.douban.com/subject/37311135/",
  "year": "2026",
  "douban_rating": "7.1",
  "rating": 4,
  "date": "2026-07-09",
  "comment": "……",
  "genres": ["剧情", "喜剧", "运动"],
  "directors": ["韩寒"],
  "actors": ["沈腾", "尹正", "黄景瑜"],
  "pubdate": "2026-02-17(中国大陆)",
  "country": "中国大陆"
}
```

读书笔记输出为每本书一个 Markdown 文件：

```markdown
# 书名

> 作者：xxx | 出版社：xxx | 评分：8.0/10（5518人评价）

---

## 第12页

摘录正文……
```

## 🚀快速开始

### 1. 克隆项目

```bash
# Gitee 镜像（国内访问快）
git clone https://gitee.com/yhl5244/douban_exporter.git

# GitHub 原仓库
git clone https://github.com/5244DragonLin/douban_exporter.git

cd douban_exporter
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 配置文件

工具可纯命令行运行，也可用 YAML 集中配置。复制示例并按需修改：

```bash
cp config.example.yaml config.yaml
# 编辑 config.yaml：填写 user.id，按需开启 features 下的功能开关
```

Cookie 等敏感信息请放在 `config.yaml`（已被 `.gitignore` 忽略）或 `cookie.txt`，**切勿提交到仓库**。字段说明见下方「配置文件」章节。

### 4. 运行

```bash
# 无参运行：自动加载同目录 config.yaml，按 features 启用项依次执行
python cli.py

# 指定子命令运行（不受 features 限制，始终可运行）
python cli.py movies                 # 导出观影记录（看过/想看/在看）
python cli.py books                  # 导出读书记录（已读/想读/在读）
python cli.py notes                  # 抓取读书笔记（标注/划线摘录）
python cli.py reviews --limit 3      # 只抓前 3 篇书评测试
python cli.py stats                  # 生成本地数据统计报告
```

## ⌨️CLI 模式

本工具是**单命令多子命令**结构，第一参数决定使用哪个功能：

```text
python cli.py <子命令> [参数]
```

| 子命令 | 功能 | 依赖 |
|--------|------|------|
| （无参 / `-c`） | 按 `config.yaml` 的 `features` 自动执行所有启用的功能（顺序：books → reviews → notes → movies → games → music） | 依启用的功能而定 |
| `books` | 读书记录导出（已读/想读/在读） | 纯标准库，无需登录 |
| `reviews` | 书评全文抓取（标题/评分/日期/全文） | 需 Cookie（登录态） |
| `notes` | 读书笔记导出（标注/划线摘录） | 纯标准库 + Cookie |
| `movies` | 观影记录导出（看过/想看/在看） | 纯标准库 + Cookie |
| `games` | 游戏记录导出（玩过/想玩/在玩） | 纯标准库 + Cookie |
| `music` | 音乐记录导出（听过/想听/在听） | 纯标准库 + Cookie |
| `stats` | 读书 + 观影统计报告（单文件 HTML） | 无网络依赖 |

> **统一增量索引**：所有抓取类子命令的增量去重统一基于各自输出目录下的隐藏索引文件 `.douban_<类型>_index.json`（记录已抓条目 ID）。首次增量若索引不存在、但已有历史数据文件，会自动从数据文件反推已抓 ID，避免整页重抓；之后去重只看索引。
>
> **⚠️ 首次增量 = 全量**：若索引文件和数据文件均不存在（即从未抓取过），首次增量模式**不会跳过任何条目**，行为等同于全量——它会抓取所有内容并建立索引。第二次起才会真正增量去重，仅抓取新增内容。

### 读书记录子命令（books）

抓取豆瓣个人已读/想读/在读列表，走 Rexxar API，只需提供豆瓣用户 ID。

```bash
# 全量抓取（已读 + 想读 + 在读）
python cli.py books --user YOUR_ID

# 指定输出目录（按分类分文件：douban_books_collect / _wish / _do）
python cli.py books -u YOUR_ID -o D:\Books

# 只抓已读（collect）/ 想读（wish）/ 在读（do）
python cli.py books -u YOUR_ID -t collect
python cli.py books -u YOUR_ID -t wish -t do

# 增量模式
python cli.py books -u YOUR_ID -m incremental

# 带登录 Cookie 抓取（可获取个人标签，匿名抓取标签列为空）
python cli.py books -u YOUR_ID --cookie "dbcl2=xxx; ck=xxx; bid=xxx"
# 或从文件读取 Cookie（本仓库约定用 cookie.txt）
python cli.py books -u YOUR_ID --cookie-file cookie.txt
# 或设置环境变量 DOUBAN_COOKIE
set DOUBAN_COOKIE=dbcl2=xxx; ck=xxx; bid=xxx
```

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `-u, --user` | 豆瓣用户 ID | 配置 `user.id`（无则交互输入） |
| `-o, --output` | 输出**目录**（文件名固定 `douban_books_{分类}.json`） | `~`（家目录） |
| `-m, --mode` | `full` 全量 / `incremental` 增量 | `full`（配置 `books.incremental: true` 可默认增量） |
| `-f, --format` | `json`（固定） | — |
| `-t, --type` | 指定分类 `collect`(已读) / `wish`(想读) / `do`(在读)，可多次指定；也可配置 `books.types` | 全部 |
| `-l, --limit` | 每分类抓取条数上限（测试用，输出到 `test_output/`） | 不限制 |
| `--max-pages` | 每分类最大页数（测试用） | `100`（页数保护） |
| `--no-delay` | 禁用翻页间随机延迟（仅测试） | `false` |
| `--cookie` | 豆瓣登录 Cookie 字符串 | 无 |
| `--cookie-file` | 从文件读取 Cookie | 无 |

输出 JSON 每条包含 11 个字段：书名、阅读日期、状态、标签、作者、译者、出版社、出版日期、我的评分、我的评论、豆瓣链接。

### 书评子命令（reviews）

抓取个人全部书评（标题/评分/日期/全文），标准库 + BeautifulSoup + Cookie，输出 Markdown / HTML。

```bash
# 抓取全部书评（输出 md + html 到 douban_reviews_output/）
python cli.py reviews

# 只抓 3 篇测试
python cli.py reviews --limit 3

# 只输出 Markdown，指定输出目录
python cli.py reviews -u YOUR_ID -f md -o D:\Reviews

# 增量模式：跳过已抓取的书评，只抓新写的（基于 .douban_reviews_index.json 索引）
python cli.py reviews -m incremental
```

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `-u, --user` | 豆瓣用户 ID | 配置或交互输入 |
| `-o, --output` | 输出目录 | `douban_reviews_output/` |
| `-c, --config` | YAML 配置文件（默认自动加载同目录 `config.yaml`） | 同目录 `config.yaml` |
| `-l, --limit` | 限制抓取篇数（测试用） | 全部 |
| `-f, --format` | `md` / `html` / `both` | `both` |
| `-m, --mode` | `full` 全量 / `incremental` 增量 | `full`（或 config `reviews.incremental`） |
| `--cookie` | 豆瓣登录 Cookie 字符串 | 配置/环境变量 |
| `--cookie-file` | 从文件读取 Cookie | 无 |

输出目录结构：

```text
douban_reviews_output/
├── md/    # 《书名》 - 书评标题.md
└── html/  # 《书名》 - 书评标题.html
```

### 读书笔记子命令（notes）

抓取个人全部读书笔记（标注/划线摘录：章节、摘要、正文），输出为 Markdown（每本书一个 `{书名}.md`）。

> **技术说明**：豆瓣笔记存在两条数据通道：① 独立笔记页通道（`/annotation/{9位ID}`）——通过 Rexxar 接口获取完整正文与书籍元数据（含副标题/评分/评价人数）；② 话题通道（`/topic/{id}`）——从网页版书级页「我对《XX》的笔记(N)」抓取章节/正文/时间，长笔记自动访问话题页补全完整正文。列表页按书聚合、保持豆瓣页面顺序。

```bash
# 抓取全部读书笔记（输出 Markdown 到配置目录）
python cli.py notes

# 指定用户 ID 与输出目录
python cli.py notes -u YOUR_ID -o D:\Notes

# 增量模式（已抓笔记 ID 去重，仅追加新笔记到对应书文件）
python cli.py notes -u YOUR_ID -m incremental

# 限制抓取条数（测试用，自动输出到 test_output/ 子目录）
python cli.py notes -u YOUR_ID -l 10

# 限制列表翻页数（测试用）
python cli.py notes -u YOUR_ID --max-pages 3
```

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `-u, --user` | 豆瓣用户 ID | 配置 `user.id` 或交互输入 |
| `-o, --output` | 输出目录 | 配置 `notes.output` 或 `~/` |
| `-m, --mode` | `full` 全量 / `incremental` 增量 | `full`（配置 `notes.incremental: true` 可默认增量） |
| `-l, --limit` | 限制抓取笔记条数（测试用，强制全量并输出到 `test_output/`） | 全部 |
| `--max-pages` | 笔记列表最大翻页数（测试用） | 不限制 |
| `--cookie` | 豆瓣登录 Cookie 字符串 | 配置/环境变量 |
| `--cookie-file` | 从文件读取 Cookie | 无 |

输出结构（每本书一个 Markdown 文件）：

```text
笔记输出目录/
├── 书名A.md
├── 书名B.md
└── .douban_notes_index.json   # 隐藏增量索引（记录已抓笔记 ID，不计入笔记内容）
```

> 笔记字段：书名、章节、正文、创建时间、笔记链接；书籍元数据：作者、副标题、出版社、出版年、评分、页数。

### 观影记录子命令（movies）

导出个人观影记录（看过/想看/在看），每个状态只输出一个 JSON 文件：`douban_movies_collect.json` / `douban_movies_wish.json` / `douban_movies_do.json`。

> **三种状态**：`collect`=看过、`wish`=想看、`do`=在看。默认三种全抓；可用 `--status` 或配置 `movies.statuses` 限定。
> **注意**：豆瓣新版接口已无 `wish` 状态，「想看」实际记录为 `mark`（标记），程序已让 `wish` 直接映射 `mark`，无需手动配置。

```bash
# 导出全部三种状态（看过/想看/在看）
python cli.py movies

# 只抓「看过」
python cli.py movies -u YOUR_ID -s collect

# 同时抓「想看」和「在看」
python cli.py movies -u YOUR_ID -s wish,do

# 指定输出根目录
python cli.py movies -u YOUR_ID -o D:\Movies

# 增量模式（基于 .douban_movies_index.json 索引去重）
python cli.py movies -u YOUR_ID -m incremental

# 限制每状态抓取条数（测试用）
python cli.py movies -u YOUR_ID -l 10
```

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `-u, --user` | 豆瓣用户 ID | 配置 `user.id` |
| `-o, --output` | 输出根目录 | 配置 `movies.output` 或 `./douban_movies_output` |
| `-s, --status` | 抓取状态 `collect`/`wish`/`do`，可逗号分隔 | 配置 `movies.statuses`（默认三种全抓） |
| `-l, --limit` | 限制每状态抓取条数（测试用） | 配置 `movies.limit`（默认不限制） |
| `-m, --mode` | `full` 全量 / `incremental` 增量 | `full`（配置 `movies.incremental: true` 可默认增量） |
| `--cookie` | 豆瓣登录 Cookie 字符串 | 配置/环境变量 |
| `--cookie-file` | 从文件读取 Cookie | 无 |

### 游戏记录子命令（games）

导出个人游戏记录（玩过/想玩/在玩），每个状态只输出一个 JSON 文件：`douban_games_collect.json` / `douban_games_wish.json` / `douban_games_do.json`。

> **三种状态**：`collect`=玩过、`wish`=想玩、`do`=在玩。默认三种全抓；可用 `--status` 或配置 `games.statuses` 限定。
> **注意**：豆瓣新版接口已无 `wish` 状态，「想玩」实际记录为 `mark`（标记），程序已让 `wish` 直接映射 `mark`。

```bash
# 导出全部三种状态（玩过/想玩/在玩）
python cli.py games

# 只抓「玩过」
python cli.py games -u YOUR_ID -s collect

# 增量模式（基于 .douban_games_index.json 索引去重）
python cli.py games -u YOUR_ID -m incremental

# 限制每状态抓取条数（测试用）
python cli.py games -u YOUR_ID -l 10
```

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `-u, --user` | 豆瓣用户 ID | 配置 `user.id` |
| `-o, --output` | 输出根目录 | 配置 `games.output` 或 `./douban_games_output` |
| `-s, --status` | 抓取状态 `collect`/`wish`/`do`，可逗号分隔 | 配置 `games.statuses`（默认三种全抓） |
| `-l, --limit` | 限制每状态抓取条数（测试用） | 配置 `games.limit`（默认不限制） |
| `-m, --mode` | `full` 全量 / `incremental` 增量 | `full`（配置 `games.incremental: true` 可默认增量） |
| `--cookie` | 豆瓣登录 Cookie 字符串 | 配置/环境变量 |
| `--cookie-file` | 从文件读取 Cookie | 无 |

### 音乐记录子命令（music）

导出个人音乐记录（听过/想听/在听），每个状态只输出一个 JSON 文件：`douban_music_collect.json` / `douban_music_wish.json` / `douban_music_do.json`。

> **三种状态**：`collect`=听过、`wish`=想听、`do`=在听。默认三种全抓；可用 `--status` 或配置 `music.statuses` 限定。
> **注意**：豆瓣新版接口已无 `wish` 状态，「想听」实际记录为 `mark`（标记），程序已让 `wish` 直接映射 `mark`。

```bash
# 导出全部三种状态（听过/想听/在听）
python cli.py music

# 只抓「听过」
python cli.py music -u YOUR_ID -s collect

# 增量模式（基于 .douban_music_index.json 索引去重）
python cli.py music -u YOUR_ID -m incremental

# 限制每状态抓取条数（测试用）
python cli.py music -u YOUR_ID -l 10
```

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `-u, --user` | 豆瓣用户 ID | 配置 `user.id` |
| `-o, --output` | 输出根目录 | 配置 `music.output` 或 `./douban_music_output` |
| `-s, --status` | 抓取状态 `collect`/`wish`/`do`，可逗号分隔 | 配置 `music.statuses`（默认三种全抓） |
| `-l, --limit` | 限制每状态抓取条数（测试用） | 配置 `music.limit`（默认不限制） |
| `-m, --mode` | `full` 全量 / `incremental` 增量 | `full`（配置 `music.incremental: true` 可默认增量） |
| `--cookie` | 豆瓣登录 Cookie 字符串 | 配置/环境变量 |
| `--cookie-file` | 从文件读取 Cookie | 无 |

> **limit 测试说明**（movies / games / music 通用）：设置 `limit` 时强制全量模式（忽略 `incremental`），且输出写入 `test_output/` 子目录，**不会覆盖/污染正式数据文件**。测试完删除 `test_output/` 即可。

### 统计报告子命令（stats）

读取本地读书/观影 JSON，生成单文件 HTML 统计报告（概览卡、年度趋势条形图、评分分布、作者/出版社/导演/演员/类型/地区排行、想读想看清单），无需网络。

```bash
# 使用 config.yaml 的 books.output / movies.output 定位数据（未指定 -c 自动加载同目录 config.yaml）
python cli.py stats

# 指定报告输出目录
python cli.py stats -o D:\Report
```

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `-o, --output` | 报告输出目录 | 配置 `stats.output`，或读书记录目录的上一级 |
| `-c, --config` | YAML 配置文件（默认自动加载同目录 `config.yaml`） | 同目录 `config.yaml` |

## 📄配置文件

未指定 `-c/--config` 时，程序自动加载脚本同目录的 `config.yaml`（不存在则按命令行参数 / 空配置运行）。配置按功能分层，只需填写你需要的部分：

```yaml
features:                  # 功能开关（置顶）：true=启用，false=禁止
  books: true
  reviews: false
  notes: true
  movies: true
  games: true
  music: true
user:
  id: "YOUR_ID"            # 豆瓣用户 ID（唯一必填）
  # cookie_file: "cookie.txt"   # Cookie 也可放文件，与 cookie 二选一
reviews:
  output: "douban_reviews_output"
  format: "both"           # md / html / both
books:
  output: "douban_books_output"
  incremental: true
notes:
  output: "douban_notes_output"
  incremental: true
movies:
  output: "douban_movies_output"
  incremental: true
  # statuses: collect,wish,do    # 抓取状态（默认三种全抓）
games:
  output: "douban_games_output"
  incremental: true
  # statuses: collect,wish,do
music:
  output: "douban_music_output"
  incremental: true
  # statuses: collect,wish,do
```

> **配置加载顺序**：内置默认值 → `config.example.yaml` → `config.yaml` → 命令行参数（后者优先）。
> 命令行显式子命令（`books`/`reviews`/`notes`/`movies`/`games`/`music`/`stats`）不受 `features` 限制，始终可运行；无参运行时按 `features` 启用的功能依次执行。
>
> **功能开关**：`features` 段位于配置最上方，控制各功能（books / reviews / notes / movies / games / music）是否启用；下方各功能段的配置项始终保留（不注释），是否生效由 `features` 决定。未配置 `features` 时默认全部启用（兼容旧配置）。
>
> 旧版扁平键（`user_id` / `cookie` / `books_output` 等）仍兼容，分层结构优先。

## 📁项目结构

```text
douban_exporter/
├── cli.py                         # 命令行入口：python cli.py <子命令> [参数]
├── douban_exporter/              # 源码包
│   ├── __init__.py               # 聚合子命令 + main() / 按 features 自动路由
│   ├── __main__.py               # 支持 python -m douban_exporter <子命令>
│   ├── core.py                   # 共享库：HTTP 请求、HTML→Markdown、增量索引、配置加载
│   ├── interests.py              # books/movies/games/music 共用的 Rexxar 导出管线（分页/增量/索引/checkpoint）
│   ├── books.py                  # 读书记录（已读/想读/在读）
│   ├── reviews.py                # 书评（Markdown / HTML 输出）
│   ├── notes.py                  # 读书笔记（标注 / 划线摘录）
│   ├── movies.py                 # 观影记录（看过/想看/在看）
│   ├── games.py                  # 游戏记录（玩过/想玩/在玩）
│   ├── music.py                  # 音乐记录（听过/想听/在听）
│   └── stats.py                  # 统计报告（读书 + 观影，单文件 HTML）
├── config.example.yaml           # 示例配置文件
├── cookie_file.example.txt       # 示例 Cookie 文件（参照此格式填入自己的 Cookie）
├── requirements.txt
├── LICENSE
├── README.md
├── .gitignore
└── assets/
    ├── donate_alipay.jpg
    └── donate_wechat.jpg
```

输出目录结构（各子命令输出文件；目录均可通过 `-o/--output` 或对应 `*.output` 配置自定义）：

```text
douban_reviews_output/          # reviews 书评
├── md/
│   ├── 《百年孤独》 - 书评标题.md
│   └── 《活着》 - 书评标题.md
└── html/
    └── 《活着》 - 书评标题.html   # 使用 --format html/both 时

douban_books_output/            # books 读书记录，每状态一个文件
├── douban_books_collect.json   # 已读
├── douban_books_wish.json      # 想读
└── douban_books_do.json        # 在读

douban_notes_output/            # notes 读书笔记，每本书一个文件
├── 《三体》.md
├── 《活着》.md
└── .douban_notes_index.json    # 隐藏增量索引

douban_movies_output/           # movies 观影记录
├── douban_movies_collect.json  # 看过
├── douban_movies_wish.json     # 想看
└── douban_movies_do.json       # 在看

douban_games_output/            # games 游戏记录（文件命名同上，douban_games_*.json）

douban_music_output/            # music 音乐记录（文件命名同上，douban_music_*.json）
```

> 用户私有文件 `config.yaml`、`cookie.txt` 含登录凭证，已通过 `.gitignore` 忽略，不会进入仓库；实际使用时自行创建即可（参照 `config.example.yaml` 与 `cookie_file.example.txt` 两个模板）。

## ❓️FAQ

**如何只更新最近新写的书评？**

使用 `reviews` 子命令的增量模式：`python cli.py reviews -m incremental`。程序基于输出目录下的 `.douban_reviews_index.json` 索引跳过已生成的书评，只抓取新写的；`--limit` 同样可用于限制篇数。

**输出的格式是什么？**

通过 `-f` / `--format` 参数选择：`md`（Markdown）、`html`（富文本 HTML，保留原始排版）、`both`（同时输出 md+html）。每篇书评一个文件，文件名格式为 `《书名》 - 书评标题.后缀`；读书记录与观影等记录类导出固定为 JSON，读书笔记固定为 Markdown。

**如何配置抓取参数？**

支持 YAML 配置文件：未指定 `-c` / `--config` 时自动加载脚本同目录的 `config.yaml`（不存在则全部用命令行参数）。参考 `config.example.yaml`，命令行参数优先级高于配置文件。配置按功能分层，各状态的抓取范围用 `movies.statuses` / `games.statuses` / `music.statuses` 配置，读书记录的分类用 `books.types` 配置。

**首次增量为什么抓了全部内容？**

若索引文件和数据文件均不存在（从未抓取过），首次增量等同于全量——先抓全并建立索引，第二次起才真正增量去重。若已有历史数据文件但索引丢失，程序会自动从数据文件反推已抓 ID，不会整页重抓。

**抓取会被限流或封号吗？**

所有请求带随机延迟模拟人类行为，失败自动重试；建议保持默认延迟，不要用 `--no-delay` 做大批量抓取。本工具仅供备份个人数据，请控制抓取频率。

## 📝已知问题 / 待改进点

- [x] movies/games/music 配置文件的状态过滤（`statuses`）已生效，并兼容旧写法 `types`
- [x] books 子命令的 `--no-delay`、`--max-pages` 参数已生效
- [x] 增量模式下新抓数据覆盖旧记录，评分/短评更新不再丢失
- [x] stats 子命令未指定 `-c` 时自动加载同目录 `config.yaml`
- [ ] 抓取影评：新增 `movie_reviews` 子命令，抓取影视条目下的用户影评，复用 `reviews` 的解析与格式保留管线
- [ ] 抓取乐评：新增 `music_reviews` 子命令，同上管线
- [ ] 抓取游戏评：新增 `game_reviews` 子命令，同上管线

## 🤝贡献

欢迎提 Issue 和 PR！

Fork → 创建分支 → 提交改动 → 发起 Pull Request。

## 📋更新日志

### v0.2.1
- **修复：** movies / games / music 配置文件的状态过滤（`statuses`）此前不生效，现已统一并兼容旧写法 `types`
- **修复：** books 子命令 `--no-delay`、`--max-pages` 参数此前无效，现已生效
- **修复：** 增量模式下已有条目的评分/短评更新不再被旧数据覆盖（新抓数据优先）
- **修复：** stats 子命令未指定 `-c` 时自动加载同目录 `config.yaml`
- **优化：** Rexxar 接口翻页步进与 `count=50` 对齐，消除约 60% 的重复请求；增量索引改为启动时一次读盘
- **优化：** books / movies / games / music 合并为共用管线 `interests.py`，清理约 400 行死代码；TLS 证书校验恢复默认开启

### v0.2
- **新增：** 数据统计报告——新增 `stats` 子命令，读取本地读书/观影 JSON 生成单文件 HTML 统计报告（概览卡、年度趋势条形图、评分分布、作者/出版社/导演/演员/类型/地区排行、想读想看清单）

### v0.1.1
- **修复：** 书评「引用」多段合并错误——同一引用块内的多段引文合并为一个引用块（Markdown 连续 `>` 行 / HTML 单个 `blockquote`），不再被拆成多个独立引用；引用块之间保持独立，不会被误合并成一个

### v0.1

- 首个可用版本：豆瓣数据导出工具，支持 6 个子命令——读书记录（`books`，已读/想读/在读）、读书笔记（`notes`，标注/划线摘录）、观影记录（`movies`，看过/想看/在看）、游戏记录（`games`，玩过/想玩/在玩）、音乐记录（`music`，听过/想听/在听）、书评全文（`reviews`，标题/评分/日期/全文）。

## ☕捐赠

你的支持是我坚持开源的动力。

| 支付宝 | 微信 |
|--------|------|
| ![支付宝](./assets/donate_alipay.jpg) | ![微信](./assets/donate_wechat.jpg) |

## ⚠️免责声明

本工具仅供学习交流使用，不得用于任何违反法律法规或侵犯第三方权益的用途。
因使用本工具产生的一切后果由使用者自行承担，作者不承担任何法律责任。

## 📃许可证

本项目基于 [MIT](LICENSE) 协议开源。
