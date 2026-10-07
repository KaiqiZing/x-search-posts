# x-search-posts

> Scrape high-engagement X (Twitter) posts by keyword + time window + like threshold, and render a self-contained HTML report.

**English** | [中文](README.zh-CN.md)

## What it is

Maps three parameters — **keyword + time window + minimum likes** — onto X's native advanced-search syntax, fetches the qualifying posts, and renders them into a **self-contained HTML report** you can open offline or share directly.

No need to memorise X search operators. No paid API quota required.

| Your parameter | Becomes | Default |
| --- | --- | --- |
| Keyword | passed through into the query | required (or use `--preset`) |
| Time window | `since:YYYY-MM-DD until:YYYY-MM-DD` | last 7 days |
| Min likes | `min_faves:N` | 1000 |

## Features

- **Three parameters, one command** — keyword, time range and like floor are all you need
- **7 built-in keyword presets** — Agentic AI, MCP, LLM Evals, Prompt Engineering, Context Engineering, Agent Skill, Vibe Coding; `--preset all` fetches every group
- **Single-file HTML report** — inline styles, clickable links, works offline, easy to share (consulting-report aesthetic: cream canvas + single cobalt accent, tuned for CJK typography)
- **Multi-group digest** — merge several groups into one report with a section index, ideal for recurring sweeps
- **Three data backends** — browser scraping (default; free, supports history) / official API (optional) / offline processing
- **Double validation** — results are re-filtered by like threshold and time window after fetching
- **Read-only by design** — only reads public posts; never likes, retweets, follows or publishes

## Requirements

- **Node.js 18+** (needed by the browser backend; the scripts auto-detect managed runtimes and common install paths)
- **Python 3.8+** (pipeline and rendering; no third-party dependencies)
- **Playwright + Chromium** (for the browser backend — see below)

## Install

```bash
git clone https://github.com/KaiqiZing/x-search-posts.git
cd x-search-posts

# Install browser-scraping dependencies (once)
npm install playwright
npx playwright install chromium
```

## Quick start

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

## Common commands

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

## Adding Chinese summaries (optional)

Posts in the generated HTML carry a “(summary pending)” placeholder. Write summaries to `summaries.json` and re-render:

```bash
# summaries.json: {"<tweet-id>": "摘要文本"}
python scripts/render_html.py --json x_hot_xxx.json --summaries summaries.json \
    --observation "Overview paragraph…" --out report.html

# Merge multiple groups into one digest (one section per JSON)
python scripts/render_html.py --json a.json b.json c.json \
    --summaries summaries.json --title "X Weekly Digest" --out weekly.html
```

## CLI reference

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

## How it works

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

## Project layout

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

## Customising the built-in presets

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

## Notes & compliance

- **Read-only**: this tool only reads public posts. It never likes, retweets, follows or publishes.
- **Rate limits**: keep single runs at ≤200 items and avoid hammering the platform with your main account.
- **No fabricated data**: likes, timestamps and links all come from actual fetches; missing fields are marked “—” rather than guessed.
- **Search is not exhaustive**: unindexed or rate-limited accounts may be absent; like counts are approximate above ~1000.
- **Time boundaries** follow UTC and may differ by a day from your local timezone; `until` is inclusive (the script adds one day automatically).
- **Please comply with X's Terms of Service and your local laws**; use this project only for lawful content research and sentiment analysis.

## Privacy & credentials

- **No credentials are committed**: the login session lives in your local `~/.workbuddy/skill-data/`, outside the project directory.
- The session is persisted by Playwright in a local Chrome profile and is **never** committed or transmitted.
- API mode reads its token from the `X_BEARER_TOKEN` environment variable — never hard-coded.
- `.gitignore` excludes the profile and generated reports.

---

## License

MIT
