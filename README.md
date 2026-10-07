# x-search-posts

> 抓取 X（Twitter）上指定关键字、指定时间范围内点赞数达标的高赞推文，输出带中文摘要的单文件 HTML 报告。
> Scrape high-engagement X (Twitter) posts by keyword + time window + like threshold, and render a self-contained HTML report.

[中文](#中文文档) · [English](#english-docs)

---

## 中文文档

### 这是什么

把「关键字 + 时间范围 + 点赞下限」三个参数映射成 X 原生高级搜索语法，取回热度达标的推文，并渲染成一篇可直接阅读、可直接分享的 **单文件 HTML 报告**。

不需要记 X 的搜索运算符，也不需要官方 API 付费额度。

| 你的参数 | 映射为 | 默认值 |
| --- | --- | --- |
| 关键字 | 原样进入查询串 | 必填（或用 `--preset`） |
| 时间范围 | `since:YYYY-MM-DD until:YYYY-MM-DD` | 最近 7 天 |
| 点赞数 | `min_faves:N` | 1000 |

### 功能特性

- **三参数即用**：一句话给出关键字、时间、点赞下限即可出报告
- **7 组内置固定关键词**：Agentic AI、MCP、LLM Evals、Prompt Engineering、Context Engineering、Agent Skill、Vibe Coding，`--preset all` 一键全拉
- **单文件 HTML 报告**：内嵌样式、链接可点击、可离线打开、可直接分享（视觉系统为 Cream 纸底 + 钴蓝单强调的咨询报告风格，适配中文排版）
- **多组合并周报**：多组结果合并成一份带分组导览的周报，适合周期性巡检
- **三种取数后端**：浏览器抓取（默认，免费、可查历史）／官方 API（可选）／离线加工
- **二次校验**：抓回的数据按点赞阈值与时间窗再过滤一遍，避免后端返回超范围结果
- **只读安全**：只读取公开推文，不点赞、不转推、不关注、不发布任何内容

### 环境要求

- **Node.js 18+**（浏览器抓取后端需要，脚本会自动探测托管运行时 / 常见安装路径）
- **Python 3.8+**（主流程与渲染，无第三方依赖）
- **Playwright + Chromium**（浏览器后端需要，见下方安装）

### 安装

```bash
git clone https://github.com/<your-name>/x-search-posts.git
cd x-search-posts

# 安装浏览器抓取依赖（只需一次）
npm install playwright
npx playwright install chromium
```

### 快速开始

```bash
# 1) 首次使用：登录 X（会弹出浏览器窗口，手动登录即可，含二次验证）
#    Windows 可直接双击 scripts/login.bat；其他平台：
node scripts/browser_collect.js --login

# 2) 采集 + 生成报告
python scripts/x_search.py --keyword "AI agent" --since 7d --min-likes 1000

# 3) 一键巡检全部 7 组内置关键词
python scripts/x_search.py --preset all --since 7d --min-likes 1000 --out ./reports
```

登录态保存在 `~/.workbuddy/skill-data/x-search-posts/chrome-profile`，**登录一次后长期有效**，无需重复登录。

### 常用命令

```bash
# 查看内置固定关键词清单
python scripts/x_search.py --preset list

# 只巡检指定几组
python scripts/x_search.py --preset prompt-engineering,context-engineering --since 14d

# 自定义关键字 + 时间窗 + 点赞阈值
python scripts/x_search.py --keyword "英伟达" --since 2026-09-01 --until 2026-09-30 --min-likes 2000

# 同时输出 HTML 与 Markdown
python scripts/x_search.py --keyword "MCP" --format both

# 环境自检（检查 Node / Playwright / 登录态）
python scripts/doctor.py
```

### 补写中文摘要（可选）

脚本直出的 HTML 中，每条推文带「（待补中文摘要）」占位。把摘要写成 `summaries.json` 后重新渲染：

```bash
# summaries.json 格式：{"<推文id>": "中文摘要"}
python scripts/render_html.py --json x_hot_xxx.json --summaries summaries.json \
    --observation "整体观察段落…" --out 报告.html

# 多组合并成周报（每个 json 一个章节）
python scripts/render_html.py --json a.json b.json c.json \
    --summaries summaries.json --title "X 高赞推文周报" --out weekly.html
```

### 命令行参数

| 参数 | 说明 |
| --- | --- |
| `--keyword` / `-k` | 自定义关键字，支持 X 运算符原样透传；与 `--preset` 二选一 |
| `--preset` | 内置固定关键词：`all` / 键名（逗号分隔多个）/ `list` 查看清单 |
| `--since` / `--until` | `YYYY-MM-DD`，或 `7d` / `2w` / `3m` / `today` |
| `--min-likes` | 点赞下限，默认 1000 |
| `--lang` | 语言过滤，如 `zh` / `en` |
| `--tab` | 搜索排序：`top`（默认）/ `latest` / `media` |
| `--format` | 报告格式：`html`（默认）/ `md` / `both` |
| `--backend` | 取数后端：`auto`（默认）/ `api` / `browser` / `offline` |
| `--from-json` | 离线加工已有 JSON 数据 |
| `--top` | 报告正文展示条数，默认 20 |
| `--out` | 输出目录，默认当前目录 |

### 工作原理

```
关键字/预设 ──► 构造 X 高级搜索检索式 ──► 选择后端取数
                                          ├─ browser：Playwright 复用登录态抓搜索页（默认）
                                          ├─ api    ：官方 X API v2（需 X_BEARER_TOKEN，仅近 7 天）
                                          └─ offline：读取已有 JSON
                       │
                       ▼
        去重 ──► 按点赞阈值/时间窗二次校验 ──► 按点赞降序
                       │
                       ▼
        report.html 模板 ──► 单文件 HTML 报告（+ 结构化 JSON）
```

### 目录结构

```
x-search-posts/
├── SKILL.md                     # WorkBuddy / Agent 技能定义（含执行流程）
├── README.md
├── references/
│   ├── x-search-operators.md    # X 高级搜索运算符参考
│   └── backends.md              # 后端选型与故障排查
├── scripts/
│   ├── x_search.py              # 主入口：采集 → 过滤 → 渲染
│   ├── xquery.py                # 检索式构造 / 归一化 / 过滤 / 排序
│   ├── browser_collect.js       # Playwright 采集（含登录流程）
│   ├── html_report.py           # HTML 渲染模块
│   ├── render_html.py           # HTML 渲染 CLI（支持多组合并）
│   ├── doctor.py                # 环境自检
│   └── login.bat                # Windows 一键登录
└── templates/
    └── report.html              # HTML 报告视觉模板
```

### 修改内置固定关键词

编辑 `scripts/x_search.py` 顶部的 `PRESET_KEYWORDS` 常量即可，CLI 与 `--preset list` 会自动跟随：

```python
PRESET_KEYWORDS = {
    "agentic-ai": {
        "label": "Agentic AI / AI Agent",
        "query": '(agentic AI OR "AI agent" OR "AI agents")',
    },
    # 增删条目即可
}
```

> 注意：X 搜索语法中 `OR` 必须大写；短语用英文双引号包裹。

### 注意事项与合规

- **只读操作**：本工具只读取公开推文数据，不点赞、不转推、不关注、不发布任何内容。
- **风控提示**：建议单次采集 ≤200 条，避免使用主账号做高频大批量抓取。
- **不编造数据**：点赞数、时间、链接均来自实际抓取结果；字段缺失时如实标注为「—」。
- **搜索不等于全集**：未被索引或被限流的账号内容可能缺席；点赞数在界面展示超过约 1000 后为近似值。
- **时间边界**：按 UTC 统计，与本地时区可能相差一天；`until` 含当天（脚本已自动 +1 天）。
- **请遵守 X 的服务条款与所在地法律法规**，仅将本项目用于合法的内容研究与舆情分析用途。

### 隐私与凭证

- 仓库内**不含任何凭证**：登录态保存在用户本地 `~/.workbuddy/skill-data/` 下，不在项目目录内。
- 登录会话由 Playwright 持久化在本地 Chrome profile 中，**不会**被提交或外传。
- 官方 API 模式的 Token 通过环境变量 `X_BEARER_TOKEN` 读取，不写入代码。
- `.gitignore` 已排除 profile、报告产物等本地文件。

---

## English Docs

### What it is

Maps three parameters — **keyword + time window + minimum likes** — onto X's native advanced-search syntax, fetches the qualifying posts, and renders them into a **self-contained HTML report** you can open offline or share directly.

No need to memorise X search operators. No paid API quota required.

| Your parameter | Becomes | Default |
| --- | --- | --- |
| Keyword | passed through into the query | required (or use `--preset`) |
| Time window | `since:YYYY-MM-DD until:YYYY-MM-DD` | last 7 days |
| Min likes | `min_faves:N` | 1000 |

### Features

- **Three parameters, one command** — keyword, time range and like floor are all you need
- **7 built-in keyword presets** — Agentic AI, MCP, LLM Evals, Prompt Engineering, Context Engineering, Agent Skill, Vibe Coding; `--preset all` fetches every group
- **Single-file HTML report** — inline styles, clickable links, works offline, easy to share (consulting-report aesthetic: cream canvas + single cobalt accent, tuned for CJK typography)
- **Multi-group digest** — merge several groups into one report with a section index, ideal for recurring sweeps
- **Three data backends** — browser scraping (default; free, supports history) / official API (optional) / offline processing
- **Double validation** — results are re-filtered by like threshold and time window after fetching
- **Read-only by design** — only reads public posts; never likes, retweets, follows or publishes

### Requirements

- **Node.js 18+** (needed by the browser backend; the scripts auto-detect managed runtimes and common install paths)
- **Python 3.8+** (pipeline and rendering; no third-party dependencies)
- **Playwright + Chromium** (for the browser backend — see below)

### Install

```bash
git clone https://github.com/<your-name>/x-search-posts.git
cd x-search-posts

# Install browser-scraping dependencies (once)
npm install playwright
npx playwright install chromium
```

### Quick start

```bash
# 1) First run: log in to X (a browser window opens; log in manually, 2FA supported)
#    On Windows you can simply double-click scripts/login.bat
node scripts/browser_collect.js --login

# 2) Fetch and render
python scripts/x_search.py --keyword "AI agent" --since 7d --min-likes 1000

# 3) Sweep all 7 built-in presets at once
python scripts/x_search.py --preset all --since 7d --min-likes 1000 --out ./reports
```

The session is stored in `~/.workbuddy/skill-data/x-search-posts/chrome-profile` — **log in once, stay logged in**.

### Common commands

```bash
# List built-in keyword presets
python scripts/x_search.py --preset list

# Sweep only selected groups
python scripts/x_search.py --preset prompt-engineering,context-engineering --since 14d

# Custom keyword + window + like floor
python scripts/x_search.py --keyword "NVIDIA" --since 2026-09-01 --until 2026-09-30 --min-likes 2000

# Emit both HTML and Markdown
python scripts/x_search.py --keyword "MCP" --format both

# Environment self-check (Node / Playwright / login state)
python scripts/doctor.py
```

### Adding Chinese summaries (optional)

Posts in the generated HTML carry a “(summary pending)” placeholder. Write summaries to `summaries.json` and re-render:

```bash
# summaries.json: {"<tweet-id>": "摘要文本"}
python scripts/render_html.py --json x_hot_xxx.json --summaries summaries.json \
    --observation "Overview paragraph…" --out report.html

# Merge multiple groups into one digest (one section per JSON)
python scripts/render_html.py --json a.json b.json c.json \
    --summaries summaries.json --title "X Weekly Digest" --out weekly.html
```

### CLI reference

| Flag | Description |
| --- | --- |
| `--keyword` / `-k` | Custom keyword; X advanced operators pass through. Mutually exclusive with `--preset` |
| `--preset` | Built-in presets: `all` / key names (comma-separated) / `list` |
| `--since` / `--until` | `YYYY-MM-DD`, or `7d` / `2w` / `3m` / `today` |
| `--min-likes` | Like floor, default 1000 |
| `--lang` | Language filter, e.g. `zh` / `en` |
| `--tab` | Sort: `top` (default) / `latest` / `media` |
| `--format` | Output: `html` (default) / `md` / `both` |
| `--backend` | Data backend: `auto` (default) / `api` / `browser` / `offline` |
| `--from-json` | Process existing JSON offline |
| `--top` | Rows shown in the report body, default 20 |
| `--out` | Output directory, default current dir |

### How it works

```
keyword/preset ──► build X advanced-search query ──► pick backend
                                                     ├─ browser: Playwright reuses your session (default)
                                                     ├─ api    : official X API v2 (needs X_BEARER_TOKEN, last 7 days only)
                                                     └─ offline: read an existing JSON
                       │
                       ▼
        dedupe ──► re-filter by like floor & time window ──► sort by likes desc
                       │
                       ▼
        report.html template ──► single-file HTML report (+ structured JSON)
```

### Project layout

```
x-search-posts/
├── SKILL.md                     # Agent skill definition (workflow included)
├── README.md
├── references/
│   ├── x-search-operators.md    # X advanced-search operator reference
│   └── backends.md              # Backend comparison & troubleshooting
├── scripts/
│   ├── x_search.py              # Main entry: fetch → filter → render
│   ├── xquery.py                # Query building / normalisation / filtering / ranking
│   ├── browser_collect.js       # Playwright collector (includes login flow)
│   ├── html_report.py           # HTML rendering module
│   ├── render_html.py           # HTML rendering CLI (multi-group merge)
│   ├── doctor.py                # Environment self-check
│   └── login.bat                # One-click login for Windows
└── templates/
    └── report.html              # HTML report template
```

### Customising the built-in presets

Edit the `PRESET_KEYWORDS` constant at the top of `scripts/x_search.py`; the CLI and `--preset list` follow automatically:

```python
PRESET_KEYWORDS = {
    "agentic-ai": {
        "label": "Agentic AI / AI Agent",
        "query": '(agentic AI OR "AI agent" OR "AI agents")',
    },
    # add or remove entries freely
}
```

> Note: `OR` must be uppercase in X search syntax; wrap phrases in double quotes.

### Notes & compliance

- **Read-only**: this tool only reads public posts. It never likes, retweets, follows or publishes.
- **Rate limits**: keep single runs at ≤200 items and avoid hammering the platform with your main account.
- **No fabricated data**: likes, timestamps and links all come from actual fetches; missing fields are marked “—” rather than guessed.
- **Search is not exhaustive**: unindexed or rate-limited accounts may be absent; like counts are approximate above ~1000.
- **Time boundaries** follow UTC and may differ by a day from your local timezone; `until` is inclusive (the script adds one day automatically).
- **Please comply with X's Terms of Service and your local laws**; use this project only for lawful content research and sentiment analysis.

### Privacy & credentials

- **No credentials are committed**: the login session lives in your local `~/.workbuddy/skill-data/`, outside the project directory.
- The session is persisted by Playwright in a local Chrome profile and is **never** committed or transmitted.
- API mode reads its token from the `X_BEARER_TOKEN` environment variable — never hard-coded.
- `.gitignore` excludes the profile and generated reports.

---

## License

MIT
