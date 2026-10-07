#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
x_search.py — X(Twitter) 高赞推文检索主程序。

两种关键字给法（二选一）：
    --keyword    自定义关键字（支持 X 高级搜索语法原样透传）
    --preset     内置固定关键词：all=全部 / preset键 / 逗号分隔多个键；--preset list 查看

其他自定义参数：
    --since/--until  时间范围（YYYY-MM-DD，支持 7d/2w/3m/today/yesterday）
    --min-likes  点赞阈值（默认 1000，可自定义）

三种数据后端：
    api      官方 X API v2（需要环境变量 X_BEARER_TOKEN）
    browser  Playwright 抓取 x.com 搜索结果页（需要一次性登录）
    offline  读取已经抓好的 JSON（--from-json），只做过滤/排序/渲染

示例：
    # 最简单：关键字 + 最近 7 天 + 点赞 ≥1000
    python x_search.py --keyword "AI agent"

    # 自定义三个参数
    python x_search.py --keyword "AI agent" --since 2026-09-01 --until 2026-09-30 --min-likes 2000

    # 一键拉全部内置固定关键词（7 大 AI 主题，各出一份报告，最后一行输出 batch 汇总）
    python x_search.py --preset all --since 7d

    # 只拉指定几组固定关键词
    python x_search.py --preset prompt-engineering,context-engineering --since 14d

    # 查看内置固定关键词清单
    python x_search.py --preset list

    # 指定后端 + 输出目录
    python x_search.py --keyword 英伟达 --since 30d --min-likes 500 --backend browser --out ./reports

    # 离线模式：把浏览器里扒到的 JSON 做二次过滤
    python x_search.py --keyword AI --from-json raw.json --min-likes 1000
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

import xquery as X  # noqa: E402
import html_report as HTMLR  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

API_ENDPOINT = "https://api.x.com/2/tweets/search/recent"
TOKEN_ENV_KEYS = ("X_BEARER_TOKEN", "TWITTER_BEARER_TOKEN", "X_API_BEARER_TOKEN")
HERE = Path(__file__).resolve().parent

# ------------------------------------------------------------------ 内置固定关键词
# 固定关键词分组：key 用于 --preset 与输出文件名，query 为 X 高级搜索检索式（OR 必须大写）。
# 维护方式：直接增删本表即可，CLI 与文档自动跟随。
PRESET_KEYWORDS: Dict[str, Dict[str, str]] = {
    "agentic-ai": {
        "label": "Agentic AI / AI Agent",
        "query": '(agentic AI OR "AI agent" OR "AI agents")',
    },
    "mcp": {
        "label": "MCP（Model Context Protocol）",
        "query": '(MCP OR "Model Context Protocol")',
    },
    "llm-evals": {
        "label": "LLM Evals / Post-deploy Evaluation",
        "query": '("LLM eval" OR "LLM evals" OR "LLM evaluation" OR "post-deploy evaluation")',
    },
    "prompt-engineering": {
        "label": "Prompt Engineering",
        "query": '("prompt engineering")',
    },
    "context-engineering": {
        "label": "Context Engineering",
        "query": '("context engineering")',
    },
    "agent-skill": {
        "label": "Agent Skill",
        "query": '("agent skill" OR "agent skills" OR agentskill)',
    },
    "vibe-coding": {
        "label": "Vibe Coding / AI Coding Agent",
        "query": '("vibe coding" OR "AI coding agent" OR "AI coding agents")',
    },
}


# ------------------------------------------------------------------ 工具

def eprint(*a):
    print(*a, file=sys.stderr, flush=True)


def slugify(text: str, limit: int = 40) -> str:
    keep = [c for c in text if c.isalnum() or c in "-_" or "\u4e00" <= c <= "\u9fff"]
    return ("".join(keep)[:limit] or "result").strip("-_") or "result"


# ------------------------------------------------------------------ 后端：官方 API

