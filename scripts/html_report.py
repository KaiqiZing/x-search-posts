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
WISH_DEFAULT = "一周开心，一周快乐，一周智能报告与你相逢。"

# 天气图标（描边风，随 currentColor 走主题色）
_ICONS = {
    "sun": '<circle cx="12" cy="12" r="4.1"/><path d="M12 2.7v2.2M12 19.1v2.2M2.7 12h2.2M19.1 12h2.2M5.5 5.5l1.5 1.5M17 17l1.5 1.5M18.5 5.5L17 7M7 17l-1.5 1.5"/>',
    "sun-cloud": '<circle cx="8.4" cy="8.4" r="3"/><path d="M8.4 1.9v1.6M2.9 8.4h1.4M3.5 3.5l1.1 1.1M13.4 3.6l-1.1 1.1"/>'
                 '<path d="M9.2 18.6h8.3a2.7 2.7 0 0 0 .2-5.4 4 4 0 0 0-7.7-.8 3.1 3.1 0 0 0-.8 6.2Z"/>',
    "cloud": '<path d="M7.4 18.4h9a3.2 3.2 0 0 0 .3-6.4 4.6 4.6 0 0 0-8.8-.9 3.6 3.6 0 0 0-.5 7.3Z"/>',
    "fog": '<path d="M7.4 14.4h9a3.2 3.2 0 0 0 .3-6.4 4.6 4.6 0 0 0-8.8-.9 3.6 3.6 0 0 0-.5 7.3Z"/>'
           '<path d="M4.6 17.9h14.8M6.4 21h11.2"/>',
    "drizzle": '<path d="M7.4 15.4h9a3.2 3.2 0 0 0 .3-6.4 4.6 4.6 0 0 0-8.8-.9 3.6 3.6 0 0 0-.5 7.3Z"/>'
               '<path d="M8.6 18.4l-.9 2.2M12.3 18.4l-.9 2.2M16 18.4l-.9 2.2"/>',
    "rain": '<path d="M7.4 15.4h9a3.2 3.2 0 0 0 .3-6.4 4.6 4.6 0 0 0-8.8-.9 3.6 3.6 0 0 0-.5 7.3Z"/>'
            '<path d="M8.4 18.2l-1.2 3M12.2 18.2l-1.2 3M16 18.2l-1.2 3"/>',
    "snow": '<path d="M7.4 15.4h9a3.2 3.2 0 0 0 .3-6.4 4.6 4.6 0 0 0-8.8-.9 3.6 3.6 0 0 0-.5 7.3Z"/>'
            '<path d="M8.5 19v2.6M7.3 19.6l2.4 1.4M9.7 19.6l-2.4 1.4M15.5 19v2.6M14.3 19.6l2.4 1.4M16.7 19.6l-2.4 1.4"/>',
    "thunder": '<path d="M7.4 15.4h9a3.2 3.2 0 0 0 .3-6.4 4.6 4.6 0 0 0-8.8-.9 3.6 3.6 0 0 0-.5 7.3Z"/>'
               '<path d="M12.8 17.6l-2.4 3.5h2.1l-.8 2.4 2.7-3.6h-2.1l.5-2.3Z"/>',
}


def _weather_icon(key: str, size: int = 36) -> str:
    body = _ICONS.get(str(key or "cloud"), _ICONS["cloud"])
    return (
        f'<svg class="wicon" width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" '
        f'stroke="currentColor" stroke-width="1.6" stroke-linecap="round" aria-hidden="true">{body}</svg>'
    )


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
        '<section class="observation" id="overview">\n'
        '  <h2>整体观察</h2>\n'
        f"  {paras}\n"
        "</section>"
    )


def _short_kw(name: str) -> str:
    """章节名压缩成侧栏宽度：去掉括号副标题与「/」后的长串。"""
    s = str(name or "").strip()
    for cut in ("（", "("):
        if cut in s:
            head = s.split(cut, 1)[0].strip()
            if len(head) >= 3:
                s = head
                break
    if " / " in s:
        head = s.split(" / ", 1)[0].strip()
        if len(head) >= 4:
            s = head
    return s or "—"


