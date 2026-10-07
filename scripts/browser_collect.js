#!/usr/bin/env node
/**
 * browser_collect.js — 用 Playwright 打开 X 搜索结果页并采集推文结构化数据。
 *
 * 采集策略（双通道，互为兜底）：
 *   通道 A：监听 SearchTimeline GraphQL 响应，直接拿到完整 JSON（推荐，字段全、含真实点赞数）
 *   通道 B：解析 DOM（article[data-testid="tweet"]），当 GraphQL 未被捕获时兜底
 *
 * 使用持久化用户目录（profile）复用登录态 —— X 未登录搜索已被严格限制。
 *
 * 用法：
 *   node browser_collect.js --url "<x.com search url>" --out result.json [options]
 *
 * 选项：
 *   --profile <dir>    持久化用户目录（默认 ~/.workbuddy/skill-data/x-search-posts/chrome-profile）
 *   --out <file>       输出 JSON 路径（默认 ./x_raw.json）
 *   --headed           显示浏览器窗口（首次登录 / 反爬更强时使用）
 *   --login            登录模式：打开登录页并等待登录完成，然后退出
 *   --scrolls <n>      最大滚动次数（默认 8）
 *   --max <n>          采够多少条就停止（默认 120）
 *   --timeout <sec>    登录模式等待秒数（默认 300；0 表示无限等待，适合交给用户慢慢登录）
 *   --channel <name>   浏览器通道：chrome | msedge | chromium（默认自动：chrome → chromium）
 *   --since <date>     早于该日期的推文出现时提前停止滚动（YYYY-MM-DD）
 *   --quiet            只输出最终 JSON 路径
 */
'use strict';

const fs = require('fs');
const os = require('os');
const path = require('path');

function loadPlaywright() {
  const candidates = [
    'playwright',
    path.join(os.homedir(), '.workbuddy', 'binaries', 'node', 'workspace', 'node_modules', 'playwright'),
    path.join(__dirname, '..', 'node_modules', 'playwright'),
  ];
  for (const c of candidates) {
    try { return require(c); } catch (e) { /* try next */ }
  }
  return null;
}

function parseArgs(argv) {
  const o = { scrolls: 8, max: 120, timeout: 300, quiet: false, headed: false, login: false };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    const next = () => argv[++i];
    switch (a) {
      case '--url': o.url = next(); break;
      case '--out': o.out = next(); break;
      case '--profile': o.profile = next(); break;
      case '--channel': o.channel = next(); break;
      case '--since': o.since = next(); break;
      case '--scrolls': o.scrolls = parseInt(next(), 10); break;
      case '--max': o.max = parseInt(next(), 10); break;
      case '--timeout': o.timeout = parseInt(next(), 10); break;
      case '--headed': o.headed = true; break;
      case '--login': o.login = true; break;
      case '--quiet': o.quiet = true; break;
      default: break;
    }
  }
  return o;
}

function log(o, ...m) { if (!o.quiet) console.error('[collect]', ...m); }

/* ----------------------------------------------------------- 数据归一化 */

function parseCountText(text) {
  if (text === null || text === undefined) return 0;
  const s = String(text).replace(/,/g, '').replace(/\s/g, '');
  const m = s.match(/^([\d.]+)\s*([KkMmBb万千]?)/);
  if (!m) return 0;
  const num = parseFloat(m[1]);
  const mult = { k: 1e3, m: 1e6, b: 1e9, '万': 1e4, '千': 1e3 }[(m[2] || '').toLowerCase()] || 1;
  return Math.round(num * mult);
}

