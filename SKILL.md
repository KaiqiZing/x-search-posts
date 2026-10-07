---
name: x-search-posts
description: 抓取 X（Twitter）上指定关键字、指定时间范围内点赞数达标的高赞推文，并输出带中文摘要的结构化报告。三个自定义参数为关键字、时间范围、点赞下限（默认 1000）；另内置 7 组 AI 主题固定关键词（Agentic AI、MCP、LLM Evals、Prompt Engineering、Context Engineering、Agent Skill、Vibe Coding），用 --preset 一键巡检。当用户提到「X / 推特 / Twitter 上点赞超过 N 的推文」「推特高赞帖子」「最近一周某话题在 X 上的爆款」「抓取推特舆情」「X 热门讨论汇总」「固定关键词巡检」「拉一下 prompt engineering / MCP / vibe coding 的推文」「min_faves 检索」等需求时使用本技能。
agent_created: true
---

# X 高赞推文抓取（x-search-posts）

## 用途

按「关键字 + 时间范围 + 点赞下限」三个参数，从 X（Twitter）取回热度达标的推文，输出**单文件 HTML 报告**（默认，视觉系统参考 Blue Professional 模板：cream 纸底 + 钴蓝单强调）与结构化 JSON。也支持用 `--preset` 一键巡检**内置的 7 组 AI 主题固定关键词**。

X 原生高级搜索已支持所需运算符，本技能把三个参数一一映射过去，无需用户记忆语法：

| 用户参数 | 映射为                                 | 默认值    |
| ---- | ----------------------------------- | ------ |
| 关键字  | 原样进入查询串                             | 必填（或用 `--preset`） |
| 时间范围 | `since:YYYY-MM-DD until:YYYY-MM-DD` | 最近 7 天 |
| 点赞数  | `min_faves:N`                       | 1000   |

## 何时使用

用户提出以下任一诉求时启用：

- 该话题在 X 上点赞过千的推文有哪些 / 帮我看下推特上最火的几条
- 某时间窗内某关键字的高赞内容汇总、舆情速览、爆款分析
- 指定点赞阈值（如 500、2000、10000）筛选推文
- 按**内置固定关键词**（Prompt Engineering、MCP、Agentic AI 等 7 组）做周期性巡检汇总
- 需要 **原始推文链接 + 点赞数** 作为可核查依据的内容调研

不适用：用户只想要 X 的使用教程、只想搜普通网页内容、或需要发推 / 互动等写操作。

## 执行流程

### 第 1 步：确认三个参数

从用户话语中提取；**缺失的用默认值并在报告中声明**，不要反复追问：

- 关键字：两种给法，**二选一**：
  - 直接给关键字（原样透传 `--keyword`）；
  - 使用内置固定关键词（见下方「内置固定关键词」）：用户说「固定关键词 / 常规巡检 / 把那几个主题都拉一遍」→ `--preset all`；点名主题（如「拉一下 prompt engineering 的爆款」）→ 对应 preset 键。
  - 完全没提且不属巡检场景 → 先问一句。
- 时间：`2026-09-01 ~ 2026-09-30`、`最近一周`（→ `--since 7d`）、`上个月`（→ `--since 30d`）。完全没提 → 默认最近 7 天。
- 点赞：`点赞超过 1000`→`--min-likes 1000`；`点赞 500 以上`→`500`；没提 → 默认 1000。

把时间换算成绝对日期后写进命令，避免「上周」这类相对表述在报告中失真。

### 第 2 步：运行检索

```bash
python scripts/x_search.py --keyword "<关键字>" --since <起> --until <止> --min-likes <N>
```

`scripts/x_search.py` 会自动：构造检索式 → 选择后端取数 → 去重 → **按点赞阈值与时间窗二次校验** → 按点赞降序 → 写出 `.md` 与 `.json`。

常用参数：

