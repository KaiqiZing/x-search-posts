#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
doctor.py — x-search-posts 环境自检。

按顺序检查：Python 逻辑 → Node → Playwright → 浏览器内核 → X 登录态 → API Token，
并给出针对性的修复命令。首次使用或采集失败时先跑这个。

    python doctor.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL_ROOT = HERE.parent
PROFILE = Path(os.path.expanduser("~")) / ".workbuddy" / "skill-data" / "x-search-posts" / "chrome-profile"

OK, WARN, BAD = "[OK]  ", "[WARN]", "[FAIL]"
results = []


def add(level: str, name: str, detail: str, fix: str = ""):
    results.append((level, name, detail, fix))
    print(f"{level} {name}: {detail}")
    if fix and level != OK:
        print(f"       → 修复: {fix}")


def run(cmd, **kw):
    try:
        return subprocess.run(cmd, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=kw.pop("timeout", 60), **kw)
    except Exception as exc:  # noqa: BLE001
        class R:
            returncode, stdout, stderr = 1, "", str(exc)
        return R()


def node_bin() -> str:
    managed = Path(os.path.expanduser("~")) / ".workbuddy" / "binaries" / "node" / "versions"
    if managed.is_dir():
        found = sorted(managed.glob("*/node.exe"), reverse=True)
        if found:
            return str(found[0])
    for c in [os.path.expandvars(r"%ProgramFiles%\nodejs\node.exe"),
              r"C:\nvm4w\nodejs\node.exe",
              "/usr/local/bin/node",
              "/usr/bin/node"]:
        if Path(c).exists():
            return c
    return "node"


def check_x_login():
    """
    直接查 profile 里的 Cookies 库是否存在 x.com 的 auth_token 记录。

    Chrome 未登录时也会创建空的 Cookies 库，因此不能以「文件存在」判定已登录。
    Cookie 值是加密的，但我们只需要判断记录是否存在，无需解密。
    """
    import shutil
    import sqlite3
    import tempfile

    if not PROFILE.exists():
        return False, "尚未建立（首次使用需登录一次）"

    candidates = (list(PROFILE.rglob("Network/Cookies")) + list(PROFILE.rglob("Cookies")))
    if not candidates:
        return False, "profile 存在但无 Cookies 库（首次使用需登录一次）"

    for db in candidates:
        tmp = None
        try:
            # 浏览器可能占用数据库，复制副本再查，避免锁库
            with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
                tmp = f.name
            shutil.copy2(db, tmp)
            con = sqlite3.connect(tmp)
            try:
                # 注意：Chrome 在 Windows 上把 cookie 值加密存储（DPAPI + v10/v11 前缀），
                # 因此 value 的「明文长度」恒为 0，length(value) 不能用来判断是否存在。
                # 但 encrypted_value 字段会有实际字节数，用它判断更可靠。
                rows = con.execute(
                    "SELECT host_key, name, length(value), length(encrypted_value) "
                    "FROM cookies WHERE name='auth_token' AND host_key LIKE '%x.com'"
                ).fetchall()
                for host, _, plain_len, enc_len in rows:
                    # 加密长度 > 0，或明文长度 > 0，都算有效登录态
                    if (enc_len or 0) > 0 or (plain_len or 0) > 0:
                        how = "加密存储" if (enc_len or 0) > 0 else "明文存储"
                        return True, f"已登录（auth_token 已保存，{how}，{host}）"
            finally:
                con.close()
        except Exception:  # noqa: BLE001
            continue
        finally:
            if tmp:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass

    return False, "profile 存在但未登录（未找到有效的 auth_token，需登录一次）"


