# douban_exporter

豆瓣数据导出工具：自动化抓取豆瓣读书书评、读书记录（已读/想读/在读）、读书笔记（标注/划线摘录）、观影记录（看过/想看/在看）、游戏记录（玩过/想玩/在玩）、音乐记录（听过/想听/在听），并支持导出为 Markdown / HTML / JSON。

## 为什么需要这个工具？

- 豆瓣没有批量导出功能，手动复制粘贴每篇书评、逐页翻看已读书单、逐条摘录读书笔记，费时费力
- 担心账号被封或丢失、文章被下架，需要本地备份作为个人知识库

**douban_exporter 解决这些问题**：书评、读书记录 / 读书笔记 / 观影记录 / 游戏 / 音乐均统一用「标准库 + BeautifulSoup 解析 + Cookie」轻量抓取，自动遍历分页、完整保留富文本排版为 Markdown 或 HTML，无需浏览器、无需登录态持久化即可批量导出。

## ⭐亮点

- **`books` 读书记录导出（已读/想读/在读）**：纯标准库 + Cookie 实现，支持 `collect`(已读)/`wish`(想读)/`do`(在读) 三种状态；每个状态输出 `douban_books_{status}.json`，列表接口一次返回作者/出版社/出版年/评分等详情字，翻页用 tqdm 进度条显示实时进度，支持全量与翻页增量两种模式，支持增量去重。
- **`notes` 读书笔记导出（标注/划线摘录）**：纯标准库 + Cookie 实现，按书聚合导出全部读书笔记，并自动提取作者、副标题、出版社、出版年、评分、页数等书籍元数据，输出为 Markdown，支持增量去重。
- **`movies` 观影记录导出（看过/想看/在看）**：纯标准库 + Cookie 实现，支持 `collect`(看过)/`wish`(想看)/`do`(在看) 三种状态；每个状态输出 `douban_movies_{status}.json`，列表接口一次返回类型/导演/演员/评分/年份/上映日期/国家等详情字段，支持增量去重。
- **`games` 游戏记录导出（玩过/想玩/在玩）**：纯标准库 + Cookie 实现，支持 `collect`(玩过)/`wish`(想玩)/`do`(在玩) 三种状态；每个状态输出 `douban_games_{status}.json`，包含平台/类型/评分等字段，支持增量去重。
- **`music` 音乐记录导出（听过/想听/在听）**：纯标准库 + Cookie 实现，支持 `collect`(听过)/`wish`(想听)/`do`(在听) 三种状态；每个状态输出 `douban_music_{status}.json`，包含歌手/类型/评分等字段，支持增量去重。

## 📊能力矩阵

| 数据类型 | 全量同步 | 增量同步 | 输出格式 | 需登录/Cookie |
|---------|:---:|:---:|---------|:---:|
| 读书记录 | ✅ | ✅ | JSON | 可选（匿名可抓） |
| 观影记录 | ✅ | ✅ | JSON | 可选（匿名可抓） |
| 游戏记录 | ✅ | ✅ | JSON | 可选（匿名可抓） |
| 音乐记录 | ✅ | ✅ | JSON | 可选（匿名可抓） |
| 读书笔记 | ✅ | ✅ | Markdown | 可选（匿名可抓） |
| 书评全文 | ✅ | ✅ | Markdown, HTML | **建议必填**（匿名易折叠/截断） |

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

### 3. 配置文件（可选）

工具可纯命令行运行，也可用 YAML 集中配置。复制示例并按需修改：

```bash
cp config.example.yaml config.yaml
# 编辑 config.yaml：填写 user.id，按需开启 features 下的功能开关
```

Cookie 等敏感信息请放在 `config.yaml`（已被 `.gitignore` 忽略）或 `cookie.txt`，**切勿提交到仓库**。配置字段说明见下方「配置文件（可选）」章节。

### 4. 运行

