# -*- coding: utf-8 -*-
"""★モデルを「単複と◎○から流した的中率・回収率」で評価する★

★なぜこのファイルが要るか★
  2026-07-30、モデル改善を全部◎の複勝率で判定していたところ、
  ユーザーから「複勝率とかどうでもええんや。単複と◎と○から流した的中率および
  回収率を上げたいって話なの」と指摘された。正当な指摘。
  複勝率が上がってもROIは上がらない（当たる分だけ配当が下がる）ことは
  実測で何度も出ていたのに、判定軸を直していなかった。

★評価する買い方（◎=1位, ○=2位, ▲=3位, △=4,5位）★
  単勝◎ / 複勝◎ / 単勝○ / 複勝○
  ワイド ◎-○ / ◎から相手3頭(○▲△) / ○から相手3頭
  馬連   ◎-○ / ◎から相手3頭
  馬単   ◎→○ / ◎→相手3頭 / ◎○の2頭マルチ
  3連複  ◎○軸-相手3頭 / ◎軸-相手4頭から2頭
  3連単  ◎1着-○▲-△まで / ◎○の1・2着マルチ-3着4頭

★ROIの分母は必ず「点数×100円×買った全レース」★（鉄則2）
  的中時だけ投資計上する実装は回収率を偽装する（過去に重大バグあり）。

★大穴1本でROIが決まる券種がある★
  3連単・3連複は最高配当を除いたROI(除1)も必ず出す。

使い方:
  python backtest/eval_bets.py <model.txt> [<model2.txt> ...]
  例: python backtest/eval_bets.py backtest/exp_tc.txt backtest/exp_jkr.txt
出力: 標準出力の表（券種×モデル）
"""
import itertools
import json
import os
import sys

import numpy as np
import lightgbm as lgb

os.environ.setdefault("LTR_NEWFEATS", "pre")
os.environ.setdefault("LTR_TC", "1")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bt_train_ltr import fval, SPLIT  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.environ.get("EVAL_DATA",
                      os.path.join(ROOT, "backtest", "nardata", "bt_all.jsonl"))


def pay_single(book, u):
    """単勝・複勝: {馬番:円} か [[馬番,円,人気],...]"""
    if isinstance(book, dict):
        return int(book.get(u, 0) or 0)
    if isinstance(book, list):
        for it in book:
            if isinstance(it, list) and it and str(int(it[0])) == u:
                return int(it[1])
    return 0


def pay_combo(book, combo, ordered):
    """ワイド/馬連/馬単/3連複/3連単。
    形式は {'2-7':160} か [[['2','7'],250], ...] の両方があり得る。
    ordered=False は順不同（ソートして突き合わせる）。"""
    want = [str(int(x)) for x in combo]
    if not ordered:
        want_key = "-".join(sorted(want, key=int))
    else:
        want_key = "-".join(want)
    if isinstance(book, dict):
        for k, v in book.items():
            parts = [p for p in str(k).replace("=", "-").split("-") if p]
            if not parts:
                continue
            key = "-".join(parts) if ordered else "-".join(sorted(parts, key=int))
            if key == want_key:
                return int(v or 0)
        return 0
    if isinstance(book, list):
        # ★実データの形★ 馬連/馬単/3連複/3連単は的中1組だけなので
        #   [['2','7'], 250] という「組リスト＋金額」の2要素。
        #   以前これを「複数組のリスト」と誤読して全券種0%になった（2026-07-30）。
        if len(book) == 2 and isinstance(book[0], list) and not isinstance(book[1], list):
            items = [book]
        else:
            items = book
        for it in items:
            if not (isinstance(it, list) and len(it) >= 2):
                continue
            ks = it[0]
            ks = ks if isinstance(ks, list) else str(ks).split("-")
            try:
                parts = [str(int(x)) for x in ks]
            except (TypeError, ValueError):
                continue
            key = "-".join(parts) if ordered else "-".join(sorted(parts, key=int))
            if key == want_key:
                return int(it[1] or 0)
    return 0