def main() -> int:
    print("=" * 66)
    print("  x-search-posts 环境自检")
    print("=" * 66)

    # 1. Python 逻辑
    try:
        sys.path.insert(0, str(HERE))
        import xquery as X
        q = X.build_query("test", min_likes=1000)
        assert "min_faves:1000" in q, q
        s, u = X.resolve_window("7d", None)
        assert s < u, (s, u)
        add(OK, "Python 逻辑", f"xquery 正常，示例检索式: {q}")
    except Exception as exc:  # noqa: BLE001
        add(BAD, "Python 逻辑", str(exc), "确认 scripts/xquery.py 与 x_search.py 在同一目录")
        return 1

    # 2. Node
    nb = node_bin()
    r = run([nb, "-e", "console.log('ok')"])
    if r.returncode == 0 and "ok" in r.stdout:
        add(OK, "Node 运行时", f"{nb}")
    else:
        add(BAD, "Node 运行时", r.stderr.strip()[:120] or "无法执行",
            "安装 Node 18+，或修正 binary_context 中的 managed node 路径")

    # 3. Playwright 模块
    probe = ("const c=[%s];"
             "for(const p of c){try{const m=require(p);"
             "console.log('FOUND '+p+' '+require(p+'/package.json').version);process.exit(0)}catch(e){}}"
             "console.log('MISSING');") % ",".join(
        json.dumps(p) for p in [
            "playwright",
            os.path.expanduser("~/.workbuddy/binaries/node/workspace/node_modules/playwright").replace("\\", "/"),
        ])
    r = run([nb, "-e", probe])
    pw_ok = "FOUND" in (r.stdout or "")
    if pw_ok:
        add(OK, "Playwright 模块", (r.stdout or "").strip())
    else:
        add(BAD, "Playwright 模块", "未找到 playwright 模块",
            'cd "%USERPROFILE%\\.workbuddy\\binaries\\node\\workspace" && npm install playwright')

    # 4. 浏览器内核
    r = run([nb, "-e",
             "const p=require('playwright');try{const e=p.chromium.executablePath();"
             "require('fs').accessSync(e);console.log('EXISTS '+e)}catch(err){console.log('NOEXEC '+err.message)}"])
    out = (r.stdout or "").strip()
    if out.startswith("EXISTS"):
        add(OK, "Chromium 内核", out[7:])
    else:
        add(WARN, "Chromium 内核", (out or r.stderr).strip()[:160] or "未检测到",
            'cd "%USERPROFILE%\\.workbuddy\\binaries\\node\\workspace" && npx playwright install chromium'
            "  （若本机已装 Chrome，采集时会自动回退到 chrome 通道）")

    # 5. 登录态（真正查 auth_token，而不是只看 Cookie 文件是否存在）
    #    Chrome 即使未登录也会创建空的 Cookies 库，只看文件存在与否会误判为「已登录」。
    logged_in, login_detail = check_x_login()
    if logged_in:
        add(OK, "X 登录态", login_detail)
    else:
        add(WARN, "X 登录态", login_detail,
            f'"{nb}" "{HERE / "browser_collect.js"}" --login')

    # 6. API Token
    token = next((os.environ.get(k) for k in ("X_BEARER_TOKEN", "TWITTER_BEARER_TOKEN",
                                              "X_API_BEARER_TOKEN") if os.environ.get(k)), None)
    if token:
        add(OK, "X API Token", f"已配置（{len(token)} 字符），api 后端可用（仅最近 7 天）")
    else:
        add(WARN, "X API Token", "未配置，将使用 browser 后端（免费，可查历史）",
            'setx X_BEARER_TOKEN "<your-token>"')

    # 汇总
    bad = [r for r in results if r[0] == BAD]
    warn = [r for r in results if r[0] == WARN]
    print("-" * 66)
    if bad:
        print(f"结论: {len(bad)} 项阻塞、{len(warn)} 项提醒 —— 按上面的修复命令处理后重跑。")
        return 1
    if warn:
        print(f"结论: 可用（{len(warn)} 项提醒）。browser 后端的登录态缺失时按提示先登录一次。")
        return 0
    print("结论: 全部就绪。可以直接运行 x_search.py。")
    print(f'\n试跑: python "{HERE / "x_search.py"}" --keyword "AI agent" --since 7d --min-likes 1000')
    return 0


if __name__ == "__main__":
    sys.exit(main())
