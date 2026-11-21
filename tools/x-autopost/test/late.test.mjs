// 昼の出し直し（土日に中央の朝の予想が出なかった時）の試験。Xにもネットにも触らない
// ---- 昼の出し直し（2026-11-15）----
{
  const { lateSlot, runLate } = await import("../src/guard.js");
  const J = (s) => Date.parse(s + "+09:00");
  const eq = (a, b, n) => { if (JSON.stringify(a) === JSON.stringify(b)) { console.log("ok  " + n); } else { console.log("NG  " + n, a, b); process.exitCode = 1; } };
  eq(lateSlot(J("2026-11-15T13:00:00")), true, "late: 日曜 13:00 は見る");
  eq(lateSlot(J("2026-11-15T13:10:00")), false, "late: 13:10 は見ない");
  eq(lateSlot(J("2026-11-15T14:30:00")), false, "late: 14:30 は見ない");
  eq(lateSlot(J("2026-11-16T13:00:00")), true, "late: 月曜も見る（祝日の開催のため。出すかどうかは runLate が決める）");
  const mk = (rows) => { const db = new Map(Object.entries(rows));
    return { db, DB: { prepare: (sql) => ({ bind: (...a) => ({ first: async () => { const v = db.get(a[0]); return v === undefined ? null : v; },
      run: async () => { if (/INSERT/.test(sql)) db.set(a[0], { body: a[a.length - 2] !== undefined ? a.find(x => typeof x === "string" && x[0] === "{") : null }); return { meta: { changes: 1 } }; } }), run: async () => ({}) }) } }; };
  const e1 = mk({ "s:20261115:morning": { body: JSON.stringify({ modes: { nar: "ok", jra: "none" }, tries: 0 }) } });
  let called = 0, mailed = 0;
  const r1 = await runLate(e1, J("2026-11-15T13:00:00"), async () => { called++; return { modes: { jra: { ok: true, posted: [{ id: "1" }] } } }; }, async () => { mailed++; });
  eq([called, mailed, r1 && r1.state], [1, 1, "ok"], "late: 中央が「なし」の日曜は出し直して知らせる");
  const e2 = mk({ "s:20261115:morning": { body: JSON.stringify({ modes: { nar: "ok", jra: "ok" }, tries: 0 }) } });
  eq(await runLate(e2, J("2026-11-15T13:00:00"), async () => { throw new Error("x"); }, async () => {}), null, "late: 朝に出ていれば何もしない");
  const e3 = mk({ "s:20261115:morning": { body: JSON.stringify({ modes: { nar: "ok", jra: "none" }, tries: 0 }) }, "m:20261115:jra": { tweet_id: "9" } });
  eq(await runLate(e3, J("2026-11-15T13:00:00"), async () => { throw new Error("x"); }, async () => {}), null, "late: 朝の投稿のIDがあれば何もしない");
  const e4 = mk({ "s:20261115:morning": { body: JSON.stringify({ modes: { nar: "ok", jra: "none" }, tries: 0, late: 4 }) } });
  eq(await runLate(e4, J("2026-11-15T13:00:00"), async () => { throw new Error("x"); }, async () => {}), null, "late: 4回やったらやめる");
  const e5 = mk({ "s:20261115:morning": { body: JSON.stringify({ modes: { nar: "ok", jra: "none" }, tries: 0 }) } });
  const r5 = await runLate(e5, J("2026-11-15T13:00:00"), async () => ({ modes: { jra: { ok: true, posts: [] } } }), async () => { throw new Error("mail"); });
  eq(r5 && r5.state !== "ok", true, "late: 何も出せなかった回は成功にしない・メールもしない");
}