| 参数                                      | 说明                                          |
| --------------------------------------- | ------------------------------------------- |
| `--keyword` / `-k`                      | 自定义关键字，支持 X 运算符原样透传；与 `--preset` 二选一   |
| `--preset`                              | 内置固定关键词：`all` 全部 / preset 键或逗号分隔多个键 / `list` 查看 |
| `--since` / `--until`                   | `YYYY-MM-DD`，或 `7d` / `2w` / `3m` / `today` |
| `--min-likes`                           | 点赞下限，默认 1000                                |
| `--lang zh`                             | 语言过滤                                        |
| `--tab top\|latest\|media`              | 搜索排序，默认 `top`（最热）                           |
| `--exclude-replies`                     | 额外排除回复（默认已排除）                               |
| `--include-retweets`                    | 保留转推（默认排除）                                  |
| `--extra "filter:links"`                | 追加原始运算符                                     |
| `--backend auto\|api\|browser\|offline` | 取数后端，默认 `auto`                              |
| `--from-json <file>`                    | 离线加工已有数据                                    |
| `--top 30`                              | 报告正文展示条数，默认 20                              |
| `--format html\|md\|both`               | 报告产物格式，默认 `html`（单文件 HTML）；`md` 为旧版 Markdown，`both` 两者都出 |
| `--out <dir>`                           | 输出目录，默认当前目录                                 |

输出文件名：`x_hot_<关键字或preset键>_<时间戳>.html` / `.json`（`--format md|both` 时另有 `.md`）。

## 内置固定关键词（--preset）

技能内置 7 组 AI 主题固定关键词，定义在 `scripts/x_search.py` 顶部的 `PRESET_KEYWORDS` 常量，**增删改直接编辑该表即可**：

| preset 键 | 覆盖主题 | 检索式 |
| --- | --- | --- |
| `agentic-ai` | Agentic AI / AI Agent | `agentic AI OR "AI agent" OR "AI agents"` |
| `mcp` | MCP（Model Context Protocol） | `MCP OR "Model Context Protocol"` |
| `llm-evals` | LLM Evals / Post-deploy Evaluation | `"LLM eval" OR "LLM evals" OR "LLM evaluation" OR "post-deploy evaluation"` |
| `prompt-engineering` | Prompt Engineering | `"prompt engineering"` |
| `context-engineering` | Context Engineering | `"context engineering"` |
| `agent-skill` | Agent Skill | `"agent skill" OR "agent skills" OR agentskill` |
| `vibe-coding` | Vibe Coding / AI Coding Agent | `"vibe coding" OR "AI coding agent" OR "AI coding agents"` |

用法：

```bash
# 一键拉全部 7 组（每组各出一份 .md/.json，最后一行输出 batch 汇总 JSON）
python scripts/x_search.py --preset all --since 7d --min-likes 1000

# 只拉指定的几组
python scripts/x_search.py --preset prompt-engineering,context-engineering --since 14d

# 查看内置清单（键名 / 主题 / 检索式）
python scripts/x_search.py --preset list
```

规则：

- `--preset` 与 `--keyword` **二选一**；时间、点赞阈值、后端等其余参数完全不变。
- `--preset all` 逐组串行抓取，**单组失败不影响其他组**；每组结果仍是一条独立 JSON（含 `html`/`markdown`/`json` 路径），多组时最后一行是 `{"batch": true, ...}` 汇总，解析时按行读取；输出文件名自动带 preset 键（如 `x_hot_prompt-engineering_20261007_090000.html`）。
- 注意事项：`--preset` + `--from-json` 离线模式不做关键字二次过滤（OR 检索式无法用单一子串校验），点赞阈值与时间窗过滤照常。

### 第 3 步：处理首次登录（browser 后端）

默认走浏览器后端。若返回 `NOT_LOGGED_IN`，说明 X 登录态尚未建立。两种触发方式，任选其一：

```bash
# 方式一：命令行（--timeout 0 = 无限等待，适合交给用户慢慢登录；不加则默认等 300 秒）
node scripts/browser_collect.js --login --timeout 0

# 方式二：把 scripts/login.bat 的路径给用户，让其双击运行（Windows 更省事）
```

用后台方式启动，然后**明确告知用户**：会在屏幕上弹出浏览器窗口，请手动登录 X（含二次验证），登录成功后脚本自动保存会话并退出，之后无需重复登录。

