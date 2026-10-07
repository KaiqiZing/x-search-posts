#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
html_report.py — 把 to_json_payload 生成的数据渲染成单文件 HTML 报告。

视觉系统参考 beautiful-html-templates / Blue Professional：
cream 纸底 + 钴蓝单强调 + tinted 卡片，无阴影；CJK 行高放大、字距归零。

模板：skills/x-search-posts/templates/report.html（占位符 {{...}} 由本模块填充）。
摘要来源：summaries 字典（推文 id → 中文摘要）；缺摘要时渲染「待补」占位。
"""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

HERE = Path(__file__).resolve().parent
TEMPLATE = HERE.parent / "templates" / "report.html"

_SUMMARY_PENDING = "（待补中文摘要）"


def _esc(v: Any) -> str:
    return html.escape(str(v if v is not None else ""), quote=True)


def _fmt_int(v: Any) -> str:
    try:
        n = int(v or 0)
    except (TypeError, ValueError):
        return "—"
    return f"{n:,}" if n > 0 else "—"


def _fmt_time(created: str) -> str:
    """ISO UTC → '2026-10-01 10:00 UTC'；解析失败原样返回。"""
    s = str(created or "").strip()
    if not s:
        return "—"
    try:
        return f"{s[:10]} {s[11:16]} UTC"
    except Exception:
        return s


def _observation_block(observation: str) -> str:
    text = (observation or "").strip()
    if not text:
        return ""
    paras = "".join(f"<p>{_esc(line)}</p>" for line in text.splitlines() if line.strip())
    return (
        '<section class="observation">\n'
        '  <h2>整体观察</h2>\n'
        f"  {paras}\n"
        "</section>"
    )


def _toc_block(payloads: List[Dict[str, Any]]) -> str:
    if len(payloads) < 2:
        return ""
    cells = []
    for i, p in enumerate(payloads, 1):
        meta = p.get("meta") or {}
        cells.append(
            f'<a class="cell" href="#sec-{i}">'
            f'<div class="k">{_esc(meta.get("count", 0))}</div>'
            f'<div class="n">{_esc(meta.get("keyword", "—"))}</div>'
            "</a>"
        )
    return f'<nav class="toc">{"".join(cells)}</nav>'


def _tweet_card(item: Dict[str, Any], *, rank: int, max_likes: int,
                summaries: Dict[str, str]) -> str:
    tid = str(item.get("id") or "")
    author = str(item.get("author") or "")
    url = str(item.get("url") or (f"https://x.com/{author}/status/{tid}" if author and tid else ""))
    text = str(item.get("text") or "")
    summary = (summaries or {}).get(tid, "").strip()

    likes = int(item.get("likes") or 0)
    pct = max(4, round(likes / max_likes * 100)) if (max_likes and likes > 0) else 0
    bar = f'<div class="bar-track"><div class="bar-fill" style="width:{pct}%"></div></div>' if pct else ""

    summary_html = (
        f'<div class="summary">{_esc(summary)}</div>'
        if summary
        else f'<div class="summary pending">{_SUMMARY_PENDING}</div>'
    )
    handle_html = (
        f'<a class="handle" href="https://x.com/{_esc(author)}">@{_esc(author)}</a>'
        if author
        else '<span class="handle">@—</span>'
    )
    link_html = f'<a href="{_esc(url)}">查看原推 →</a>' if url else ""

    metrics = (
        f'<div class="tweet-metrics"><span class="likes num">{_fmt_int(likes)}</span> 赞'
        f' · {_fmt_int(item.get("retweets"))} 转 · {_fmt_int(item.get("replies"))} 评'
        f' · {_fmt_int(item.get("views"))} 浏览</div>'
    )

    return (
        f'<article class="tweet">\n'
        f'  <div class="tweet-head">\n'
        f'    <span class="rank">{rank:02d}</span>\n'
        f'    <div class="who">{handle_html}'
        f'<span class="name">{_esc(item.get("author_name") or "")}</span></div>\n'
        f"    {metrics}\n"
        f"  </div>\n"
        f"  {bar}\n"
        f"  {summary_html}\n"
        f'  <blockquote class="orig">{_esc(text)}</blockquote>\n'
        f'  <div class="tweet-foot"><span>{_esc(_fmt_time(item.get("created_at")))}</span>'
        f"<span>{link_html}</span></div>\n"
        f"</article>"
    )


def _section_block(payload: Dict[str, Any], *, index: int,
                   summaries: Dict[str, str]) -> str:
    meta = payload.get("meta") or {}
    items: List[Dict[str, Any]] = payload.get("items") or []
    keyword = str(meta.get("keyword") or "—")
    count = int(meta.get("count") or len(items))
    min_likes = int(meta.get("min_likes") or 0)
    since = meta.get("since") or "—"
    until = meta.get("until") or "—"
    query = str(meta.get("query") or "")
    search_url = str(meta.get("search_url") or "")
    max_likes = max((int(i.get("likes") or 0) for i in items), default=0)

    cards = "\n".join(
        _tweet_card(it, rank=rank, max_likes=max_likes, summaries=summaries)
        for rank, it in enumerate(items, 1)
    ) or '<article class="tweet"><div class="summary pending">本组无达标推文</div></article>'

    src_link = f' · <a href="{_esc(search_url)}">搜索页</a>' if search_url else ""
    src = (
        f'<details class="src"><summary>检索式与来源</summary>'
        f'<div class="q">{_esc(query)}</div>'
        f"<div>后端 {_esc(meta.get('backend') or '—')}{src_link}</div></details>"
    )

    return (
        f'<section class="section" id="sec-{index}">\n'
        f'  <div class="accent-line"></div>\n'
        f'  <div class="section-head">\n'
        f'    <div><span class="eyebrow eyebrow--cn">Section {index:02d} · {_esc(keyword)}</span>\n'
        f'    <h2 class="sec-title disp">{_esc(keyword)}</h2></div>\n'
        f'    <span class="pill">{count} 条 · ≥{_fmt_int(min_likes)} 赞</span>\n'
        f"  </div>\n"
        f'  <div class="sec-note">{_esc(since)} ~ {_esc(until)} (UTC)</div>\n'
        f"  {src}\n"
        f"  {cards}\n"
        f"</section>"
    )


def render_report(
    payloads: List[Dict[str, Any]],
    *,
    title: str = "X 高赞推文巡检报告",
    tag_pill: str = "",
    observation: str = "",
    summaries: Optional[Dict[str, str]] = None,
) -> str:
    """
    把一个或多个 payload（to_json_payload 产物）渲染成完整 HTML。

    payloads: 每项为 {meta:{keyword,query,since,until,min_likes,backend,search_url,count,generated_at}, items:[...]}
    summaries: {推文id: 中文摘要}；缺失时渲染「待补」占位。
    """
    if not isinstance(payloads, list):
        payloads = [payloads]
    payloads = [p for p in payloads if isinstance(p, dict) and p.get("meta")]
    if not payloads:
        raise ValueError("render_report: 没有有效的 payload（需要 meta + items 结构）")

    template = TEMPLATE.read_text(encoding="utf-8")
    summaries = summaries or {}

    # 汇总时间范围与阈值（多组时取并集展示）
    sinces = [p["meta"].get("since") for p in payloads if p["meta"].get("since")]
    untils = [p["meta"].get("until") for p in payloads if p["meta"].get("until")]
    minls = [int(p["meta"].get("min_likes") or 0) for p in payloads]
    backends = sorted({str(p["meta"].get("backend") or "") for p in payloads} - {""})
    total = sum(int(p.get("meta", {}).get("count") or 0) for p in payloads)

    range_txt = (
        f"{min(sinces)} ~ {max(untils)} (UTC)" if sinces and untils else "—"
    )
    minl_txt = f"≥{min(minls):,}" if minls else "—"
    backend_txt = " / ".join(backends) if backends else "—"
    meta_line = (
        f"<b>{_esc(range_txt)}</b> · 点赞阈值 <b>{_esc(minl_txt)}</b> · "
        f"共 <b>{total}</b> 条命中 · 后端 <b>{_esc(backend_txt)}</b>"
    )

    sections = "\n\n".join(
        _section_block(p, index=i, summaries=summaries)
        for i, p in enumerate(payloads, 1)
    )
    gen_at = payloads[0]["meta"].get("generated_at") or ""

    out = (
        template
        .replace("{{TITLE}}", _esc(title))
        .replace("{{TAG_PILL}}", _esc(tag_pill or range_txt))
        .replace("{{META_LINE}}", meta_line)
        .replace("{{OBSERVATION}}", _observation_block(observation))
        .replace("{{TOC}}", _toc_block(payloads))
        .replace("{{SECTIONS}}", sections)
        .replace("{{GENERATED_AT}}", _esc(gen_at))
    )
    return out


def load_payload(path: Path) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))
