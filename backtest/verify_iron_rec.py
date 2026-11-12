# -*- coding: utf-8 -*-
"""★「鉄板」バッジの条件付きROIを現行モデルで測り直す★（2026-08-03）

なぜ: tweet.html の鉄板バッジは「◎1番人気×単勝1.9倍以下×10頭以下 → 複勝率86%/ROI94%」
      を表示しているが、監査コメント自身が【★未検証★ 946R時代の値で現行モデルでは
      測り直していない】と認めている。表示だけ断定形なのは盛り。

条件（tweet.html の isIronRec と同一）:
    出走頭数 <= IRON_FIELD_MAX(10) かつ ◎が1番人気 かつ 単勝オッズ <= IRON_ODDS_MAX(1.9)

オッズ: keiba.go.jp公式の単勝確定オッズ（odds_2026MM.zip・2026-03〜が存在する全期間）。
       バッジ判定は朝の途中オッズだが、バックテストでは確定オッズを代理に使う。
使い方: python backtest/verify_iron_rec.py
"""
import csv
import io
import json
import os
import sys
import zipfile
import glob

import numpy as np
import lightgbm as lgb

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
os.environ.setdefault("LTR_NEWFEATS", "pre")
os.environ.setdefault("LTR_TC", "1")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bt_train_ltr import fval, SPLIT  # noqa: E402
from eval_bets import pay_single      # noqa: E402  ★払戻の読み方は自前で書かない★

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "backtest", "nardata", "bt_all.jsonl")
MODEL = os.path.join(ROOT, "backtest", "ltr_model.txt")
FIELD_MAX, ODDS_MAX = 10, 1.9
TRACK_CODE = {'門別': '30', '盛岡': '35', '水沢': '36', '浦和': '42', '船橋': '43',
              '大井': '44', '川崎': '45', '金沢': '46', '笠松': '47', '名古屋': '48',
              '園田': '50', '姫路': '51', '高知': '54', '佐賀': '55', '帯広ば': '65'}


def load_odds():
    """odds_2026MM.zip → rid → {馬番: (単勝オッズ, 人気)}"""
    odds = {}
    for zp in sorted(glob.glob(os.path.join(ROOT, "backtest", "nardata", "odds_*.zip"))):
        with zipfile.ZipFile(zp) as z:
            for name in z.namelist():
                text = z.read(name).decode("utf-8-sig", errors="replace")
                for row in csv.reader(io.StringIO(text)):
                    if len(row) < 10 or row[3] != "単勝":
                        continue
                    tc = TRACK_CODE.get(row[0])
                    if not tc:
                        continue
                    rid = f"{row[1][:4]}{tc}{row[1][4:]}{int(row[2]):02d}"
                    try:
                        odds.setdefault(rid, {})[str(int(row[4]))] = (float(row[7]), int(row[9]))
                    except ValueError:
                        pass
    return odds


def main():
    odds = load_odds()
    print(f"オッズ: {len(odds):,}レース分を読込（2026-03〜の公式確定オッズ）")
    B = lgb.Booster(model_file=MODEL)
    F = B.feature_name()
    n = hit = ret = tret = 0
    with open(DATA, encoding="utf-8") as f:
        for line in f:
            try:
                rc = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rc["d"] < max(SPLIT, "20260301") or rc["rid"] not in odds:
                continue
            hs = [h for h in rc["h"] if h.get("rk") is not None]
            if len(hs) < 5 or len(hs) > FIELD_MAX or not (rc.get("pay") or {}).get("fuku"):
                continue
            s = B.predict(np.array([[fval(h, rc, k) for k in F] for h in hs], float))
            top = hs[int(np.argmax(s))]
            num = str(int(top["n"]))
            od = odds[rc["rid"]].get(num)
            if not od or od[1] != 1 or od[0] > ODDS_MAX:
                continue
            n += 1
            v = pay_single(rc["pay"].get("fuku"), num)
            ret += v
            hit += 1 if v else 0
            tret += pay_single(rc["pay"].get("tan"), num)
    if not n:
        print("該当なし")
        return 1
    print(f"\n鉄板条件（{FIELD_MAX}頭以下 × ◎1番人気 × 単勝{ODDS_MAX}倍以下）")
    print(f"  {n:,}R  ◎複勝率 {100*hit/n:.1f}%  複勝ROI {ret/n:.1f}%  単勝ROI {tret/n:.1f}%")
    # Wilson 95%CI（複勝率）
    p = hit / n
    z = 1.96
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    w = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / den
    print(f"  複勝率 Wilson95%CI: {100*(c-w):.1f}〜{100*(c+w):.1f}%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
