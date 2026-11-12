# -*- coding: utf-8 -*-
"""LTRスコア→◎の複勝確率のキャリブレーション（実測較正）

★何のため★
  tweet.htmlの信頼度(firmness)はヒューリスティックで、実際の複勝確率とは別物。
  「◎複勝見込み68%」のような**実測に裏打ちされた数字**を表示に追加する。
  判定（狙い目/見送り）の閾値は触らない＝蓄積記録の意味を変えない。表示専用。

★方法★
  holdout(2023〜)で本番モデルの◎について
    c = 0.6*gap + 0.4*nextGap
      gap    = (◎スコア - レース平均) / レース内スコア幅
      nextGap= (◎スコア - 2位スコア) / レース内スコア幅
  を計算し、10分位ビンごとの実測複勝率を表にする。
  ★オッズは使わない★（事前予想の条件で較正する）

出力: deploy/data/ltr_calib.json
  {"nar":{"edges":[...9個の境界...],"p":[...10個の複勝率%...],"n":[...]}, "jra":{...}}
使い方: python backtest/calib_ltr.py
"""
import json
import os
import sys

import numpy as np
import lightgbm as lgb

os.environ.setdefault("LTR_NEWFEATS", "pre")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bt_train_ltr import fval, SPLIT  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "deploy", "data", "ltr_calib.json")

JOBS = [
    ("nar", os.path.join(ROOT, "backtest", "ltr_model.txt"),
     os.path.join(ROOT, "backtest", "nardata", "bt_all.jsonl")),
    ("jra", os.path.join(ROOT, "backtest", "ltr_model_jra.txt"),
     os.path.join(ROOT, "backtest", "nardata", "bt_jra.jsonl")),
]

# ★C12（地方・2026-09-27採用）★ ◎= z(LTR)+2.0·z(補助) の最大。本番(tweet.html)と同じく
#   raw' = mean(LTR)+std(LTR)·(s/std(s)) に戻してから c を計算する。
#   旧表のまま出すと全ビンで約10pt出しすぎになる（実測）ので、C12専用の表を別キーで持つ。
RES_MODEL = os.path.join(ROOT, "backtest", "ltr_res_model.txt")
C12_K = 2.0
if os.path.exists(RES_MODEL):
    JOBS.append(("narC12", os.path.join(ROOT, "backtest", "ltr_model.txt"),
                 os.path.join(ROOT, "backtest", "nardata", "bt_all.jsonl")))


def _z(a):
    sd = a.std()
    return (a - a.mean()) / sd if sd > 0 else a * 0


out = {}
for mode, mf, data in JOBS:
    B = lgb.Booster(model_file=mf)
    F = B.feature_name()
    BR = lgb.Booster(model_file=RES_MODEL) if mode == "narC12" else None
    cs, hits = [], []
    with open(data, encoding="utf-8") as f:
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
            X = np.array([[fval(h, rc, k) for k in F] for h in hs], float)
            s = B.predict(X)
            if BR is not None:
                comb = _z(s) + C12_K * _z(BR.predict(X))
                sc = comb.std()
                s = s.mean() + s.std() * (comb / sc if sc > 0 else comb * 0)
            top = int(np.argmax(s))
            spread = float(s.max() - s.min()) or 1.0
            gap = (float(s[top]) - float(s.mean())) / spread
            s2 = float(np.partition(s, -2)[-2])
            next_gap = (float(s[top]) - s2) / spread
            cs.append(0.6 * gap + 0.4 * next_gap)
            hits.append(int(hs[top]["rk"]) <= 3)
    cs = np.array(cs)
    hits = np.array(hits)
    edges = np.quantile(cs, np.arange(1, 10) / 10.0)
    bins = np.searchsorted(edges, cs)
    p, n = [], []
    for b in range(10):
        m = bins == b
        n.append(int(m.sum()))
        p.append(round(100.0 * hits[m].mean(), 1) if m.sum() else None)
    out[mode] = {"edges": [round(float(e), 4) for e in edges], "p": p, "n": n}
    print(f"[{mode}] {len(cs):,}R  分位→複勝率%: {p}")
    # 単調性の確認（較正が意味を持つ前提。多少の凸凹は許容）
    mono = sum(1 for i in range(9) if p[i + 1] is not None and p[i] is not None
               and p[i + 1] >= p[i])
    print(f"  単調増加ペア {mono}/9")

os.makedirs(os.path.dirname(OUT), exist_ok=True)
tmp = OUT + ".tmp"
with open(tmp, "w", encoding="utf-8") as f:
    json.dump({"note": "LTR◎のc=0.6*gap+0.4*nextGap 10分位→実測複勝率%(2023-)。"
                       "オッズ不使用=事前条件。表示専用。narC12=C12の並び(raw')で作った地方用", **out}, f,
              ensure_ascii=False, separators=(",", ":"))
os.replace(tmp, OUT)
print("出力:", os.path.relpath(OUT, ROOT))
