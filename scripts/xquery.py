#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
xquery.py — X(Twitter) 检索查询构造 / 结果归一化 / 过滤排序 / 输出渲染。

纯逻辑模块，不做任何网络请求，可单独测试。

核心映射（用户只需给 3 个参数）：
    keyword   -> 原样进入查询串
    time      -> since:YYYY-MM-DD until:YYYY-MM-DD
    like      -> min_faves:N
"""

from __future__ import annotations

import datetime as _dt
import json
import re
from typing import Any, Dict, Iterable, List, Optional

# ---------------------------------------------------------------- 日期处理

_DATE_RE = re.compile(r"^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})$")
_REL_RE = re.compile(r"^(\d+)\s*([dwmh])$", re.I)


def today_utc() -> _dt.date:
    """X 搜索的日期边界按 UTC 计算。"""
    return _dt.datetime.now(_dt.timezone.utc).date()


def parse_date(value: Optional[str], *, default: Optional[_dt.date] = None) -> Optional[_dt.date]:
    """
    解析用户给定的日期。支持：
      2026-09-01 / 2026/9/1 / 2026.9.1
      7d / 2w / 3m / 48h   （相对今天，m = 30 天）
      today / yesterday / now
    """
    if value is None:
        return default
    v = str(value).strip()
    if not v:
        return default
    low = v.lower()
    base = today_utc()
    if low in ("today", "now"):
        return base
    if low == "yesterday":
        return base - _dt.timedelta(days=1)

    m = _REL_RE.match(v)
    if m:
        n = int(m.group(1))
        unit = m.group(2).lower()
        days = {"d": 1, "w": 7, "m": 30, "h": 1}[unit]
        if unit == "h":
            return base - _dt.timedelta(days=max(1, n // 24))
        return base - _dt.timedelta(days=n * days)

    m = _DATE_RE.match(v)
    if m:
        y, mo, d = (int(x) for x in m.groups())
        try:
            return _dt.date(y, mo, d)
        except ValueError as exc:
            raise ValueError(f"非法日期 {value!r}: {exc}") from exc

    raise ValueError(
        f"无法解析日期 {value!r}，请使用 YYYY-MM-DD，或相对写法 7d / 2w / 3m / today / yesterday"
    )


def is_relative(value: Optional[str]) -> bool:
    """判断是否为相对写法（7d / 2w / 3m / today / yesterday）。"""
    if not value:
        return False
    v = str(value).strip().lower()
    return bool(_REL_RE.match(v)) or v in ("today", "now", "yesterday")


def resolve_window(since: Optional[str], until: Optional[str], default_days: int = 7):
    """
    返回 (since_date, until_date)，until_date 为用户语义上的「含当天」上界。

    规则（优先级从上到下）：
      - since 是相对写法（7d/2w/3m）→ since = today - N，until = today
        （「最近两周」的正确解读；不能把 2w 当成上界）
      - 只给绝对 since → until = today
      - 只给 until → since = until - default_days
      - 都不给 → since = today - default_days, until = today
    """
    s = parse_date(since, default=None)
    u = parse_date(until, default=None)

    if s is not None and is_relative(since):
        # 「最近 2 周」= since 起算到今天；若同时显式给了 until，则以 until 为准
        u = u if u is not None else today_utc()
    elif s is None and u is None:
        u = today_utc()
        s = u - _dt.timedelta(days=default_days)
    elif s is None:
        s = u - _dt.timedelta(days=default_days)
    elif u is None:
        u = today_utc()

    if s > u:
        raise ValueError(f"起始日期 {s} 晚于结束日期 {u}")
    return s, u


# ---------------------------------------------------------------- 查询构造

def build_query(
    keyword: str,
    *,
    min_likes: Optional[int] = None,
    since: Optional[_dt.date] = None,
    until: Optional[_dt.date] = None,
    lang: Optional[str] = None,
    min_retweets: Optional[int] = None,
    min_replies: Optional[int] = None,
    exclude_retweets: bool = True,
    exclude_replies: bool = True,
    extra: Optional[Iterable[str]] = None,
    until_inclusive: bool = True,
) -> str:
    """
    构造 X 高级搜索查询串。

    注意 until: 在 X 中是「不包含」语义，因此 until_inclusive=True 时自动 +1 天，
    让用户说「到 9 月 30 日」时能真正包含 9 月 30 日。
    """
    kw = (keyword or "").strip()
    if not kw:
        raise ValueError("keyword 不能为空")

    parts: List[str] = [kw]
    if min_likes is not None and int(min_likes) > 0:
        parts.append(f"min_faves:{int(min_likes)}")
    if min_retweets:
        parts.append(f"min_retweets:{int(min_retweets)}")
    if min_replies:
        parts.append(f"min_replies:{int(min_replies)}")

    if since:
        parts.append(f"since:{since.isoformat()}")
    if until:
        end = until + _dt.timedelta(days=1) if until_inclusive else until
        parts.append(f"until:{end.isoformat()}")

    if lang:
        parts.append(f"lang:{lang.strip().lower()}")

    if exclude_retweets:
        parts.append("-is:retweet")
    if exclude_replies:
        parts.append("-filter:replies")

    for e in _as_extra_list(extra):
        parts.append(e)

    return " ".join(parts)


def _as_extra_list(extra: Any) -> List[str]:
    """兼容 str / list / None 三种入参，避免把字符串当可迭代对象逐字符拆开。"""
    if not extra:
        return []
    if isinstance(extra, str):
        return [x for x in (extra.strip(),) if x]
    out = []
    for e in extra:
        e = (e or "").strip() if isinstance(e, str) else str(e).strip()
        if e:
            out.append(e)
    return out


def search_url(query: str, tab: str = "top") -> str:
    """构造 x.com 搜索结果页 URL。tab: top | latest | media"""
    from urllib.parse import quote
    f = {"top": "top", "latest": "live", "media": "media"}.get(tab, "top")
    return f"https://x.com/search?q={quote(query)}&src=typed_query&f={f}"


# ---------------------------------------------------------------- 归一化

def _as_int(v: Any) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


def parse_count_text(text: str) -> int:
    """
    把 "1,234" / "12.3K" / "1.2M" / "1.2万" / "3千" 这类展示值还原成整数。
    """
    if text is None:
        return 0
    s = str(text).strip().replace(",", "").replace(" ", "")
    if not s:
        return 0
    m = re.match(r"^([\d.]+)\s*([KkMmBb万万千])?", s)
    if not m:
        return 0
    num = float(m.group(1))
    unit = (m.group(2) or "").lower()
    mult = {"k": 1_000, "m": 1_000_000, "b": 1_000_000_000, "万": 10_000, "千": 1_000}.get(unit, 1)
    return int(num * mult)


def normalize_tweet(raw: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    把不同后端抓到的原始对象统一成：
    {id, url, author, author_name, text, created_at, likes, retweets, replies, views, source}
    """
    if not raw:
        return None

    tid = str(raw.get("id") or raw.get("id_str") or raw.get("tweet_id") or "").strip()
    text = raw.get("text") or raw.get("full_text") or raw.get("note_tweet") or ""
    text = str(text).strip()
    if not tid and not text:
        return None

    handle = str(raw.get("author") or raw.get("screen_name") or raw.get("username") or "").lstrip("@")
    url = raw.get("url") or (f"https://x.com/{handle}/status/{tid}" if handle and tid
                             else (f"https://x.com/i/web/status/{tid}" if tid else ""))

    likes = raw.get("likes")
    likes = parse_count_text(likes) if isinstance(likes, str) else _as_int(likes)

    created = raw.get("created_at") or raw.get("time") or ""
    created = _norm_created_at(str(created))

    return {
        "id": tid,
        "url": url,
        "author": handle,
        "author_name": str(raw.get("author_name") or raw.get("name") or "").strip(),
        "text": re.sub(r"\s+\n", "\n", text).strip(),
        "created_at": created,
        "likes": likes,
        "retweets": _as_int(raw.get("retweets") if not isinstance(raw.get("retweets"), str)
                            else parse_count_text(raw["retweets"])),
        "replies": _as_int(raw.get("replies") if not isinstance(raw.get("replies"), str)
                           else parse_count_text(raw["replies"])),
        "views": _as_int(raw.get("views") if not isinstance(raw.get("views"), str)
                         else parse_count_text(raw["views"])),
        "source": raw.get("source") or raw.get("backend") or "",
    }


