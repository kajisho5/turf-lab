/* 当地実績用の馬ページだけを最速で充填。出馬表pastはサーバーキャッシュから読む(netkeiba負荷ゼロ) */
const SEED = "https://kajikeiba.com/proxy_seed.php?t=sw-seed-9f2a1c7e";
const SEED2 = "https://seventh-well.com/odds/proxy_seed.php?t=sw-seed-9f2a1c7e";
const SEED3 = "https://seventh-well.com/lab/proxy_seed.php?t=sw-seed-9f2a1c7e";
const UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36";
const SLEEP = ms => new Promise(r => setTimeout(r, ms));
const b64url = s => Buffer.from(s).toString("base64").replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
const DATE = process.argv[2] || (() => { const d = new Date(Date.now() + 9 * 3600 * 1000); return d.toISOString().slice(0, 10).replace(/-/g, ""); })();

async function viaProxy(url) {   // サーバーキャッシュ経由（netkeibaを叩かない）
  const r = await fetch(`https://kajikeiba.com/proxy.php?u=${b64url(url)}`, { headers: { "User-Agent": UA } });
  return r.ok ? await r.text() : "";
}
async function fetchNK(url) {
  const r = await fetch(url, { headers: { "User-Agent": UA, "Referer": "https://db.netkeiba.com/" } });
  if (!r.ok) throw new Error("HTTP " + r.status);
  return Buffer.from(await r.arrayBuffer());
}
async function seed(url, buf, ctype) {
  const payload = JSON.stringify({ url, body_b64: buf.toString("base64"), ctype });
  let ok = 0;
  for (const ep of [SEED, SEED2, SEED3]) {
    try { const r = await fetch(ep, { method: "POST", headers: { "Content-Type": "application/json" }, body: payload });
      const j = await r.json().catch(() => null); if (j && j.ok) ok++; } catch (_) { }
  }
  return ok;
}
(async () => {
  const list = await viaProxy(`https://nar.netkeiba.com/top/race_list_sub.html?kaisai_date=${DATE}`);
  const ids = [...new Set((list.match(/race_id=(\d{12})/g) || []).map(s => s.slice(8)))];
  console.log(`レース: ${ids.length}`);
  const hids = new Set();
  for (const rid of ids) {
    const past = await viaProxy(`https://nar.netkeiba.com/race/shutuba_past.html?race_id=${rid}`);
    for (const m of past.matchAll(/db\.netkeiba\.com\/horse\/(\d{10})/g)) hids.add(m[1]);
  }
  console.log(`馬: ${hids.size}頭を充填`);
  let n = 0, ok2 = 0;
  for (const hid of hids) {
    n++;
    const u = `https://db.netkeiba.com/horse/result/${hid}/`;
    try { const b = await fetchNK(u);
      if (b.length > 1000) { const s = await seed(u, b, "text/html; charset=UTF-8"); if (s >= 2) ok2++; process.stdout.write(s >= 2 ? "✓" : "△"); }
      else process.stdout.write("-");
    } catch (_) { process.stdout.write("x"); }
    if (n % 30 === 0) process.stdout.write(` ${n}/${hids.size}\n`);
    await SLEEP(700);
  }
  console.log(`\n完了: ${ok2}/${hids.size} 両サイト充填`);
})();
