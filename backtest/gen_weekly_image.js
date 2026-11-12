/* 週間成績のTwitter用画像を自動生成する（未着手リスト「週間成績の自動画像」）
 *
 * データ源は本番サーバーの蓄積のみ（predictions.php=公開した予想 / results.php=確定結果）。
 * バックテストではなく「実際に公開した予想」の成績であることが肝（盛らない・実測のみ）。
 * 数字はその週の実測がそのまま入るので、良い週も悪い週もそのまま出る。
 *
 * 使い方: node backtest/gen_weekly_image.js [終了日YYYYMMDD=昨日] [日数=7]
 * 出力:   backtest/store/weekly/weekly_<開始>_<終了>.png（1200x675 @2x）
 *
 * 描画は puppeteer-core + Edge（canvas手描きより綺麗・CLAUDE.md方針）。
 * DADS準拠: 本文16px以上・コントラスト4.5:1以上（濃紺#141a2a×白/金は十分）。
 */
const fs = require('fs');
const path = require('path');
const puppeteer = require('puppeteer-core');

const EDGE = 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe';
const BASE = 'https://seventh-well.com/odds';
const OUTDIR = path.join(__dirname, 'store', 'weekly');

const sleep = ms => new Promise(r => setTimeout(r, ms));

async function getJson(url) {
  // 連投はWAFに弾かれた前科があるので必ず間隔を空ける
  await sleep(350);
  const r = await fetch(url, { headers: { 'User-Agent': 'Mozilla/5.0 weekly-image' } });
  if (!r.ok) throw new Error(`HTTP ${r.status} ${url}`);
  return r.json();
}

function ymd(d) {
  return d.getFullYear() * 10000 + (d.getMonth() + 1) * 100 + d.getDate();
}
function md(s) { return `${+String(s).slice(4, 6)}/${+String(s).slice(6, 8)}`; }

async function collect(dates, mode) {
  const races = new Map(); // rid -> ◎馬番（保存は不変=noclobberなので最初の1件でよい）
  for (const d of dates) {
    let pj;
    try { pj = await getJson(`${BASE}/predictions.php?action=list&date=${d}&mode=${mode}`); }
    catch (e) { continue; }
    for (const rec of pj.records || []) {
      for (const r of rec.races || []) {
        if (r.skip || !r.marks || !r.race_id || races.has(String(r.race_id))) continue;
        const o = r.marks.find(m => m.mk === '◎');
        // 日付はrid由来にしない（JRAのrid=場+回+日でMMDDを含まない）。予想を引いた日付を使う
        if (o && o.num != null) races.set(String(r.race_id), { onum: String(+o.num), d });
      }
    }
  }
  const agg = { n: 0, win: 0, winRet: 0, fuku: 0, fukuRet: 0, daily: {} };
  const ids = [...races.keys()];
  for (let i = 0; i < ids.length; i += 60) {
    let rj;
    try { rj = await getJson(`${BASE}/results.php?action=get&ids=${ids.slice(i, i + 60).join(',')}`); }
    catch (e) { continue; }
    for (const [rid, rec] of Object.entries(rj.results || {})) {
      const { onum, d: day } = races.get(rid) || {};
      if (!onum || !rec || !rec.ranks || !(rec.pays || {}).fukusho) continue;
      const dd = (agg.daily[day] ||= { n: 0, fuku: 0 });
      agg.n++; dd.n++;
      if (+rec.ranks[onum] === 1) {
        agg.win++;
        for (const t of rec.pays.tansho || []) {
          if (t.nums && String(+t.nums[0]) === onum) agg.winRet += t.yen / 100;
        }
      }
      for (const f of rec.pays.fukusho || []) {
        if (f.nums && String(+f.nums[0]) === onum) { agg.fuku++; dd.fuku++; agg.fukuRet += f.yen / 100; }
      }
    }
  }
  return agg;
}

function pct(a, b) { return b ? (100 * a / b).toFixed(1) : '—'; }