```bash
# 无参运行：自动加载同目录 config.yaml，按 features 启用项依次执行（books→reviews→notes→movies→games→music）
python cli.py

# 显式子命令（不受 features 限制，始终可运行）
python cli.py reviews -c config.yaml

# 只抓前 3 篇测试
python cli.py reviews --limit 3

# 指定用户 ID 与输出目录
python cli.py reviews -u YOUR_ID -o D:\MyReviews

# 使用配置文件运行：按 config.yaml 的 features 配置自动执行所有启用的功能（书评/读书记录/笔记/观影记录）
python cli.py -c config.yaml
# 无参运行时自动加载同目录 config.yaml，按 features 配置执行
python cli.py

# 抓取读书笔记（标注/划线摘录）：纯标准库 + Cookie，输出为 Markdown（每本书一个 {书名}.md）
python cli.py notes

# 指定用户 ID 与输出目录
python cli.py notes -u YOUR_ID -o D:\Notes

# 导出观影记录（看过/想看/在看）：纯标准库，无需 Playwright
python cli.py movies

# 只抓「看过」，指定输出目录（详情字段由列表接口一次返回，无需 -e）
python cli.py movies -u YOUR_ID -s collect -o D:\Movies
```

## ⚙️配置文件（可选）

未指定 `-c/--config` 时，程序自动加载脚本同目录的 `config.yaml`（不存在则按命令行参数 / 空配置运行）。配置文件按功能分层，只需填写你需要的部分：

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
games:
  output: "douban_games_output"
  incremental: true
music:
  output: "douban_music_output"
  incremental: true
```

> **配置加载顺序**：内置默认值 → `config.example.yaml` → `config.yaml` → 命令行参数（后者优先）。
> 命令行显式子命令（`books`/`reviews`/`notes`/`movies`/`games`/`music`）不受 `features` 限制，始终可运行；无参运行时按 `features` 启用的功能依次执行。完整字段见 `config.example.yaml`，常见问题见 FAQ。

## ⌨️CLI 模式

本工具是**单命令多子命令**结构，第一参数决定使用哪个功能：

```
python cli.py <子命令> [参数]
```

| 子命令 | 功能 | 依赖 |
|--------|------|------|
| （无参 / `-c`） | 不指定子命令时，按 `config.yaml` 的 `features` 自动执行所有启用的功能（顺序：books → reviews → notes → movies → games → music） | 依启用的功能而定 |
| `reviews` | 书评全文抓取（标准库 + BeautifulSoup + Cookie） | 需 Cookie（登录态） |
| `books` | 读书记录导出（已读/想读/在读） | 纯标准库，无需登录 |
| `notes` | 读书笔记导出（标注/划线摘录） | 纯标准库 + Cookie |
| `movies` | 观影记录导出（看过/想看/在看） | 纯标准库 + Cookie |
| `games` | 游戏记录导出（玩过/想玩/在玩） | 纯标准库 + Cookie |
| `music` | 音乐记录导出（听过/想听/在听） | 纯标准库 + Cookie |

> **统一增量索引**：所有子命令（books / reviews / notes / movies / games / music）的增量去重统一基于各自输出目录下的隐藏索引文件 `.douban_<类型>_index.json`（记录已抓条目 ID）。首次增量若索引不存在、但已有历史数据文件，会自动从数据文件反推已抓 ID，避免整页重抓；之后去重只看索引。各数据文件（如 `douban_movies_collect.json`）仍照常保留，并合并为完整交付物。
>
> **⚠️ 首次增量 = 全量**：若索引文件和数据文件均不存在（即从未抓取过），首次增量模式**不会跳过任何条目**，行为等同于全量——它会抓取所有内容并建立索引。第二次起才会真正增量去重，仅抓取新增内容。

---

### 读书记录子命令（books）

抓取豆瓣个人已读/想读/在读列表，**纯标准库实现，无需登录**（Rexxar API），只需提供豆瓣用户 ID。

```bash
# 全量抓取（已读 + 想读 + 在读）
python cli.py books --user YOUR_ID

