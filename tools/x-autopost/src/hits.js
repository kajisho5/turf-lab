/* ★勝負の的中速報（2026-11-13・docs/design/X_BATTLE_SUMMARY_DESIGN.md）
   朝に★勝負と公開したレースで ◎ が1着になったら、朝の投稿への返信で知らせる（文だけ）。
   - 予想・★勝負は朝に保存されたものをそのまま読む（採点し直さない）。
   - 着順と払戻は結果のページから読む。確定していなければ次の回に回す。払戻が読めなければ払戻の行を出さない。
   - 1レースにつき1回だけ。外れは投稿しないが、戦績の分母には入れる。
   - 止める時は wrangler.toml の HITS を "0" にする。 */
const SITE = "https://seventh-well.com/odds";
const AFTER_MIN = 3;        // 発走の何分後から結果を見に行くか
const GIVE_UP_MIN = 120;    // 発走から何分たっても確定しなければあきらめる
const MAX_FETCH = 8;        // 1回の実行で結果を見に行くレース数の上限

export const HITS_DDL = `CREATE TABLE IF NOT EXISTS xpost_log (
  k TEXT PRIMARY KEY, date TEXT NOT NULL, mode TEXT NOT NULL, tweet_id TEXT, body TEXT, ts INTEGER NOT NULL)`;

/* 結果のページから 単勝・複勝 の馬番と払戻を読む。確定前（払戻の表が無い）は null */
export function parseResult(html) {
  const row = (cls) => {
    const m = String(html || "").match(new RegExp('<tr class="' + cls + '">([\\s\\S]*?)</tr>'));
    if (!m) return null;
    const res = (m[1].match(/class="Result">([\s\S]*?)<\/td>/) || [])[1] || "";
    const nums = [...res.matchAll(/<span>\s*(\d{1,2})\s*<\/span>/g)].map(x => String(parseInt(x[1], 10)));
    const pay = ((m[1].match(/class="Payout">\s*<span>([\s\S]*?)<\/span>/) || [])[1] || "")
      .split(/<br\s*\/?>/).map(t => parseInt(t.replace(/[^\d]/g, ""), 10)).filter(n => n > 0);
    return { nums, pay };
  };
  const t = row("Tansho");
  if (!t || !t.nums.length) return null;
  const f = row("Fukusho") || { nums: [], pay: [] };
  const map = (r) => { const o = {}; if (r.nums.length === r.pay.length) r.nums.forEach((n, i) => { o[n] = r.pay[i]; }); return o; };
  return { win: t.nums, tan: map(t), fuku: map(f) };
}

/* 朝の予想と★勝負の記録から、★勝負のレースを発走順に並べる */
export function battleRaces(records, locks) {
  const pub = {};
  (locks || []).forEach(l => { const t = String(l.tc || ""); if (t.startsWith("pub_") && l.pub) pub[t.slice(4)] = l.pub; });
  const out = [];
  (records || []).forEach(rec => {
    const p = pub[String(rec.tc)]; if (!p) return;
    (rec.races || []).forEach(r => {
      if (!r || r.skip || !r.race_id || !(r.marks || []).length) return;
      const f = p[r.no] || p[String(r.no)];
      if (!f || !f.battle) return;
      out.push({ rid: String(r.race_id), track: rec.trackName || r.track || "", no: r.no, post: String(r.post || ""),
        num: String(r.marks[0].num), name: String(r.marks[0].name || "") });
    });
  });
  return out.sort((a, b) => (a.post < b.post ? -1 : a.post > b.post ? 1 : (a.rid < b.rid ? -1 : 1)));
}

/* "HH:MM" → その日の0時からの分。読めなければ null */
export function postMin(s) { const m = String(s || "").match(/^(\d{1,2}):(\d{2})$/); return m ? (+m[1]) * 60 + (+m[2]) : null; }

/* 今見に行くレース（発走 AFTER_MIN 分後〜GIVE_UP_MIN 分後・未記録のもの） */
export function dueRaces(races, doneSet, nowMin) {
  return races.filter(r => { const p = postMin(r.post); return p != null && !doneSet.has(r.rid) && nowMin >= p + AFTER_MIN && nowMin <= p + GIVE_UP_MIN; });
}

