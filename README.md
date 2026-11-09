# x-search-posts

> Scrape high-engagement X (Twitter) posts by keyword + time window + like threshold, and render a self-contained HTML report.

**English** | [中文](README.zh-CN.md)

> **Personal, non-commercial use only — and that applies to the scraped data too.**
> This is **not** an open-source license. Neither this code nor anything it collects may be used
> commercially, redistributed, or published. Read [License](#license) before you clone.

## What it is

Maps three parameters — **keyword + time window + minimum likes** — onto X's native advanced-search syntax, fetches the qualifying posts, and renders them into a **self-contained HTML report** you can open offline, for your own reading.

No need to memorise X search operators. No paid API quota required.

| Your parameter | Becomes | Default |
| --- | --- | --- |
| Keyword | passed through into the query | required (or use `--preset`) |
| Time window | `since:YYYY-MM-DD until:YYYY-MM-DD` | last 7 days |
| Min likes | `min_faves:N` | 1000 |

## Features

- **Three parameters, one command** — keyword, time range and like floor are all you need
- **7 built-in keyword presets** — Agentic AI, MCP, LLM Evals, Prompt Engineering, Context Engineering, Agent Skill, Vibe Coding; `--preset all` fetches every group
- **Single-file HTML report** — inline styles, clickable links, works offline, one file to keep alongside your own notes (consulting-report aesthetic: cream canvas + single cobalt accent, tuned for CJK typography)
- **Built-in sidebar navigation** — fixed left rail with per-section counts, scroll-spy highlighting and a reading progress bar; collapses into a drawer on narrow screens, hidden when printing
- **Today's weather & greeting in the header** — fetched automatically via the key-free open-meteo API (location: explicit city → config → IP geolocation → local timezone fallback), with a blessing line; degrades gracefully to a plain date pill if the lookup fails
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
├── README.zh-CN.md
├── LICENSE                      # Non-commercial, personal-use-only (binding text)
├── LICENSE.zh-CN.md             # Chinese reference translation
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
- **Please comply with X's Terms of Service and your local laws**; use this project only for lawful personal content research and sentiment analysis. See [License](#license) — commercial use of **the code or the data** is prohibited.

## Privacy & credentials

- **No credentials are committed**: the login session lives in your local `~/.workbuddy/skill-data/`, outside the project directory.
- The session is persisted by Playwright in a local Chrome profile and is **never** committed or transmitted.
- API mode reads its token from the `X_BEARER_TOKEN` environment variable — never hard-coded.
- `.gitignore` excludes the profile and generated reports.

---

## Contributors

Thanks to everyone who has contributed to this project.

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

### About the contributors

- **kq-zing** — project ideation, requirements and review.
- **WorkBuddy** — AI assistant; wrote and refined the scripts, HTML report template and documentation in collaboration with the author.

Emoji legend follows the [all-contributors](https://allcontributors.org/docs/en/emoji-key) specification: 💻 code · 🤔 ideas · 🤖 AI assistance · 📖 documentation.

---

## License

**Non-commercial, personal use only.** This is a custom proprietary license, not an open-source one.
Publishing this repository publicly grants you permission to *read* the code — nothing more. See
[LICENSE](LICENSE) for the binding text (English controls), or
[LICENSE.zh-CN.md](LICENSE.zh-CN.md) for the Chinese reference translation.

Three rules, and none of them have exceptions:

| # | Rule | What it forbids |
| --- | --- | --- |
| **1** | **The code may not be used commercially** | Selling, licensing, renting, sublicensing or SaaS-ifying this project; embedding it in a paid product; using it in billable consulting, research or advisory work; using it for the business operations of any for-profit entity |
| **2** | **The data may not be used commercially** | Selling or licensing collected posts; bulk republishing or compiling them into a distributed dataset; using them to train or evaluate a commercial model; feeding them into paid reports, newsletters, dashboards, trading signals or investment-research products |
| **3** | **Personal use only** | Any use by or on behalf of a third party. No redistribution, no publishing, no running it for someone else, no making its output available to others — free or paid |

**Why the data is separate.** The code is the author's; the posts are not. Collected content belongs to
X Corp. and to the original authors, and this license grants you no rights in it whatsoever. It also does
not override X's Terms of Service — complying with those remains your own obligation.

**Not granted:** any rights beyond running and modifying a private copy for yourself. All other rights are
reserved by the copyright holder. Any breach terminates the grant immediately and requires you to delete
all copies of the Software and all Data obtained through it.

If you need commercial rights, contact the author for a separate written agreement.