# 指定输出目录和格式（按分类分文件：douban_books_collect / _wish / _do，扩展名由 -f 决定）
python cli.py books -u YOUR_ID -o D:\Books
python cli.py books -u YOUR_ID -o D:\Books -f json
python cli.py books -u YOUR_ID -f json   # 输出到默认目录 ~/douban_books_collect.json 等

# 使用 YAML 配置文件（推荐：可配置 cookie / books_output / user_id）
python cli.py books -c config.yaml

# 只抓已读（collect）/ 想读（wish）/ 在读（do）
python cli.py books -u YOUR_ID -t collect
python cli.py books -u YOUR_ID -t wish -t do

# 带登录 Cookie 抓取（可获取个人标签，匿名抓取标签列为空）
python cli.py books -u YOUR_ID --cookie "dbcl2=xxx; ck=xxx; bid=xxx"
# 或从文件读取 Cookie（文件内容即 Cookie 字符串，参考 cookie_file.example.txt，本仓库约定用 cookie.txt）
python cli.py books -u YOUR_ID --cookie-file cookie.txt
# 或设置环境变量 DOUBAN_COOKIE
set DOUBAN_COOKIE=dbcl2=xxx; ck=xxx; bid=xxx

python cli.py books -u YOUR_ID -m incremental
```

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `-u, --user` | 豆瓣用户 ID | 配置 `user.id`（无则交互输入） |
| `-o, --output` | 输出**目录**（按分类命名 `douban_books_collect`/`douban_books_wish`/`douban_books_do`，扩展名由 `-f` 决定） | `~`（家目录） |
| `-m, --mode` | `full` 全量 / `incremental` 翻页增量 | `full`（配置 `books.incremental: true` 可默认增量） |
| `-f, --format` | `json`（固定） | — |
| `-t, --type` | 指定分类 `collect`(已读) / `wish`(想读) / `do`(在读)，可多次指定；也可在 config.yaml 的 `books.types` 中配置 | 全部（config `books.types` 优先于默认；都不指定则抓全部） |
| `--max-pages` | 每分类最大页数（测试用） | 不限制 |
| `--cookie` | 豆瓣登录 Cookie 字符串 | 无 |
| `--cookie-file` | 从文件读取 Cookie | 无 |

> **推荐用 YAML 配置**：在 `config.yaml` 中按分层结构填写 `user.id`、`books.output`、`books.format` 等字段后，直接 `python cli.py books` 即可（未指定 `-c` 时自动加载脚本同目录 `config.yaml`，标签以中文逗号「，」分隔）。命令行参数优先于配置文件。

输出 JSON 每条包含 11 个字段：书名、阅读日期、状态、标签、作者、出版社、出版日期、我的评分、我的评论、豆瓣链接、豆瓣ID。

### 书评子命令（reviews）

抓取个人全部书评（标题/评分/日期/全文），**标准库 + BeautifulSoup 解析 + Cookie 实现，无需 Playwright**，输出 Markdown / HTML。

```bash
# 抓取全部书评（输出 md + html 到 douban_reviews_output/；未指定 -c 自动加载同目录 config.yaml）
python cli.py reviews

# 只抓 2 篇测试
python cli.py reviews --limit 2

# 只输出 Markdown，指定输出目录
python cli.py reviews -u YOUR_ID -f md -o D:\Reviews

