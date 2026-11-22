// worker.js の通し（にせのブラウザ・にせのX・にせのデータベース。ネットには触らない。鍵は見本の文字）
// worker.js は Cloudflare のブラウザ部品を読み込むので、その1行だけ差し替えた写しを作って動かす
import { readFileSync, writeFileSync, mkdtempSync, copyFileSync } from "node:fs";
import { tmpdir } from "node:os"; import { join, dirname } from "node:path"; import { fileURLToPath, pathToFileURL } from "node:url";
const here = dirname(fileURLToPath(import.meta.url)), src = join(here, "..", "src");
const dir = mkdtempSync(join(tmpdir(), "autopost-"));
for (const f of ["posts.js", "hits.js", "guard.js", "grade.js", "wake.js", "warm.js", "stages.js"]) copyFileSync(join(src, f), join(dir, f));
let code = readFileSync(join(src, "worker.js"), "utf8");
const imp = 'import puppeteer from "@cloudflare/puppeteer";';
if (!code.includes(imp)) { console.log("NG worker.js の読み込みの行が変わった"); process.exit(1); }
writeFileSync(join(dir, "worker.mjs"), code.replace(imp, "const puppeteer = globalThis.__pp;").replace(/\.\/(posts|hits|guard)\.js/g, "./$1.js"));
let ok = 0, ng = 0;
const eq = (n, a, b) => { const r = JSON.stringify(a) === JSON.stringify(b); r ? ok++ : (ng++, console.log("NG", n, JSON.stringify(a), JSON.stringify(b))); };
const at = (s) => Date.parse(s + "+09:00");
const PNG = "data:image/png;base64,iVBORw0KGgo" + "A".repeat(1200);

function fakeDB() {
  const t = new Map(), preds = [], results = new Set(), gen = new Map();
  const db = { rows: t, preds, results, gen, async batch(list) { for (const x of list) await x.run(); return []; }, prepare(sql) { let a = []; const st = {
    bind(...x) { a = x; return st; },
    async run() {
      if (/^CREATE/.test(sql)) return { meta: { changes: 0 } };
      if (/xpost_gen/.test(sql)) {
        if (/^INSERT/.test(sql)) { gen.set(a[0], { body: a[2], date: a[1] }); return { meta: { changes: 1 } }; }
        if (/^DELETE FROM xpost_gen WHERE k LIKE/.test(sql)) { const p = a[0].replace("%", ""); for (const k of [...gen.keys()]) if (k.startsWith(p)) gen.delete(k); return { meta: { changes: 1 } }; }
        if (/^DELETE/.test(sql)) { for (const [k, v] of [...gen]) if (v.date < a[0]) gen.delete(k); return { meta: { changes: 1 } }; }
      }
      if (/^UPDATE xpost_log/.test(sql)) { const r = t.get(a[2]); if (r) r.body = a[0]; return { meta: { changes: r ? 1 : 0 } }; }
      if (/^INSERT OR REPLACE/.test(sql)) { t.set(a[0], { k: a[0], date: a[1], mode: a[2], tweet_id: a[3], body: a[4] }); return { meta: { changes: 1 } }; }
      if (/^INSERT OR IGNORE/.test(sql)) { if (t.has(a[0])) return { meta: { changes: 0 } }; t.set(a[0], { k: a[0], date: a[1], mode: a[2], tweet_id: a[3], body: a[4] }); return { meta: { changes: 1 } }; }
      throw new Error(sql); },
    async first() { if (/^SELECT 1/.test(sql)) return { 1: 1 }; if (/xpost_gen/.test(sql)) return gen.get(a[0]) || null; return t.get(a[0]) || null; },
    async all() {
      if (/FROM predictions/.test(sql)) return { results: preds.filter(p => p.date === a[0] && p.mode === a[1]).map(p => ({ k: `${p.date}_${p.mode}_${p.tc}`, body: JSON.stringify(p) })) };
      if (/FROM results/.test(sql)) return { results: a.filter(x => results.has(x)).map(k => ({ k })) };
      if (/FROM xpost_log WHERE k LIKE 'job:%'/.test(sql)) return { results: [...t.values()].filter(r => r.k.startsWith("job:") && (r.date === a[0] || r.date === a[1])) };
      if (/FROM xpost_log WHERE k LIKE \?/.test(sql)) { const p = a[0].replace("%", ""); return { results: [...t.values()].filter(r => r.k.startsWith(p)) }; }
      return { results: [] }; } }; return st; } };
  return db;
}
// にせのページ: mode ごとの __autoOut を返す
let outs = {}, opened = [];
globalThis.__pp = { launch: async () => ({
  newPage: async () => { let u = ""; return {
    goto: async (x) => { u = x; opened.push(x.replace(/^.*\?/, "")); },
    waitForFunction: async () => ({ jsonValue: async () => pageOut(u) }),
    close: async () => {} }; },
  close: async () => {} }) };