function fromGraphql(node) {
  let r = node;
  // 转推包装
  if (r.legacy && r.legacy.retweeted_status_result) {
    r = r.legacy.retweeted_status_result.result || r;
  }
  // 可见性受限的推文
  if (r.tweet && !r.legacy) r = r.tweet;
  const legacy = r.legacy || {};
  const text = (r.note_tweet && r.note_tweet.note_tweet_results &&
    r.note_tweet.note_tweet_results.result && r.note_tweet.note_tweet_results.result.text)
    || legacy.full_text || '';
  const id = String(r.rest_id || legacy.id_str || '');
  const user = (r.core && r.core.user_results && r.core.user_results.result) || {};
  const screen = (user.core && user.core.screen_name) || (user.legacy && user.legacy.screen_name) || '';
  if (!id && !text) return null;
  return {
    id,
    url: screen && id ? `https://x.com/${screen}/status/${id}` : '',
    author: screen,
    author_name: (user.core && user.core.name) || (user.legacy && user.legacy.name) || '',
    text,
    created_at: legacy.created_at || '',
    likes: legacy.favorite_count || 0,
    retweets: legacy.retweet_count || 0,
    replies: legacy.reply_count || 0,
    views: (r.views && r.views.count) || 0,
    source: 'graphql',
  };
}

function walkGraphql(node, out, depth) {
  if (!node || typeof node !== 'object' || depth > 24) return;
  if (Array.isArray(node)) { for (const v of node) walkGraphql(v, out, depth + 1); return; }
  const legacy = node.legacy;
  if (legacy && typeof legacy === 'object' &&
      (Object.prototype.hasOwnProperty.call(legacy, 'full_text') ||
       Object.prototype.hasOwnProperty.call(legacy, 'favorite_count'))) {
    const t = fromGraphql(node);
    if (t && t.id) out.push(t);
  }
  for (const k of Object.keys(node)) {
    const v = node[k];
    if (v && typeof v === 'object') walkGraphql(v, out, depth + 1);
  }
}

/* ----------------------------------------------------------- DOM 兜底 */

const DOM_EXTRACT = `(() => {
  const out = [];
  for (const a of document.querySelectorAll('article[data-testid="tweet"]')) {
    const link = a.querySelector('a[href*="/status/"]');
    const href = link ? link.getAttribute('href') : '';
    const m = href && href.match(/\\/([^\\/]+)\\/status\\/(\\d+)/);
    const timeEl = a.querySelector('time');
    const textEl = a.querySelector('[data-testid="tweetText"]');
    const likeEl = a.querySelector('[data-testid="like"]');
    let likes = 0;
    if (likeEl) {
      const lbl = likeEl.getAttribute('aria-label') || '';
      const cnt = likeEl.querySelector('[data-testid="app-text-transition-container"]');
      const raw = lbl || (cnt ? cnt.textContent : '') || '';
      const mm = String(raw).replace(/,/g, '').match(/([\\d.]+\\s*[KkMmBb万千]?)/);
      if (mm) {
        const num = parseFloat(mm[1]);
        const u = (mm[1].replace(/[\\d.\\s]/g, '') || '').toLowerCase();
        likes = Math.round(num * ({k:1e3, m:1e6, b:1e9, '万':1e4, '千':1e3}[u] || 1));
      }
    }
    out.push({
      id: m ? m[2] : '',
      url: href ? 'https://x.com' + href : '',
      author: m ? m[1] : '',
      author_name: '',
      text: textEl ? textEl.innerText : '',
      created_at: timeEl ? (timeEl.getAttribute('datetime') || '') : '',
      likes, retweets: 0, replies: 0, views: 0,
      source: 'dom'
    });
  }
  return out;
})()`;

/* ----------------------------------------------------------- 主流程 */

async function launch(playwright, o) {
  const profile = o.profile || path.join(os.homedir(), '.workbuddy', 'skill-data', 'x-search-posts', 'chrome-profile');
  fs.mkdirSync(profile, { recursive: true });
  const channels = o.channel ? [o.channel] : ['chrome', 'msedge', 'chromium'];
  let lastErr;
  for (const ch of channels) {
    try {
      const ctx = await playwright.chromium.launchPersistentContext(profile, {
        channel: ch,
        headless: !o.headed && !o.login,
        viewport: { width: 1280, height: 900 },
        locale: 'zh-CN',
        args: ['--disable-blink-features=AutomationControlled', '--no-first-run', '--no-default-browser-check'],
      });
      log(o, `浏览器通道: ${ch}，profile: ${profile}`);
      return { ctx, channel: ch };
    } catch (e) {
      lastErr = e;
      log(o, `通道 ${ch} 启动失败: ${String(e.message).split('\n')[0]}`);
    }
  }
  throw new Error(`无法启动浏览器。请先执行安装：npm exec playwright install chromium\n原始错误: ${lastErr && lastErr.message}`);
}

