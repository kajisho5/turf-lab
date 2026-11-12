/* 今日のオッズだけを最速で充填（予想を早く出すため）。メインシーダーと並走OK */
const SEED = "https://kajikeiba.com/proxy_seed.php?t=sw-seed-9f2a1c7e";
const SEED2 = "https://seventh-well.com/odds/proxy_seed.php?t=sw-seed-9f2a1c7e";
const SEED3 = "https://seventh-well.com/lab/proxy_seed.php?t=sw-seed-9f2a1c7e";
const UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36";
const SLEEP = ms => new Promise(r => setTimeout(r, ms));
const DATE = process.argv[2] || (() => { const d = new Date(Date.now() + 9 * 3600 * 1000); return d.toISOString().slice(0, 10).replace(/-/g, ""); })();

async function fetchNK(url) {
  const r = await fetch(url, { headers: { "User-Agent": UA, "Referer": "https://nar.netkeiba.com/" } });
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
  const list = (await fetchNK(`https://nar.netkeiba.com/top/race_list_sub.html?kaisai_date=${DATE}`)).toString("utf8");
  const ids = [...new Set((list.match(/race_id=(\d{12})/g) || []).map(s => s.slice(8)))];
  console.log(`${DATE} オッズ充填: ${ids.length}レース×2形式`);
  let n = 0;
  for (const rid of ids) {
    n++;
    for (const q of ["type=1", "type=1&action=init"]) {
      const u = `https://nar.netkeiba.com/api/api_get_nar_odds.html?race_id=${rid}&${q}`;
      try { const b = await fetchNK(u);
        if (b.length > 50) { const ok = await seed(u, b, "application/json; charset=UTF-8"); process.stdout.write(ok >= 2 ? "✓" : "△"); }
        else process.stdout.write("-");
      } catch (_) { process.stdout.write("x"); }
      await SLEEP(700);
    }
    if (n % 6 === 0) process.stdout.write(` ${n}/${ids.length}\n`);
  }
  console.log("\nオッズ充填完了");
})();
