// 朝の前に中央のページを取っておく仕組みの試験（ネットにも本物のDBにも触らない）
import { warmSlot, listRids, pickWarm, runWarm } from "../src/warm.js";
let ok = 0, ng = 0;
const eq = (n, a, b) => { const r = JSON.stringify(a) === JSON.stringify(b); r ? ok++ : (ng++, console.log("NG", n, JSON.stringify(a), JSON.stringify(b))); };
const J = (h, m) => Date.UTC(2026, 10, 14, h - 9, m);   // 日本時間 2026-11-14 h:m
eq("5:00 は取る回", warmSlot(J(5, 0)), true);
eq("8:20 は取る回", warmSlot(J(8, 20)), true);
eq("8:30 は取らない（朝の本番）", warmSlot(J(8, 30)), false);
eq("4:50 は取らない", warmSlot(J(4, 50)), false);
eq("昼は取らない", warmSlot(J(12, 0)), false);
eq("一覧から番号を拾う（重複なし）", listRids('a href="x?race_id=202605050401&a" b race_id=202605050402 c race_id=202605050401'), ["202605050401", "202605050402"]);
eq("まだのものだけ・件数まで", pickWarm(["a", "b", "c", "d"], ["b"], 0, 2), ["a", "c"]);
eq("見はじめる場所をずらす", pickWarm(["a", "b", "c", "d"], ["b"], 2, 2), ["d", "a"]);
eq("全部済みなら空", pickWarm(["a"], ["a"], 5), []);
// にせのDBとにせの通信
const mkDB = () => { const rows = {}; return { rows, prepare: sql => ({ run: async () => ({}), bind: (...a) => ({ first: async () => rows[a[0]] ? { body: rows[a[0]] } : null, run: async () => { rows[a[0]] = a[4]; return {}; } }) }) }; };
const page = "x".repeat(30000), list = Array.from({ length: 8 }, (_, i) => `race_id=20260505040${i + 1}`).join(" ") + " ".repeat(300);
let calls = [], fail = new Set();
const dec = u => atob(decodeURIComponent(String(u).split("u=")[1].split("&")[0]).replace(/-/g, "+").replace(/_/g, "/"));
globalThis.fetch = async u => { const t = dec(u); calls.push(t);
  if (t.includes("race_list_sub")) return fail.has("list") ? { ok: false, headers: { get: () => null }, text: async () => "" } : { ok: true, headers: { get: () => "miss" }, text: async () => list };
  const rid = t.slice(-12); return fail.has(rid) ? { ok: false, headers: { get: () => null }, text: async () => "" } : { ok: true, headers: { get: () => "relay" }, text: async () => page }; };
const nosleep = async () => {};
let env = { DB: mkDB() };
eq("取る回でなければ何もしない", [await runWarm(env, J(12, 0), { sleep: nosleep }), calls.length], [null, 0]);
fail.add("list");
let r = await runWarm(env, J(5, 0), { sleep: nosleep });
eq("一覧が取れない時は次の回に任せる（開催なしと決めつけない）", [r.list, r.none, calls.length], [false, false, 1]);
fail.delete("list"); fail.add("202605050402"); calls = [];
r = await runWarm(env, J(5, 10), { sleep: nosleep });
eq("一覧＋6レースぶん取りに行く", [calls.length, r.races, r.tried], [7, 8, 6]);
eq("取れたぶんだけ済みにする", r.got, r.done);
calls = []; fail.clear();
r = await runWarm(env, J(5, 20), { sleep: nosleep });
r = await runWarm(env, J(5, 30), { sleep: nosleep });
eq("何回かで全部そろう", r.done, 8);
calls = [];
r = await runWarm(env, J(5, 40), { sleep: nosleep });
eq("そろったあとは取りに行かない", [calls.length, r.tried], [0, 0]);
eq("同じレースを二重に数えない", new Set(JSON.parse(env.DB.rows["wm:20261114"]).done).size, 8);
// レースの無い一覧が返る日
const W = (h, m) => Date.UTC(2026, 10, 17, h - 9, m);   // 火曜
env = { DB: mkDB() }; calls = [];
globalThis.fetch = async u => { calls.push(1); return { ok: true, headers: { get: () => "miss" }, text: async () => "<div>" + " ".repeat(400) + "</div>" }; };
for (const mm of [0, 10, 20, 30, 40]) r = await runWarm(env, W(5, mm), { sleep: nosleep });
eq("平日は3回見て無ければやめる", [calls.length, r.none], [3, true]);
env = { DB: mkDB() }; calls = [];
for (const mm of [0, 10, 20, 30, 40]) r = await runWarm(env, J(5, mm), { sleep: nosleep });
eq("土日（と月曜）は開催なしと決めつけず見に行き続ける", [calls.length, r.none], [5, false]);
console.log("OK", ok, "NG", ng); process.exit(ng ? 1 : 0);