async function isLoggedIn(ctx) {
  const cookies = await ctx.cookies('https://x.com');
  return cookies.some((c) => c.name === 'auth_token' && c.value);
}

async function loginFlow(playwright, o) {
  const { ctx } = await launch(playwright, { ...o, login: true, headed: true });
  const page = ctx.pages()[0] || (await ctx.newPage());
  await page.goto('https://x.com/login', { waitUntil: 'domcontentloaded' }).catch(() => {});
  const unlimited = !o.timeout || o.timeout <= 0;
  log(o, unlimited
    ? '请在弹出的浏览器窗口中登录 X。登录窗口会一直等待，登录成功即自动保存。'
    : `请在弹出的浏览器窗口中登录 X。最多等待 ${o.timeout} 秒…`);

  const deadline = unlimited ? Infinity : Date.now() + o.timeout * 1000;
  while (Date.now() < deadline) {
    let ok = false;
    try {
      ok = await isLoggedIn(ctx);
    } catch (e) {
      // 窗口被关闭 / 上下文销毁 —— 优雅退出，不要把异常抛给上层
      log(o, '⚠️ 浏览器窗口已关闭，登录未完成。需要时重新运行 --login 即可。');
      return 5;
    }
    if (ok) {
      log(o, '✅ 登录成功，登录态已保存到 profile 目录。');
      await ctx.close().catch(() => {});
      return 0;
    }
    await page.waitForTimeout(3000).catch(() => {});
  }
  log(o, `❌ 等待超时（${o.timeout} 秒），未检测到登录态。可用 --timeout 0 无限等待后重试。`);
  await ctx.close().catch(() => {});
  return 2;
}

