#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
render_html.py — 把 x_search.py 产出的 .json 渲染成最终单文件 HTML 报告。

两种用法：

    # 单组（把 x_search 生成的带「待补摘要」占位的 HTML 升级为带摘要的终稿）
    python render_html.py --json x_hot_prompt-engineering_xxx.json \
        --summaries summaries.json --out 报告.html

    # 多组合并（--preset all 之后出一份总周报，每个 json 一个章节）
    python render_html.py --json *.json --summaries summaries.json \
        --observation "本周观察…" --title "X 高赞推文周报 2026-10-06~10-12" \
        --out x_weekly_digest_2026-10-12.html

summaries 格式：{"<推文id>": "中文摘要", ...}（扁平，按 id 匹配所有组）。
observation：报告开头的「整体观察」段落，纯文本，多个空行分段。

输出：写 --out 指定的单个 HTML 文件，stdout 打印一行结果 JSON。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

import html_report as HR  # noqa: E402


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        description="把 x_search.py 的 .json 渲染成单文件 HTML 报告（支持多组合并成周报）")
    p.add_argument("--json", nargs="+", required=True, help="一个或多个 payload .json（每组一个章节）")
    p.add_argument("--summaries", help="中文摘要映射 json：{\"<推文id>\": \"摘要\"}")
    p.add_argument("--observation", help="「整体观察」段落文本（纯文本）")
    p.add_argument("--observation-file", help="从文件读取整体观察文本（优先于 --observation）")
    p.add_argument("--title", default="X 高赞推文巡检报告", help="报告主标题")
    p.add_argument("--tag", help="头部右上角 pill 文案，默认取时间范围")
    p.add_argument("--out", required=True, help="输出 HTML 路径")
    args = p.parse_args(argv)

    try:
        payloads: List[Dict] = []
        for jf in args.json:
            payloads.append(HR.load_payload(Path(jf)))

        summaries: Dict[str, str] = {}
        if args.summaries:
            raw = json.loads(Path(args.summaries).read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raise ValueError("--summaries 文件应为 {\"<推文id>\": \"摘要\"} 形式的对象")
            summaries = {str(k): str(v) for k, v in raw.items()}

        observation = ""
        if args.observation_file:
            observation = Path(args.observation_file).read_text(encoding="utf-8")
        elif args.observation:
            observation = args.observation

        html_str = HR.render_report(
            payloads,
            title=args.title,
            tag_pill=args.tag or "",
            observation=observation,
            summaries=summaries,
        )
        out_path = Path(args.out).expanduser().resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(html_str, encoding="utf-8")

        n_sum = sum(1 for p in payloads for it in (p.get("items") or [])
                    if str(it.get("id") or "") in summaries)
        print(json.dumps({
            "ok": True,
            "out": str(out_path),
            "sections": len(payloads),
            "tweets": sum(int(p.get("meta", {}).get("count") or 0) for p in payloads),
            "summaries_filled": n_sum,
        }, ensure_ascii=False))
        return 0
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    sys.exit(main())