// stage=fetch: 朝は「場のカードの数」だけ場の予想を、夜は1レースの予想と結果を保存したことにする（holes＝保存しないレースの数）
let curDB = null, holes = 0;
function pageOut(u) {
  const mode = /mode=(\w+)/.exec(u)[1], o = outs[mode];
  if (!/stage=fetch/.test(u)) return o;
  if (!o || !o.ok) return o;
  const date = o.date || "20261114";
  if (/auto=morning/.test(u)) {
    const tracks = (o.cards || []).map((_, i) => ({ tc: "t" + i, trackName: "架空" + i, total: 2, pred: 2, skip: 0, err: 0, rids: [`${mode}${i}a`, `${mode}${i}b`] }));
    tracks.forEach((t, i) => { if (!curDB.preds.some(p => p.date === date && p.mode === mode && p.tc === t.tc))
      curDB.preds.push({ date, mode, tc: t.tc, trackName: t.trackName, races: t.rids.slice(0, i === 0 ? 2 - holes : 2).map(r => ({ race_id: r, marks: [{ mk: "◎" }], skip: false })) }); });
    return { ok: true, date, stage: "fetch", tracks };
  }
  const rid = mode + "E";
  if (!curDB.preds.some(p => p.date === date && p.mode === mode)) curDB.preds.push({ date, mode, tc: "e", trackName: "架空", races: [{ race_id: rid, marks: [{ mk: "◎" }], skip: false }] });
  if (!holes) curDB.results.add(rid);
  return { ok: true, date, stage: "fetch", tracks: [{ tc: "e", total: 1, decided: 1, cancelled: 0, cancelledRids: [] }] };
}
// にせのX: 画像の受付と投稿。fail に入れた回数目の投稿だけ断る
let tweets = [], uploads = 0, failTweet = () => null, failUpload = null;
globalThis.fetch = async (url, init) => {
  const resp = (status, body) => ({ ok: status < 300, status, text: async () => JSON.stringify(body), json: async () => body });
  if (String(url).includes("media/upload")) { uploads++; return failUpload ? resp(failUpload[0], failUpload[1]) : resp(200, { media_id_string: "m" + uploads }); }
  if (String(url).includes("/2/tweets")) { const b = JSON.parse(init.body); const f = failTweet(b, tweets.length); if (f) return resp(f[0], f[1]);
    tweets.push(b); return resp(201, { data: { id: "t" + tweets.length } }); }
  if (String(url).includes("/2/users/me")) return resp(200, { data: { username: "otter_keiba" } });
  if (String(url).includes("nar_index_asof")) return resp(200, { asof: "20261113" });
  if (String(url).includes("seventh-well.com/odds/")) return { ok: true, status: 200, text: async () => "__autoOut narT {", json: async () => ({}) };
  throw new Error("想定外の通信 " + url);
};
const mails = [];
const mkEnv = () => ({ DB: (curDB = fakeDB()), BROWSER: {}, TWEET_URL: "https://example.test/tweet.html", DRYRUN: "0", HITS: "0",
  X_API_KEY: "sample-a", X_API_SECRET: "sample-b", X_ACCESS_TOKEN: "sample-c", X_ACCESS_SECRET: "sample-d",
  X_CONSUMER_KEY: "sample-a", X_CONSUMER_SECRET: "sample-b", X_ACCESS_TOKEN_SECRET: "sample-d",
  MAIL: { send: async (m) => { mails.push(m.subject + "\n" + m.text); } } });