- 用户可能在忙，不要因为窗口没被立刻操作就判定失败；等待期间可以先把关键字等其他准备工作谈定。
- 若窗口被用户关掉，脚本返回退出码 5 并提示重新运行 `--login`，不会抛异常。**不要反复自动弹窗打扰用户**——窗口被关掉后改为告知用户「方便时双击 `scripts/login.bat`」。
- 用户确认登录完成（或脚本输出「登录成功」）后再继续第 2 步。

### 第 4 步：补写中文摘要，产出最终 HTML

脚本直出的 HTML 中每条推文带「（待补中文摘要）」占位，**必须补写后交付**：

1. 读取输出的 `.json`，逐条消化正文（长推文会完整保留，不要只看片段）。
2. 写摘要映射文件 `summaries.json`：`{"<推文id>": "1~2 句中文摘要"}`——谁、说了什么、结论或数据是什么。
3. 写「整体观察」文本：本期最热的话题切口、有无同一事件刷屏、意见是否分裂。
4. 渲染终稿（单组升级、多组合并成周报，命令相同）：

```bash
# 单组：升级该组 HTML
python scripts/render_html.py --json x_hot_xxx.json --summaries summaries.json \
    --observation "整体观察…" --out 报告.html

# 多组合并（--preset all 后出周报，每组一个章节，自动带分组导览）
python scripts/render_html.py --json x_hot_a.json x_hot_b.json … \
    --summaries summaries.json --observation "整体观察…" \
    --title "X 高赞推文周报 <日期区间>" --out x_weekly_digest_<日期>.html
```

5. 用 `present_files` 展示最终 HTML（单文件自包含，链接可点击）。若同一事件被多人讨论，摘要在组内合并成「事件 → 代表推文」呈现，不要平铺 20 条。

HTML 视觉模板在 `templates/report.html`（参考 beautiful-html-templates / Blue Professional）。改样式直接编辑该文件；渲染逻辑在 `scripts/html_report.py`，CLI 入口是 `scripts/render_html.py`。

### 第 5 步：口径说明

- HTML 页脚已内置口径说明（UTC 边界、until 含当天、点赞近似值、只读采集），无需重复手写。
- 回复中仍需标注实际使用的后端与检索式，便于复现。

## 后端说明

取数有三条链路，加工逻辑完全一致（详见 `references/backends.md`）：

- **browser**（默认）：Playwright 复用登录态抓取 x.com 搜索页，免费、可查历史。优先捕获 `SearchTimeline` 接口拿精确点赞数，接口未捕获时回退 DOM 解析。
- **api**：官方 X API v2，需 `X_BEARER_TOKEN`，**仅覆盖最近 7 天**。
- **offline**：`--from-json` 加工已采集数据。零依赖兜底——可先用内置浏览器技能（`playwright-cli` / `agent-browser`）打开搜索页采集，再交给本技能过滤排序，保证不同批次口径一致。

## 参考文档

- `templates/report.html`——HTML 报告视觉模板（参考 beautiful-html-templates / Blue Professional：cream 纸底 + 钴蓝单强调 + tinted 卡片），改样式直接编辑。
- `references/x-search-operators.md`——X 高级搜索运算符全表、时间边界陷阱、可直接套用的检索模板。
- `references/backends.md`——后端选型对比、首次登录步骤、组件安装路径、故障排查表。

## 注意事项

- **只读操作**：本技能只读取公开推文数据，不点赞、不转推、不关注、不发送任何内容。
- **风控**：单次采集建议 ≤200 条（`--max-items`），避免用主账号做高频大批量抓取。
- **不编造**：点赞数、时间、链接全部来自实际抓取结果。字段缺失时（如 DOM 兜底时无转发数）如实标注为「—」，不要推测填充。
- **内置关键词维护**：检索式里 OR 必须**大写**（X 语法）；短语用英文双引号包裹。要增删固定关键词，直接编辑 `scripts/x_search.py` 顶部的 `PRESET_KEYWORDS` 表，CLI 与 `--preset list` 自动跟随。
- **关键字无结果时**，依次尝试：降低 `--min-likes`、放宽时间窗、改用 `--tab latest`、把长关键词拆成核心词。
