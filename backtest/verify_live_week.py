# -*- coding: utf-8 -*-
"""本番の予想（pred_data）を公式確定払戻で答え合わせし、旧LTRとC12を同じレースで比べる。

★何のため★ 2026-09-28 に地方の◎を C12 に切り替えた（mv=2.2）。
  holdout では 単勝◎ROI +5.2 / 複勝◎ROI +2.7 だったが、それは公式データで作った◎の話。
  本番の◎（netkeiba取得→tweet.htmlで採点→保存）でも同じように動いているかを確かめる。

★見るもの★
  1. 本番◎の成績（単勝・複勝の的中率/ROI、◎平均人気）… 買った全レースを分母に
  2. 同じレースを公式データで採点した 旧LTR◎ / C12◎ の成績と、その差（対応あり・ブートストラップCI）
  3. 本番◎ と 公式データ版◎ の一致率（train/serve skew。旧モデル期は76%だった）
  4. mv（保存されたモデル版）の内訳 … C12 が本当に効いているか（mv=2.2 の割合）

★1週間(約250R)では ROI の差は検出できない（単勝ROIの95%CIは±15pt程度）★
  判定に使うのは「壊れていないか」（C12が適用されているか・一致率が落ちていないか・
  ◎平均人気が holdout どおり上がっているか）。ROI の良し悪しは数か月分で見る。

使い方:
  python backtest/verify_live_week.py                     # 直近7日
  python backtest/verify_live_week.py 20260928 20261004   # 期間指定
出力: backtest/store/live_verify/<from>_<to>.json と標準出力
"""
import glob
import json
import os
import sys
from datetime import date, timedelta

import numpy as np
import lightgbm as lgb

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
os.environ.setdefault("LTR_NEWFEATS", "pre")
os.environ.setdefault("LTR_TC", "1")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from bt_train_ltr import fval            # noqa: E402
from eval_bets import pay_single         # noqa: E402

ROOT = os.path.dirname(HERE)
PRED = os.path.join(HERE, "store", "pred_data")
DATA = os.path.join(HERE, "nardata", "bt_all.jsonl")
OUTD = os.path.join(HERE, "store", "live_verify")
C12_K = 2.0                               # tweet.html の C12_K と同値


def _z(a):
    sd = a.std()
    return (a - a.mean()) / sd if sd > 0 else a * 0


def load_preds(d0, d1):
    out = {}
    for f in sorted(glob.glob(os.path.join(PRED, "*_nar_*.json"))):
        dt = os.path.basename(f)[:8]
        if not (d0 <= dt <= d1):
            continue
        try:
            d = json.load(open(f, encoding="utf-8"))
        except Exception:
            continue
        for r in d.get("races") or []:
            rid = str(r.get("race_id") or "")
            if not rid or rid[4:6] == "65":          # ばんえいは別スコア
                continue
            marks = r.get("marks") or []
            if r.get("skip") or not marks:
                continue
            out[rid] = {"mv": d.get("mv"), "o": str(int(marks[0]["num"]))}
    return out


def load_bt(rids):
    bt = {}
    with open(DATA, encoding="utf-8") as f:
        for line in f:
            i = line.find('"rid"')
            if i < 0:
                continue
            rc = json.loads(line)
            if rc.get("rid") in rids:
                bt[rc["rid"]] = rc
    return bt


def boot_ci(x, n_boot=4000, seed=0):
    x = np.asarray(x, float)
    if len(x) < 2:
        return (None, None)
    rng = np.random.default_rng(seed)
    m = x[rng.integers(0, len(x), (n_boot, len(x)))].mean(axis=1)
    return (round(float(np.percentile(m, 2.5)), 1), round(float(np.percentile(m, 97.5)), 1))


def summ(rows, key):
    tan = [r[key + "_tan"] for r in rows]
    fuku = [r[key + "_fuku"] for r in rows]
    pops = [r[key + "_pop"] for r in rows if r[key + "_pop"]]
    n = len(rows)
    if not n:
        return {"n": 0}
    return {
        "n": n,
        "tan_hit": round(100 * sum(1 for v in tan if v) / n, 1),
        "tan_roi": round(sum(tan) / n, 1), "tan_roi_ci": boot_ci(tan),
        "fuku_hit": round(100 * sum(1 for v in fuku if v) / n, 1),
        "fuku_roi": round(sum(fuku) / n, 1), "fuku_roi_ci": boot_ci(fuku),
        "avg_pop": round(float(np.mean(pops)), 2) if pops else None,
    }


