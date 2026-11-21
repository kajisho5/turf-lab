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