# 增量模式：跳过已抓取的书评，只抓新写的（基于 .douban_reviews_index.json 索引）
python cli.py reviews -m incremental
```

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `-u, --user` | 豆瓣用户 ID | 配置或交互输入 |
| `-o, --output` | 输出目录 | `douban_reviews_output/` |
| `-c, --config` | YAML 配置文件（默认自动加载脚本同目录 `config.yaml`，不存在则空配置） | 同目录 `config.yaml` |
| `-l, --limit` | 限制抓取篇数（测试用） | 全部 |
| `-f, --format` | `md` / `html` / `both` | `both` |
| `-m, --mode` | `full`（全量）/ `incremental`（增量，跳过已抓取书评） | `full`（或 config `reviews.incremental`） |
| `--cookie` | 豆瓣登录 Cookie 字符串 | 配置/环境变量 |

输出目录结构：
```
douban_reviews_output/
├── md/    # 《书名》书评标题.md
└── html/  # 《书名》书评标题.html
```

### 读书笔记子命令（notes）

抓取个人全部读书笔记（标注/划线摘录：章节、摘要、正文），**纯标准库 + Cookie 实现，无需 Playwright**，输出为 Markdown（每本书一个 `{书名}.md`，遵循《书籍阅读笔记撰写指南》）。

> **技术说明**：豆瓣笔记存在两条数据通道：① 独立笔记页通道（`/annotation/{9位ID}`）——通过 Rexxar 接口获取完整正文与书籍元数据（含副标题/评分/评价人数）；② 话题通道（`/topic/{id}`）——从网页版书级页「我对《XX》的笔记(N)」抓取章节/正文/时间，长笔记自动访问话题页补全完整正文。列表页按书聚合、保持豆瓣页面顺序。

```bash
# 抓取全部读书笔记（输出 Markdown 到配置目录；未指定 -c 自动加载同目录 config.yaml）
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

```
笔记输出目录/
├── 书名A.md
├── 书名B.md
└── .douban_notes_index.json   # 隐藏增量索引（记录已抓笔记 ID，不计入笔记内容）
```

> 笔记字段：书名、章节、正文、创建时间、笔记链接；书籍元数据：作者、副标题、出版社、出版年、评分、页数。独立笔记页通道由接口返回精确评分与评价人数（如 `8.0/10（5518人评价）`）；话题通道由书级页星级换算（如 `8.0/10`）。

### 观影记录子命令（movies）

导出个人观影记录（看过/想看/在看），**纯标准库 + Cookie 实现，无需 Playwright**，每个状态**只输出一个 JSON 文件**到 `output/` 目录：`douban_movies_collect.json` / `douban_movies_wish.json` / `douban_movies_do.json`（与书籍导出的 `douban_books_*.json` 命名风格一致）。

> **三种状态**：`collect`=看过、`wish`=想看、`do`=在看。默认三种全抓；可用 `--status` 或配置 `movies.statuses` 限定。
> **注意**：豆瓣新版接口已无 `wish` 状态，「想看」实际记录为 `mark`（标记），程序已让 `wish` 直接映射 `mark`，无需手动配置。
> **详情字段**：列表接口一次返回类型/导演/演员/评分/年份/上映日期/国家（`genres/directors/actors/douban_rating/year/pubdate/country`），无需逐部抓取；翻页用 tqdm 进度条显示实时进度。

