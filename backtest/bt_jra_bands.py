# -*- coding: utf-8 -*-
"""中央: 断然人気の複勝・単勝（オッズ帯の決まり）。決まりは backtest/PREREG_jra_bands_20261121.md に先に書いた。
出すのは集計だけ。使い方: python backtest/bt_jra_bands.py
"""
import collections
import json
import os
import sys

import numpy as np

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from eval_bets import pay_single         # noqa: E402

DATA = os.environ.get("JRA_DATA", os.path.join(HERE, "nardata", "bt_jra.jsonl"))
SEL = tuple(os.environ.get("BANDS_SEL", "20150101,20240101").split(","))
FIN = tuple(os.environ.get("BANDS_FIN", "20240101,99999999").split(","))
XS = [1.1, 1.2, 1.3, 1.4, 1.5, 1.7, 2.0]
FIELDS = {"全部": lambda n: True, "7頭以下": lambda n: n <= 7, "8頭以上": lambda n: n >= 8}
BANDS = [(1.0, 1.4), (1.5, 1.9), (2.0, 2.9), (3.0, 4.9), (5.0, 9.9), (10.0, 19.9), (20.0, 49.9), (50.0, 9999)]
MIN_SEL = 500


def ci(x, n=2000):
    rng = np.random.default_rng(7)
    m = [x[rng.integers(0, len(x), len(x))].mean() for _ in range(n)]
    return [round(float(np.percentile(m, 2.5)), 1), round(float(np.percentile(m, 97.5)), 1)]


def stat(x, with_ci=True):
    x = np.array(x, float)
    if not len(x):
        return {"n": 0}
    d = {"n": int(len(x)), "roi": round(float(x.mean()), 1), "hit": round(100 * float((x > 0).mean()), 1)}
    if with_ci and len(x) >= 100:
        d["ci"] = ci(x)
    return d


def main():
    odds = {}
    with open(DATA + ".odds", encoding="utf-8") as f:
        for line in f:
            rid, v = json.loads(line)
            if rid >= SEL[0][:4]:
                odds[rid] = v
    R = {"sel": collections.defaultdict(list), "fin": collections.defaultdict(list)}
    band = collections.defaultdict(list)
    fuku_pay = {"sel": collections.Counter(), "fin": collections.Counter()}
    nr = collections.Counter()
    ex = collections.Counter()
    last = ""
    with open(DATA, encoding="utf-8") as f:
        for line in f:
            rc = json.loads(line)
            d = rc["d"]
            part = "sel" if SEL[0] <= d < SEL[1] else "fin" if FIN[0] <= d < FIN[1] else None
            if not part:
                continue
            last = max(last, d)
            pay = rc.get("pay") or {}
            if not pay.get("tan") or not pay.get("fuku"):
                ex["払戻なし"] += 1
                continue
            hs = [h for h in rc["h"] if h.get("rk") is not None]
            od = odds.get(rc["rid"]) or {}
            if len(hs) < 5 or any(od.get(str(int(h["n"]))) in (None, 0) for h in hs):
                ex["オッズ欠け・5頭未満"] += 1
                continue
            nr[part] += 1
            n = len(hs)
            for v in (pay["fuku"].values() if isinstance(pay["fuku"], dict) else [it[1] for it in pay["fuku"]]):
                fuku_pay[part][int(v)] += 1
            fav = [h for h in hs if h.get("pop") == 1]
            if len(fav) == 1:
                u = str(int(fav[0]["n"]))
                o = od[u]
                pt, pf = pay_single(pay["tan"], u), pay_single(pay["fuku"], u)
                for x in XS:
                    if o <= x + 1e-9:
                        R[part][("単勝", x, "全部")].append(pt)
                        for fn_, ok in FIELDS.items():
                            if ok(n):
                                R[part][("複勝", x, fn_)].append(pf)
            if part == "sel":
                for h in hs:
                    u = str(int(h["n"]))
                    o = od[u]
                    for lo, hi in BANDS:
                        if lo <= o <= hi + 0.05:
                            band[(lo, hi)].append(pay_single(pay["tan"], u))
                            break
    print(f"データの最終日 {last}  選ぶ {nr['sel']:,}R / 最終 {nr['fin']:,}R  除外 {dict(ex)}")
    print("\n参考（判定には使わない）: 全馬の単勝・オッズ帯別（選ぶ期間）")
    for (lo, hi), x in sorted(band.items()):
        s = stat(x, False)
        print(f"  {lo:>5}〜{hi if hi < 9999 else '':<6} {s['n']:>8,}点  的中 {s['hit']:>5}%  回収率 {s['roi']}")
    for part, lab in (("sel", "選ぶ期間"), ("fin", "最終期間")):
        c = fuku_pay[part]
        tot = sum(c.values())
        print(f"参考: 複勝の払戻（{lab}・{tot:,}件）100円 {c[100]:,} / 110円 {c[110]:,} / 120円 {c[120]:,}")

    print("\n選ぶ期間の成績（28通り）")
    rows = []
    for key in sorted(R["sel"], key=lambda k: (k[0], k[2], k[1])):
        s = stat(R["sel"][key])
        rows.append((key, s))
        print(f"  {key[0]} ≤{key[1]} {key[2]:<5} {s}")
    ok = [(k, s) for k, s in rows if s["n"] >= MIN_SEL]
    chosen = []
    if ok:
        chosen.append(max(ok, key=lambda t: t[1]["roi"])[0])
        chosen += [k for k, s in ok if s.get("ci") and s["ci"][0] > 100 and k not in chosen]
    out = {"last": last, "sel": {str(k): s for k, s in rows}, "final": {}}
    print("\n★最終期間（選んだ決まりだけ・1回）")
    for k in chosen:
        f = stat(R["fin"].get(k, []))
        v = ("判定できない（100点未満）" if f["n"] < 100 else
             "合格（下側が100%超）" if f["ci"][0] > 100 else "不合格（100%は超えない）")
        yr = {}
        out["final"][str(k)] = {**f, "verdict": v}
        print(f"  {k[0]} ≤{k[1]} {k[2]}: {f} → {v}")
    if not chosen:
        print("  選べる決まりが無い（500点以上が無い）")
    os.makedirs(os.path.join(HERE, "store", "discovery"), exist_ok=True)
    json.dump(out, open(os.path.join(HERE, "store", "discovery", "jra_bands.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
