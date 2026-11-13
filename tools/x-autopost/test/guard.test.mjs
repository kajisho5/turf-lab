// 自動投稿の見張り（やり直し・朝の前の点検）の試験。Xにもネットにも触らない
import { jst, isRehearsalTime, retryKind, modeState, stateOf, planRetry, markStart, saveState, loadState, runRetry, rehearsal, GUARD_FROM } from "../src/guard.js";
let ok = 0, ng = 0;
const eq = (n, a, b) => { const r = JSON.stringify(a) === JSON.stringify(b); r ? ok++ : (ng++, console.log("NG", n, JSON.stringify(a), JSON.stringify(b))); };
const at = (s) => Date.parse(s + "+09:00");            // 日本時間の文字列 → ミリ秒

// どの回か
eq("6:30 は点検", isRehearsalTime(at("2026-11-14T06:30:00")), true);
eq("8:30 は点検ではない", isRehearsalTime(at("2026-11-14T08:30:00")), false);
eq("22:30 は点検ではない", isRehearsalTime(at("2026-11-14T22:30:00")), false);
eq("9:00 は点検ではない", isRehearsalTime(at("2026-11-14T09:00:00")), false);
eq("日付は日本時間", jst(at("2026-11-14T06:30:00")).date, "20261114");
eq("やり直し 朝", [retryKind(at("2026-11-14T09:00:00")), retryKind(at("2026-11-14T09:20:00")), retryKind(at("2026-11-14T09:10:00")), retryKind(at("2026-11-14T10:00:00"))], ["morning", "morning", null, null]);
eq("やり直し 夜", [retryKind(at("2026-11-14T22:50:00")), retryKind(at("2026-11-14T23:10:00")), retryKind(at("2026-11-14T22:40:00")), retryKind(at("2026-11-14T23:00:00"))], ["evening", "evening", null, null]);

// 1モードの結果の読み方
eq("投稿できた", modeState({ ok: true, posted: [{ id: "1", images: 9 }] }), "ok");
eq("11/13 朝の実物（鍵）", modeState({ ok: false, error: 'media upload 400: {"errors":[{"code":215,"message":"Bad Authentication data."}]}' }), "auth");
eq("401", modeState({ error: "tweet 401: Unauthorized" }), "auth");
eq("開催なし", modeState({ ok: false, error: "no races" }), "none");
eq("素材0件", modeState({ ok: true, posts: [] }), "none");
eq("待ち切れ", modeState({ ok: false, error: "Waiting failed: 420000ms exceeded" }), "fail");
eq("Xの一時的な失敗", modeState({ ok: false, error: "tweet 503: over capacity" }), "fail");
eq("途中まで", modeState({ ok: false, error: "tweet 503", partial: [{ id: "9", images: 4 }] }), "part");
eq("結果なし", modeState(undefined), "fail");
eq("まとめ", stateOf({ modes: { nar: { posted: [{ id: "1" }] }, jra: { error: "no races" } } }, ["nar", "jra"]), { nar: "ok", jra: "none" });
eq("お試しはやり直さない", stateOf({ dry: true, modes: { nar: { ok: true, posts: [{}] } } }, ["nar"]), { nar: "dry" });
eq("全体が落ちた", stateOf(null, ["nar", "jra"]), { nar: "fail", jra: "fail" });

// やり直すかどうか
const M = ["nar", "jra"];
eq("失敗だけやり直す", planRetry({ modes: { nar: "fail", jra: "none" }, tries: 0 }, "20261114", M).run, ["nar"]);
eq("鍵はやり直さない", planRetry({ modes: { nar: "auth", jra: "none" }, tries: 0 }, "20261114", M).run, []);
eq("途中まではやり直さない", planRetry({ modes: { nar: "part", jra: "ok" }, tries: 0 }, "20261114", M).run, []);
eq("2回まで", planRetry({ modes: { nar: "fail" }, tries: 2 }, "20261114", M).run, []);
eq("記録なし（入れる前の日）", planRetry(null, "20261113", M).run, []);
eq("記録なし（入れた後）", planRetry(null, GUARD_FROM, M).run, M);
eq("途中で止まった記録は知らせるだけ", [planRetry({ started: 1 }, "20261114", M).run, !!planRetry({ started: 1 }, "20261114", M).warn], [[], true]);
eq("知らせは1回", planRetry({ started: 1, warned: 1 }, "20261114", M).warn, null);
eq("DBなし", planRetry(undefined, "20261114", M).run, []);

