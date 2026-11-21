# -*- coding: utf-8 -*-
"""中央: 調教タイム（坂路 HC・ウッド WC）から、レース前14日の項目を作る（検証用の別ファイル）。

入力: 環境変数 JRA_CHOKYO（os.pathsep 区切り）の JV-Link ダンプ（SLOP / WOOD）
出力: bt_jra.jsonl.chokyo  1行 = [rid, {馬番: {項目: 値}}]
位置は 2026-11-21 に実データで確かめた（0始まりのバイト位置）:
  共通 11=トレセン(0美浦/1栗東) 12:20=調教日 24:34=血統登録番号
  HC(60B) 34:38=4F合計 55:58=最後の1Fのラップ（×0.1秒。4F合計＝ラップ4つの和で一致 11,130/11,138）
  WC(105B) 34=コース 79:83=4F合計 100:103=最後の1Fのラップ
項目（どれも「その日・そのトレセン（ウッドはコースも）で走った全馬の中での速さ」＝平均との差÷ばらつき。大きいほど速い）
  hz=坂路4Fの最良 / hlast=最後の坂路の4F / hl=最後の坂路の終い1F
  wz=ウッド4Fの最良 / wlast=最後のウッドの4F / wl=最後のウッドの終い1F
  cz=hz と wz の良い方 / cnt=本数 / gap=最後の調教からの日数
使うのはレースの前日まで（当日の調教は使わない）。
使い方: JRA_CHOKYO=slop.txt:wood.txt python backtest/build_jra_chokyo.py
"""
import collections
import datetime
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from build_jra_dataset import DUMP, OUT, S_KEY, S_UMA, S_KETTO, S_FIN, num  # noqa: E402

WIN = 14


def dnum(s):
    return datetime.date(int(s[:4]), int(s[4:6]), int(s[6:8])).toordinal()


def main():
    raw = collections.defaultdict(list)       # (日,トレセン,種別) -> [(馬, 4F, 終い1F)]
    for path in [x for x in os.environ.get("JRA_CHOKYO", "").split(os.pathsep) if x]:
        if not os.path.exists(path):
            print(f"  無い: {path}")
            continue
        with open(path, "rb") as f:
            for l in f:
                t = l[:2]
                if t == b"HC":
                    f4, l1, kind = num(l[34:38]), num(l[55:58]), "H"
                elif t == b"WC":
                    f4, l1, kind = num(l[79:83]), num(l[100:103]), "W" + l[34:35].decode("ascii", "replace")
                else:
                    continue
                if not f4 or not l1 or not (450 <= f4 <= 750) or not (100 <= l1 <= 250):
                    continue                    # 軽い運動・計測の乱れは外す
                raw[(l[12:20].decode(), l[11:12], kind)].append((l[24:34], f4, l1))
    horse = collections.defaultdict(list)      # 馬 -> [(日の通し番号, 種別H/W, z4, z1)]
    for (d, _, kind), rows in raw.items():
        if len(rows) < 20:
            continue
        m4 = sum(r[1] for r in rows) / len(rows)
        s4 = (sum((r[1] - m4) ** 2 for r in rows) / len(rows)) ** 0.5 or 1
        m1 = sum(r[2] for r in rows) / len(rows)
        s1 = (sum((r[2] - m1) ** 2 for r in rows) / len(rows)) ** 0.5 or 1
        o = dnum(d)
        for h, f4, l1 in rows:
            horse[h].append((o, kind[0], (m4 - f4) / s4, (m1 - l1) / s1))
    for h in horse:
        horse[h].sort()
    days = sorted({k[0] for k in raw})
    if not days:
        print("調教データが無い")
        return 1
    first = dnum(days[0]) + WIN
    print(f"調教 {sum(len(v) for v in raw.values()):,}本  {days[0]}〜{days[-1]}  馬 {len(horse):,}頭")

    se = collections.defaultdict(list)
    for path in DUMP + [x for x in os.environ.get("JRA_EXTRA_DUMPS", "").split(os.pathsep) if x]:
        if not os.path.exists(path):
            continue
        with open(path, "rb") as f:
            for line in f:
                if line[:2] == b"SE" and line[11:19].decode("ascii", "replace") >= days[0]:
                    rows, kt = se[line[S_KEY]], line[S_KETTO]
                    for i, r in enumerate(rows):
                        if r[S_KETTO] == kt:
                            rows[i] = line
                            break
                    else:
                        rows.append(line)
    n = nh = nany = 0
    with open(OUT + ".chokyo", "w", encoding="utf-8") as fo:
        for k in sorted(se):
            o = dnum(k[:8].decode())
            if o < first:
                continue
            out = {}
            for r in se[k]:
                if not num(r[S_FIN]):
                    continue
                ws = [w for w in horse.get(r[S_KETTO], ()) if o - WIN <= w[0] < o]
                H = [w for w in ws if w[1] == "H"]
                W = [w for w in ws if w[1] == "W"]
                d = {"hz": max((w[2] for w in H), default=None), "hlast": H[-1][2] if H else None, "hl": H[-1][3] if H else None,
                     "wz": max((w[2] for w in W), default=None), "wlast": W[-1][2] if W else None, "wl": W[-1][3] if W else None,
                     "cnt": len(ws), "gap": o - ws[-1][0] if ws else None}
                both = [x for x in (d["hz"], d["wz"]) if x is not None]
                d["cz"] = max(both) if both else None
                out[str(num(r[S_UMA]))] = {a: (round(v, 3) if isinstance(v, float) else v) for a, v in d.items()}
                nh += 1
                nany += bool(ws)
            if out:
                fo.write(json.dumps([k[:8].decode() + k[8:10].decode() + f"{int(k[14:16]):02d}", out]) + "\n")
                n += 1
    print(f"出力 {os.path.basename(OUT)}.chokyo  {n:,}レース  馬 {nh:,}頭のうち14日以内に調教あり {100 * nany / max(nh, 1):.0f}%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
