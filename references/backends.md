# 后端选择与故障排查

`x_search.py` 把「怎么把数据取回来」和「怎么加工数据」解耦。取数有三条链路，加工（过滤 / 去重 / 排序 / 出报告）永远由同一套确定性代码完成。

| 后端 | 依赖 | 覆盖时间 | 点赞数精度 | 适用场景 |
|---|---|---|---|---|
| `api` | 环境变量 `X_BEARER_TOKEN`（付费档位） | **仅最近 7 天**（recent search） | 精确 | 有 API 权限、要自动化跑批 |
| `browser` | Node + Playwright + 一次性登录 | 任意历史（受搜索索引限制） | 精确（GraphQL）/ 近似（DOM 兜底） | 默认推荐，免费 |
| `offline` | 无 | 取决于输入文件 | 取决于输入文件 | 手工采集后二次加工、结果复现 |

`--backend auto`（默认）的判定顺序：有 `X_BEARER_TOKEN` → 走 `api`；否则 → 走 `browser`。

---

## browser 后端

### 一次性登录

X 已限制未登录搜索，必须先登录并保存会话：

```bash
node scripts/browser_collect.js --login --timeout 0
```

`--timeout 0` = 无限等待（推荐，交给用户按自己的节奏登录）；默认等 300 秒。

会弹出真实浏览器窗口，手动完成登录（含二次验证）即可。脚本每 3 秒轮询一次 `auth_token` cookie，检测到后自动保存到 profile 目录并退出：

```
%USERPROFILE%\.workbuddy\skill-data\x-search-posts\chrome-profile
```

之后所有采集都复用该 profile，无需重复登录。会话过期时重复该命令即可。

退出码：`0` 登录成功 / `2` 等待超时 / `5` 用户主动关闭了窗口（均可用同一命令重试）。

> 用的是独立的 profile 目录，因此**不会**、也无法复用你日常 Chrome 里已登录的 X 会话——Chrome 会锁定默认 profile。手动登录一次是必要成本。

### 采集机制

1. 打开 `https://x.com/search?q=<检索式>&f=top`
2. **通道 A**：监听 `SearchTimeline` GraphQL 响应，直接解析完整 JSON（拿到的是精确 `favorite_count`）
3. **通道 B**：若 GraphQL 未被捕获，回退解析 `article[data-testid="tweet"]` DOM（点赞数为界面近似值）
4. 按 `End` / 滚轮翻页，直到达到 `--max-items` 或翻出时间窗下界
5. 两通道结果按推文 ID 合并，GraphQL 优先

采集速度约 **每条 0.2~0.5 秒**，120 条约需 60~90 秒。脚本内置随机等待以降低风控概率。

### 已安装组件（本机）

| 组件 | 位置 / 版本 |
|---|---|
| Playwright（Node） | `%USERPROFILE%\.workbuddy\binaries\node\workspace\node_modules\playwright` |
| Chromium 内核 | `%LOCALAPPDATA%\ms-playwright\` |

缺组件时的重装命令：

```bash
cd "%USERPROFILE%\.workbuddy\binaries\node\workspace"
npm install playwright
npx playwright install chromium
```

### 常见故障

| 现象 | 原因 | 处理 |
|---|---|---|
| `NOT_LOGGED_IN` | profile 无登录态或已过期 | 执行 `--login` 重新登录 |
| `PLAYWRIGHT_MISSING` | 缺 Node 版 Playwright | 按上表重装 |
| 采集 0 条但页面有结果 | 全屏遮罩（敏感内容 / 年龄确认）未点掉 | 加 `--headed` 观察，必要时手动点一次并保留 profile |
| GraphQL 通道为空、仅 DOM | 接口版本变化或响应被跳过 | DOM 兜底仍可用；点赞数为近似值，报告中注明 |
| 弹出 «Something went wrong» | 翻页过快触发限流 | 降低 `--scrolls`，隔几分钟重试 |
| Chrome 通道启动失败 | 未安装 Chrome | 脚本会自动回退 `msedge` → 内置 `chromium` |

> **风控提示**：高频、大批量采集可能触发账号临时限制。建议单次 ≤ 200 条、单日不超过若干轮，避免用主账号做大规模抓取。

---

## api 后端

需要 X 开发者平台的 Bearer Token（Basic 档位及以上）。配置：

```bash
setx X_BEARER_TOKEN "AAAA..."
```

或临时注入：`X_BEARER_TOKEN=xxx python x_search.py ...`

限制与注意事项：

- `/2/tweets/search/recent` **只覆盖最近 7 天**。超出窗口会返回空结果，此时改用 `browser` 后端。
- `min_faves` 不是 API 官方运算符，`x_search.py` 会自动从 API 查询串中剥离它，改在本地按 `public_metrics.like_count` 过滤，结果等价。
- 错误码：`401` Token 失效；`403` 档位不足；`429` 限速（脚本已内置 0.6s 间隔）。

---

## offline 后端（零依赖兜底）

当既没有 API Token、浏览器又暂时不可用时，可以由 Agent 直接用内置浏览器技能（`playwright-cli` 或 `agent-browser`）打开搜索页，把抓到的内容整理成 JSON 再交给本 skill 加工：

```bash
python scripts/x_search.py --keyword "AI agent" --since 7d --min-likes 1000 --from-json raw.json
```

接受的 JSON 格式（字段尽量给全，缺失字段会被安全忽略）：

```json
{
  "items": [
    {
      "id": "1234567890",
      "author": "sama",
      "text": "推文正文……",
      "created_at": "2026-09-28T12:30:00Z",
      "likes": 5200,
      "retweets": 610,
      "replies": 88,
      "url": "https://x.com/sama/status/1234567890"
    }
  ]
}
```

`likes` 支持 `5200` 数字，也支持 `"5.2K"` / `"1.2万"` 这类界面文案，会自动换算。

> 离线模式下 `--min-likes` / `--since` / `--until` 会被**重新执行一遍**，因此可以把抓取范围放宽、再用本 skill 收口，保证不同批次结果口径一致。