const w = (await import(pathToFileURL(join(dir, "worker.mjs")).href)).default;
const run = async (env, cron, t) => { const ps = []; await w.scheduled({ cron, scheduledTime: at(t) }, env, { waitUntil: (p) => ps.push(p) }); await Promise.all(ps); };
const reset = () => { holes = 0; tweets = []; uploads = 0; failTweet = () => null; failUpload = null; mails.length = 0; opened = []; };
const MORNING = "30 21,23 * * *", EVENING = "30 13 * * *", TEN = "*/10 0-14,20-23 * * *";
const morningOut = (n) => ({ ok: true, date: "20261114", caption: "11/14 地方競馬の予想", summary: { image: PNG }, cards: Array.from({ length: n }, () => ({ image: PNG })) });
const noRace = { ok: false, error: "no races" };
const state = async (env, kind) => JSON.parse((await env.DB.prepare("SELECT body FROM xpost_log WHERE k=?").bind(`s:20261114:${kind}`).first()).body);

// 1) 朝 8:30: 画像5枚を1件にまとめて投稿／中央は開催なし
{ reset(); const env = mkEnv(); outs = { nar: morningOut(4), jra: noRace };
  await run(env, MORNING, "2026-11-14T08:30:00");
  eq("朝: 1件・画像5枚", [tweets.length, tweets[0].media.media_ids.length, tweets[0].text], [1, 5, "11/14 地方競馬の予想"]);
  eq("朝: 記録", await state(env, "morning"), { modes: { nar: "ok", jra: "none" }, tries: 0 });
  eq("朝: 投稿のIDを覚える", (await env.DB.prepare("SELECT tweet_id FROM xpost_log WHERE k=?").bind("m:20261114:nar").first()).tweet_id, "t1");
  eq("朝: メール", mails[0].split("\n")[0].startsWith("【投稿OK】朝の予想"), true);
  await run(env, TEN, "2026-11-14T09:00:00");
  eq("朝: 成功した日はやり直さない", tweets.length, 1); }
// 2) 6:30 は点検だけ。投稿もページを開くこともしない。問題なしならメールも無し
{ reset(); const env = mkEnv(); outs = { nar: morningOut(4), jra: noRace };
  await run(env, MORNING, "2026-11-14T06:30:00");
  eq("点検: 投稿しない・開かない・メールなし", [tweets.length, opened.length, mails.length, env.DB.rows.size], [0, 0, 0, 0]); }
// 3) 朝が一時的な失敗 → 9:00 に地方だけ出し直す
{ reset(); const env = mkEnv(); outs = { nar: { ok: false, error: "Waiting failed: 420000ms exceeded" }, jra: noRace };
  await run(env, MORNING, "2026-11-14T08:30:00");
  eq("失敗の記録", [(await state(env, "morning")).modes, tweets.length, mails[0].startsWith("【⚠失敗あり】")], [{ nar: "fail", jra: "none" }, 0, true]);
  outs = { nar: morningOut(2), jra: noRace }; opened = [];
  await run(env, TEN, "2026-11-14T09:00:00");
  eq("やり直し: 地方だけ開いて投稿（取得と生成の2回開く）", [opened.length, /mode=nar/.test(opened[0]), tweets.length, (await state(env, "morning")).modes.nar], [2, true, 1, "ok"]);
  eq("やり直し: メール", [mails[1].split("\n")[0].includes("朝の予想・やり直し"), mails[1].includes("※やり直し（1回目）")], [true, true]);
  eq("やり直し: 的中速報のためのID", (await env.DB.prepare("SELECT tweet_id FROM xpost_log WHERE k=?").bind("m:20261114:nar").first()).tweet_id, "t1");
  await run(env, TEN, "2026-11-14T09:20:00");
  eq("直ったあとは出さない", tweets.length, 1); }
