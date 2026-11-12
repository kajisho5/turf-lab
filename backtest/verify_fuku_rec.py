# -*- coding: utf-8 -*-
"""★「複勝推奨」の条件付きROIを現行モデルで測り直す★（2026-07-31）

なぜ: tweet.html のツイート定型句と scoring_explainer.html が
      **複勝ROI 89%** を公開しているが、これは GBM 時代に測った値。
      その後モデルは LTR に替わり(v4.3.13/15)、さらに騎手・厩舎・父が入った(v4.3.19-20)。
      公開している数字は「今のモデルの実力」ではない可能性が高い。

条件（tweet.html の isFukuRec と同一）:
    出走頭数 <= FUKU_FIELD_MAX(9) かつ 信頼度firmO >= FUKU_FIRM_MIN(40)
    かつ ◎が FUKU_POP_MAX(3) 番人気以内

信頼度firmO は tweet.html の firmness() をそのまま移植した。
スコアは `s = 50 + ltr*12` の線形写像だが、firmness は spread で正規化するので
**生のLTR値で計算しても同値**（線形変換に不変）。

使い方:
  python backtest/verify_fuku_rec.py                       # 地方
  EVAL_DATA=backtest/nardata/bt_jra.jsonl \
  FUKU_MODEL=backtest/ltr_model_jra.txt python backtest/verify_fuku_rec.py
"""
import json
import os
import sys

import numpy as np
import lightgbm as lgb

os.environ.setdefault("LTR_NEWFEATS", "pre")
os.environ.setdefault("LTR_TC", "1")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bt_train_ltr import fval, SPLIT  # noqa: E402
from eval_bets import pay_single      # noqa: E402  ★払戻の読み方は自前で書かない★

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.environ.get("EVAL_DATA", os.path.join(ROOT, "backtest", "nardata", "bt_all.jsonl"))
MODEL = os.environ.get("FUKU_MODEL", os.path.join(ROOT, "backtest", "ltr_model.txt"))
FIELD_MAX, FIRM_MIN, POP_MAX = 9, 40, 3


def clamp01(v):
    return 0.0 if v < 0 else (1.0 if v > 1 else v)


def firmness(ss, pop):
    """tweet.html の firmness(scored, odds, 0) の移植。ss=スコア降順, pop=◎の人気"""
    if len(ss) < 2:
        return None
    mx, mn = max(ss), min(ss)
    mean = sum(ss) / len(ss)
    spread = (mx - mn) or 1.0
    gap = (ss[0] - mean) / spread
    next_gap = (ss[0] - ss[1]) / spread
    if pop is None:
        pop_score = 0.5
    elif pop <= 1:
        pop_score = 1.0
    elif pop <= 2:
        pop_score = 0.82
    elif pop <= 3:
        pop_score = 0.66
    elif pop <= 4:
        pop_score = 0.52
    elif pop <= 5:
        pop_score = 0.4
    else:
        pop_score = max(0.12, 0.4 - (pop - 5) * 0.06)
    base = 0.34 * clamp01(gap) + 0.22 * clamp01(next_gap * 1.5 + 0.2) + 0.44 * pop_score
    return round(clamp01(base) * 100)


def main():
    B = lgb.Booster(model_file=MODEL)
    F = B.feature_name()
    all_n = all_hit = all_ret = 0
    rec_n = rec_hit = rec_ret = 0
    by_year = {}
    with open(DATA, encoding="utf-8") as f:
        for line in f:
            try:
                rc = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rc["d"] < SPLIT:
                continue
            hs = [h for h in rc["h"] if h.get("rk") is not None]
            if len(hs) < 6 or not (rc.get("pay") or {}).get("tan"):
                continue
            s = B.predict(np.array([[fval(h, rc, k) for k in F] for h in hs], float))
            order = np.argsort(-s)
            ss = [float(s[i]) for i in order]
            top = hs[order[0]]
            num = str(int(top["n"]))
            v = pay_single(rc["pay"].get("fuku"), num)
            all_n += 1
            all_ret += v
            all_hit += 1 if v else 0
            pop = top.get("pop")
            if len(hs) > FIELD_MAX or pop is None or int(pop) > POP_MAX:
                continue
            if (firmness(ss, int(pop)) or 0) < FIRM_MIN:
                continue
            rec_n += 1
            rec_ret += v
            rec_hit += 1 if v else 0
            y = rc["d"][:4]
            a = by_year.setdefault(y, [0, 0, 0])
            a[0] += 1
            a[1] += 1 if v else 0
            a[2] += v

    print(f"データ: {os.path.relpath(DATA, ROOT)}  モデル: {os.path.basename(MODEL)}  "
          f"holdout {SPLIT}〜")
    print(f"\n全レース   {all_n:>7,}R  ◎複勝率 {100*all_hit/all_n:.1f}%  "
          f"複勝ROI {all_ret/all_n:.1f}%")
    if not rec_n:
        print("複勝推奨に該当なし")
        return 1
    print(f"複勝推奨   {rec_n:>7,}R  ◎複勝率 {100*rec_hit/rec_n:.1f}%  "
          f"複勝ROI {rec_ret/rec_n:.1f}%   （全体の{100*rec_n/all_n:.1f}%）")
    print(f"           条件: {FIELD_MAX}頭以下 × 信頼度{FIRM_MIN}+ × ◎{POP_MAX}番人気以内")
    print("\n年別（複勝推奨）")
    for y in sorted(by_year):
        n, h, r = by_year[y]
        print(f"  {y}: {n:>5,}R  複勝率 {100*h/n:>5.1f}%  ROI {r/n:>5.1f}%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
