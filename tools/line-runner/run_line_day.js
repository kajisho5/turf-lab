/* LINE配信の無人運転ランナー
 *
 * 毎朝タスクスケジューラから起動され、ヘッドレスEdgeで
 * 本番の tweet.html?auto=line を開く。以降は tweet.html 側が
 * 予想→オッズ監視→LINE配信→総括まで全部やる（このスクリプトは器を保つだけ）。
 *
 * ★なぜヘッドレスブラウザか★
 *   特徴量の組み立て・netkeibaパーサ・プロキシ・配分ロジックは全部
 *   tweet.html に実装済み。Node/Pythonに書き写すと二重管理になり、
 *   本体を直すたびにランナーだけ古いロジックで配信する事故が起きる。実物を実物のまま動かす。
 *
 * ★クラッシュ自動復帰（2026-08-01追加）★
 *   中央初日にヘッドレスEdgeが約1時間で落ち、node本体だけ生き残って配信が終日停止した。
 *   ブラウザの死活を60秒ごとに監視し、落ちていたら立て直す。
 *   立て直し後は真っさらなセッションだが、予想はnoclobberでサーバーの朝版が守られ、
 *   配信の二重送信も line_sent/ のサーバー側マーカーで防がれるので、再起動しても安全。
 *
 * 終了: 21:40（地方ナイター最終レース後）。ログ: logs/YYYYMMDD.log
 * 使い方: node run_line_day.js [--smoke]
 */
const fs = require('fs');
const path = require('path');
const puppeteer = require('puppeteer-core');

const EDGE = 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe';
const URL = process.env.LINE_URL || 'https://seventh-well.com/odds/tweet.html?auto=line';
const END_H = 21, END_M = 40;
const SMOKE = process.argv.includes('--smoke');

const LOGDIR = path.join(__dirname, 'logs');
fs.mkdirSync(LOGDIR, { recursive: true });
const jst = () => new Date(Date.now() + 9 * 3600e3);
const ymd = () => jst().toISOString().slice(0, 10).replace(/-/g, '');
const log = (m) => {
  const line = `[${jst().toISOString().slice(11, 19)}] ${m}`;
  console.log(line);
  fs.appendFileSync(path.join(LOGDIR, ymd() + '.log'), line + '\n');
};

/* ブラウザを立ち上げ、地方（＋中央が開催なら）タブを開く。{browser, pages, dead} を返す。 */
async function bringUp() {
  const browser = await puppeteer.launch({
    executablePath: EDGE,
    headless: 'new',
    args: ['--no-sandbox', '--disable-dev-shm-usage'],
  });
  const state = { browser, pages: [], dead: false };
  browser.on('disconnected', () => {
    if (!state.dead) { state.dead = true; log('★ブラウザ切断を検知（クラッシュ/終了）'); }
  });
  const open = async (url, tag) => {
    const p = await browser.newPage();
    await p.evaluateOnNewDocument(() => { try { localStorage.setItem('tweetGate.ok', '1'); } catch (e) {} });
    p.on('console', (msg) => log(`${tag}: ` + msg.text().slice(0, 300)));
    p.on('pageerror', (e) => log(`${tag}!: ` + String(e).slice(0, 300)));
    await p.goto(url, { waitUntil: 'domcontentloaded', timeout: 60000 });
    log(`ページ読込完了[${tag}]: ` + url);
    return p;
  };
  state.pages.push(['地方', await open(URL, '地方')]);
  /* 中央（土日・一部祝日）は開催がある日だけ。曜日決め打ちにせずレース一覧を見る。 */
  try {
    const d = ymd();
    const listUrl = `https://race.netkeiba.com/top/race_list_sub.html?kaisai_date=${d}`;
    const u = Buffer.from(listUrl).toString('base64').replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
    const html = await (await fetch(`https://seventh-well.com/odds/proxy.php?u=${u}`)).text();
    const n = (html.match(/race_id=\d{12}/g) || []).length;
    log(`中央の開催判定: レース候補 ${n} 件`);
    if (n > 0) state.pages.push(['中央', await open(URL + '&mode=jra', '中央')]);
    else log('中央は本日開催なし → 地方のみで運転');
  } catch (e) { log('中央の開催判定に失敗（地方のみ継続）: ' + e.message); }
  return state;
}

/* Promiseにタイムアウトを付ける（死んだページの$evalが無限待ちするのを防ぐ） */
const withTimeout = (pr, ms) => Promise.race([pr, new Promise((_, rej) => setTimeout(() => rej(new Error('timeout')), ms))]);
/* ★生存確認★ browser.isConnected() はこのpuppeteer-coreに無い（2026-08-01に例外多発）。
   バージョン非依存の browser.pages() で代替する。切断/クラッシュなら投げる or disconnectedで dead。 */
async function isAlive(state) {
  if (!state || state.dead || !state.browser) return false;
  try { await withTimeout(state.browser.pages(), 8e3); return true; }
  catch (_) { return false; }
}

(async () => {
  log('起動' + (SMOKE ? '（smoke）' : ''));
  let cur = await bringUp();
  let ticks = 0;

  const HEALTH_MS = SMOKE ? 15e3 : 60e3;   // 死活監視は60秒ごと（速く復帰する）
  const health = setInterval(async () => {
    try {
      // ブラウザが落ちていたら立て直す
      if (!(await isAlive(cur))) {
        log('★再起動: ブラウザが落ちていたので立て直す');
        try { if (cur && cur.browser) await cur.browser.close().catch(() => {}); } catch (_) {}
        try { cur = await bringUp(); log('★再起動完了'); } catch (e) { log('再起動失敗（次周期で再試行）: ' + e.message); cur = null; }
        return;
      }
      // 生存時は5分ごとにstatusをログ（60秒×5）
      ticks++;
      if (ticks % 5 === 0 || SMOKE) {
        for (const [tag, p] of cur.pages) {
          try { const st = await withTimeout(p.$eval('#status', (el) => el.textContent), 10e3); log(`status[${tag}]: ` + String(st).slice(0, 160)); }
          catch (e) { log(`beat失敗[${tag}]: ` + e.message); }
        }
      }
    } catch (e) { log('health例外: ' + (e.message || e)); }
  }, HEALTH_MS);

  const until = SMOKE
    ? Date.now() + (+process.env.SMOKE_MS || 60e3)
    : (() => { const d = jst(); d.setUTCHours(END_H, END_M, 0, 0);
               return Date.now() + Math.max(60e3, d.getTime() - jst().getTime()); })();
  while (Date.now() < until) { await new Promise((r) => setTimeout(r, 30e3)); }
  clearInterval(health);
  log('終了時刻に到達。閉じる');
  try { if (cur && cur.browser) await cur.browser.close(); } catch (_) {}
  log('終了');
})().catch((e) => { log('致命的エラー: ' + (e.stack || e)); process.exit(1); });
