# -*- coding: utf-8 -*-
"""中央競馬のリーディング集計（騎手・調教師・馬主）

★列位置は実データで同定した（docs/DATA_SOURCES.md に記録）★
  種類数が実際の人数と合うかで確かめている:
    調教師略称 90-98    260種 （JRA調教師 約200人 + 地方/海外の短期）
    騎手略称  306-314  240種 （JRA騎手 約150人 + 短期免許）
    馬主名   104-168  1,717種

★ROIの分母は買った全レース★
  「その騎手の複勝を全騎乗100円ずつ買った」計算。的中時だけ投資計上しない。

出力: backtest/jra_leading.json
"""
import collections
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DUMP = [os.path.join(ROOT, "backtest", "jvdata", "target_all.txt"),
        os.path.join(ROOT, "backtest", "jvdata", "setup_2026.txt")]
OUT = os.path.join(ROOT, "backtest", "jra_leading.json")

S_KEY, S_UMA, S_FIN = slice(11, 27), slice(28, 30), slice(334, 336)
S_TR, S_JK, S_OW = slice(90, 98), slice(306, 314), slice(104, 168)
H_KEY = slice(11, 27)
H_FUKU = (141, 5, 2, 13)          # 複勝: 先頭141・5枠・組2桁・1件13バイト

JYO = {f"{i:02d}" for i in range(1, 11)}      # 中央の場コードだけ
RECENT = "20240101"


def fuku_of(rec):
    out = {}
    start, cnt, kd, ln = H_FUKU
    for i in range(cnt):
        p = start + i * ln
        k = rec[p:p + kd].decode("ascii", "replace").strip()
        y = rec[p + kd:p + kd + 9].decode("ascii", "replace").strip()
        if k and y.isdigit() and int(y) > 0:
            out[str(int(k))] = int(y)
    return out


def main():
    pays = {}
    # kind -> seg -> name -> [n, win, top3, ret]
    agg = {k: (collections.defaultdict(lambda: [0, 0, 0, 0]),
               collections.defaultdict(lambda: [0, 0, 0, 0]))
           for k in ("jockey", "trainer", "owner")}
    races = set()

    for path in DUMP:
        if not os.path.exists(path):
            continue
        # ★2周する★ 払戻(HR)がSEより後ろに出ることがあるので、先に払戻を全部集める
        with open(path, "rb") as f:
            for line in f:
                if line[:2] == b"HR":
                    pays[line[H_KEY]] = fuku_of(line)
        with open(path, "rb") as f:
            for line in f:
                if line[:2] != b"SE":
                    continue
                k = line[S_KEY]
                if k[8:10].decode("ascii", "replace") not in JYO:
                    continue          # 海外・地方交流は中央のリーディングに入れない
                fin = line[S_FIN].decode("ascii", "replace").strip()
                if not fin.isdigit():
                    continue
                rk = int(fin)
                uma = str(int(line[S_UMA].decode("ascii", "replace") or 0))
                ret = (pays.get(k) or {}).get(uma, 0)
                recent = k[:8].decode() >= RECENT
                races.add(k)
                for kind, sl in (("jockey", S_JK), ("trainer", S_TR), ("owner", S_OW)):
                    name = line[sl].decode("cp932", "replace").strip()
                    if not name:
                        continue
                    for seg, use in ((0, True), (1, recent)):
                        if not use:
                            continue
                        e = agg[kind][seg][name]
                        e[0] += 1
                        e[1] += (rk == 1)
                        e[2] += (rk <= 3)
                        e[3] += ret
        print(f"  読了 {os.path.basename(path)}  レース {len(races):,}", flush=True)

    out = {"races": len(races), "recent_from": RECENT, "data": {}}
    for kind in agg:
        out["data"][kind] = [
            {k: v for k, v in seg.items()} for seg in agg[kind]
        ]
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    print(f"\n出力: {os.path.relpath(OUT, ROOT)}  {len(races):,}レース")
    for kind in agg:
        print(f"  {kind}: 通算 {len(agg[kind][0]):,}人 / 直近 {len(agg[kind][1]):,}人")
    return 0


if __name__ == "__main__":
    sys.exit(main())
