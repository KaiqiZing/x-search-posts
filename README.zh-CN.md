# x-search-posts

> 抓取 X（Twitter）上指定关键字、指定时间范围内点赞数达标的高赞推文，输出带中文摘要的单文件 HTML 报告。

[English](README.md) | **中文**

## 这是什么

把「关键字 + 时间范围 + 点赞下限」三个参数映射成 X 原生高级搜索语法，取回热度达标的推文，并渲染成一篇可直接阅读、可直接分享的 **单文件 HTML 报告**。

不需要记 X 的搜索运算符，也不需要官方 API 付费额度。

| 你的参数 | 映射为 | 默认值 |
| --- | --- | --- |
| 关键字 | 原样进入查询串 | 必填（或用 `--preset`） |
| 时间范围 | `since:YYYY-MM-DD until:YYYY-MM-DD` | 最近 7 天 |
| 点赞数 | `min_faves:N` | 1000 |

## 功能特性

- **三参数即用**：一句话给出关键字、时间、点赞下限即可出报告
- **7 组内置固定关键词**：Agentic AI、MCP、LLM Evals、Prompt Engineering、Context Engineering、Agent Skill、Vibe Coding，`--preset all` 一键全拉
- **单文件 HTML 报告**：内嵌样式、链接可点击、可离线打开、可直接分享（视觉系统为 Cream 纸底 + 钴蓝单强调的咨询报告风格，适配中文排版）
- **多组合并周报**：多组结果合并成一份带分组导览的周报，适合周期性巡检
- **三种取数后端**：浏览器抓取（默认，免费、可查历史）／官方 API（可选）／离线加工
- **二次校验**：抓回的数据按点赞阈值与时间窗再过滤一遍，避免后端返回超范围结果
- **只读安全**：只读取公开推文，不点赞、不转推、不关注、不发布任何内容

## 环境要求

- **Node.js 18+**（浏览器抓取后端需要，脚本会自动探测托管运行时 / 常见安装路径）
- **Python 3.8+**（主流程与渲染，无第三方依赖）
- **Playwright + Chromium**（浏览器后端需要，见下方安装）

## 安装

```bash
git clone https://github.com/KaiqiZing/x-search-posts.git
cd x-search-posts

# 安装浏览器抓取依赖（只需一次）
npm install playwright
npx playwright install chromium
```

## 快速开始

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

## 常用命令

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

## 补写中文摘要（可选）

脚本直出的 HTML 中，每条推文带「（待补中文摘要）」占位。把摘要写成 `summaries.json` 后重新渲染：

```bash
# summaries.json 格式：{"<推文id>": "中文摘要"}
python scripts/render_html.py --json x_hot_xxx.json --summaries summaries.json \
    --observation "整体观察段落…" --out 报告.html

# 多组合并成周报（每个 json 一个章节）
python scripts/render_html.py --json a.json b.json c.json \
    --summaries summaries.json --title "X 高赞推文周报" --out weekly.html
```

## 命令行参数

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

## 工作原理

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

## 目录结构

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

## 修改内置固定关键词

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

## 注意事项与合规

- **只读操作**：本工具只读取公开推文数据，不点赞、不转推、不关注、不发布任何内容。
- **风控提示**：建议单次采集 ≤200 条，避免使用主账号做高频大批量抓取。
- **不编造数据**：点赞数、时间、链接均来自实际抓取结果；字段缺失时如实标注为「—」。
- **搜索不等于全集**：未被索引或被限流的账号内容可能缺席；点赞数在界面展示超过约 1000 后为近似值。
- **时间边界**：按 UTC 统计，与本地时区可能相差一天；`until` 含当天（脚本已自动 +1 天）。
- **请遵守 X 的服务条款与所在地法律法规**，仅将本项目用于合法的内容研究与舆情分析用途。

## 隐私与凭证

- 仓库内**不含任何凭证**：登录态保存在用户本地 `~/.workbuddy/skill-data/` 下，不在项目目录内。
- 登录会话由 Playwright 持久化在本地 Chrome profile 中，**不会**被提交或外传。
- 官方 API 模式的 Token 通过环境变量 `X_BEARER_TOKEN` 读取，不写入代码。
- `.gitignore` 已排除 profile、报告产物等本地文件。

---

## 贡献者

感谢所有参与本项目的人。

<!-- ALL-CONTRIBUTORS-LIST:START - Do not remove or modify this section -->
<!-- prettier-ignore-start -->
<!-- markdownlint-disable -->
<table>
  <tbody>
    <tr>
      <td align="center" valign="top" width="14.28%"><a href="https://github.com/KaiqiZing"><img src="https://avatars.githubusercontent.com/u/50580359?v=4" width="100px;" alt="KQ Zing"/><br /><sub><b>KQ Zing</b></sub></a><br /><a href="https://github.com/KaiqiZing/x-search-posts/commits?author=KaiqiZing" title="Code">💻</a> <a href="#-project-ideation-KaiqiZing" title="Project ideation">🤔</a></td>
      <td align="center" valign="top" width="14.28%"><a href="https://www.workbuddy.cn"><img src=".github/assets/workbuddy-avatar.png" width="100px;" alt="WorkBuddy"/><br /><sub><b>WorkBuddy</b></sub></a><br /><a href="#-ai-assistance-WorkBuddy" title="AI assistance">🤖</a> <a href="https://github.com/KaiqiZing/x-search-posts/commits?author=WorkBuddy" title="Code">💻</a> <a href="#-documentation-WorkBuddy" title="Documentation">📖</a></td>
    </tr>
  </tbody>
</table>

<!-- markdownlint-restore -->
<!-- prettier-ignore-end -->

<!-- ALL-CONTRIBUTORS-LIST:END -->

### 关于贡献者

- **kq-zing** —— 项目构思、需求提出与验收。
- **WorkBuddy** —— AI 助手；与作者协作编写并打磨脚本、HTML 报告模板与文档。

图标含义遵循 [all-contributors](https://allcontributors.org/docs/en/emoji-key) 规范：💻 代码 · 🤔 创意 · 🤖 AI 协助 · 📖 文档。

---

## License

MIT
