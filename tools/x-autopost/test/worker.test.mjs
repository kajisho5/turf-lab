// worker.js の通し（にせのブラウザ・にせのX・にせのデータベース。ネットには触らない。鍵は見本の文字）
// worker.js は Cloudflare のブラウザ部品を読み込むので、その1行だけ差し替えた写しを作って動かす
import { readFileSync, writeFileSync, mkdtempSync, copyFileSync } from "node:fs";
import { tmpdir } from "node:os"; import { join, dirname } from "node:path"; import { fileURLToPath, pathToFileURL } from "node:url";
const here = dirname(fileURLToPath(import.meta.url)), src = join(here, "..", "src");
const dir = mkdtempSync(join(tmpdir(), "autopost-"));
for (const f of ["posts.js", "hits.js", "guard.js"]) copyFileSync(join(src, f), join(dir, f));
let code = readFileSync(join(src, "worker.js"), "utf8");
const imp = 'import puppeteer from "@cloudflare/puppeteer";';
if (!code.includes(imp)) { console.log("NG worker.js の読み込みの行が変わった"); process.exit(1); }
writeFileSync(join(dir, "worker.mjs"), code.replace(imp, "const puppeteer = globalThis.__pp;").replace(/\.\/(posts|hits|guard)\.js/g, "./$1.js"));
let ok = 0, ng = 0;
const eq = (n, a, b) => { const r = JSON.stringify(a) === JSON.stringify(b); r ? ok++ : (ng++, console.log("NG", n, JSON.stringify(a), JSON.stringify(b))); };
const at = (s) => Date.parse(s + "+09:00");
const PNG = "data:image/png;base64,iVBORw0KGgo=";

function fakeDB() {
  const t = new Map();
  return { rows: t, prepare(sql) { let a = []; const st = {
    bind(...x) { a = x; return st; },
    async run() {
      if (/^CREATE/.test(sql)) return { meta: { changes: 0 } };
      if (/^INSERT OR REPLACE/.test(sql)) { t.set(a[0], { k: a[0], date: a[1], mode: a[2], tweet_id: a[3], body: a[4] }); return { meta: { changes: 1 } }; }
      if (/^INSERT OR IGNORE/.test(sql)) { if (t.has(a[0])) return { meta: { changes: 0 } }; t.set(a[0], { k: a[0], date: a[1], mode: a[2], tweet_id: a[3], body: a[4] }); return { meta: { changes: 1 } }; }
      throw new Error(sql); },
    async first() { if (/^SELECT 1/.test(sql)) return { 1: 1 }; return t.get(a[0]) || null; },
    async all() { return { results: [] }; } }; return st; } };
}
// にせのページ: mode ごとの __autoOut を返す
let outs = {}, opened = [];
globalThis.__pp = { launch: async () => ({
  newPage: async () => { let u = ""; return {
    goto: async (x) => { u = x; opened.push(x.replace(/^.*\?/, "")); },
    waitForFunction: async () => ({ jsonValue: async () => outs[/mode=(\w+)/.exec(u)[1]] }),
    close: async () => {} }; },
  close: async () => {} }) };
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
const mkEnv = () => ({ DB: fakeDB(), BROWSER: {}, TWEET_URL: "https://example.test/tweet.html", DRYRUN: "0", HITS: "0",
  X_API_KEY: "sample-a", X_API_SECRET: "sample-b", X_ACCESS_TOKEN: "sample-c", X_ACCESS_SECRET: "sample-d",
  X_CONSUMER_KEY: "sample-a", X_CONSUMER_SECRET: "sample-b", X_ACCESS_TOKEN_SECRET: "sample-d",
  MAIL: { send: async (m) => { mails.push(m.subject + "\n" + m.text); } } });
const w = (await import(pathToFileURL(join(dir, "worker.mjs")).href)).default;
const run = async (env, cron, t) => { const ps = []; await w.scheduled({ cron, scheduledTime: at(t) }, env, { waitUntil: (p) => ps.push(p) }); await Promise.all(ps); };
const reset = () => { tweets = []; uploads = 0; failTweet = () => null; failUpload = null; mails.length = 0; opened = []; };
const MORNING = "30 21,23 * * *", EVENING = "30 13 * * *", TEN = "*/10 0-14 * * *";
const morningOut = (n) => ({ ok: true, date: "20261114", summary: { image: PNG }, cards: Array.from({ length: n }, () => ({ image: PNG })) });
const noRace = { ok: false, error: "no races" };
const state = async (env, kind) => JSON.parse((await env.DB.prepare("SELECT body FROM xpost_log WHERE k=?").bind(`s:20261114:${kind}`).first()).body);

// 1) 朝 8:30: 画像5枚を1件にまとめて投稿／中央は開催なし
{ reset(); const env = mkEnv(); outs = { nar: morningOut(4), jra: noRace };
  await run(env, MORNING, "2026-11-14T08:30:00");
  eq("朝: 1件・画像5枚", [tweets.length, tweets[0].media.media_ids.length, tweets[0].text], [1, 5, "11/14\n地方競馬の予想です"]);
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
  eq("やり直し: 地方だけ開いて投稿", [opened.length, /mode=nar/.test(opened[0]), tweets.length, (await state(env, "morning")).modes.nar], [1, true, 1, "ok"]);
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
console.log("OK", ok, "NG", ng); process.exit(ng ? 1 : 0);
