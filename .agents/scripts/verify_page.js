#!/usr/bin/env node
/**
 * 路书页面校验 —— 通用模板，不绑定具体计划。
 *
 * 期望值来自 <plan-dir>/manifest.json，不写死在脚本里：
 *   trip.days                      → 日期标签数量
 *   budget.tiers[tier].per_person_range → 各档住宿切换后的人均数字
 *   map_guide.share_url            → 页面上必须出现的分享链接
 *
 * 覆盖：字体加载 / 日期切换 / 图片与死文件 / 预算联动 / 清单持久化 /
 *       六档宽度横向溢出 / 打印态 / 控制台错误 / 二维码解码（可选）
 *
 * 用法：
 *   NODE_PATH=<node_modules> node verify_page.js <plan-dir> [--shots <dir>]
 *
 * 依赖 playwright-core + 本机已安装的 Playwright Chromium（npx playwright install chromium）。
 * 浏览器路径按 Windows / macOS / Linux 依次查找，可用 ROADBOOK_CHROME 显式指定。
 */
const { chromium } = require('playwright-core');
const fs = require('fs');
const path = require('path');
const os = require('os');

const planDir = path.resolve(process.argv[2] || '.');
const shotsIdx = process.argv.indexOf('--shots');
const shotsDir = shotsIdx > -1 ? path.resolve(process.argv[shotsIdx + 1]) : path.join(planDir, '.shots');
const HTML = path.join(planDir, 'index.html');
const MANIFEST = path.join(planDir, 'manifest.json');
const slug = path.basename(planDir);

const norm = s => String(s == null ? '' : s).replace(/[,\s\u00a0]/g, '');
const rngToStr = r => Array.isArray(r) ? r.map(v => v.toLocaleString('en-US')).join('–') : String(r);

let pass = 0, fail = 0;
function ck(name, ok, extra) {
  if (ok) { pass++; console.log('  PASS  ' + name + (extra ? '  → ' + extra : '')); }
  else { fail++; console.log('  FAIL  ' + name + (extra ? '  → ' + extra : '')); }
}
function eq(name, got, want) { ck(name, norm(got) === norm(want), `got "${got}" want "${want}"`); }

function findChrome() {
  // 允许显式覆盖：CI、非常规安装位置、或本机 Chrome
  const override = process.env.ROADBOOK_CHROME || process.env.CHROMIUM_EXECUTABLE_PATH;
  if (override) {
    if (fs.existsSync(override)) return override;
    throw new Error(`ROADBOOK_CHROME 指向的文件不存在：${override}`);
  }

  // 各平台 Playwright 浏览器的安装根目录
  const roots = [
    process.env.PLAYWRIGHT_BROWSERS_PATH,
    path.join(os.homedir(), 'AppData', 'Local', 'ms-playwright'),   // Windows
    path.join(os.homedir(), 'Library', 'Caches', 'ms-playwright'),  // macOS
    path.join(os.homedir(), '.cache', 'ms-playwright'),             // Linux
    '/ms-playwright',                                               // Playwright 官方容器镜像
  ].filter(p => p && fs.existsSync(p));

  if (!roots.length) {
    throw new Error(
      '找不到 Playwright 浏览器目录。先装一次浏览器：npx playwright install chromium\n' +
      '  或用 ROADBOOK_CHROME=<chromium 可执行文件路径> 显式指定。'
    );
  }

  // 每个 chromium-<build> 目录下可执行文件的相对路径，按平台排列
  const bins = [
    ['chrome-win64', 'chrome.exe'],
    ['chrome-win', 'chrome.exe'],
    ['chrome-mac', 'Chromium.app', 'Contents', 'MacOS', 'Chromium'],
    ['chrome-mac-arm64', 'Chromium.app', 'Contents', 'MacOS', 'Chromium'],
    ['chrome-linux', 'chrome'],
    ['chrome-headless-shell-win64', 'chrome-headless-shell.exe'],
    ['chrome-headless-shell-mac-arm64', 'chrome-headless-shell'],
    ['chrome-headless-shell-linux64', 'chrome-headless-shell'],
  ];

  for (const root of roots) {
    const dirs = fs.readdirSync(root)
      .filter(d => /^(chromium_headless_shell|chromium)-\d+$/.test(d))
      // 完整 chromium 优先于 headless shell；同类型按构建号从新到旧
      .sort((a, b) => {
        const rank = d => (d.startsWith('chromium-') ? 0 : 1);
        if (rank(a) !== rank(b)) return rank(a) - rank(b);
        return parseInt(b.split('-')[1]) - parseInt(a.split('-')[1]);
      });
    for (const d of dirs) {
      for (const parts of bins) {
        const p = path.join(root, d, ...parts);
        if (fs.existsSync(p)) return p;
      }
    }
  }

  throw new Error(
    '在 Playwright 浏览器目录里没找到可用的 Chromium。装一次即可：npx playwright install chromium\n' +
    '  已查找：' + roots.join(' / ') + '\n' +
    '  或用 ROADBOOK_CHROME=<chromium 可执行文件路径> 显式指定。'
  );
}