async function collect(playwright, o) {
  if (!o.url) throw new Error('缺少 --url 参数');
  const { ctx, channel } = await launch(playwright, o);
  const page = ctx.pages()[0] || (await ctx.newPage());

  if (!(await isLoggedIn(ctx))) {
    await ctx.close();
    const err = new Error(
      'NOT_LOGGED_IN: 未检测到 X 登录态。X 已限制未登录搜索，请先运行登录模式：\n' +
      '  node browser_collect.js --login'
    );
    err.code = 'NOT_LOGGED_IN';
    throw err;
  }

  const captured = [];
  const seenResp = new Set();
  page.on('response', (resp) => {
    const u = resp.url();
    if (!/\/graphql\/[^/]+\/(SearchTimeline|TweetDetail|UserTweets|SearchAdaptive)/.test(u)) return;
    if (seenResp.has(u)) return;
    seenResp.add(u);
    resp.json().then((j) => {
      try { walkGraphql(j, captured, 0); } catch (e) { /* ignore */ }
    }).catch(() => {});
  });

  log(o, `打开: ${o.url}`);
  await page.goto(o.url, { waitUntil: 'domcontentloaded', timeout: 60000 }).catch((e) => log(o, `goto 警告: ${e.message}`));

  // 处理可能的「敏感内容」/「年龄确认」中间页
  try {
    const confirm = page.locator('div[role="button"]:has-text("查看"), div[role="button"]:has-text("View"), div[role="button"]:has-text("Yes, view profile")').first();
    if (await confirm.isVisible({ timeout: 2500 })) { await confirm.click().catch(() => {}); }
  } catch (e) { /* ignore */ }

  await page.waitForTimeout(4000);

  const domMap = new Map();
  const sinceMs = o.since ? Date.parse(o.since + 'T00:00:00Z') : 0;

  for (let i = 0; i <= o.scrolls; i++) {
    // page.evaluate 传字符串表达式，返回值一定是可序列化的普通数组；
    // 传函数时在某些情况下会返回非数组（undefined/序列化异常），导致 for..of 报 "not iterable"。
    let batch = [];
    try {
      const r = await page.evaluate(DOM_EXTRACT);
      if (Array.isArray(r)) batch = r;
      else log(o, `⚠️ DOM 提取返回非数组（${typeof r}），本轮跳过`);
    } catch (e) {
      log(o, `⚠️ DOM 提取失败：${String(e.message).split('\n')[0]}`);
    }
    for (const t of (Array.isArray(batch) ? batch : [])) if (t && t.id) domMap.set(t.id, t);

    const total = captured.length + domMap.size;
    log(o, `第 ${i} 轮：graphql=${captured.length} dom=${domMap.size} 合计≈${total}`);
    if (total >= o.max) break;

    // 滚到底部触发下一批加载
    await page.keyboard.press('End').catch(() => {});
    await page.mouse.wheel(0, 3000).catch(() => {});
    await page.waitForTimeout(2200 + Math.floor(Math.random() * 900));

    // 一旦出现早于 since 的推文，说明已翻出时间窗，可以停止
    if (sinceMs) {
      const dates = [...domMap.values()].map((t) => Date.parse(t.created_at || '')).filter((x) => !isNaN(x));
      if (dates.length && Math.min(...dates) < sinceMs - 86400000 * 2) {
        log(o, '已翻过早于 since 的推文，停止滚动。');
        break;
      }
    }
  }

  const dom = [...domMap.values()];
  const graphql = captured;
  const hasGraphql = graphql.length > 0;
  const merged = hasGraphql ? graphql : dom;

  // GraphQL 数据更全：用 DOM 里的 created_at / 点赞做补全
  if (hasGraphql && dom.length) {
    const byId = new Map(dom.map((d) => [d.id, d]));
    for (const g of merged) {
      const d = byId.get(g.id);
      if (!d) continue;
      if (!g.created_at) g.created_at = d.created_at;
      if (!g.likes) g.likes = d.likes;
      if (!g.text) g.text = d.text;
    }
  }

  await ctx.close();

  const payload = {
    meta: {
      url: o.url,
      channel,
      profile: o.profile || path.join(os.homedir(), '.workbuddy', 'skill-data', 'x-search-posts', 'chrome-profile'),
      scraped_at: new Date().toISOString(),
      via: hasGraphql ? 'graphql' : 'dom',
      count: merged.length,
      elapsed_scrolls: o.scrolls,
    },
    items: merged,
  };

  const out = o.out || path.join(process.cwd(), 'x_raw.json');
  fs.mkdirSync(path.dirname(path.resolve(out)), { recursive: true });
  fs.writeFileSync(out, JSON.stringify(payload, null, 2), 'utf8');
  if (o.quiet) {
    process.stdout.write(out + '\n');
  } else {
    log(o, `✅ 采集完成：${merged.length} 条（通道 ${payload.meta.via}）→ ${out}`);
    process.stdout.write(JSON.stringify({ ok: true, out, count: merged.length, via: payload.meta.via }) + '\n');
  }
  return 0;
}

if (require.main === module) {
  (async () => {
    const o = parseArgs(process.argv.slice(2));
    const playwright = loadPlaywright();
    if (!playwright) {
      process.stderr.write(
        'PLAYWRIGHT_MISSING: 未找到 playwright 模块。请执行：\n' +
        '  cd "%USERPROFILE%/.workbuddy/binaries/node/workspace"\n' +
        '  npm install playwright && npx playwright install chromium\n'
      );
      process.exit(3);
    }
    try {
      process.exit(o.login ? await loginFlow(playwright, o) : await collect(playwright, o));
    } catch (e) {
      process.stderr.write(String((e && e.message) || e) + '\n');
      process.exit(e && e.code === 'NOT_LOGGED_IN' ? 4 : 1);
    }
  })();
}

module.exports = { walkGraphql, fromGraphql, parseCountText, parseArgs, DOM_EXTRACT };