function html(range, nar, jra) {
  const col = (title, a) => a.n ? `
    <div class="col">
      <div class="mode">${title}<span class="n">${a.n}レース</span></div>
      <div class="big">${pct(a.fuku, a.n)}<span class="unit">%</span></div>
      <div class="cap">◎複勝率（3着以内 ${a.fuku}/${a.n}）</div>
      <div class="sub">
        <div><span class="k">◎単勝的中</span><span class="v">${pct(a.win, a.n)}%</span></div>
        <div><span class="k">単勝回収率</span><span class="v">${pct(a.winRet, a.n)}%</span></div>
        <div><span class="k">複勝回収率</span><span class="v">${pct(a.fukuRet, a.n)}%</span></div>
      </div>
      <div class="days"><span class="chip" style="border:none;background:none;padding-left:0">日別の◎複勝</span>${Object.keys(a.daily).sort().map(d =>
        `<span class="chip">${md(d)}<b>${a.daily[d].fuku}/${a.daily[d].n}</b></span>`).join('')}</div>
    </div>` : `
    <div class="col"><div class="mode">${title}</div><div class="cap" style="margin-top:40px">今週は対象レースなし</div></div>`;
  return `<!doctype html><meta charset="utf-8"><style>
  *{margin:0;box-sizing:border-box;font-family:"Yu Gothic UI","Noto Sans JP",sans-serif}
  body{width:1200px;height:675px;background:#141a2a;color:#f2f4f8;padding:46px 56px;display:flex;flex-direction:column}
  .head{display:flex;align-items:baseline;gap:18px}
  .brand{font-size:26px;font-weight:800;color:#ffd766;letter-spacing:.04em}
  .title{font-size:40px;font-weight:800}
  .range{font-size:22px;color:#aab4c8;margin-left:auto}
  .cols{display:flex;gap:40px;flex:1;margin-top:34px}
  .col{flex:1;background:#1c2438;border:1px solid #2c3a58;border-radius:16px;padding:30px 36px}
  .mode{font-size:24px;font-weight:700;color:#9fc1ff}
  .mode .n{font-size:18px;color:#aab4c8;font-weight:400;margin-left:12px}
  .big{font-size:96px;font-weight:800;line-height:1.15;color:#ffd766;font-variant-numeric:tabular-nums}
  .big .unit{font-size:40px;margin-left:4px}
  .cap{font-size:18px;color:#cdd6e4}
  .sub{margin-top:22px;display:flex;flex-direction:column;gap:10px}
  .sub div{display:flex;justify-content:space-between;font-size:21px;border-bottom:1px solid #2c3a58;padding-bottom:8px}
  .k{color:#aab4c8}.v{font-weight:700;font-variant-numeric:tabular-nums}
  .days{margin-top:24px;display:flex;flex-wrap:wrap;gap:10px}
  .chip{background:#141a2a;border:1px solid #2c3a58;border-radius:8px;padding:7px 12px;font-size:17px;color:#aab4c8}
  .chip b{color:#f2f4f8;margin-left:8px;font-variant-numeric:tabular-nums}
  .foot{margin-top:26px;display:flex;justify-content:space-between;align-items:center;font-size:18px;color:#aab4c8}
  .foot b{color:#f2f4f8}
  </style><body>
  <div class="head"><span class="brand">カジ競馬</span><span class="title">週間成績</span><span class="range">${range}</span></div>
  <div class="cols">${col('地方競馬', nar)}${col('中央競馬', jra)}</div>
  <div class="foot"><span>予想は毎朝<b>オッズ発表前</b>に公開。外れも含む全予想を記録しています</span><span><b>kajikeiba.com/record/</b></span></div>
  </body>`;
}

async function main() {
  const endArg = process.argv[2];
  const days = +(process.argv[3] || 7);
  const end = endArg ? endArg
    : (() => { const d = new Date(Date.now() + 9 * 3600e3 - 24 * 3600e3); return String(ymd(new Date(d.toISOString().slice(0, 10)))); })();
  const dates = [];
  {
    const e = new Date(`${String(end).slice(0, 4)}-${String(end).slice(4, 6)}-${String(end).slice(6, 8)}`);
    for (let i = days - 1; i >= 0; i--) dates.push(String(ymd(new Date(e.getTime() - i * 24 * 3600e3))));
  }
  console.log(`集計期間: ${dates[0]}〜${dates[dates.length - 1]}`);
  const nar = await collect(dates, 'nar');
  const jra = await collect(dates, 'jra');
  console.log('nar:', JSON.stringify(nar.daily), `n=${nar.n} 複勝${nar.fuku} 単勝${nar.win}`);
  console.log('jra:', JSON.stringify(jra.daily), `n=${jra.n} 複勝${jra.fuku} 単勝${jra.win}`);
  if (!nar.n && !jra.n) { console.log('対象レースなし。画像は作らない'); return; }

  fs.mkdirSync(OUTDIR, { recursive: true });
  // 表示期間は「実際に結果があった日」の範囲にする（保存開始前の日を含めて広く見せない）
  const have = [...Object.keys(nar.daily), ...Object.keys(jra.daily)].sort();
  const range = `${md(have[0])}〜${md(have[have.length - 1])}`;
  const htmlPath = path.join(OUTDIR, 'weekly.html');
  fs.writeFileSync(htmlPath, html(range, nar, jra));

  const browser = await puppeteer.launch({ executablePath: EDGE, headless: 'new', args: ['--no-sandbox'] });
  try {
    const page = await browser.newPage();
    await page.setViewport({ width: 1200, height: 675, deviceScaleFactor: 2 });
    await page.goto('file:///' + htmlPath.replace(/\\/g, '/'), { waitUntil: 'networkidle0' });
    const out = path.join(OUTDIR, `weekly_${dates[0]}_${dates[dates.length - 1]}.png`);
    await page.screenshot({ path: out });
    console.log('出力:', out);
  } finally { await browser.close(); }
}

main().catch(e => { console.error(e); process.exit(1); });