// 4) 鍵の失敗（11/13 朝と同じ返答）→ やり直さない
{ reset(); const env = mkEnv(); outs = { nar: morningOut(2), jra: noRace }; failUpload = [400, { errors: [{ code: 215, message: "Bad Authentication data." }] }];
  await run(env, MORNING, "2026-11-14T08:30:00");
  eq("鍵: 記録", (await state(env, "morning")).modes.nar, "auth");
  const n = uploads; await run(env, TEN, "2026-11-14T09:00:00");
  eq("鍵: やり直さない", [uploads, tweets.length], [n, 0]); }
// 5) 夜: 1件にまとめた投稿をXが断る → 分けて出す。2件目で止まる → 途中までの記録・やり直さない
{ reset(); const env = mkEnv();
  outs = { nar: { ok: true, date: "20261114", posts: [{ text: "まとめ", images: [] }, { text: "答え合わせです", images: [PNG, PNG] }, { text: "回収率です", images: [PNG] }] }, jra: noRace };
  failTweet = (b, n) => (b.media && b.media.media_ids.length === 3) ? [403, { detail: "too many media" }] : (n === 2 ? [503, { detail: "over capacity" }] : null);
  await run(env, EVENING, "2026-11-14T22:30:00");
  eq("夜: 途中まで", [tweets.length, (await state(env, "evening")).modes.nar, mails[0].includes("途中まで投稿して止まりました（2件）")], [2, "part", true]);
  failTweet = () => null; await run(env, TEN, "2026-11-14T22:50:00");
  eq("夜: 途中までの回は出し直さない", tweets.length, 2); }
// 6) 夜: まとめて1件で通る
{ reset(); const env = mkEnv();
  outs = { nar: { ok: true, date: "20261114", posts: [{ text: "まとめ", images: [] }, { text: "答え合わせです", images: [PNG, PNG] }] }, jra: noRace };
  await run(env, EVENING, "2026-11-14T22:30:00");
  eq("夜: 1件・文は画像なしの投稿の文", [tweets.length, tweets[0].text, tweets[0].media.media_ids.length, (await state(env, "evening")).modes], [1, "まとめ", 2, { nar: "ok", jra: "none" }]); }
// 7) 11/13 19:20 の事故の再現: 古い指定の回・知らない指定の回・ずれた時刻の回からは投稿しない。同じ回は2度出さない
{ reset(); const env = mkEnv();
  outs = { nar: { ok: true, date: "20261114", posts: [{ text: "まとめ", images: [] }, { text: "答え合わせです", images: [PNG] }] }, jra: noRace };
  await run(env, "*/10 1-13 * * *", "2026-11-14T19:20:00");
  await run(env, "*/10 3-9 * * *", "2026-11-14T19:30:00");
  await run(env, "0 5 * * *", "2026-11-14T14:00:00");
  await run(env, EVENING, "2026-11-14T19:20:00");
  await run(env, "30 23 * * *", "2026-11-14T08:30:00");
  eq("想定外の回は投稿しない", [tweets.length, opened.length], [0, 0]);
  await run(env, EVENING, "2026-11-14T22:30:00"); await run(env, EVENING, "2026-11-14T22:30:00");
  eq("同じ回は1度だけ", tweets.length, 1); }
