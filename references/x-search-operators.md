# X（Twitter）高级搜索运算符速查

X 搜索结果页与官方 API 都接受这套运算符。本 skill 的三个自定义参数正是映射到其中的三个：

| 用户参数 | 映射为 | 说明 |
|---|---|---|
| 关键字 | 原样进入查询串 | 可直接写运算符，skill 不做转义 |
| 时间 | `since:YYYY-MM-DD` + `until:YYYY-MM-DD` | 见下方「时间边界陷阱」 |
| 点赞数 | `min_faves:N` | N 为下限，可自定义 |

## 参与度

| 运算符 | 作用 | 示例 |
|---|---|---|
| `min_faves:N` | 点赞数 **至少** N | `人工智能 min_faves:1000` |
| `min_retweets:N` | 转推数至少 N | `min_retweets:50` |
| `min_replies:N` | 回复数至少 N | `min_replies:25` |
| `-min_faves:N` | 点赞数 **至多** N（上限） | `-min_faves:5000` |

> ⚠️ `min_faves` 系列是社区长期验证但**未被 X 官方文档承诺**的运算符。X 界面上的互动数在超过约 1000 后会做近似展示，但搜索过滤本身仍按精确值工作。

## 时间

| 运算符 | 语义 | 示例 |
|---|---|---|
| `since:YYYY-MM-DD` | **包含**该日 | `since:2026-09-01` |
| `until:YYYY-MM-DD` | **不包含**该日 | `until:2026-10-01` |

### 时间边界陷阱（本 skill 已自动处理）

`until:` 是排他语义。用户说「9 月 1 日到 9 月 30 日」时，正确查询是：

```
since:2026-09-01 until:2026-10-01
```

而不是 `until:2026-09-30`（那样会漏掉整个 9 月 30 日）。
`x_search.py` 默认自动 +1 天（`--until-exclusive` 可关闭该行为）。

日期按 **UTC** 计算，与本地时区可能差一天。

## 账号

| 运算符 | 作用 | 示例 |
|---|---|---|
| `from:user` | 指定账号发出 | `from:naval` |
| `to:user` | 回复某账号 | `to:stripe` |
| `@user` | 提及某账号 | `@stripe` |
| `list:<id>` | 某公开列表成员 | `list:1234567890` |
| `filter:verified` / `filter:blue_verified` | 仅认证账号 | `AI filter:blue_verified` |

## 内容类型

| 运算符 | 作用 |
|---|---|
| `-is:retweet` | 排除转推（**本 skill 默认启用**） |
| `-filter:replies` | 排除回复（**本 skill 默认启用**） |
| `filter:media` / `filter:images` / `filter:videos` | 含媒体 |
| `filter:links` | 含链接 |
| `filter:quote` | 引用推文 |
| `is:quote` / `is:reply` | 仅引用 / 仅回复 |
| `url:domain` | 链接到指定域名（连字符换成下划线） |

## 语言与地点

| 运算符 | 作用 | 示例 |
|---|---|---|
| `lang:xx` | 语言 | `lang:zh`、`lang:en` |
| `near:city within:15km` | 地点与半径 | `near:深圳 within:25km` |

> `near:` 依赖推文自带定位数据，覆盖极稀疏，只适合本地活动类检索。

## 组合原则

运算符是「层层收窄」的关系。推荐叠加顺序：

1. 关键词（核心词 + `OR` / 引号短语）
2. `-is:retweet -filter:replies`（去掉噪音）
3. `since:` / `until:`（时间窗）
4. `min_faves:N`（按热度收口）
5. `lang:` / `filter:links` 等（按内容形态收口）

### 可直接套用的模板

```
# 中文圈高赞讨论
"大模型" OR "AI 应用" min_faves:1000 lang:zh -is:retweet -filter:replies since:2026-09-01 until:2026-10-01

# 某公司被提及且点赞过千（排除官方号自吹）
("Tesla" OR "特斯拉") min_faves:2000 -from:Tesla lang:zh since:2026-01-01

# 热门长文/带链接内容
"AI agent" min_faves:500 filter:links lang:en -is:retweet
```

## 检索式的固有局限

- X 搜索**不等于完整集合**：不索引全部历史内容，被限流的账号可能不出现。
- 未登录搜索已被严格限制，`x_search.py` 必须使用已登录会话或官方 API。
- 若查询返回过少，优先**去掉参与度运算符**排查，再逐个加回。
