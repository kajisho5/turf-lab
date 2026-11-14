/* ★勝負の的中速報（2026-11-13・docs/design/X_BATTLE_SUMMARY_DESIGN.md）
   朝に★勝負と公開したレースで ◎ が1着になったら、朝の投稿への返信で知らせる（文だけ）。
   - 予想・★勝負は朝に保存されたものをそのまま読む（採点し直さない）。
   - 着順と払戻は結果のページから読む。確定していなければ次の回に回す。払戻が読めなければ払戻の行を出さない。
   - 1レースにつき1回だけ。外れは投稿しないが、戦績の分母には入れる。
   - 止める時は wrangler.toml の HITS を "0" にする。 */
const SITE = "https://seventh-well.com/odds";
const AFTER_MIN = 3;        // 発走の何分後から結果を見に行くか
const GIVE_UP_MIN = 120;    // 発走から何分たっても確定しなければあきらめる
const MAX_FETCH = 12;       // 1回の実行で結果を見に行くレース数の上限（全レースを見るようにしたので 8 → 12）
/* ★中央は少しずつ見に行く（2026-11-14）★
   中央の結果のページは、直接は取れず（netkeiba が 400 を返す）中継を通る。中継は短い時間に続けて頼むと断られる（429）。
   11/14 は全レースを10分おきに最大12件ずつ頼んだせいで、31レース中12レースしか結果を記録できなかった。
   中央は 1回4件まで・1件ごとに2秒あける・発走10分後から、にする（地方は直接取れるので今までどおり）。 */
const JRA_MAX_FETCH = 4, JRA_GAP_MS = 2000, JRA_AFTER_MIN = 10;
const JRA_GIVE_UP_MIN = 420;   // 中央は取れない回が多いので、発走の7時間後まで（夜の答え合わせの前まで）取りに行き続ける。取れた結果は中継の側に残り、夜の回がそれを使う
export const BIG_TAN = 1000;   // 高配当の的中（単独で出す）の線引き＝単勝の払戻がこの額以上。根拠は docs/design/X_HIT_AND_GRADE_DESIGN.md

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
        num: String(r.marks[0].num), name: String(r.marks[0].name || ""), strong: r.strong ? String(r.strong) : null });
    });
  });
  return out.sort((a, b) => (a.post < b.post ? -1 : a.post > b.post ? 1 : (a.rid < b.rid ? -1 : 1)));
}

/* 朝に予想を出した全レースを発走順に並べる（battle＝朝に★勝負と公開したか）。高配当の的中はこの全部が対象 */
export function allRaces(records, locks) {
  const pub = {};
  (locks || []).forEach(l => { const t = String(l.tc || ""); if (t.startsWith("pub_") && l.pub) pub[t.slice(4)] = l.pub; });
  const out = [];
  (records || []).forEach(rec => {
    const p = pub[String(rec.tc)] || {};
    (rec.races || []).forEach(r => {
      if (!r || r.skip || !r.race_id || !(r.marks || []).length) return;
      const f = p[r.no] || p[String(r.no)];
      out.push({ rid: String(r.race_id), track: rec.trackName || r.track || "", no: r.no, post: String(r.post || ""),
        num: String(r.marks[0].num), name: String(r.marks[0].name || ""), strong: r.strong ? String(r.strong) : null, battle: !!(f && f.battle) });
    });
  });
  return out.sort((a, b) => (a.post < b.post ? -1 : a.post > b.post ? 1 : (a.rid < b.rid ? -1 : 1)));
}

/* 高配当の的中の文（画像が作れなかった時の代わり。ふだんはページが作った文を使う）。played/won は今日の◎の戦績 */
export function bigText(r, res, played, won, mode) {
  const lines = ["🎯 朝の予想が的中", `${r.track}${r.no}R ◎${r.num} ${r.name}　1着`];
  const tan = res.tan[r.num]; if (tan) lines.push(`単勝 ${tan.toLocaleString("ja-JP")}円`);
  lines.push(`今日の◎：${played}戦${won}勝`);
  lines.push("#競馬予想 " + (mode === "jra" ? "#競馬" : "#地方競馬"));
  return lines.join("\n");
}