// 7) 週間まとめ: 月曜 9:10。まだ集計が無ければ出さず、12:10 に出す。出したあとは出さない
{ reset(); const env = mkEnv();
  outs = { nar: { ok: false, kind: "weekly", error: "no races（20261109 の週は日曜ぶんの結果がまだ入っていない）" } };
  await run(env, TEN, "2026-11-16T09:10:00");
  eq("週間: まだ無い → 出さない・メールも無し", [tweets.length, mails.length, /auto=weekly&mode=nar&wk=20261109/.test(opened[0])], [0, 0, true]);
  outs = { nar: { ok: true, kind: "weekly", image: PNG, text: "先週（11/9〜11/15）の成績です" } };
  await run(env, TEN, "2026-11-16T12:10:00");
  eq("週間: 12:10 に出す", [tweets.length, tweets[0].text, tweets[0].media.media_ids.length, mails[0].startsWith("【投稿OK】週間まとめ")], [1, "先週（11/9〜11/15）の成績です", 1, true]);
  const n = opened.length; await run(env, TEN, "2026-11-16T15:10:00");
  eq("週間: 出したあとは開きもしない", [tweets.length, opened.length], [1, n]);
  await run(env, TEN, "2026-11-17T09:10:00");
  eq("週間: 火曜は何もしない", [tweets.length, opened.length], [1, n]); }
// 8) 週間まとめ: 3回とも出せなかったら、最後の回だけメールで知らせる
{ reset(); const env = mkEnv();
  outs = { nar: { ok: false, kind: "weekly", error: "no races（20261109 の週は150レース未満）" } };
  for (const t of ["09:10", "12:10", "15:10"]) await run(env, TEN, `2026-11-16T${t}:00`);
  eq("週間: 出せない週は最後に1通だけ", [tweets.length, mails.length], [0, 1]); }
// ---- 段階（2026-11-23）----
const stg = async (env, d, kind, mode) => JSON.parse(((await env.DB.prepare("SELECT body FROM xpost_log WHERE k=?").bind(`st:${d}:${kind}:${mode}`).first()) || { body: "{}" }).body);
// 9) 取得が欠けていたら、生成も投稿もしない。理由が状態とメールに残る。直れば 9:00 に続きから出す
{ reset(); const env = mkEnv(); outs = { nar: morningOut(3), jra: noRace }; holes = 1;
  await run(env, MORNING, "2026-11-14T08:30:00");
  const s1 = await stg(env, "20261114", "morning", "nar");
  eq("欠け: 投稿しない・生成のページを開かない", [tweets.length, opened.filter(x => /stage=gen/.test(x)).length], [0, 0]);
  eq("欠け: 状態に理由", [s1.fetch.s, s1.fetch.total, s1.fetch.got, s1.gen === undefined], ["miss", 6, 5, true]);
  eq("欠け: メールに理由", [mails[0].startsWith("【⚠失敗あり】"), mails[0].includes("取得の確認で止めました")], [true, true]);
  eq("欠け: やり直しの対象", (await state(env, "morning")).modes.nar, "fail");
  curDB.preds.length = 0; holes = 0;
  await run(env, TEN, "2026-11-14T09:00:00");
  const s2 = await stg(env, "20261114", "morning", "nar");
  eq("直った: 取得→生成→投稿", [tweets.length, s2.fetch.s, s2.gen.s, s2.post.s, s2.post.ids], [1, "ok", "ok", "ok", ["t1"]]); }