def _side_meta_block(weather: Optional[Dict[str, Any]], wish: str, tag: str) -> str:
    """右上角：当日天气卡片 + 祝福语；无天气数据时退化为时间范围胶囊。"""
    if not weather or not weather.get("ok"):
        return f'<span class="pill">{_esc(tag)}</span>'

    temp = weather.get("temp")
    temp_txt = f"{temp}°" if temp is not None else "—"
    cond = str(weather.get("cond") or "—")
    city = str(weather.get("city") or "—")
    parts = [city]
    if weather.get("date_label"):
        parts.append(str(weather["date_label"]))
    tmin, tmax = weather.get("tmin"), weather.get("tmax")
    if tmin is not None and tmax is not None:
        parts.append(f"{tmin}~{tmax}°C")
    if weather.get("pop") is not None:
        parts.append(f"降水 {weather['pop']}%")
    sub = " · ".join(parts)

    wish_html = f'<div class="wish">{_esc(wish)}</div>' if wish else ""
    return (
        '<div class="side-meta">\n'
        f'        <div class="weather" role="note" aria-label="{_esc(city)}今日天气">\n'
        f"          {_weather_icon(weather.get('icon'))}\n"
        "          <div>\n"
        f'            <div class="wnow"><span class="wtemp">{_esc(temp_txt)}</span>'
        f'<span class="wcond">{_esc(cond)}</span></div>\n'
        f'            <div class="wsub">{_esc(sub)}</div>\n'
        "          </div>\n"
        "        </div>\n"
        f"        {wish_html}\n"
        "      </div>"
    )


def _sidenav_block(payloads: List[Dict[str, Any]], *, nav_title: str, nav_sub: str,
                   has_observation: bool, foot_note: str) -> str:
    """左侧固定导航：概览 + 分组（带条数）+ 页脚口径说明。"""
    groups = []
    for i, p in enumerate(payloads, 1):
        meta = p.get("meta") or {}
        count = int(meta.get("count") or len(p.get("items") or []))
        cls = "nav-item is-zero" if count == 0 else "nav-item"
        groups.append(
            f'      <li><a class="{cls}" href="#sec-{i}"><span class="no">{i:02d}</span>'
            f'<span class="nm">{_esc(_short_kw(meta.get("keyword")))}</span>'
            f'<span class="ct">{count}</span></a></li>'
        )
    groups_html = "\n".join(groups)

    overview_group = ""
    if has_observation:
        overview_group = (
            '  <div>\n    <div class="lbl">概览</div>\n    <ul>\n'
            '      <li><a class="nav-item" href="#overview"><span class="no">—</span>'
            '<span class="nm">整体观察</span></a></li>\n'
            "    </ul>\n  </div>\n\n"
        )

    return (
        '<button class="nav-toggle" id="nav-toggle" type="button" '
        'aria-label="打开导航" aria-controls="sidenav">☰</button>\n'
        '<div class="nav-backdrop" id="nav-backdrop"></div>\n\n'
        '<nav class="sidenav" id="sidenav" aria-label="报告导航">\n'
        '  <div class="progress" id="nav-progress"></div>\n'
        '  <a class="brand" href="#top">\n'
        f'    <div class="t">{_esc(nav_title)}</div>\n'
        f'    <div class="d">{_esc(nav_sub)}</div>\n'
        "  </a>\n\n"
        f"{overview_group}"
        '  <div>\n    <div class="lbl">分组</div>\n    <ul>\n'
        f"{groups_html}\n"
        "    </ul>\n  </div>\n\n"
        '  <div class="foot">\n    <a href="#notes">口径说明 ↓</a>\n'
        f"    <div>{_esc(foot_note)}</div>\n  </div>\n"
        "</nav>"
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
    weather: Optional[Dict[str, Any]] = None,
    wish: str = WISH_DEFAULT,
    nav_title: Optional[str] = None,
    nav_sub: Optional[str] = None,
) -> str:
    """
    把一个或多个 payload（to_json_payload 产物）渲染成完整 HTML。

    payloads: 每项为 {meta:{keyword,query,since,until,min_likes,backend,search_url,count,generated_at}, items:[...]}
    summaries: {推文id: 中文摘要}；缺失时渲染「待补」占位。
    weather: weather.get_weather() 的返回值；给了就在右上角渲染天气卡片 + 祝福语，否则退化为时间胶囊。
    wish: 天气卡片下方的祝福语（默认「一周开心，一周快乐，一周智能报告与你相逢。」）。
    nav_title / nav_sub: 左侧导航顶部的标题与副标题，默认取 title / 时间范围。
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

    # 左侧导航：标题取主标题（截断避免撑破 256px），副标题取时间范围
    nt = nav_title or title
    if len(nt) > 22:
        nt = nt[:21].rstrip() + "…"
    ns = nav_sub or (f"{min(sinces)[5:]} ~ {max(untils)[5:]}" if sinces and untils else range_txt)
    foot_note = f"点赞 {minl_txt} · {backend_txt} 后端 · 只读采集"

    out = (
        template
        .replace("{{SIDENAV}}", _sidenav_block(
            payloads, nav_title=nt, nav_sub=ns,
            has_observation=bool((observation or "").strip()), foot_note=foot_note))
        .replace("{{TITLE}}", _esc(title))
        .replace("{{SIDE_META}}", _side_meta_block(weather, wish, tag_pill or range_txt))
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