```bash
# 导出全部三种状态（看过/想看/在看）
python cli.py movies

# 只抓「看过」
python cli.py movies -u YOUR_ID -s collect

# 同时抓「想看」和「在看」
python cli.py movies -u YOUR_ID -s wish,do

# 指定输出根目录
python cli.py movies -u YOUR_ID -o D:\Movies

# 增量模式（基于 .douban_movies_index.json 索引去重，不重复抓取）
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

> **limit 测试说明**：设置 `limit` 时强制全量模式（忽略 `incremental`），且输出写入 `test_output/` 子目录，**不会覆盖/污染正式数据文件**——正式文件始终保留给增量去重使用。测试完删除 `test_output/` 即可。

输出结构（每个状态一个 JSON 文件，直接铺在输出根目录）：

```
观影输出根目录/
├── douban_movies_collect.json    # 看过（供增量与后续分析复用）
├── douban_movies_wish.json       # 想看（豆瓣新版 mark 状态）
└── douban_movies_do.json         # 在看（若存在）
```



### 游戏记录子命令（games）

导出个人游戏记录（玩过/想玩/在玩），**纯标准库 + Cookie 实现，无需 Playwright**，每个状态**只输出一个 JSON 文件**到 `output/` 目录：`douban_games_collect.json` / `douban_games_wish.json` / `douban_games_do.json`。

> **三种状态**：`collect`=玩过、`wish`=想玩、`do`=在玩。默认三种全抓；可用 `--status` 或配置 `games.statuses` 限定。
> **注意**：豆瓣新版接口已无 `wish` 状态，「想玩」实际记录为 `mark`（标记），程序已让 `wish` 直接映射 `mark`，无需手动配置。
> **详情字段**：列表接口一次返回平台/类型/评分等字段，无需逐部抓取；翻页用 tqdm 进度条显示实时进度。

```bash
# 导出全部三种状态（玩过/想玩/在玩）
python cli.py games

# 只抓「玩过」
python cli.py games -u YOUR_ID -s collect

# 同时抓「想玩」和「在玩」
python cli.py games -u YOUR_ID -s wish,do

# 指定输出根目录
python cli.py games -u YOUR_ID -o D:\Games

# 增量模式（基于 .douban_games_index.json 索引去重，不重复抓取）
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

> **limit 测试说明**：设置 `limit` 时强制全量模式（忽略 `incremental`），且输出写入 `test_output/` 子目录，**不会覆盖/污染正式数据文件**——正式文件始终保留给增量去重使用。测试完删除 `test_output/` 即可。

输出结构（每个状态一个 JSON 文件，直接铺在输出根目录）：

```
游戏输出根目录/
├── douban_games_collect.json    # 玩过（供增量与后续分析复用）
├── douban_games_wish.json       # 想玩（豆瓣新版 mark 状态）
└── douban_games_do.json         # 在玩（若存在）
```

### 音乐记录子命令（music）

导出个人音乐记录（听过/想听/在听），**纯标准库 + Cookie 实现，无需 Playwright**，每个状态**只输出一个 JSON 文件**到 `output/` 目录：`douban_music_collect.json` / `douban_music_wish.json` / `douban_music_do.json`。

> **三种状态**：`collect`=听过、`wish`=想听、`do`=在听。默认三种全抓；可用 `--status` 或配置 `music.statuses` 限定。
> **注意**：豆瓣新版接口已无 `wish` 状态，「想听」实际记录为 `mark`（标记），程序已让 `wish` 直接映射 `mark`，无需手动配置。
> **详情字段**：列表接口一次返回歌手/类型/评分等字段，无需逐部抓取；翻页用 tqdm 进度条显示实时进度。

```bash
# 导出全部三种状态（听过/想听/在听）
python cli.py music

# 只抓「听过」
python cli.py music -u YOUR_ID -s collect

# 同时抓「想听」和「在听」
python cli.py music -u YOUR_ID -s wish,do

# 指定输出根目录
python cli.py music -u YOUR_ID -o D:\Music

# 增量模式（基于 .douban_music_index.json 索引去重，不重复抓取）
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

> **limit 测试说明**：设置 `limit` 时强制全量模式（忽略 `incremental`），且输出写入 `test_output/` 子目录，**不会覆盖/污染正式数据文件**——正式文件始终保留给增量去重使用。测试完删除 `test_output/` 即可。

输出结构（每个状态一个 JSON 文件，直接铺在输出根目录）：

```
音乐输出根目录/
├── douban_music_collect.json    # 听过（供增量与后续分析复用）
├── douban_music_wish.json       # 想听（豆瓣新版 mark 状态）
└── douban_music_do.json         # 在听（若存在）
```

## 📂项目结构

```
douban_exporter/
├── cli.py                         # 命令行入口：python cli.py <子命令> [参数]
├── douban_exporter/              # 源码包（douban_exporter 模块）
│   ├── __init__.py               # 聚合 6 个子命令 + main() / 按 features 自动路由
│   ├── __main__.py               # 支持 python -m douban_exporter <子命令>
│   ├── core.py                   # 共享库：HTTP 请求、HTML→Markdown、增量索引、配置加载
│   ├── books.py                  # 读书记录（已读/想读/在读）
│   ├── reviews.py                # 书评（Markdown / HTML 输出）
│   ├── notes.py                  # 读书笔记（标注 / 划线摘录）
│   ├── movies.py                 # 观影记录（看过/想看/在看）
│   ├── games.py                  # 游戏记录（玩过/想玩/在玩）
│   └── music.py                  # 音乐记录（听过/想听/在听）
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