def _norm_created_at(value: str) -> str:
    """统一成 ISO8601（UTC）。支持 "Wed Oct 10 20:19:24 +0000 2018" 与 ISO 两种。"""
    if not value:
        return ""
    v = value.strip()
    if re.match(r"^\d{4}-\d{2}-\d{2}T", v):
        return v.replace("Z", "+00:00")
    try:
        dt = _dt.datetime.strptime(v, "%a %b %d %H:%M:%S %z %Y")
        return dt.astimezone(_dt.timezone.utc).isoformat(timespec="seconds")
    except ValueError:
        pass
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return _dt.datetime.strptime(v, fmt).replace(tzinfo=_dt.timezone.utc).isoformat(timespec="seconds")
        except ValueError:
            continue
    return v


# ---------------------------------------------------------------- 过滤排序

def tweet_date(item: Dict[str, Any]) -> Optional[_dt.date]:
    v = item.get("created_at") or ""
    if not v:
        return None
    try:
        return _dt.datetime.fromisoformat(v.replace("Z", "+00:00")).astimezone(_dt.timezone.utc).date()
    except ValueError:
        return None


def dedupe(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """按 id 去重；无 id 时按正文前 80 字符兜底去重。"""
    seen, out = set(), []
    for it in items:
        key = it.get("id") or (it.get("text") or "")[:80]
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(it)
    return out


def filter_items(
    items: List[Dict[str, Any]],
    *,
    min_likes: int = 0,
    since: Optional[_dt.date] = None,
    until: Optional[_dt.date] = None,
    keyword: str = "",
) -> List[Dict[str, Any]]:
    """二次校验：点赞阈值 + 时间窗 + 关键字（防止后端返回超范围结果）。"""
    kw = (keyword or "").lower()
    out = []
    for it in items:
        if it.get("likes", 0) < int(min_likes or 0):
            continue
        d = tweet_date(it)
        if d:
            if since and d < since:
                continue
            if until and d > until:
                continue
        if kw and kw not in (it.get("text") or "").lower():
            # 关键字可能只出现在被截断/引用部分，这里放宽：仅当正文完全不含才丢弃
            if kw not in json.dumps(it, ensure_ascii=False).lower():
                continue
        out.append(it)
    return out


def rank_by_likes(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """按点赞降序（红涨绿跌无关，纯热度排序）。"""
    return sorted(items, key=lambda x: (x.get("likes", 0), x.get("retweets", 0)), reverse=True)


# ---------------------------------------------------------------- 输出渲染

def to_markdown(
    items: List[Dict[str, Any]],
    *,
    keyword: str,
    query: str,
    since: Optional[_dt.date],
    until: Optional[_dt.date],
    min_likes: int,
    backend: str,
    link: str = "",
    top_n: int = 20,
) -> str:
    now = _dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    win = f"{since} ~ {until}" if since and until else "-"
    L: List[str] = []
    L.append(f"# 🔥 X 高赞推文 · {keyword}")
    L.append("")
    L.append("| 项 | 值 |")
    L.append("|---|---|")
    L.append(f"| 关键词 | `{keyword}` |")
    L.append(f"| 时间范围 (UTC) | {win} |")
    L.append(f"| 点赞阈值 | ≥ {min_likes} |")
    L.append(f"| 命中条数 | {len(items)} |")
    L.append(f"| 数据来源 | {backend} |")
    L.append(f"| 检索式 | `{query}` |")
    if link:
        L.append(f"| 原始搜索页 | [打开 X 搜索结果]({link}) |")
    L.append(f"| 生成时间 | {now} |")
    L.append("")

    if not items:
        L.append("> ⚠️ 本次未命中任何满足条件的推文。可尝试：降低点赞阈值、放宽时间范围、"
                 "或改用 `--kw-mode or` 拆分关键词。")
        return "\n".join(L)

    L.append("## 📊 热度排行（待补中文摘要）")
    L.append("")
    L.append("| # | 作者 | 点赞 | 转发 | 时间(UTC) | 原文片段 |")
    L.append("|---|---|---|---|---|---|")
    for i, it in enumerate(items[:top_n], 1):
        snippet = re.sub(r"\s+", " ", it.get("text") or "")[:60].replace("|", "\\|")
        author = f"@{it['author']}" if it.get("author") else "(未知)"
        L.append(
            f"| {i} | [{author}](https://x.com/{it.get('author','')}) | "
            f"**{it.get('likes',0):,}** | {it.get('retweets',0):,} | "
            f"{(it.get('created_at') or '')[:16].replace('T',' ')} | {snippet} |"
        )
    L.append("")
    L.append("---")
    L.append("")
    L.append(f"## 📝 明细（Top {min(top_n, len(items))}）")
    L.append("")

    for i, it in enumerate(items[:top_n], 1):
        L.append(f"### {i}. @{it.get('author') or '?'} · {it.get('likes',0):,} 赞")
        L.append("")
        body = (it.get("text") or "").strip()
        L.append(body if body else "(无正文)")
        L.append("")
        if it.get("url"):
            L.append(f"[→ 查看原推]({it['url']})")
            L.append("")
        L.append(f"<sub>点赞 {it.get('likes',0):,} · 转发 {it.get('retweets',0):,} · "
                 f"回复 {it.get('replies',0):,} · 时间 {it.get('created_at') or '?'}</sub>")
        L.append("")
        L.append("---")
        L.append("")

    if len(items) > top_n:
        L.append(f"> 剩余 {len(items) - top_n} 条见同名 `.json` 文件。")
        L.append("")
    return "\n".join(L)


def to_json_payload(
    items: List[Dict[str, Any]],
    *,
    keyword: str,
    query: str,
    since: Optional[_dt.date],
    until: Optional[_dt.date],
    min_likes: int,
    backend: str,
    link: str = "",
) -> Dict[str, Any]:
    return {
        "meta": {
            "keyword": keyword,
            "query": query,
            "since": since.isoformat() if since else None,
            "until": until.isoformat() if until else None,
            "min_likes": min_likes,
            "backend": backend,
            "search_url": link,
            "count": len(items),
            "generated_at": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
        },
        "items": items,
    }