/* "HH:MM" → その日の0時からの分。読めなければ null */
export function postMin(s) { const m = String(s || "").match(/^(\d{1,2}):(\d{2})$/); return m ? (+m[1]) * 60 + (+m[2]) : null; }

/* 今見に行くレース（発走 AFTER_MIN 分後〜GIVE_UP_MIN 分後・未記録のもの） */
export function dueRaces(races, doneSet, nowMin, giveUp) {
  return races.filter(r => { const p = postMin(r.post); return p != null && !doneSet.has(r.rid) && nowMin >= p + AFTER_MIN && nowMin <= p + (giveUp || GIVE_UP_MIN); });
}

/* 速報の文。played/won はこのレースを含めた今日の★勝負の戦績 */
export function hitText(r, res, played, won) {
  const lines = ["🎯 ★勝負 的中", `${r.track}${r.no}R ◎${r.num} ${r.name}　1着`];
  if (r.strong) lines.push(`強み：${r.strong}`);          // 朝に保存した文をそのまま使う（作り直さない）
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

/* 10分おきの回。reply(text, toId) は投稿して投稿IDを返す関数（worker.js が渡す）。
   big(r, mode, date, st) は高配当の的中を画像つきの単独の投稿で出して投稿IDを返す関数（無ければ出さない）。
   記録: r:レースID＝そのレースの◎の結果（全レース）／h:レースID＝★勝負の結果（今までどおり） */
export async function runHits(env, reply, { dry, big, sleep } = {}) {
  const wait = sleep || ((ms) => new Promise(r => setTimeout(r, ms)));   // sleep は試験用（ふだんは本当に待つ）
  const out = { date: null, checked: 0, posted: [], missed: 0, big: [], skipped: null };
  if (!env.DB) { out.skipped = "DB なし"; return out; }
  const j = new Date(Date.now() + 9 * 3600e3);
  const date = j.toISOString().slice(0, 10).replace(/-/g, ""); out.date = date;
  const nowMin = j.getUTCHours() * 60 + j.getUTCMinutes();
  const bigOn = !!big && env.BIGHIT !== "0";
  await env.DB.prepare(HITS_DDL).run();
  for (const mode of ["nar", "jra"]) {
    const m = await env.DB.prepare("SELECT tweet_id FROM xpost_log WHERE k=?").bind(`m:${date}:${mode}`).first();
    if (!m || !m.tweet_id) continue;                       // 朝の投稿が無い日は何もしない
    const pred = await getJson(`${SITE}/predictions.php?action=list&mode=${mode}&date=${date}`);
    const lk = await getJson(`${SITE}/predictions.php?action=listlocks&mode=${mode}&date=${date}`);
    const all = allRaces(pred.records, lk.locks);
    const races = bigOn ? all : all.filter(r => r.battle);   // 高配当を止めている時は、今までどおり★勝負だけ見に行く
    if (!races.length) continue;
    const hRows = (await env.DB.prepare("SELECT k, body FROM xpost_log WHERE date=? AND mode=? AND k LIKE 'h:%'").bind(date, mode).all()).results || [];
    const rRows = (await env.DB.prepare("SELECT k, body FROM xpost_log WHERE date=? AND mode=? AND k LIKE 'r:%'").bind(date, mode).all()).results || [];
    const isWin = (x, key) => { try { return JSON.parse(x.body)[key] === 1; } catch { return false; } };
    const hDone = new Set(hRows.map(x => String(x.k).slice(2))), rDone = new Set(rRows.map(x => String(x.k).slice(2)));
    let played = hRows.length, won = hRows.filter(x => isWin(x, "hit")).length;        // ★勝負の戦績
    let aPlayed = rRows.length, aWon = rRows.filter(x => isWin(x, "win")).length;       // 全レースの◎の戦績
    // まだ見ていないレース（★勝負は h:、それ以外は r: が無いもの）
    const todo = races.filter(r => bigOn ? !rDone.has(r.rid) : !hDone.has(r.rid));
    const jra = mode === "jra";
    let due = dueRaces(todo, new Set(), nowMin, jra ? JRA_GIVE_UP_MIN : 0).filter(r => !jra || nowMin >= postMin(r.post) + JRA_AFTER_MIN);
    // 中央は回ごとに見はじめる場所をずらす（同じレースが取れないまま先頭に居座って、ほかが見られなくなるのを防ぐ）
    if (jra && due.length > JRA_MAX_FETCH) { const off = Math.floor(nowMin / 10) % due.length; due = due.slice(off).concat(due.slice(0, off)); }
    due = due.slice(0, jra ? JRA_MAX_FETCH : MAX_FETCH);
    let nth = 0;
    for (const r of due) {
      if (jra && nth++ > 0) await wait(JRA_GAP_MS);
      const base = mode === "nar" ? "https://nar.netkeiba.com" : "https://race.netkeiba.com";
      const u = btoa(`${base}/race/result.html?race_id=${r.rid}`).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
      let res = null;
      try { const h = await fetch(`${SITE}/proxy.php?u=${u}&_=${Date.now()}`); res = h.ok ? parseResult(await h.text()) : null; } catch { res = null; }
      out.checked++;
      if (!res) continue;                                   // まだ確定していない → 次の回
      const hit = res.win.includes(r.num) ? 1 : 0;
      const tan = res.tan[r.num] || 0;
      const isBig = bigOn && hit === 1 && tan >= BIG_TAN;
      // 全レースの記録（高配当を出す時だけ付ける。先に記録が取れた時だけ先へ進む＝二重投稿を防ぐ）
      if (bigOn) {
        const insR = await env.DB.prepare("INSERT OR IGNORE INTO xpost_log(k,date,mode,tweet_id,body,ts) VALUES(?,?,?,?,?,?)")
          .bind(`r:${r.rid}`, date, mode, null, JSON.stringify({ win: hit, tan, big: isBig ? 1 : 0 }), Date.now()).run();
        if (!insR.meta || !insR.meta.changes) continue;
        aPlayed++; aWon += hit;
      }
      // ★勝負の記録と返信（今までどおり。高配当で単独の投稿を出すレースは返信しない）
      if (r.battle && !hDone.has(r.rid)) {
        played++; won += hit;
        const text = hit ? hitText(r, res, played, won) : null;
        const ins = await env.DB.prepare("INSERT OR IGNORE INTO xpost_log(k,date,mode,tweet_id,body,ts) VALUES(?,?,?,?,?,?)")
          .bind(`h:${r.rid}`, date, mode, null, JSON.stringify({ hit, text, win: res.win, big: isBig ? 1 : 0 }), Date.now()).run();
        if (ins.meta && ins.meta.changes) {
          if (!hit) out.missed++;
          else if (isBig) { /* 下の単独の投稿で出す */ }
          else if (dry) out.posted.push({ rid: r.rid, text, dry: true });
          else {
            try {
              const id = await reply(text, m.tweet_id);
              await env.DB.prepare("UPDATE xpost_log SET tweet_id=? WHERE k=?").bind(String(id), `h:${r.rid}`).run();
              out.posted.push({ rid: r.rid, id });
            } catch (e) {
              out.posted.push({ rid: r.rid, error: String(e && e.message || e) });   // 投稿に失敗しても出し直さない（記録は残る）
            }
          }
        }
      }
      if (isBig) {
        const st = { played: aPlayed, won: aWon, tan, text: bigText(r, res, aPlayed, aWon, mode) };
        if (dry) { out.big.push({ rid: r.rid, tan, text: st.text, dry: true }); continue; }
        try {
          const id = await big(r, mode, date, st);
          await env.DB.prepare("UPDATE xpost_log SET tweet_id=? WHERE k=?").bind(String(id), `r:${r.rid}`).run();
          out.big.push({ rid: r.rid, tan, id });
        } catch (e) {
          out.big.push({ rid: r.rid, tan, error: String(e && e.message || e) });      // 失敗しても出し直さない
        }
      }
    }
  }
  return out;
}