// 通し（にせのデータベース）
function fakeDB() {
  const t = new Map();
  return { rows: t, prepare(sql) { let a = []; const st = {
    bind(...x) { a = x; return st; },
    async run() {
      if (/^CREATE/.test(sql)) return { meta: { changes: 0 } };
      if (/^INSERT OR REPLACE/.test(sql)) { t.set(a[0], { k: a[0], date: a[1], mode: a[2], tweet_id: a[3], body: a[4] }); return { meta: { changes: 1 } }; }
      if (/^INSERT OR IGNORE/.test(sql)) { if (t.has(a[0])) return { meta: { changes: 0 } }; t.set(a[0], { k: a[0], date: a[1], mode: a[2], tweet_id: a[3], body: a[4] }); return { meta: { changes: 1 } }; }
      throw new Error(sql); },
    async first() { if (/^SELECT 1/.test(sql)) return { 1: 1 }; return t.get(a[0]) || null; } }; return st; } };
}
{
  const env = { DB: fakeDB() }, calls = [], mails = [];
  const runAll = async (kind, mode) => { calls.push(kind + ":" + mode); return { modes: { [mode]: { ok: true, posted: [{ id: "777", images: 9 }] } } }; };
  const notify = async (kind, r, note) => { mails.push([kind, r ? Object.keys(r.modes) : null, note]); };
  const d = "20261114";
  await markStart(env, d, "morning");
  await saveState(env, d, "morning", { modes: { nar: "fail", jra: "none" }, tries: 0 });
  eq("やり直しの回ではない時刻は何もしない", await runRetry(env, at("2026-11-14T09:10:00"), M, runAll, notify), null);
  let r = await runRetry(env, at("2026-11-14T09:00:00"), M, runAll, notify);
  eq("失敗した地方だけ出し直す", [calls, r.state, mails], [["morning:nar"], { modes: { nar: "ok", jra: "none" }, tries: 1 }, [["morning", ["nar"], "やり直し（1回目）"]]]);
  r = await runRetry(env, at("2026-11-14T09:20:00"), M, runAll, notify);
  eq("直ったら次の回は何もしない", [calls.length, r.run], [1, []]);

  // 2回とも失敗 → 2回で止まる
  const env2 = { DB: fakeDB() }, c2 = [];
  const bad = async (kind, mode) => { c2.push(mode); return { modes: { [mode]: { ok: false, error: "Waiting failed: 420000ms exceeded" } } }; };
  await saveState(env2, d, "evening", { modes: { nar: "fail", jra: "ok" }, tries: 0 });
  await runRetry(env2, at("2026-11-14T22:50:00"), M, bad, notify);
  await runRetry(env2, at("2026-11-14T23:10:00"), M, bad, notify);
  eq("失敗が続いても2回まで", [c2, (await loadState(env2, d, "evening")).tries], [["nar", "nar"], 2]);

  // 途中で落ちた（印だけ残る）→ 次の回は出し直さない
  const env3 = { DB: fakeDB() }, c3 = [];
  await saveState(env3, d, "morning", { modes: { nar: "fail", jra: "none" }, tries: 0 });
  const dies = async (kind, mode) => { c3.push(mode); throw new Error("worker killed"); };
  await runRetry(env3, at("2026-11-14T09:00:00"), M, dies, notify);
  eq("例外は失敗として記録", (await loadState(env3, d, "morning")).modes.nar, "fail");

  // 記録が無い日: 入れる前の日は何もしない／入れた後は、朝の投稿のIDが無いモードだけ
  const env4 = { DB: fakeDB() }, c4 = [];
  const fine = async (kind, mode) => { c4.push(kind + ":" + mode); return { modes: { [mode]: { ok: true, posted: [{ id: "5", images: 1 }] } } }; };
  await runRetry(env4, at("2026-11-13T22:50:00"), M, fine, notify);
  eq("入れる前の日（今夜）は出し直さない", c4, []);
  await env4.DB.prepare("INSERT OR REPLACE INTO xpost_log(k,date,mode,tweet_id,body,ts) VALUES(?,?,?,?,?,?)").bind("m:20261115:nar", "20261115", "nar", "123", null, 0).run();
  await runRetry(env4, at("2026-11-15T09:00:00"), M, fine, notify);
  eq("朝の投稿のIDがあるモードは出し直さない", c4, ["morning:jra"]);

  // 回が途中で止まった記録 → 知らせるだけ（1回）
  const env5 = { DB: fakeDB() }, m5 = [];
  await markStart(env5, d, "evening");
  const n5 = async (kind, r, note) => { m5.push(note); };
  await runRetry(env5, at("2026-11-14T22:50:00"), M, fine, n5);
  await runRetry(env5, at("2026-11-14T23:10:00"), M, fine, n5);
  eq("途中で止まった回は知らせるだけ・1回", [m5.length, c4.length], [1, 1]);
  await markStart(env5, d, "evening");
  eq("始まりの印は結果を上書きしない", (await loadState(env5, d, "evening")).warned, 1);
}
// 朝の前の点検
{
  const pages = { "tweet.html": "… window.__autoOut …", "core/ltr_model_t.js": "narT", "data/horses.json": '{"a":1}', "data/horses_time.json": '{"a":1}', "data/nar_index_asof.json": '{"asof":"20261113"}' };
  const get = (over = {}) => async (u) => { const f = u.replace("https://seventh-well.com/odds/", "").split("?")[0]; const b = f in over ? over[f] : pages[f];
    return b == null ? { ok: false, status: 404, text: async () => "", json: async () => ({}) } : { ok: true, status: 200, text: async () => b, json: async () => JSON.parse(b) }; };
  const env = { DB: fakeDB() }, t = at("2026-11-14T06:30:00");
  const good = async () => ({ ok: true, status: 200, body: "{}" });
  eq("問題なし", await rehearsal(env, t, good, get()), []);
  eq("鍵が通らない", (await rehearsal(env, t, async () => ({ ok: false, status: 401, body: "Unauthorized" }), get())).length, 1);
  eq("時計の索引が無い", (await rehearsal(env, t, good, get({ "data/horses_time.json": null })))[0], "data/horses_time.json が読めません（404）");
  eq("索引が1日古いだけなら言わない", await rehearsal(env, t, good, get({ "data/nar_index_asof.json": '{"asof":"20261112"}' })), []);
  eq("索引が2日以上古い", (await rehearsal(env, t, good, get({ "data/nar_index_asof.json": '{"asof":"20261111"}' }))).length, 1);
  eq("D1なし", (await rehearsal({}, t, good, get())).length, 1);
}
console.log("OK", ok, "NG", ng); process.exit(ng ? 1 : 0);