(async () => {
  if (!fs.existsSync(HTML)) { console.error('找不到 ' + HTML); process.exit(2); }
  const meta = fs.existsSync(MANIFEST) ? JSON.parse(fs.readFileSync(MANIFEST, 'utf-8')) : {};
  const days = (meta.trip && meta.trip.days) || null;
  const tiers = (meta.budget && meta.budget.tiers) || null;
  const shareUrl = (meta.map_guide && meta.map_guide.share_url) || null;
  fs.mkdirSync(shotsDir, { recursive: true });

  const browser = await chromium.launch({ executablePath: findChrome() });
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  const errs = [];
  page.on('pageerror', e => errs.push('pageerror: ' + e.message));
  page.on('console', m => { if (m.type() === 'error') errs.push('console: ' + m.text()); });
  page.on('requestfailed', r => errs.push('requestfailed: ' + r.url().split('/').slice(-2).join('/')));

  await page.goto('file:///' + HTML.replace(/\\/g, '/'), { waitUntil: 'load' });
  await page.waitForTimeout(1200);
  console.log(`\n计划：${slug}`);

  /* ---------- 1. 字体 ---------- */
  console.log('\n=== 1. 字体 ===');
  const fonts = await page.evaluate(async () => {
    await document.fonts.ready;
    return {
      wenkai: document.fonts.check('16px "LXGW WenKai Screen"'),
      sarasa: document.fonts.check('16px "Sarasa Mono SC"'),
      loaded: [...document.fonts].map(f => f.family + ':' + f.status).join(', '),
    };
  });
  ck('霞鹜文楷子集已加载', fonts.wenkai, fonts.loaded);
  ck('更纱黑体子集已加载', fonts.sarasa);

  /* ---------- 2. 日期切换 ---------- */
  console.log('\n=== 2. 日期标签切换 ===');
  const tabs = await page.$$eval('.daytabs button', bs => bs.map(b => b.dataset.day));
  if (days) eq('日期标签数量 = manifest.trip.days', tabs.length, days);
  else ck('有日期标签', tabs.length > 0, tabs.join(','));
  for (const d of tabs) {
    await page.click(`.daytabs button[data-day="${d}"]`);
    await page.waitForTimeout(160);
    const on = await page.evaluate(() => [...document.querySelectorAll('.day.on')].map(x => x.id));
    const sel = await page.$eval(`.daytabs button[data-day="${d}"]`, x => x.getAttribute('aria-selected'));
    ck(`D${d}：只显示一个面板且 aria-selected=true`,
      on.length === 1 && on[0] === 'day-' + d && sel === 'true', on.join(',') + ' sel=' + sel);
  }

  /* ---------- 3. 图片 ---------- */
  console.log('\n=== 3. 图片资源 ===');
  for (const d of tabs) { await page.click(`.daytabs button[data-day="${d}"]`); await page.waitForTimeout(200); }
  const imgs = await page.evaluate(async () => {
    const all = [...document.images];
    await Promise.all(all.map(i => i.complete ? 0 : new Promise(r => { i.onload = i.onerror = r; })));
    return all.map(i => ({ src: i.getAttribute('src'), ok: i.complete && i.naturalWidth > 0 }));
  });
  const bad = imgs.filter(i => !i.ok);
  ck(`全部 ${imgs.length} 张图片加载成功`, bad.length === 0, bad.map(i => i.src).join(' | ') || '无');
  const imgDir = path.join(planDir, 'assets', 'images');
  if (fs.existsSync(imgDir)) {
    const refs = imgs.map(i => i.src.split('/').pop());
    const orphan = fs.readdirSync(imgDir).filter(f => !refs.includes(f));
    // 二维码位图 PNG 属有意保留的转发/保存素材，页面用 SVG，不计入
    const orphanPhoto = orphan.filter(f => /\.(jpe?g|png|webp)$/i.test(f) && !/qr\.png$/i.test(f));
    ck('目录内实景照片无未引用死文件', orphanPhoto.length === 0, orphanPhoto.join(' | ') || '无');
    if (orphan.length) console.log('        （有意保留的非页面资源：' + orphan.join(', ') + '）');
  }

  /* ---------- 4. 预算联动 ---------- */
  const tierBtns = await page.$$('[data-tier]');
  if (tierBtns.length) {
    console.log('\n=== 4. 预算：住宿档位联动 ===');
    // 各计划的 data-b 键名不统一（lodge / stay、total_with_buffer / total_range…），
    // 所以按别名表探测，而不是硬编码。manifest 里没有的字段就跳过并说明，不算失败。
    const PRESENT = new Set(await page.$$eval('[data-b]', els => els.map(e => e.dataset.b)));
    console.log('        页面 data-b 键：' + [...PRESENT].sort().join(', '));
    const FIELD_MAP = [
      ['per_person_range', ['perhead', 'per_person', 'perperson', '人均']],
      ['total_with_buffer', ['total', '总额']],
      ['total_range', ['total', '总额']],
      ['subtotal_range', ['subtotal', 'sub', '分项']],
      ['lodging_total', ['lodge', 'stay', 'lodging', '住宿']],
      ['buffer_range', ['buffer', '机动']],
    ];
    const money = k => page.$eval(`[data-b="${k}"]`, e => e.textContent.trim());
    for (const t of tiers ? Object.keys(tiers) : []) {
      const btn = await page.$(`[data-tier="${t}"]`);
      if (!btn) { ck(`存在 ${t} 档按钮`, false); continue; }
      await btn.click(); await page.waitForTimeout(200);
      const m = tiers[t];
      const used = new Set();
      for (const [field, aliases] of FIELD_MAP) {
        if (m[field] == null) continue;                       // manifest 没这个字段
        const key = aliases.find(a => PRESENT.has(a) && !used.has(a));
        if (!key) continue;                                    // 本页没有对应键
        used.add(key);
        const want = Array.isArray(m[field])
          ? rngToStr(m[field])
          : Number(m[field]).toLocaleString('en-US');
        eq(`${t} ${field} → [data-b="${key}"]`, await money(key), want);
      }
      const skipped = FIELD_MAP.filter(([f]) => m[f] != null).length - used.size;
      if (skipped > 0) console.log(`        （${t}：${skipped} 个 manifest 字段在本页无对应键，已跳过）`);
      const pressed = await page.$$eval('[data-tier]', bs => bs.filter(b => b.getAttribute('aria-pressed') === 'true').length);
      ck(`${t} 同时只有一个档位被按下`, pressed === 1, 'pressed=' + pressed);
    }
  }

  /* ---------- 4b. 切换组（自动发现） ---------- */
  // 任何「一组共享某个 data-* 属性、且带 aria-pressed」的按钮，都按切换组处理：
  // 逐个点击 → 断言同时只有一个按下 → 断言切换确实改变了页面内容。
  // 这样不必为新计划的每一种联动（路线二选一、进沟与否…）单独写测试。
  {
    const groups = await page.evaluate(() => {
      const out = {};
      for (const b of document.querySelectorAll('button[aria-pressed]')) {
        for (const a of b.getAttributeNames()) {
          if (a.startsWith('data-') && a !== 'data-go' && b.getAttribute(a) !== '') {
            (out[a] = out[a] || []).push(b.getAttribute(a));
          }
        }
      }
      return out;
    });
    // 切换按钮可能藏在未激活的日面板里，点击前先把所在面板切出来，否则 click 会超时。
    async function reveal(attr, v) {
      const dayId = await page.evaluate(({ attr, v }) => {
        const b = document.querySelector(`[${attr}="${v}"]`);
        const day = b && b.closest('.day');
        return day ? day.id : null;
      }, { attr, v });
      if (dayId) {
        const tab = await page.$(`.daytabs button[data-day="${dayId.replace('day-', '')}"]`);
        if (tab) { await tab.click(); await page.waitForTimeout(150); }
      }
    }

    const names = Object.keys(groups).filter(k => groups[k].length > 1);
    if (names.length) {
      console.log('\n=== 4b. 切换组联动（自动发现）===');
      for (const attr of names) {
        const opts = groups[attr];
        const texts = [];
        let ok = true;
        for (const v of opts) {
          try {
            await reveal(attr, v);
            await page.click(`[${attr}="${v}"]`, { timeout: 5000 });
            await page.waitForTimeout(200);
          } catch (e) {
            ck(`${attr}="${v}"：可点击`, false, String(e.message).split('\n')[0]);
            ok = false; break;
          }
          const pressed = await page.$$eval(`[${attr}]`,
            bs => bs.filter(b => b.getAttribute('aria-pressed') === 'true').length);
          ck(`${attr}="${v}"：组内只有一个按下`, pressed === 1, 'pressed=' + pressed);
          texts.push((await page.evaluate(() => document.body.innerText)).replace(/\s+/g, ' '));
        }
        if (ok) {
          const uniq = new Set(texts).size;
          ck(`${attr}：${opts.length} 个选项切换后页面内容各不相同`, uniq === opts.length,
            `${uniq}/${opts.length} 种内容`);
          // 复原到第一个选项，避免影响后续检查
          try {
            await reveal(attr, opts[0]);
            await page.click(`[${attr}="${opts[0]}"]`, { timeout: 5000 });
            await page.waitForTimeout(200);
          } catch { /* 复原失败不影响后续断言 */ }
        }
      }
    }
  }

  /* ---------- 5. 清单 ---------- */
  const boxes = await page.$$('#checklist input[type=checkbox]');
  if (boxes.length) {
    console.log('\n=== 5. 出发清单 ===');
    const n = boxes.length;
    // 各计划的进度文案措辞可能不同，只比数字，不比句式
    const prog = async () => {
      const txt = await page.$eval('#prog', e => e.textContent);
      const m = txt.match(/(\d+)\s*\/\s*(\d+)/);
      return m ? `${m[1]}/${m[2]}` : txt.trim();
    };
    eq('初始进度', await prog(), `0/${n}`);
    await page.evaluate(() => {
      const b = document.querySelectorAll('#checklist input');
      [b[0], b[Math.floor(b.length / 2)], b[b.length - 1]].forEach(x => {
        x.checked = true; x.dispatchEvent(new Event('change', { bubbles: true }));
      });
    });
    await page.waitForTimeout(200);
    eq('勾 3 项后进度', await prog(), `3/${n}`);
    await page.reload({ waitUntil: 'load' }); await page.waitForTimeout(900);
    eq('刷新后勾选保持（localStorage）', await prog(), `3/${n}`);
    const undone = await page.$('#onlyUndone');
    if (undone) {
      await undone.click(); await page.waitForTimeout(200);
      const hidden = await page.$$eval('#checklist label', ls => ls.filter(l => l.style.display === 'none').length);
      ck('只看未完成 → 隐藏已勾的 3 项', hidden === 3, 'hidden=' + hidden);
    }
    const reset = await page.$('#reset');
    if (reset) {
      await reset.click(); await page.waitForTimeout(200);
      eq('清空勾选', await prog(), `0/${n}`);
    }
  }

  /* ---------- 6. 横向溢出 ---------- */
  console.log('\n=== 6. 横向溢出 ===');
  for (const w of [320, 375, 414, 768, 1024, 1280]) {
    await page.setViewportSize({ width: w, height: 900 }); await page.waitForTimeout(200);
    const r = await page.evaluate(() => ({ d: document.documentElement.scrollWidth, v: window.innerWidth }));
    ck(`${w}px 无横向溢出`, r.d <= r.v + 1, `scrollWidth=${r.d} inner=${r.v}`);
  }

  /* ---------- 6b. 宽表格不许被压扁 ---------- */
  // 曾经的问题：表格只给了 table 一个偏小的 min-width，4 列装不下时浏览器硬折行，
  // 「08:00–09:30」被折成两行、「移动／耗时」表头折成两行、费用列因 nowrap 变成
  // 一条不可折行的长文本把前几列挤扁。这条检查把那个现象固定住。
  console.log('\n=== 6b. 宽表格不压缩列宽 ===');
  {
    await page.setViewportSize({ width: 375, height: 900 });
    await page.evaluate(() => document.querySelectorAll('.day').forEach(d => d.classList.add('on')));
    // 必须让页面重算可滚状态：日面板此前是 display:none，clientWidth 为 0，
    // 那时算出的 is-scrollable 全是 false（陈旧值）。派发 resize 触发重算。
    await page.evaluate(() => window.dispatchEvent(new Event('resize')));
    await page.waitForTimeout(500);
    const tbl = await page.evaluate(() => {
      // 用 Range 的客户端矩形按「视觉行」计数。
      // 不要用 height / line-height：单元格里的 .tag 徽标 line-height 是 1.6，
      // 会把行框撑高，算出来就成了两行（实测被这个坑了一次，误报 5 张表折行）。
      const lines = el => {
        const r = document.createRange();
        r.selectNodeContents(el);
        const tops = [...r.getClientRects()].map(x => x.top).sort((a, b) => a - b);
        let n = 0, last = -1e9;
        for (const t of tops) { if (t - last > 4) { n++; last = t; } }   // 4px 容差合并同一行
        return Math.max(1, n);
      };
      return [...document.querySelectorAll('.daybody .tscroll')].map(sc => {
        const t = sc.querySelector('table');
        if (!t) return null;
        const minW = parseFloat(getComputedStyle(t).minWidth) || 0;
        const first = [...t.querySelectorAll('tbody tr')].map(r => r.children[0]).filter(Boolean);
        const th3 = t.querySelector('thead th:nth-child(3)');
        return {
          tw: Math.round(t.getBoundingClientRect().width),
          cw: sc.clientWidth,
          scrollable: sc.classList.contains('is-scrollable'),
          maxTimeLines: first.length ? Math.max(...first.map(lines)) : 0,
          head3Lines: th3 ? lines(th3) : 0,
        };
      }).filter(Boolean);
    });
    await page.click('.daytabs button[data-day="1"]'); await page.waitForTimeout(200);

    // 关键性质：窄屏下宽表格应当「装不下、由滚动接管」。
    // 如果它反而装得下，说明列被压缩到适配了——正是要避免的那种难看。
    // （不要拿表宽去和它自己的 min-width 比，那是同义反复，永远通过。）
    const fits = tbl.filter(x => !x.scrollable);
    ck(`窄屏下 ${tbl.length} 张日表格全部溢出容器（改由滚动接管，而非压缩适配）`,
      fits.length === 0, fits.length ? fits.map(x => `${x.tw}≤${x.cw}`).join(' ') : '全部溢出');
    const wrapped = tbl.filter(x => x.maxTimeLines > 1);
    ck('「时段」列不折行（时间区间保持同一行）', wrapped.length === 0,
      wrapped.length ? `${wrapped.length} 张表折行` : '全部单行');
    const badHead = tbl.filter(x => x.head3Lines > 1);
    ck('表头第三列不折行（移动／耗时 等）', badHead.length === 0,
      badHead.length ? badHead.map(x => x.head3Lines + ' 行').join(' ') : '全部单行');
    if (tbl.length) console.log(`        375px 下日表格宽度 ${[...new Set(tbl.map(x => x.tw))].join('/')}px，容器的滚动条接管溢出`);
  }

  /* ---------- 7. 打印态 ---------- */
  console.log('\n=== 7. 打印态 ===');
  await page.setViewportSize({ width: 1024, height: 900 }); await page.waitForTimeout(200);
  await page.emulateMedia({ media: 'print' }); await page.waitForTimeout(400);
  const pr = await page.evaluate(() => ({
    days: [...document.querySelectorAll('.day')].map(d => getComputedStyle(d).display),
    tabs: document.querySelector('.daytabs') ? getComputedStyle(document.querySelector('.daytabs')).display : null,
  }));
  ck('打印态所有日面板展开', pr.days.length > 0 && pr.days.every(d => d !== 'none'), pr.days.join(','));
  if (pr.tabs !== null) ck('打印态隐藏日期标签栏', pr.tabs === 'none', 'tabs=' + pr.tabs);
  await page.emulateMedia({ media: 'screen' }); await page.waitForTimeout(200);

  /* ---------- 8. 分享链接 ---------- */
  if (shareUrl) {
    console.log('\n=== 8. 地图指南分享链接 ===');
    const txt = await page.evaluate(() => document.body.innerText);
    ck('页面正文含 manifest 登记的分享链接', txt.includes(shareUrl), shareUrl);
  }

  /* ---------- 9. 交付物口径扫描 ---------- */
  // 页面是交付物，不是对话窗口：不得出现说明「这份文档还没做完、以后还会改」的文字。
  // 这些禁令写在 travel-story-preview/SKILL.md 第七节；这里把它变成可执行检查。
  console.log('\n=== 9. 交付物口径扫描 ===');
  {
    // 只列会误伤的具体说法。注意「待确认」本身是允许的核验状态标签
    // （标注外部票价/班次的浮动），不在此列；被禁的是「待确认事项」这类暴露草稿状态的标题。
    const BANNED = [
      ['告诉我', '把用户当对话对象，应移到交付消息里'],
      ['暂按', '暴露占位/草稿状态'],
      ['示例窗口', '暴露占位状态'],
      ['示意日期', '暴露占位状态'],
      ['待确认事项', '以「未完成」为标题'],
      ['待补', '暴露未完成'],
      ['再更新', '承诺后续修改'],
      ['同步更新', '承诺后续修改'],
      ['二维码不变', '承诺后续修改'],
      ['我再改', '承诺后续修改'],
      ['还在完善', '暴露未完成'],
      ['之后再补', '承诺后续修改'],
      ['记得找我', '把用户当对话对象'],
    ];
    const body = await page.evaluate(() => document.body.innerText.replace(/\s+/g, ' '));
    const hits = [];
    for (const [phrase, why] of BANNED) {
      let i = body.indexOf(phrase);
      while (i > -1) {
        hits.push({ phrase, why, ctx: body.slice(Math.max(0, i - 16), i + phrase.length + 16) });
        i = body.indexOf(phrase, i + 1);
      }
    }
    ck('页面无「文档尚未完成 / 以后会改」的表述', hits.length === 0,
      hits.length ? hits.map(h => `「${h.phrase}」…${h.ctx}…`).join(' ｜ ') : '无');
    if (hits.length) {
      for (const h of hits) console.log(`        ${h.phrase}：${h.why}`);
      console.log('        → 改到交付消息里对用户说，或改写成陈述句（见 travel-story-preview 第七节）');
    }
  }

  /* ---------- 10. 截图 ---------- */
  console.log('\n=== 10. 截图 ===');
  await page.setViewportSize({ width: 1280, height: 1000 }); await page.waitForTimeout(300);
  const p1 = path.join(shotsDir, 'desktop.png');
  await page.screenshot({ path: p1, fullPage: false });
  await page.setViewportSize({ width: 375, height: 812 }); await page.waitForTimeout(300);
  const p2 = path.join(shotsDir, 'mobile.png');
  await page.screenshot({ path: p2 });
  console.log('  ' + path.relative(planDir, p1) + '\n  ' + path.relative(planDir, p2));

  // 单独给地图指南区块拍一张元素截图 —— decode_qr.py 要靠它解码「渲染后的二维码」，
  // 整页截图里二维码太小、位置不定，解不出来。
  const guide = await page.$('#guide');
  if (guide) {
    // 用显式偏移滚动并临时关掉 CSS 的平滑滚动：scrollIntoView 会被吸顶导航压住标题，
    // 拍出来的取证图不好看（页面本身没问题，只是截图难看）。
    await page.evaluate(() => {
      const html = document.documentElement;
      const prev = html.style.scrollBehavior;
      html.style.scrollBehavior = 'auto';
      const el = document.getElementById('guide');
      window.scrollTo(0, el.getBoundingClientRect().top + window.scrollY - 96);
      html.style.scrollBehavior = prev;
    });
    await page.waitForTimeout(600);
    const p3 = path.join(shotsDir, 'guide.png');
    await guide.screenshot({ path: p3 });
    console.log('  ' + path.relative(planDir, p3) + '  ← 供 decode_qr.py 解码用');
  }

  /* ---------- 11. 控制台 ---------- */
  console.log('\n=== 11. 控制台 ===');
  ck('无 JS 错误 / 资源加载失败', errs.length === 0, errs.join(' | ') || '无');

  console.log(`\n===== ${slug}：${pass} 通过 / ${fail} 失败 =====`);
  await browser.close();
  process.exit(fail ? 1 : 0);
})().catch(e => {
  // 脚本自身出错（不是页面问题）时给出可定位的信息，而不是甩一段堆栈
  const line = String(e.stack || e).split('\n').find(l => l.includes('verify_page.js')) || '';
  console.error('\n✗ 校验中断：脚本自身出错，不代表页面有问题。');
  console.error('  ' + String(e.message).split('\n')[0]);
  if (line) console.error('  ' + line.trim());
  console.error('  多半是该计划的 DOM 结构与脚本假设不同 —— 请让脚本适配，而非改页面。');
  process.exit(2);
});
