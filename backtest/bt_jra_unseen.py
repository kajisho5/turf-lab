# -*- coding: utf-8 -*-
"""中央: いまの本番モデル（ltr_model_jra.txt）を、作った時に見ていない期間で採点する。

  ◎（モデルの1位）と1番人気を同じレースで並べる。モデルは作り直さない（読むだけ）。
  ROI の分母は「買った全レース×100円」。払戻の無いレースは両方から外し、その数を出す。
  出すのは集計だけ（馬名・生データは出さない）。

使い方: python backtest/bt_jra_unseen.py [新しい期間の開始日=20260713]
出力: 標準出力 と backtest/store/discovery/jra_unseen.json
"""
import json
import os
import sys
from collections import defaultdict

import numpy as np
import lightgbm as lgb

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
os.environ.setdefault("LTR_NEWFEATS", "pre")
os.environ.setdefault("LTR_TC", "1")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from bt_train_ltr import fval, SPLIT      # noqa: E402
from eval_bets import pay_single          # noqa: E402

NEW_FROM = sys.argv[1] if len(sys.argv) > 1 else "20260713"
DATA = os.environ.get("JRA_DATA", os.path.join(HERE, "nardata", "bt_jra.jsonl"))


def boot(x, n=2000, seed=7):
    x = np.asarray(x, float)
    if len(x) < 30:
        return None
    rng = np.random.default_rng(seed)
    m = [x[rng.integers(0, len(x), len(x))].mean() for _ in range(n)]
    return [round(float(np.percentile(m, 2.5)), 1), round(float(np.percentile(m, 97.5)), 1)]


def summarize(rows):
    """rows: [(ai_win, ai_top3, ai_tan, ai_fuku, fav_win, fav_top3, fav_tan, fav_fuku, ai_pop)]"""
    a = np.array(rows, float)
    if not len(a):
        return {"n": 0}
    out = {"n": int(len(a))}
    for nm, o in (("ai", 0), ("fav", 4)):
        out[nm] = {"win": round(100 * a[:, o].mean(), 1), "top3": round(100 * a[:, o + 1].mean(), 1),
                   "tan_roi": round(a[:, o + 2].mean(), 1), "fuku_roi": round(a[:, o + 3].mean(), 1)}
    out["ai"]["avg_pop"] = round(float(np.nanmean(a[:, 8])), 2)
    out["ai"]["same_as_fav"] = round(100 * float(np.mean(a[:, 8] == 1)), 1)
    out["diff_top3_ci"] = boot(100 * (a[:, 1] - a[:, 5]))
    out["diff_tan_ci"] = boot(a[:, 2] - a[:, 6])
    return out


def main():
    B = lgb.Booster(model_file=os.path.join(HERE, "ltr_model_jra.txt"))
    F = B.feature_name()
    per = defaultdict(list)      # 期間 -> rows
    mon = defaultdict(list)      # 新しい期間の月 -> rows
    nopay = defaultdict(int)
    nofav = defaultdict(int)
    last = ""
    with open(DATA, encoding="utf-8") as f:
        for line in f:
            rc = json.loads(line)
            d = rc["d"]
            if d < SPLIT:
                continue
            last = max(last, d)
            p = "new" if d >= NEW_FROM else "old"
            hs = [h for h in rc["h"] if h.get("rk") is not None]
            if len(hs) < 5:
                continue
            pay = rc.get("pay") or {}
            if not pay.get("tan") or not pay.get("fuku"):
                nopay[p] += 1
                continue
            fav = [h for h in hs if h.get("pop") == 1]
            if len(fav) != 1:
                nofav[p] += 1
                continue
            fav = fav[0]
            X = np.array([[fval(h, rc, k) for k in F] for h in hs], float)
            o = hs[int(np.argmax(B.predict(X)))]
            on, fn_ = str(int(o["n"])), str(int(fav["n"]))
            row = (o["rk"] == 1, o["rk"] <= 3, pay_single(pay["tan"], on), pay_single(pay["fuku"], on),
                   fav["rk"] == 1, fav["rk"] <= 3, pay_single(pay["tan"], fn_), pay_single(pay["fuku"], fn_),
                   o.get("pop") or np.nan)
            per[p].append(row)
            if p == "new":
                mon[d[:6]].append(row)
    out = {"model_split": SPLIT, "new_from": NEW_FROM, "last_date": last,
           "old": summarize(per["old"]), "new": summarize(per["new"]),
           "new_by_month": {m: summarize(r) for m, r in sorted(mon.items())},
           "excluded_no_payout": dict(nopay), "excluded_no_single_favorite": dict(nofav)}
    print(f"データの最終日 {last}")
    for p, lab in (("old", f"今までの検証期間 {SPLIT}〜{NEW_FROM}の前日"), ("new", f"新しい期間 {NEW_FROM}〜")):
        s = out[p]
        print(f"\n{lab}: {s['n']:,}R（払戻なしで除外 {nopay[p]:,} / 1番人気が決まらず除外 {nofav[p]:,}）")
        if not s["n"]:
            continue
        for nm, l2 in (("ai", "◎（AI）  "), ("fav", "1番人気  ")):
            v = s[nm]
            print(f"  {l2} 勝率 {v['win']:4.1f}%  3着内 {v['top3']:4.1f}%  単ROI {v['tan_roi']:5.1f}  複ROI {v['fuku_roi']:5.1f}")
        print(f"  ◎の平均人気 {s['ai']['avg_pop']}  ◎が1番人気と同じ {s['ai']['same_as_fav']}%")
        print(f"  差（◎−1番人気）の95%区間  3着内 {s['diff_top3_ci']}pt  単ROI {s['diff_tan_ci']}")
    for m, s in out["new_by_month"].items():
        print(f"  {m}: {s['n']:>4}R  ◎ 3着内 {s['ai']['top3']}% 単ROI {s['ai']['tan_roi']} / 1人気 3着内 {s['fav']['top3']}% 単ROI {s['fav']['tan_roi']}")
    os.makedirs(os.path.join(HERE, "store", "discovery"), exist_ok=True)
    json.dump(out, open(os.path.join(HERE, "store", "discovery", "jra_unseen.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