> 说明：用户私有文件 `config.yaml`、`cookie.txt` 含登录凭证，已通过 `.gitignore` 忽略，不会进入仓库；实际使用时自行创建即可（参照上方两个 `.example` 模板）。

源码按职责拆分为 `douban_exporter/` 包，`cli.py` 仅为入口：

- **`core.py`（共享库）**：HTTP 请求与 Cookie、HTML→Markdown 转换、增量索引（`.douban_<类型>_index.json`）、配置文件加载与归一化、各子命令共用的工具函数
- **各子命令模块**：`books.py` / `reviews.py` / `notes.py` / `movies.py` / `games.py` / `music.py` 各自实现对应抓取逻辑与命令行参数
- **书评（reviews 子命令）**：标准库 + BeautifulSoup 解析 + Cookie 抓取全部书评（标题/评分/日期/全文），支持 md/html/both
- **读书记录（books 子命令）**：纯标准库抓取已读/想读/在读，含翻页增量
- **读书笔记（notes 子命令）**：纯标准库 + Cookie 按书聚合抓取标注/划线摘录，自动适配独立笔记页 / 话题两条数据通道，含书籍元数据提取与增量去重
- **观影记录（movies 子命令）**：纯标准库 + Cookie 导出看过/想看/在看，列表接口一次返回详情字段
- **游戏记录（games 子命令）**：纯标准库 + Cookie 导出玩过/想玩/在玩，列表接口一次返回平台/类型/评分等字段
- **音乐记录（music 子命令）**：纯标准库 + Cookie 导出听过/想听/在听，列表接口一次返回歌手/类型/评分等字段

输出目录结构（各子命令输出文件；目录均可通过 `-o/--output` 或对应 `*.output` 配置自定义）：

```
douban_reviews_output/          # reviews 书评（默认，由 -o 控制）
├── md/
│   ├── 《百年孤独》 - 书评标题.md
│   └── 《活着》 - 书评标题.md
├── html/
│   └── 《活着》 - 书评标题.html   (使用 --format html/both 时)

# books 读书记录：输出到 books.output 指定目录（默认家目录 ~），每状态一个文件
douban_books_collect.json       # 已读
douban_books_wish.json          # 想读
douban_books_do.json            # 在读

# notes 读书笔记：输出到 notes.output 指定目录（默认由配置决定），每本书一个文件
《三体》.md
《活着》.md

douban_movies_output/           # movies 观影记录（默认，由 movies.output 控制）
├── douban_movies_collect.json  # 看过
├── douban_movies_wish.json     # 想看
└── douban_movies_do.json       # 在看

douban_games_output/            # games 游戏记录（默认，由 games.output 控制）
├── douban_games_collect.json   # 玩过
├── douban_games_wish.json      # 想玩
└── douban_games_do.json        # 在玩

douban_music_output/            # music 音乐记录（默认，由 music.output 控制）
├── douban_music_collect.json   # 听过
├── douban_music_wish.json      # 想听
└── douban_music_do.json        # 在听
```

## ❓️FAQ

**如何只更新最近新写的书评？**

