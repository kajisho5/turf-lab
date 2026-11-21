// 依頼された出し直し（1つの場だけ・1回だけ）の試験。Xにもネットにも触らない
{
  const { runAsk } = await import("../src/guard.js");
  const J = (s) => Date.parse(s + "+09:00");
  const eq = (a, b, n) => { if (JSON.stringify(a) === JSON.stringify(b)) { console.log("ok  " + n); } else { console.log("NG  " + n, a, b); process.exitCode = 1; } };
  const mk = (rows) => { const db = new Map(Object.entries(rows));
    return { db, DB: { prepare: (sql) => ({ bind: (...a) => ({
      first: async () => { const v = db.get(a[0]); return v === undefined ? null : v; },
      run: async () => { if (/^UPDATE/.test(sql)) db.set(a[2], { body: a[0] }); return { meta: { changes: 1 } }; } }) }) } }; };
  const T = J("2026-11-21T15:00:00");
  const e1 = mk({ "ask:20261121": { body: JSON.stringify({ mode: "nar", tc: "65" }) } });
  const seen = []; let mailed = 0;
  const r1 = await runAsk(e1, T, async (mode, tc) => { seen.push(mode + tc + JSON.parse(e1.db.get("ask:20261121").body).done); return { modes: { nar: { ok: true, posted: [{ id: "1" }] } } }; }, async () => { mailed++; });
  eq([seen, mailed, r1 && r1.state], [["nar651"], 1, "ok"], "ask: 依頼があれば1回出す（先に済みの印が付いている）");
  eq(await runAsk(e1, T, async () => { throw new Error("x"); }, async () => {}), null, "ask: 済みなら二度と出さない");
  eq(await runAsk(mk({}), T, async () => { throw new Error("x"); }, async () => {}), null, "ask: 依頼が無ければ何もしない");
  for (const bad of [{ mode: "x", tc: "65" }, { mode: "nar", tc: "6" }, { mode: "nar", tc: "65&x=1" }, { mode: "nar" }])
    eq(await runAsk(mk({ "ask:20261121": { body: JSON.stringify(bad) } }), T, async () => { throw new Error("x"); }, async () => {}), null, "ask: 形が違う依頼は無視 " + JSON.stringify(bad));
  const e2 = mk({ "ask:20261121": { body: JSON.stringify({ mode: "nar", tc: "65" }) } });
  const r2 = await runAsk(e2, T, async () => { throw new Error("落ちた"); }, async () => { throw new Error("mail"); });
  eq([r2 && r2.state !== "ok", JSON.parse(e2.db.get("ask:20261121").body).done], [true, 1], "ask: 途中で落ちても済みのまま（二重に出さない）");
  eq(await runAsk(mk({ "ask:20261120": { body: JSON.stringify({ mode: "nar", tc: "65" }) } }), T, async () => { throw new Error("x"); }, async () => {}), null, "ask: 別の日の依頼は動かない");
}
// ---- 夜の回の依頼・やり直しの上限・失敗の理由（2026-11-22）----
{
  const { runAsk, planRetry, errsOf, runRetry } = await import("../src/guard.js");
  const J = (s) => Date.parse(s + "+09:00");
  const eq = (a, b, n) => { if (JSON.stringify(a) === JSON.stringify(b)) { console.log("ok  " + n); } else { console.log("NG  " + n, a, b); process.exitCode = 1; } };
  const mk = (rows) => { const db = new Map(Object.entries(rows));
    return { db, DB: { prepare: (sql) => ({ run: async () => ({ meta: { changes: 0 } }), bind: (...a) => ({
      first: async () => { const v = db.get(a[0]); return v === undefined ? null : v; },
      run: async () => { if (/^UPDATE/.test(sql)) db.set(a[2], { body: a[0] }); else if (/INSERT/.test(sql)) db.set(a[0], { body: a[4] }); return { meta: { changes: 1 } }; } }) }) } }; };
  const T = J("2026-11-22T07:00:00");
  const e1 = mk({ "ask:20261122": { body: JSON.stringify({ kind: "evening", mode: "jra", date: "20261121" }) } });
  const seen = [];
  const r1 = await runAsk(e1, T, async (mode, tc, kind, d) => { seen.push([mode, tc, kind, d]); return { modes: { jra: { ok: false, error: "429: Too Many Requests" } } }; }, async () => {});
  const b1 = JSON.parse(e1.db.get("ask:20261122").body);
  eq([seen, r1 && r1.state, b1.done, b1.error], [[["jra", null, "evening", "20261121"]], "fail", 1, "429: Too Many Requests"], "ask: 前の日の夜を1回出す。失敗の理由が記録に残る");
  eq(await runAsk(mk({ "ask:20261122": { body: JSON.stringify({ kind: "evening", mode: "jra", date: "20261119" }) } }), T, async () => { throw new Error("x"); }, async () => {}), null, "ask: 2日以上前の夜は出さない");
  eq(planRetry({ modes: { jra: "fail" }, tries: 2 }, "20261122", ["nar", "jra"]).run, [], "retry: 上限の指定が無ければ2回で止まる（今までどおり）");
  eq(planRetry({ modes: { jra: "fail" }, tries: 2, max: 4 }, "20261122", ["nar", "jra"]).run, ["jra"], "retry: 上限4なら3回目も動く");
  eq(errsOf({ modes: { nar: { ok: true }, jra: { error: "x".repeat(500) } } }, ["nar", "jra"]).jra.length, 300, "errs: 理由は300字まで");
  const e2 = mk({ "s:20261122:evening": { body: JSON.stringify({ modes: { nar: "ok", jra: "fail" }, tries: 2 }) } });
  let n = 0;
  const r2 = await runRetry(e2, J("2026-11-22T23:40:00"), ["nar", "jra"], async () => { n++; return { modes: { jra: { ok: false, error: "えらー" } } }; }, async () => {});
  const b2 = JSON.parse(e2.db.get("s:20261122:evening").body);
  eq([n, b2.tries, b2.errs && b2.errs.jra], [1, 3, "えらー"], "retry: 夜の3回目（23:40）が動き、理由が残る");
}