# 買い方の定義。marks=[◎,○,▲,△,△] の馬番リストを受け、
# (券種キー, ordered, [組...]) を返す。点数=組の数。
def plans(m):
    o, t, s = m[0], m[1], m[2]
    aite3 = m[1:4]                 # ○▲△
    aite4 = m[1:5]                 # ○▲△△
    P = {}
    P["単勝◎"] = ("tan", False, [[o]])
    P["複勝◎"] = ("fuku", False, [[o]])
    P["単勝○"] = ("tan", False, [[t]])
    P["複勝○"] = ("fuku", False, [[t]])
    P["ワイド◎-○"] = ("wide", False, [[o, t]])
    P["ワイド◎→相手3"] = ("wide", False, [[o, x] for x in aite3])
    P["ワイド○→相手3"] = ("wide", False, [[t, x] for x in [o] + m[2:4]])
    P["馬連◎-○"] = ("umaren", False, [[o, t]])
    P["馬連◎→相手3"] = ("umaren", False, [[o, x] for x in aite3])
    P["馬単◎→○"] = ("umatan", True, [[o, t]])
    P["馬単◎→相手3"] = ("umatan", True, [[o, x] for x in aite3])
    P["馬単◎○マルチ"] = ("umatan", True, [[o, t], [t, o]])
    P["3連複◎○-相手3"] = ("sanpuku", False,
                        [[o, t, x] for x in m[2:5]])
    P["3連複◎-相手4から2"] = ("sanpuku", False,
                          [[o, a, b] for a, b in itertools.combinations(aite4, 2)])
    P["3連単◎1着-○▲-△"] = ("santan", True,
                        [[o, a, b] for a in m[1:3] for b in m[1:5] if b != a])
    P["3連単◎○12着マルチ-3着4"] = ("santan", True,
                            [[a, b, c] for a, b in [(o, t), (t, o)]
                             for c in m[2:6] if c not in (a, b)])
    return P


def run(model_file):
    B = lgb.Booster(model_file=model_file)
    F = B.feature_name()
    acc = {}          # name -> [買ったレース数, 点数合計, 的中レース数, 払戻合計, 最高配当]
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
            X = np.array([[fval(h, rc, k) for k in F] for h in hs], float)
            s = B.predict(X)
            order = np.argsort(-s)
            marks = [str(int(hs[i]["n"])) for i in order[:6]]
            if len(marks) < 6:
                continue
            for name, (kind, ordered, combos) in plans(marks).items():
                a = acc.setdefault(name, [0, 0, 0, 0, 0])
                a[0] += 1
                a[1] += len(combos)
                got = 0
                for c in combos:
                    v = (pay_single(pay.get(kind), c[0]) if kind in ("tan", "fuku")
                         else pay_combo(pay.get(kind), c, ordered))
                    got += v
                if got:
                    a[2] += 1
                    a[3] += got
                    a[4] = max(a[4], got)
    return acc


def main():
    files = sys.argv[1:]
    if not files:
        print(__doc__)
        return 1
    res = {f: run(f) for f in files}
    names = list(next(iter(res.values())).keys())
    w = max(len(n) for n in names) + 2
    print(f"データ: {os.path.relpath(DATA, ROOT)}  holdout {SPLIT}〜")
    for f in files:
        a = res[f]
        n0 = a[names[0]][0]
        print(f"\n=== {os.path.basename(f)}  {n0:,}R ===")
        print(f"{'買い方':<{w}}{'点/R':>5}{'的中率':>8}{'ROI':>8}{'除1':>8}")
        for n in names:
            races, pts, hit, ret, mx = a[n]
            if not races:
                continue
            inv = pts * 100
            roi = 100 * ret / inv if inv else 0
            roi_ex = 100 * (ret - mx) / inv if inv else 0
            print(f"{n:<{w}}{pts/races:>5.1f}{100*hit/races:>7.1f}%"
                  f"{roi:>7.1f}%{roi_ex:>7.1f}%")
    if len(files) >= 2:
        base, cand = files[0], files[1]
        print(f"\n=== 差分（{os.path.basename(cand)} − {os.path.basename(base)}）===")
        print(f"{'買い方':<{w}}{'的中率差':>9}{'ROI差':>8}")
        for n in names:
            rb, pb, hb, tb, _ = res[base][n]
            rc_, pc, hc, tc_, _ = res[cand][n]
            if not rb or not rc_:
                continue
            dh = 100 * hc / rc_ - 100 * hb / rb
            dr = (100 * tc_ / (pc * 100)) - (100 * tb / (pb * 100))
            flag = "◯" if dr > 0 else ("×" if dr < 0 else "")
            print(f"{n:<{w}}{dh:>+8.1f}pt{dr:>+7.1f}pt {flag}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
