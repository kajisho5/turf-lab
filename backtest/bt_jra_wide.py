# -*- coding: utf-8 -*-
"""中央: 人気2頭のワイド・馬連と2番人気の複勝。決まりは backtest/PREREG_jra_wide_20261121.md に先に書いた。
出すのは集計だけ。使い方: python backtest/bt_jra_wide.py
"""
import collections
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from eval_bets import pay_single, pay_combo      # noqa: E402
from bt_jra_bands import stat, DATA               # noqa: E402

SEL = tuple(os.environ.get("BANDS_SEL", "20150101,20240101").split(","))
FIN = tuple(os.environ.get("BANDS_FIN", "20240101,99999999").split(","))
AS, BS = [1.5, 2.0, 3.0], [3.0, 4.0, 5.0]


def main():
    odds = {}
    with open(DATA + ".odds", encoding="utf-8") as f:
        for line in f:
            rid, v = json.loads(line)
            if rid >= SEL[0][:4]:
                odds[rid] = v
    R = {"sel": collections.defaultdict(list), "fin": collections.defaultdict(list)}
    w110 = collections.Counter()
    with open(DATA, encoding="utf-8") as f:
        for line in f:
            rc = json.loads(line)
            d = rc["d"]
            part = "sel" if SEL[0] <= d < SEL[1] else "fin" if FIN[0] <= d < FIN[1] else None
            if not part:
                continue
            pay = rc.get("pay") or {}
            if not pay.get("fuku") or not pay.get("wide") or not pay.get("umaren"):
                continue
            hs = [h for h in rc["h"] if h.get("rk") is not None]
            od = odds.get(rc["rid"]) or {}
            if len(hs) < 8 or any(od.get(str(int(h["n"]))) in (None, 0) for h in hs):
                continue
            p1 = [h for h in hs if h.get("pop") == 1]
            p2 = [h for h in hs if h.get("pop") == 2]
            if len(p1) != 1 or len(p2) != 1:
                continue
            u1, u2 = str(int(p1[0]["n"])), str(int(p2[0]["n"]))
            o1, o2 = od[u1], od[u2]
            if isinstance(pay["wide"], dict):
                for v in pay["wide"].values():
                    w110[(part, int(v) if int(v) <= 120 else 999)] += 1
            pw, pu, pf = pay_combo(pay["wide"], [u1, u2], False), pay_combo(pay["umaren"], [u1, u2], False), pay_single(pay["fuku"], u2)
            for a in AS:
                for b in BS:
                    if o1 <= a + 1e-9 and o2 <= b + 1e-9:
                        R[part][("ワイド", a, b)].append(pw)
                        R[part][("馬連", a, b)].append(pu)
                        R[part][("複勝2番人気", a, b)].append(pf)
    for part, lab in (("sel", "選ぶ期間"), ("fin", "最終期間")):
        print(f"参考: ワイドの払戻（{lab}）100円 {w110[(part, 100)]:,} / 110円 {w110[(part, 110)]:,} / 120円 {w110[(part, 120)]:,} / それ以上 {w110[(part, 999)]:,}")
    print("\n選ぶ期間（27通り）")
    chosen = []
    for kind in ("ワイド", "馬連", "複勝2番人気"):
        best = None
        for a in AS:
            for b in BS:
                s = stat(R["sel"][(kind, a, b)])
                print(f"  {kind} 1番人気≤{a}・2番人気≤{b}: {s}")
                if s["n"] >= 500 and (best is None or s["roi"] > best[1]["roi"]):
                    best = ((kind, a, b), s)
        if best:
            chosen.append(best[0])
    out = {}
    print("\n★最終期間（券種ごとに選んだ1つ・1回）")
    for k in chosen:
        f = stat(R["fin"].get(k, []))
        v = ("判定できない（100点未満）" if f["n"] < 100 else "合格（下側が100%超）" if f["ci"][0] > 100 else "不合格（100%は超えない）")
        out[str(k)] = {**f, "verdict": v}
        print(f"  {k[0]} 1番人気≤{k[1]}・2番人気≤{k[2]}: {f} → {v}")
    os.makedirs(os.path.join(HERE, "store", "discovery"), exist_ok=True)
    json.dump(out, open(os.path.join(HERE, "store", "discovery", "jra_wide.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