/* 速報の文。played/won はこのレースを含めた今日の★勝負の戦績 */
export function hitText(r, res, played, won) {
  const lines = ["🎯 ★勝負 的中", `${r.track}${r.no}R ◎${r.num} ${r.name}　1着`];
  const tan = res.tan[r.num], fuku = res.fuku[r.num];
  if (tan && fuku) lines.push(`単勝 ${tan}円／複勝 ${fuku}円`);
  else if (tan) lines.push(`単勝 ${tan}円`);
  lines.push(`今日の★勝負：${played}戦${won}勝`);
  return lines.join("\n");
}

async function getJson(url) {
  const r = await fetch(url, { headers: { Accept: "application/json" } });
  if (!r.ok) throw new Error(`${url} → ${r.status}`);
  return r.json();
}

/* 朝の投稿のIDを覚える（朝の回から呼ぶ）。失敗しても朝の投稿は成功のまま */
export async function rememberMorning(env, date, mode, tweetId) {
  if (!env.DB || !tweetId) return;
  await env.DB.prepare(HITS_DDL).run();
  await env.DB.prepare("INSERT OR REPLACE INTO xpost_log(k,date,mode,tweet_id,body,ts) VALUES(?,?,?,?,?,?)")
    .bind(`m:${date}:${mode}`, date, mode, String(tweetId), null, Date.now()).run();
}

/* 10分おきの回。reply(text, toId) は投稿して投稿IDを返す関数（worker.js が渡す） */
export async function runHits(env, reply, { dry } = {}) {
  const out = { date: null, checked: 0, posted: [], missed: 0, skipped: null };
  if (!env.DB) { out.skipped = "DB なし"; return out; }
  const j = new Date(Date.now() + 9 * 3600e3);
  const date = j.toISOString().slice(0, 10).replace(/-/g, ""); out.date = date;
  const nowMin = j.getUTCHours() * 60 + j.getUTCMinutes();
  await env.DB.prepare(HITS_DDL).run();
  for (const mode of ["nar", "jra"]) {
    const m = await env.DB.prepare("SELECT tweet_id FROM xpost_log WHERE k=?").bind(`m:${date}:${mode}`).first();
    if (!m || !m.tweet_id) continue;                       // 朝の投稿が無い日は何もしない
    const pred = await getJson(`${SITE}/predictions.php?action=list&mode=${mode}&date=${date}`);
    const lk = await getJson(`${SITE}/predictions.php?action=listlocks&mode=${mode}&date=${date}`);
    const races = battleRaces(pred.records, lk.locks);
    if (!races.length) continue;
    const rows = (await env.DB.prepare("SELECT k, body FROM xpost_log WHERE date=? AND mode=? AND k LIKE 'h:%'").bind(date, mode).all()).results || [];
    const done = new Set(rows.map(x => String(x.k).slice(2)));
    let played = rows.length, won = rows.filter(x => { try { return JSON.parse(x.body).hit === 1; } catch { return false; } }).length;
    for (const r of dueRaces(races, done, nowMin).slice(0, MAX_FETCH)) {
      const base = mode === "nar" ? "https://nar.netkeiba.com" : "https://race.netkeiba.com";
      const u = btoa(`${base}/race/result.html?race_id=${r.rid}`).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
      let res = null;
      try { const h = await fetch(`${SITE}/proxy.php?u=${u}&_=${Date.now()}`); res = h.ok ? parseResult(await h.text()) : null; } catch { res = null; }
      out.checked++;
      if (!res) continue;                                   // まだ確定していない → 次の回
      const hit = res.win.includes(r.num) ? 1 : 0;
      played++; won += hit;
      const text = hit ? hitText(r, res, played, won) : null;
      // 先に記録を取る（取れた時だけ投稿＝二重投稿を防ぐ）
      const ins = await env.DB.prepare("INSERT OR IGNORE INTO xpost_log(k,date,mode,tweet_id,body,ts) VALUES(?,?,?,?,?,?)")
        .bind(`h:${r.rid}`, date, mode, null, JSON.stringify({ hit, text, win: res.win }), Date.now()).run();
      if (!ins.meta || !ins.meta.changes) continue;
      if (!hit) { out.missed++; continue; }
      if (dry) { out.posted.push({ rid: r.rid, text, dry: true }); continue; }
      try {
        const id = await reply(text, m.tweet_id);
        await env.DB.prepare("UPDATE xpost_log SET tweet_id=? WHERE k=?").bind(String(id), `h:${r.rid}`).run();
        out.posted.push({ rid: r.rid, id });
      } catch (e) {
        out.posted.push({ rid: r.rid, error: String(e && e.message || e) });   // 投稿に失敗しても出し直さない（記録は残る）
      }
    }
  }
  return out;
}