def fetch_api(query: str, *, limit: int, lang: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    X API v2 recent search。需要 Bearer Token（付费档位）。
    注意：min_faves 不是 API 官方运算符，点赞阈值在本地过滤（见 filter_items）。
    """
    import urllib.error
    import urllib.parse
    import urllib.request

    token = next((os.environ.get(k) for k in TOKEN_ENV_KEYS if os.environ.get(k)), None)
    if not token:
        raise RuntimeError(
            "MISSING_TOKEN: 未找到 X API Bearer Token。请设置环境变量 X_BEARER_TOKEN，"
            "或改用 --backend browser（免费，需一次性登录）或 --backend offline。"
        )

    # API 端不支持 min_faves，去掉阈值条件避免查询被拒
    import re as _re
    api_query = _re.sub(r"\bmin_faves:\d+\s*", "", query).strip()

    items: List[Dict[str, Any]] = []
    next_token = None
    max_per_page = 100
    while len(items) < limit:
        params = {
            "query": api_query,
            "max_results": str(min(max_per_page, max(10, limit - len(items)))),
            "tweet.fields": "public_metrics,created_at,lang,author_id,note_tweet",
            "expansions": "author_id",
            "user.fields": "username,name,verified",
        }
        if next_token:
            params["next_token"] = next_token
        url = API_ENDPOINT + "?" + urllib.parse.urlencode(params)

        req = urllib.request.Request(url, headers={
            "Authorization": f"Bearer {token}",
            "User-Agent": "x-search-posts/1.0",
        })
        try:
            with urllib.request.urlopen(req, timeout=45) as r:
                data = json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", "ignore")[:400]
            hint = {
                401: "Token 无效或已过期。",
                403: "该 Token 无权访问 search/recent（需 Basic 及以上付费档位）。",
                429: "触发速率限制，请稍后重试或降低 --limit。",
            }.get(exc.code, "")
            raise RuntimeError(f"X API 返回 {exc.code}：{hint}\n{body}") from exc
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"X API 请求失败：{exc}") from exc

        users = {}
        for u in (data.get("includes") or {}).get("users", []) or []:
            users[u.get("id")] = u

        for t in data.get("data", []) or []:
            m = t.get("public_metrics") or {}
            note = ((t.get("note_tweet") or {}).get("text")) if isinstance(t.get("note_tweet"), dict) else None
            u = users.get(t.get("author_id"), {})
            items.append(X.normalize_tweet({
                "id": t.get("id"),
                "text": note or t.get("text", ""),
                "created_at": t.get("created_at", ""),
                "likes": m.get("like_count", 0),
                "retweets": m.get("retweet_count", 0),
                "replies": m.get("reply_count", 0),
                "author": u.get("username", ""),
                "author_name": u.get("name", ""),
                "source": "api",
            }))

        next_token = (data.get("meta") or {}).get("next_token")
        if not next_token or not (data.get("data") or []):
            break
        time.sleep(0.6)  # 温和限速

    return [i for i in items if i]


# ------------------------------------------------------------------ 后端：浏览器抓取

def _node_bin() -> str:
    """按优先级查找 node：环境变量 → WorkBuddy 托管运行时（任意版本，取最新）→ 常见安装路径。"""
    env_node = os.environ.get("X_SEARCH_NODE") or os.environ.get("NODE_BIN")
    if env_node and Path(env_node).exists():
        return env_node

    managed = Path(os.path.expanduser("~")) / ".workbuddy" / "binaries" / "node" / "versions"
    if managed.is_dir():
        found = sorted(managed.glob("*/node.exe"), reverse=True)
        if found:
            return str(found[0])

    cands = [
        os.path.expandvars(r"%ProgramFiles%\nodejs\node.exe"),
        r"C:\nvm4w\nodejs\node.exe",
        "/usr/local/bin/node",
        "/usr/bin/node",
    ]
    for c in cands:
        if Path(c).exists():
            return c

    import shutil as _sh
    return _sh.which("node") or "node"


def fetch_browser(args, query: str, url: str, raw_out: Path) -> List[Dict[str, Any]]:
    script = HERE / "browser_collect.js"
    if not script.exists():
        raise RuntimeError(f"缺少采集脚本：{script}")

    cmd = [_node_bin(), str(script), "--url", url, "--out", str(raw_out),
           "--scrolls", str(args.scrolls), "--max", str(args.max_items), "--quiet"]
    if args.headed:
        cmd.append("--headed")
    if args.since_date:
        cmd += ["--since", args.since_date.isoformat()]

    eprint(f"[*] 启动浏览器采集（可能需要 30~90 秒）…")
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    out = (proc.stdout or "").strip()
    err = (proc.stderr or "").strip()

    if proc.returncode == 4 or "NOT_LOGGED_IN" in err:
        raise RuntimeError(
            "NOT_LOGGED_IN: X 未登录，搜索接口会被拦截。请先执行一次性登录：\n"
            f'  "{_node_bin()}" "{script}" --login\n'
            "登录窗口关闭后登录态会自动保存，后续无需重复登录。"
        )
    if proc.returncode == 3 or "PLAYWRIGHT_MISSING" in err:
        raise RuntimeError(
            "PLAYWRIGHT_MISSING: 缺少 Playwright。安装命令：\n"
            '  cd "%USERPROFILE%\\.workbuddy\\binaries\\node\\workspace"\n'
            "  npm install playwright && npx playwright install chromium"
        )
    if proc.returncode != 0 and not raw_out.exists():
        raise RuntimeError(f"浏览器采集失败：\n{err or out or '(无输出)'}")
    if err:
        eprint(err)

    data = json.loads(raw_out.read_text(encoding="utf-8"))
    return [X.normalize_tweet(i) for i in data.get("items", []) if i]


# ------------------------------------------------------------------ 离线

def fetch_offline(path: Path) -> List[Dict[str, Any]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    rows = raw.get("items") if isinstance(raw, dict) else raw
    if not isinstance(rows, list):
        raise RuntimeError("--from-json 文件格式应为 list 或 {'items': [...]} ")
    return [X.normalize_tweet(r) for r in rows if r]


# ------------------------------------------------------------------ 主流程

def run_collection(
    args,
    *,
    key: Optional[str],
    label: str,
    query_src: str,
    stem: str,
    out_dir: Path,
    since_d,
    until_d,
    ts: str,
) -> Dict[str, Any]:
    """
    跑单个关键字的完整流水线：构造检索式 → 取数 → 去重过滤 → 排序 → 落盘。

    key 为 preset 键（--keyword 路径时为 None）；结果以一行 JSON 打印到 stdout，
    成功含 markdown/json 路径，失败含 error，便于上层逐行解析。
    """
    query = X.build_query(
        query_src,
        min_likes=args.min_likes,
        since=since_d,
        until=until_d,
        lang=args.lang,
        exclude_retweets=not args.include_retweets,
        exclude_replies=args.exclude_replies,
        extra=[args.extra] if args.extra else None,
        until_inclusive=not args.until_exclusive,
    )
    url = X.search_url(query, args.tab)

    result: Dict[str, Any] = {"ok": False, "label": label}
    if key:
        result["preset"] = key

    eprint("=" * 68)
    eprint(f"  关键字   : {label}" + (f"   [preset: {key}]" if key else ""))
    eprint(f"  时间范围 : {since_d} ~ {until_d}  (UTC)")
    eprint(f"  点赞阈值 : >= {args.min_likes}")
    eprint(f"  检索式   : {query}")
    eprint(f"  搜索页   : {url}")
    eprint("=" * 68)

    backend = args.backend
    used = backend
    raw_items: List[Dict[str, Any]] = []

    try:
        if args.from_json:
            backend, used = "offline", "offline"
            raw_items = fetch_offline(Path(args.from_json))
        elif backend == "offline":
            raise RuntimeError("--backend offline 需要同时提供 --from-json")
        elif backend in ("auto", "api") and any(os.environ.get(k) for k in TOKEN_ENV_KEYS):
            used = "api"
            raw_items = fetch_api(query, limit=args.limit)
        elif backend in ("auto", "browser"):
            used = "browser"
            raw_out = out_dir / f"{stem}_{ts}_raw.json"
            raw_items = fetch_browser(args, query, url, raw_out)
        elif backend == "api":
            raise RuntimeError(
                "MISSING_TOKEN: 未配置 X_BEARER_TOKEN，无法使用官方 API 后端。"
                "可改用 --backend browser 或 --backend offline。"
            )
    except RuntimeError as exc:
        eprint(f"\n[x] [{label}] {exc}\n")
        result.update({"error": str(exc), "query": query, "search_url": url})
        print(json.dumps(result, ensure_ascii=False))
        return result

    raw_items = [i for i in raw_items if i]
    # 二次校验的关键字过滤只适用于「单一关键字 + 离线数据」；preset 是 OR 检索式，无法用单一子串校验
    filter_kw = query_src if (used == "offline" and not key) else ""
    items = X.filter_items(
        X.dedupe(raw_items),
        min_likes=args.min_likes,
        since=since_d,
        until=until_d,
        keyword=filter_kw,
    )
    items = X.rank_by_likes(items)

    payload = X.to_json_payload(items, keyword=label, query=query, since=since_d,
                                until=until_d, min_likes=args.min_likes, backend=used, link=url)

    md_path = None
    html_path = None
    json_path = out_dir / f"{stem}_{ts}.json"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.format in ("html", "both"):
        html_str = HTMLR.render_report([payload], title=f"X 高赞推文 · {label}")
        html_path = out_dir / f"{stem}_{ts}.html"
        html_path.write_text(html_str, encoding="utf-8")
    if args.format in ("md", "both"):
        md = X.to_markdown(items, keyword=label, query=query, since=since_d, until=until_d,
                           min_likes=args.min_likes, backend=used, link=url, top_n=args.top)
        md_path = out_dir / f"{stem}_{ts}.md"
        md_path.write_text(md, encoding="utf-8")

    done = []
    if html_path:
        done.append(f"报告 : {html_path}")
    if md_path:
        done.append(f"报告 : {md_path}")
    done.append(f"数据 : {json_path}")

    eprint(f"\n[✓] [{label}] 采集 {len(raw_items)} 条 → 过滤后 {len(items)} 条")
    for line in done:
        eprint(f"[✓] {line}")

    result.update({
        "ok": True,
        "backend": used,
        "query": query,
        "search_url": url,
        "raw_count": len(raw_items),
        "matched": len(items),
        "format": args.format,
        "html": str(html_path) if html_path else None,
        "markdown": str(md_path) if md_path else None,
        "json": str(json_path),
        "top": [{"author": i["author"], "likes": i["likes"], "url": i["url"],
                 "created_at": i["created_at"]} for i in items[:args.top]],
    })
    print(json.dumps(result, ensure_ascii=False))
    return result


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        description="抓取 X(Twitter) 指定关键字 / 时间范围内点赞数达标的高赞推文",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--keyword", "-k",
                   help="自定义关键字（支持 X 高级搜索语法）；与 --preset 二选一")
    p.add_argument("--preset",
                   help="使用内置固定关键词：preset 键 / 逗号分隔多个键 / all=全部 / list=查看清单")
    p.add_argument("--since", help="起始日期 YYYY-MM-DD，或 7d/2w/3m/today")
    p.add_argument("--until", help="结束日期 YYYY-MM-DD（含当天）")
    p.add_argument("--min-likes", type=int, default=1000, help="点赞数下限，默认 1000")
    p.add_argument("--lang", help="语言过滤，如 zh / en")
    p.add_argument("--tab", default="top", choices=["top", "latest", "media"], help="搜索排序：top/latest/media")
    p.add_argument("--exclude-replies", action="store_true", help="排除回复")
    p.add_argument("--include-retweets", action="store_true", help="包含转推（默认排除）")
    p.add_argument("--extra", help="附加原始查询片段，如 'filter:links -from:bot'")
    p.add_argument("--until-exclusive", action="store_true", help="until 按 X 原生语义（不含当天）")

    p.add_argument("--backend", default="auto", choices=["auto", "api", "browser", "offline"])
    p.add_argument("--from-json", help="离线模式输入文件（等同于 --backend offline）")
    p.add_argument("--limit", type=int, default=100, help="API 模式最多取多少条")
    p.add_argument("--max-items", type=int, default=120, help="浏览器模式最多采集多少条")
    p.add_argument("--scrolls", type=int, default=8, help="浏览器模式滚动次数")
    p.add_argument("--headed", action="store_true", help="浏览器显示窗口")

    p.add_argument("--top", type=int, default=20, help="报告正文展示条数，默认 20")
    p.add_argument("--format", default="html", choices=["html", "md", "both"],
                   help="报告产物格式：html（默认，单文件 HTML）/ md（Markdown）/ both")
    p.add_argument("--out", default=".", help="输出目录")
    p.add_argument("--name", help="输出文件名前缀，默认按关键字自动生成")
    p.add_argument("--quiet", action="store_true", help="减少日志")
    args = p.parse_args(argv)

    preset_spec = (args.preset or "").strip().lower().replace("_", "-")

    if preset_spec == "list":
        print(json.dumps(
            {"ok": True, "presets": [
                {"key": k, "label": v["label"], "query": v["query"]}
                for k, v in PRESET_KEYWORDS.items()]},
            ensure_ascii=False, indent=2))
        return 0

    if args.keyword and preset_spec:
        eprint("[x] --keyword 与 --preset 二选一，不要同时提供。")
        return 2
    if not args.keyword and not preset_spec:
        eprint("[x] 必须提供 --keyword 或 --preset（--preset list 可查看内置固定关键词）。")
        return 2

    # 解析目标关键字列表（--keyword 一项；--preset 可多项）
    targets: List[Dict[str, str]] = []
    if args.keyword:
        targets.append({"key": "", "label": args.keyword, "query_src": args.keyword})
    else:
        keys = (list(PRESET_KEYWORDS) if preset_spec == "all"
                else [k.strip() for k in preset_spec.split(",") if k.strip()])
        unknown = [k for k in keys if k not in PRESET_KEYWORDS]
        if unknown:
            eprint(f"[x] 未知的 preset：{', '.join(unknown)}。"
                   f"可用值：{', '.join(PRESET_KEYWORDS)} 或 all。")
            return 2
        targets = [{"key": k, "label": PRESET_KEYWORDS[k]["label"],
                    "query_src": PRESET_KEYWORDS[k]["query"]} for k in keys]

    try:
        since_d, until_d = X.resolve_window(args.since, args.until, default_days=7)
    except ValueError as exc:
        eprint(f"[x] {exc}")
        return 2
    args.since_date = since_d

    out_dir = Path(args.out).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")

    results: List[Dict[str, Any]] = []
    for t in targets:
        key = t["key"]
        if args.name:
            stem = f"{args.name}_{key}" if key else args.name
        else:
            stem = f"x_hot_{key}" if key else f"x_hot_{slugify(t['query_src'])}"
        results.append(run_collection(
            args, key=key or None, label=t["label"], query_src=t["query_src"], stem=stem,
            out_dir=out_dir, since_d=since_d, until_d=until_d, ts=ts))

    ok_n = sum(1 for r in results if r.get("ok"))
    if len(results) > 1:
        print(json.dumps({
            "ok": ok_n > 0,
            "batch": True,
            "total": len(results),
            "succeeded": ok_n,
            "failed": len(results) - ok_n,
            "results": [{k: r.get(k) for k in ("preset", "label", "ok", "matched",
                                               "html", "markdown", "json", "error")}
                        for r in results],
        }, ensure_ascii=False))
    return 0 if ok_n else 3


if __name__ == "__main__":
    sys.exit(main())
