/* netkeibaブロック時の緊急バイパス：開発PCで取得→proxy.phpのキャッシュに充填
 *
 * このPCのIPはnetkeibaに弾かれていない。ここで当日の
 *   ・レース一覧(race_list_sub) ・各レースの出馬表(shutuba_past/shutuba)
 *   ・単勝オッズAPI ・結果(result)
 * を取得し、proxy_seed.php 経由でサーバーの cache/proxy/ に置く。
 * proxy.php は既にキャッシュfallback実装済みなので、これだけでサイトが動き出す。
 *
 * 使い方: node seed_proxy_cache.js [YYYYMMDD]   （省略時=今日JST）
 *   スロットル1.2秒/req（自分のIPまで弾かれないように）
 */
const SEED = "https://kajikeiba.com/proxy_seed.php?t=sw-seed-9f2a1c7e";
const SEED2 = "https://seventh-well.com/odds/proxy_seed.php?t=sw-seed-9f2a1c7e";
const SEED3 = "https://seventh-well.com/lab/proxy_seed.php?t=sw-seed-9f2a1c7e";
const UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36";
const SLEEP = ms => new Promise(r => setTimeout(r, ms));

function jstToday() {
  const d = new Date(Date.now() + 9 * 3600 * 1000);
  return d.toISOString().slice(0, 10).replace(/-/g, "");
}
const DATE = process.argv[2] || jstToday();

async function fetchNK(url) {
  const r = await fetch(url, { headers: { "User-Agent": UA, "Accept-Language": "ja,en;q=0.8", "Referer": "https://nar.netkeiba.com/" } });
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  const buf = Buffer.from(await r.arrayBuffer());
  const ctype = r.headers.get("content-type") || "text/html; charset=UTF-8";
  return { buf, ctype };
}

async function seed(url, buf, ctype) {
  // ★両方に必ず充填する★ kajikeiba と /odds/(tweet.html) はキャッシュディレクトリが別。
  //   最初の成功でreturnすると片方だけ動いて片方が死んだままになる（実際になった）。
  const payload = JSON.stringify({ url, body_b64: buf.toString("base64"), ctype });
  let ok = 0;
  for (const ep of [SEED, SEED2, SEED3]) {
    try {
      const r = await fetch(ep, { method: "POST", headers: { "Content-Type": "application/json", "User-Agent": UA }, body: payload });
      const j = await r.json().catch(() => null);
      if (j && j.ok) ok++;
    } catch (_) { }
  }
  return ok;   // 0=失敗 / 1=片方 / 2=両方
}

async function grabAndSeed(url, label) {
  try {
    const { buf, ctype } = await fetchNK(url);
    if (buf.length < 500) { console.log(`  skip(small) ${label}`); return null; }
    const ok = await seed(url, buf, ctype);
    console.log(`  ${ok >= 2 ? "✓✓" : ok === 1 ? "✓(片方)" : "✗seed失敗"} ${label} (${(buf.length / 1024).toFixed(0)}KB)`);
    return buf.toString("utf8");
  } catch (e) { console.log(`  ✗ ${label}: ${e.message}`); return null; }
}

(async () => {
  console.log(`=== ${DATE} のnetkeibaデータをこのPCで取得→サーバーへ充填 ===`);
  // 1) レース一覧
  const listUrl = `https://nar.netkeiba.com/top/race_list_sub.html?kaisai_date=${DATE}`;
  const listHtml = await grabAndSeed(listUrl, "レース一覧");
  if (!listHtml) { console.log("一覧が取れない（このPCも弾かれてる？）"); return; }
  const ids = [...new Set((listHtml.match(/race_id=(\d{12})/g) || []).map(s => s.slice(8)))];
  console.log(`レース数: ${ids.length}`);

  // 2) 各レース: shutuba_past（予想の心臓）→ shutuba → オッズAPI(2形式) → 結果
  //    ★キャッシュキーはURL完全一致★ tweet.htmlは type=1、race_app.jsは type=1&action=init。両方充填する。
  let n = 0;
  const hids = new Set();
  for (const rid of ids) {
    n++;
    console.log(`[${n}/${ids.length}] ${rid}`);
    const past = await grabAndSeed(`https://nar.netkeiba.com/race/shutuba_past.html?race_id=${rid}`, "出馬表past");
    if (past) for (const m of past.matchAll(/db\.netkeiba\.com\/horse\/(\d{10})/g)) hids.add(m[1]);
    await SLEEP(1100);
    await grabAndSeed(`https://nar.netkeiba.com/race/shutuba.html?race_id=${rid}`, "出馬表");
    await SLEEP(1100);
    await grabAndSeed(`https://nar.netkeiba.com/api/api_get_nar_odds.html?race_id=${rid}&type=1`, "オッズ(tweet形式)");
    await SLEEP(1100);
    await grabAndSeed(`https://nar.netkeiba.com/api/api_get_nar_odds.html?race_id=${rid}&type=1&action=init`, "オッズ(race形式)");
    await SLEEP(1100);
    await grabAndSeed(`https://nar.netkeiba.com/race/result.html?race_id=${rid}`, "結果");
    await SLEEP(1100);
  }
  // 3) 当地実績用の馬ページ（tweet.htmlの「当地実績を反映」が全馬ぶん取りに来る）
  console.log(`馬ページ充填: ${hids.size}頭`);
  let h = 0;
  for (const hid of hids) {
    h++;
    await grabAndSeed(`https://db.netkeiba.com/horse/result/${hid}/`, `馬${h}/${hids.size}`);
    await SLEEP(1100);
  }
  console.log("完了。kajikeiba.com / tweet.html とも取得が全部キャッシュから即答になるはず。");
})();