使用 `reviews` 子命令的增量模式：`python cli.py reviews -m incremental`。程序基于输出目录下的 `.douban_reviews_index.json` 索引（记录已抓书评的 review id）跳过已生成的书评，只抓取新写的；`--limit` 同样可用于限制篇数。

**输出的格式是什么？**

通过 `-f` / `--format` 参数选择：`md`（Markdown）、`html`（富文本 HTML，保留原始排版）、`both`（同时输出 md+html）。每篇书评一个文件，文件名格式为 `《书名》 - 书评标题.后缀`。

**如何配置抓取参数？**

支持 YAML 配置文件：未指定 `-c` / `--config` 时自动加载脚本同目录的 `config.yaml`（若存在；不存在则相当于空配置，全部用命令行参数）。参考 `config.example.yaml`，也可以全部用命令行参数。命令行参数优先级高于配置文件。配置按功能分层：

```yaml
features:                  # 功能开关（置顶）：true=启用，false=禁止
  books: true              # 读书记录抓取（已读/想读/在读）
  reviews: true            # 书评抓取（reviews 子命令，纯标准库 + Cookie）
  notes: true              # 读书笔记（标注）抓取（notes 子命令）
  movies: true             # 观影记录导出（看过/想看/在看）
user:
  id: "132021081"          # 豆瓣用户 ID（唯一必填）
  cookie: "..."            # 登录 Cookie（books / reviews / notes / movies 共用）
reviews:
  output: "douban_reviews_output"   # 书评输出目录
  format: "both"                    # md / html / both
books:
  output: "C:/Users/11609"        # 已读/想读/在读输出目录（按分类命名 douban_books_collect/_wish/_do，扩展名由 format 决定）
  format: "json"                    # 固定 json
notes:
  output: "C:/Users/11609"        # 读书笔记输出目录（按书名生成 {书名}.md）
  incremental: true                 # 默认增量模式：基于 .douban_notes_index.json 索引去重追加
movies:
  output: "C:/Users/11609/douban_movies"   # 观影输出根目录（每个状态输出 douban_movies_{status}.json 到该目录）
  enrich: false                              # 是否抓取影片详情做统计
  incremental: false                         # 增量模式：基于 .douban_movies_index.json 索引去重
  # statuses: collect,wish,do                 # 抓取状态（默认三种全抓）
```

> **功能开关**：`features` 段位于配置最上方，控制各功能（books / reviews / notes / movies / games / music）是否启用。下方各功能段的配置项始终保留（不注释），是否生效由 `features` 决定。
> - **纯无参运行** `python cli.py` 时，自动按 `features` 中启用的功能**依次全部执行**（顺序：books → reviews → notes → movies → games → music），不交互询问；全部禁用则提示你在 config.yaml 中至少启用一个。
> - **命令行优先**：显式指定子命令（`books` / `reviews` / `notes` / `movies` / `games` / `music`）不受 features 限制，始终可运行——你明确说要跑哪个就跑哪个。
> - 未配置 `features` 时默认全部启用（兼容旧配置）。

> 旧版扁平键（`user_id` / `cookie` / `books_output` 等）仍兼容，分层结构优先。

## 🤝贡献

欢迎提 Issue 和 PR！

Fork → 创建分支 → 提交改动 → 发起 Pull Request。

## 🧭下一步计划

- [ ] **抓取影评**：新增 `movie_reviews` 子命令，抓取豆瓣影视条目下的用户影评（标题/评分/日期/全文），复用 `reviews` 的 `_extract_review_content` + `html_to_markdown` 格式保留管线，输出 Markdown / HTML。
- [ ] **抓取乐评**：新增 `music_reviews` 子命令，抓取豆瓣音乐条目下的乐评，同上管线。
- [ ] **抓取游戏评**：新增 `game_reviews` 子命令，抓取豆瓣游戏条目下的游戏评，同上管线。

## 📋更新日志

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

[MIT](LICENSE)

