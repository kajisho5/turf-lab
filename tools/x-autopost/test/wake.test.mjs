// 毎朝のデータ更新を起こす仕組みの試験（GitHubにもネットにも触らない）
import { jstDay, needWake, wakeDeploy, daysLeft } from "../src/wake.js";
let ok = 0, ng = 0;
const eq = (n, a, b) => { const r = JSON.stringify(a) === JSON.stringify(b); r ? ok++ : (ng++, console.log("NG", n, JSON.stringify(a), JSON.stringify(b))); };
const T = Date.UTC(2026, 10, 13, 19, 40);   // 日本時間 2026-11-14 04:40
eq("今日（日本時間）", jstDay(T), "20261114");
eq("もう今日ぶんなら起こさない", needWake({ asof: "20261113", built: "20261114" }, "20261114"), false);
eq("きのうのままなら起こす", needWake({ asof: "20261112", built: "20261113" }, "20261114"), true);
eq("読めなかったら起こす", needWake(null, "20261114"), true);
const calls = [];
const mk = (asof, status) => async (u, o) => { u = String(u); calls.push([u.split("?")[0], o && o.method || "GET", o && o.headers && o.headers.Authorization || null]);
  if (u.includes("nar_index_asof")) return asof ? { ok: true, json: async () => asof } : { ok: false };
  return { ok: status === 204, status, text: async () => "Bad credentials" }; };
globalThis.fetch = mk({ asof: "20261112", built: "20261113" }, 204);
let r = await wakeDeploy({}, T);
eq("鍵が無ければ何もしない（通信もしない）", [r.woke, calls.length], [false, 0]);
r = await wakeDeploy({ GH_DISPATCH_TOKEN: "dummy-token-for-test" }, T);
eq("起こす", [r.woke, r.status], [true, 204]);
eq("起こす先と鍵の渡し方", calls[1], ["https://api.github.com/repos/kajisho5/turf-lab/actions/workflows/deploy-site.yml/dispatches", "POST", "Bearer dummy-token-for-test"]);
eq("結果に鍵の値を入れない", JSON.stringify(r).includes("dummy-token"), false);
calls.length = 0; globalThis.fetch = mk({ asof: "20261113", built: "20261114" }, 204);
r = await wakeDeploy({ GH_DISPATCH_TOKEN: "dummy-token-for-test" }, T);
eq("更新済みなら起こさない", [r.woke, calls.length], [false, 1]);
globalThis.fetch = mk({ asof: "20261112", built: "20261113" }, 401);
r = await wakeDeploy({ GH_DISPATCH_TOKEN: "dummy-token-for-test" }, T);
eq("鍵が違う時は失敗として返す", [r.woke, r.status, r.body], [false, 401, "Bad credentials"]);
eq("期限まであと何日（GitHub の書き方）", daysLeft("2026-12-01 03:00:00 UTC", T), 17);
eq("期限なし・読めない時は null", [daysLeft(null, T), daysLeft("", T), daysLeft("なし", T)], [null, null, null]);
console.log("OK", ok, "NG", ng); process.exit(ng ? 1 : 0);
