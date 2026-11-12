# -*- coding: utf-8 -*-
"""アンサンブルに伸びしろがあるかを16券種で測る

★なぜ先にこれを測るのか★
  2026-07-30、8モデル構成（TabPFN/GNN/TFT/MoE…）の提案を受けた。
  設計・実装・保守に数週間かかる話なので、その前に
  **「そもそもモデルを増やすと良くなるのか」** を最も安い方法で測る。
  乱数シードだけ違う同一構成の平均で伸びなければ、
  アルゴリズムを増やす方向の期待値も低いと判断できる（分散低減すら効かないため）。

  ★判定は eval_bets.py と同じ16券種・◎優先★（複勝率では判断しない）

使い方:
  python backtest/eval_ensemble.py <base.txt> <m1.txt> <m2.txt> ...
  例: python backtest/eval_ensemble.py backtest/exp_final33.txt \
        backtest/exp_final33.txt backtest/exp_seed7.txt backtest/exp_seed2026.txt
  第1引数=比較の基準（単体）、第2引数以降=平均する材料
"""
import json
import os
import sys

import numpy as np
import lightgbm as lgb

os.environ.setdefault("LTR_NEWFEATS", "pre")
os.environ.setdefault("LTR_TC", "1")
os.environ.setdefault("LTR_NODMS", "1")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bt_train_ltr import fval, SPLIT  # noqa: E402
from eval_bets import plans, pay_single, pay_combo, DATA  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def run(models, label):
    """models = [Booster,...] のスコア平均で◎○▲△を決め、16券種を集計"""
    F = [m.feature_name() for m in models]
    acc = {}
    with open(DATA, encoding="utf-8") as f:
        for line in f:
            try:
                rc = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rc["d"] < SPLIT:
                continue
            hs = [h for h in rc["h"] if h.get("rk") is not None]
            if len(hs) < 6:
                continue
            pay = rc.get("pay") or {}
            if not pay.get("tan"):
                continue
            # ★スコアはレース内で標準化してから平均する★
            #   生のraw値はモデルごとに尺度が違うので、そのまま足すと
            #   1本のモデルの尺度が支配してしまい「平均」にならない。
            zs = []
            for m, feats in zip(models, F):
                X = np.array([[fval(h, rc, k) for k in feats] for h in hs], float)
                s = m.predict(X)
                sd = s.std() or 1.0
                zs.append((s - s.mean()) / sd)
            s = np.mean(zs, axis=0)
            order = np.argsort(-s)
            marks = [str(int(hs[i]["n"])) for i in order[:6]]
            if len(marks) < 6:
                continue
            for name, (kind, ordered, combos) in plans(marks).items():
                a = acc.setdefault(name, [0, 0, 0, 0])
                a[0] += 1
                a[1] += len(combos)
                got = 0
                for c in combos:
                    got += (pay_single(pay.get(kind), c[0]) if kind in ("tan", "fuku")
                            else pay_combo(pay.get(kind), c, ordered))
                if got:
                    a[2] += 1
                    a[3] += got
    return acc


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 1
    base = lgb.Booster(model_file=sys.argv[1])
    members = [lgb.Booster(model_file=p) for p in sys.argv[2:]]
    print(f"単体: {os.path.basename(sys.argv[1])}")
    print(f"平均: {len(members)}本 ({', '.join(os.path.basename(p) for p in sys.argv[2:])})\n")
    a1 = run([base], "単体")
    a2 = run(members, "平均")
    names = list(a1.keys())
    w = max(len(n) for n in names) + 2
    print(f"{'買い方':<{w}}{'単体ROI':>9}{'平均ROI':>9}{'差':>8}{'的中差':>9}")
    win = lose = 0
    for n in names:
        r1, p1, h1, t1 = a1[n]
        r2, p2, h2, t2 = a2[n]
        if not r1 or not r2:
            continue
        roi1 = 100 * t1 / (p1 * 100)
        roi2 = 100 * t2 / (p2 * 100)
        dh = 100 * h2 / r2 - 100 * h1 / r1
        d = roi2 - roi1
        if d > 0:
            win += 1
        elif d < 0:
            lose += 1
        print(f"{n:<{w}}{roi1:>8.1f}%{roi2:>8.1f}%{d:>+7.1f}pt{dh:>+8.1f}pt")
    print(f"\nROIが改善した券種: {win} / 悪化: {lose}")
    print("★判定★ ±0.3pt以内に収まるなら、アンサンブル方向は打ち止め")
    return 0


if __name__ == "__main__":
    sys.exit(main())