// 10) 夜: 結果が欠けていたら止める（11/22 の中央の 9/19 と同じ形）
{ reset(); const env = mkEnv(); holes = 1;
  outs = { nar: { ok: true, date: "20261114", posts: [{ text: "まとめ", images: [] }, { text: "答え合わせです", images: [PNG] }] }, jra: noRace };
  await run(env, EVENING, "2026-11-14T22:30:00");
  const s1 = await stg(env, "20261114", "evening", "nar");
  eq("夜の欠け: 止める", [tweets.length, s1.fetch.s, s1.fetch.missing, (await state(env, "evening")).modes.nar], [0, "miss", ["narE"], "fail"]);
  // 手で「欠けを承知で進める」（accept）→ 取得し直さずに生成・投稿
  await env.DB.prepare("INSERT OR REPLACE INTO xpost_log(k,date,mode,tweet_id,body,ts) VALUES(?,?,?,?,?,?)").bind("job:20261114:evening:nar", "20261114", "nar", null, JSON.stringify({ kind: "evening", mode: "nar", date: "20261114", steps: ["gen", "post"], accept: true }), 1).run();
  opened = [];
  await run(env, TEN, "2026-11-14T22:40:00");
  const s2 = await stg(env, "20261114", "evening", "nar");
  eq("承知で進める: 投稿・記録が残る", [tweets.length, s2.fetch.accepted, s2.fetch.missing, s2.post.s, opened.filter(x => /stage=fetch/.test(x)).length], [1, 1, ["narE"], "ok", 0]); }
// 11) 投稿でXが断った → 生成は済みなので、やり直しは保存した画像で投稿だけ（ページを開かない）
{ reset(); const env = mkEnv(); outs = { nar: morningOut(2), jra: noRace };
  failTweet = () => [503, { detail: "over capacity" }];
  await run(env, MORNING, "2026-11-14T08:30:00");
  eq("投稿の失敗: 状態", [(await stg(env, "20261114", "morning", "nar")).post.s, (await state(env, "morning")).modes.nar], ["fail", "fail"]);
  failTweet = () => null; opened = [];
  await run(env, TEN, "2026-11-14T09:00:00");
  eq("投稿だけやり直す", [opened.length, tweets.length, tweets[0].media.media_ids.length, (await stg(env, "20261114", "morning", "nar")).post.s], [0, 1, 3, "ok"]); }
// 12) 中央の先行取得: 7:00 に取得だけ。8:30 は取得し直さず、保存から生成して投稿
{ reset(); const env = mkEnv(); outs = { nar: noRace, jra: morningOut(2) };
  await env.DB.prepare("INSERT OR REPLACE INTO xpost_log(k,date,mode,tweet_id,body,ts) VALUES(?,?,?,?,?,?)").bind("wm:20261114", "20261114", "-", null, JSON.stringify({ rids: ["jra0a", "jra0b", "jra1a", "jra1b"] }), 1).run();
  await run(env, TEN, "2026-11-14T07:00:00");
  eq("先行: 取得だけ", [opened.length, /stage=fetch/.test(opened[0]), tweets.length, (await stg(env, "20261114", "morning", "jra")).fetch.s], [1, true, 0, "ok"]);
  await run(env, TEN, "2026-11-14T07:20:00");
  eq("先行: 済んだら次の回は何もしない", opened.length, 1);
  opened = [];
  await run(env, MORNING, "2026-11-14T08:30:00");
  eq("8:30: 中央は生成から（取得し直さない）", [opened.filter(x => /mode=jra/.test(x)).map(x => /stage=(\w+)/.exec(x)[1]), tweets.length], [["gen"], 1]); }
// 13) 先行取得: 一覧のレースが欠けていたら止める（8:00 の最後の回だけメール）
{ reset(); const env = mkEnv(); outs = { nar: noRace, jra: morningOut(1) };
  await env.DB.prepare("INSERT OR REPLACE INTO xpost_log(k,date,mode,tweet_id,body,ts) VALUES(?,?,?,?,?,?)").bind("wm:20261114", "20261114", "-", null, JSON.stringify({ rids: ["jra0a", "jra0b", "jra9z"] }), 1).run();
  for (const t of ["07:00", "07:20", "07:40"]) await run(env, TEN, `2026-11-14T${t}:00`);
  const s1 = await stg(env, "20261114", "morning", "jra");
  eq("先行の欠け: 止める・メールはまだ", [s1.fetch.s, s1.fetch.missing, mails.length], ["miss", ["jra9z（保存なし）"], 0]);
  await run(env, TEN, "2026-11-14T08:00:00");
  eq("先行の欠け: 8:00 にメール", [mails.length, mails[0] && mails[0].includes("中央の先行取得")], [1, true]); }