def main():
    if len(sys.argv) >= 3:
        d0, d1 = sys.argv[1], sys.argv[2]
    else:
        t = date.today()
        d0, d1 = (t - timedelta(days=7)).strftime("%Y%m%d"), (t - timedelta(days=1)).strftime("%Y%m%d")
    preds = load_preds(d0, d1)
    bt = load_bt(set(preds))
    B = lgb.Booster(model_file=os.path.join(HERE, "ltr_model.txt"))
    BR = lgb.Booster(model_file=os.path.join(HERE, "ltr_res_model.txt"))
    F = B.feature_name()

    rows, miss = [], {"no_official": 0, "no_pay": 0, "live_o_scratched": 0}
    for rid, p in preds.items():
        rc = bt.get(rid)
        if not rc:
            miss["no_official"] += 1
            continue
        pay = rc.get("pay") or {}
        if not pay.get("tan") or not pay.get("fuku"):
            miss["no_pay"] += 1
            continue
        hs = [h for h in rc["h"] if h.get("rk") is not None]
        if len(hs) < 2:
            miss["no_pay"] += 1
            continue
        nums = [str(int(h["n"])) for h in hs]
        if p["o"] not in nums:                      # 本番◎が取消/除外
            miss["live_o_scratched"] += 1
            continue
        pop = {str(int(h["n"])): h.get("pop") for h in hs}
        X = np.array([[fval(h, rc, k) for k in F] for h in hs], float)
        s_old = B.predict(X)
        s_c12 = _z(s_old) + C12_K * _z(BR.predict(X))
        o_old, o_c12 = nums[int(np.argmax(s_old))], nums[int(np.argmax(s_c12))]
        row = {"rid": rid, "date": rc["d"], "mv": p["mv"]}
        for key, o in (("live", p["o"]), ("old", o_old), ("c12", o_c12)):
            row[key + "_o"] = o
            row[key + "_tan"] = pay_single(pay.get("tan"), o)
            row[key + "_fuku"] = pay_single(pay.get("fuku"), o)
            row[key + "_pop"] = pop.get(o)
        rows.append(row)

    mvs = {}
    for r in rows:
        mvs[str(r["mv"])] = mvs.get(str(r["mv"]), 0) + 1
    c12_rows = [r for r in rows if str(r["mv"]) == "2.2"]
    old_rows = [r for r in rows if str(r["mv"]) != "2.2"]
    res = {
        "period": [d0, d1], "races": len(rows), "excluded": miss, "mv": mvs,
        "live": summ(rows, "live"), "official_old": summ(rows, "old"), "official_c12": summ(rows, "c12"),
        "paired_c12_minus_old": {
            "tan_roi": round(float(np.mean([r["c12_tan"] - r["old_tan"] for r in rows])), 1) if rows else None,
            "tan_roi_ci": boot_ci([r["c12_tan"] - r["old_tan"] for r in rows]),
            "fuku_roi": round(float(np.mean([r["c12_fuku"] - r["old_fuku"] for r in rows])), 1) if rows else None,
            "fuku_roi_ci": boot_ci([r["c12_fuku"] - r["old_fuku"] for r in rows]),
            "o_differs": round(100 * np.mean([r["c12_o"] != r["old_o"] for r in rows]), 1) if rows else None,
        },
        # 本番◎と公式版◎の一致率。mv=2.2 の日は C12版と、それ以前は旧LTR版と比べる
        "agree_live_vs_official": {
            "c12_period": round(100 * np.mean([r["live_o"] == r["c12_o"] for r in c12_rows]), 1) if c12_rows else None,
            "c12_period_n": len(c12_rows),
            "old_period": round(100 * np.mean([r["live_o"] == r["old_o"] for r in old_rows]), 1) if old_rows else None,
            "old_period_n": len(old_rows),
        },
    }
    os.makedirs(OUTD, exist_ok=True)
    out = os.path.join(OUTD, f"{d0}_{d1}.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"summary": res, "rows": rows}, f, ensure_ascii=False, indent=1)

    print(f"期間 {d0}〜{d1}  対象 {len(rows)}R  除外 {miss}  mv内訳 {mvs}")
    for label, k in (("本番◎", "live"), ("公式・旧LTR◎", "official_old"), ("公式・C12◎", "official_c12")):
        s = res[k]
        if not s.get("n"):
            continue
        print(f"  {label:<10} 単的中{s['tan_hit']:5.1f}% 単ROI{s['tan_roi']:6.1f} {s['tan_roi_ci']}  "
              f"複的中{s['fuku_hit']:5.1f}% 複ROI{s['fuku_roi']:6.1f} {s['fuku_roi_ci']}  ◎平均人気{s['avg_pop']}")
    pc = res["paired_c12_minus_old"]
    print(f"  C12−旧（同じレース・公式データ）: 単ROI {pc['tan_roi']} {pc['tan_roi_ci']} / "
          f"複ROI {pc['fuku_roi']} {pc['fuku_roi_ci']} / ◎が変わった {pc['o_differs']}%")
    ag = res["agree_live_vs_official"]
    print(f"  本番◎と公式版◎の一致: C12期 {ag['c12_period']}% (n={ag['c12_period_n']}) / "
          f"旧期 {ag['old_period']}% (n={ag['old_period_n']})")
    print("出力:", os.path.relpath(out, ROOT))


if __name__ == "__main__":
    main()
