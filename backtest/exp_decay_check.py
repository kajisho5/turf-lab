# -*- coding: utf-8 -*-
"""時間減衰(半減期3年)のJRAモデルが本物かを検証する

判定基準（docs/IMPROVEMENT_PLAN.md「5. 判定で守ること」）:
  - 年別の一貫性（holdout 2023〜2026 を年ごとに分ける）
  - ペア比較のブートストラップ95%区間（同じレースで◎が違う所だけ効くので強力）
  - 最良年を除いた再計算

使い方: python backtest/exp_decay_check.py backtest/nardata/bt_jra.jsonl \
            backtest/exp_jra_base.txt backtest/exp_jra_decay3.txt
"""
import json
import math
import os
import sys

import numpy as np
import lightgbm as lgb

# bt_train_ltr.py と同じ特徴量定義を再利用（pre構成）
os.environ.setdefault("LTR_NEWFEATS", "pre")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bt_train_ltr import fval, SPLIT  # noqa: E402

DATA = sys.argv[1]
M_A = lgb.Booster(model_file=sys.argv[2])   # base
M_B = lgb.Booster(model_file=sys.argv[3])   # 比較対象
# ★特徴量リストはモデル自身から取る★ 列数が違うモデル同士（tc有無など）も比べられる
F_A = M_A.feature_name()
F_B = M_B.feature_name()

rows = []  # (year, hitA, hitB, tanA, tanB, fukuA, fukuB, samePick)
with open(DATA, encoding="utf-8") as f:
    for line in f:
        try:
            rc = json.loads(line)
        except json.JSONDecodeError:
            continue
        if rc["d"] < SPLIT:
            continue
        hs = [h for h in rc["h"] if h.get("rk") is not None]
        if len(hs) < 5:
            continue
        Xa = np.array([[fval(h, rc, k) for k in F_A] for h in hs], float)
        Xb = np.array([[fval(h, rc, k) for k in F_B] for h in hs], float)
        a = hs[int(np.argmax(M_A.predict(Xa)))]
        b = hs[int(np.argmax(M_B.predict(Xb)))]
        pay = rc.get("pay") or {}

        def payof(book, u):
            if isinstance(book, dict):
                return int(book.get(u, 0) or 0)
            if isinstance(book, list):
                for it in book:
                    if isinstance(it, list) and it and str(int(it[0])) == u:
                        return int(it[1])
            return 0
        ua, ub = str(int(a["n"])), str(int(b["n"]))
        rows.append((rc["d"][:4],
                     int(a["rk"]) <= 3, int(b["rk"]) <= 3,
                     payof(pay.get("tan"), ua), payof(pay.get("tan"), ub),
                     payof(pay.get("fuku"), ua), payof(pay.get("fuku"), ub),
                     a["n"] == b["n"], rc.get("tc")))

years = sorted({r[0] for r in rows})
print(f"holdout {len(rows):,}R / ◎が違うレース {sum(1 for r in rows if not r[7]):,}R")
print("\n年別（base → decay3）")
for y in years:
    g = [r for r in rows if r[0] == y]
    n = len(g)
    ha = 100 * sum(r[1] for r in g) / n
    hb = 100 * sum(r[2] for r in g) / n
    ta = sum(r[3] for r in g) / n
    tb = sum(r[4] for r in g) / n
    print(f"  {y}: 複勝率 {ha:.1f}% → {hb:.1f}% ({hb-ha:+.1f}pt)  "
          f"単ROI {ta:.1f}% → {tb:.1f}% ({tb-ta:+.1f}pt)  ({n:,}R)")

# 最良年（decay3の改善が最大の年）を除いた再計算
diffs = {y: (sum(r[2] for r in rows if r[0] == y) - sum(r[1] for r in rows if r[0] == y))
         for y in years}
best = max(diffs, key=diffs.get)
g = [r for r in rows if r[0] != best]
n = len(g)
print(f"\n最良年({best})を除く: 複勝率 {100*sum(r[1] for r in g)/n:.2f}% → "
      f"{100*sum(r[2] for r in g)/n:.2f}%  ({n:,}R)")

# 場別（tc別）の複勝率差 — どの場で効いた/損したか
TCN = {11: "帯広", 30: "門別", 35: "盛岡", 36: "水沢", 42: "浦和", 43: "船橋",
       44: "大井", 45: "川崎", 46: "金沢", 47: "笠松", 48: "名古屋",
       50: "園田", 51: "姫路", 54: "高知", 55: "佐賀"}
tcs = sorted({r[8] for r in rows if r[8] is not None}, key=str)
if len(tcs) > 1:
    print("\n場別（B−Aの複勝率差）")
    ranked = []
    for t in tcs:
        g = [r for r in rows if r[8] == t]
        n = len(g)
        if n < 200:
            continue
        d = 100 * (sum(r[2] for r in g) - sum(r[1] for r in g)) / n
        ranked.append((d, t, n, 100 * sum(r[2] for r in g) / n))
    for d, t, n, hb in sorted(ranked, reverse=True):
        try:
            name = TCN.get(int(t), str(t))   # tcはJSONでは文字列('48')
        except (TypeError, ValueError):
            name = str(t)
        print(f"  {name}: {d:+.1f}pt → {hb:.1f}%  ({n:,}R)")

# ペア差のブートストラップ95%区間（複勝率の差・単ROIの差）
rng = np.random.default_rng(42)
hit = np.array([(r[2] - r[1]) for r in rows], float)
tan = np.array([(r[4] - r[3]) for r in rows], float)
idx = rng.integers(0, len(rows), (2000, len(rows)))
bs_hit = 100 * hit[idx].mean(axis=1)
bs_tan = tan[idx].mean(axis=1)
print(f"\nペア差ブートストラップ95%区間（decay3 − base）")
print(f"  複勝率差: {100*hit.mean():+.2f}pt  [{np.percentile(bs_hit,2.5):+.2f}, "
      f"{np.percentile(bs_hit,97.5):+.2f}]")
print(f"  単ROI差 : {tan.mean():+.1f}pt  [{np.percentile(bs_tan,2.5):+.1f}, "
      f"{np.percentile(bs_tan,97.5):+.1f}]")