// 14) 手で段階を動かす: /stage で状態を見る・依頼する・10分ごとの回が動かす・投稿済みは断る
{ reset(); const env = mkEnv(); env.TRIGGER_KEY = "sample-key"; outs = { nar: morningOut(1), jra: noRace };
  const get = async (q) => JSON.parse(await (await w.fetch(new Request("https://example.test/stage?" + q), env)).text());
  eq("鍵が違えば断る", (await get("key=x")).error, "forbidden (key不一致)");
  const v = await get("key=sample-key&date=20261114");
  eq("状態の表示（何も動かさない）", [v.date, opened.length, typeof v.stages.morning.nar], ["20261114", 0, "object"]);
  const q = await get("key=sample-key&kind=morning&mode=nar&step=fetch&date=" + new Date(Date.now() + 9 * 3600e3).toISOString().slice(0, 10).replace(/-/g, "") + "&go=1");
  eq("依頼できる", [q.queued, q.steps], [true, ["fetch"]]);
  eq("待っている依頼は重ねない", (await get(q.date && ("key=sample-key&kind=morning&mode=nar&step=fetch&date=" + q.date + "&go=1"))).refused, true);
  eq("2日前は断る", (await get("key=sample-key&kind=morning&mode=nar&step=all&date=20261110&go=1")).refused, true); }
// 15) 依頼の実行（runJobs）: 取得だけ頼めば取得だけ、続けて all なら生成と投稿。投稿済みのあとは all を断る
{ reset(); const env = mkEnv(); env.TRIGGER_KEY = "sample-key"; outs = { nar: morningOut(1), jra: noRace };
  const get = async (q) => JSON.parse(await (await w.fetch(new Request("https://example.test/stage?" + q), env)).text());
  const d = "20261114";
  await env.DB.prepare("INSERT OR REPLACE INTO xpost_log(k,date,mode,tweet_id,body,ts) VALUES(?,?,?,?,?,?)").bind(`job:${d}:morning:nar`, d, "nar", null, JSON.stringify({ kind: "morning", mode: "nar", date: d, steps: ["fetch"] }), 1).run();
  await run(env, TEN, "2026-11-14T08:10:00");
  eq("依頼: 取得だけ", [tweets.length, (await stg(env, d, "morning", "nar")).fetch.s, JSON.parse(env.DB.rows.get(`job:${d}:morning:nar`).body).done], [0, "ok", 1]);
  await env.DB.prepare("INSERT OR REPLACE INTO xpost_log(k,date,mode,tweet_id,body,ts) VALUES(?,?,?,?,?,?)").bind(`job:${d}:morning:nar`, d, "nar", null, JSON.stringify({ kind: "morning", mode: "nar", date: d, steps: ["fetch", "gen", "post"] }), 2).run();
  opened = [];
  await run(env, TEN, "2026-11-14T08:20:00");
  eq("依頼: 続きから（取得し直さない）", [opened.map(x => /stage=(\w+)/.exec(x)[1]), tweets.length, (await stg(env, d, "morning", "nar")).post.s], [["gen"], 1, "ok"]);
  await env.DB.prepare("INSERT OR REPLACE INTO xpost_log(k,date,mode,tweet_id,body,ts) VALUES(?,?,?,?,?,?)").bind(`job:${d}:morning:nar`, d, "nar", null, JSON.stringify({ kind: "morning", mode: "nar", date: d, steps: ["post"], force: true }), 3).run();
  await run(env, TEN, "2026-11-14T08:40:00");
  eq("依頼: 投稿済みは force でも出さない", tweets.length, 1); }
console.log("OK", ok, "NG", ng); process.exit(ng ? 1 : 0);

