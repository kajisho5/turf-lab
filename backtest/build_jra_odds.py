# -*- coding: utf-8 -*-
"""中央: 馬ごとの確定単勝オッズを別ファイル（bt_jra.jsonl.odds）に書き出す。

bt_jra.jsonl 本体には手を入れない（形を変えると既存の検証が全部ずれるため）。
読み方は build_jra_dataset.py と同じ（追加ぶん JRA_EXTRA_DUMPS は同じ馬を置き換える）。
1行 = [rid, {馬番: オッズ}]。出すのは数字だけ。
使い方: python backtest/build_jra_odds.py
"""
import collections
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from build_jra_dataset import DUMP, OUT, S_KEY, S_UMA, S_KETTO, S_FIN, S_ODDS, S_POP, num  # noqa: E402


def main():
    se = collections.defaultdict(list)
    for path in DUMP:
        if not os.path.exists(path):
            continue
        with open(path, "rb") as f:
            for line in f:
                if line[:2] == b"SE":
                    se[line[S_KEY]].append(line)
    for path in [x for x in os.environ.get("JRA_EXTRA_DUMPS", "").split(os.pathsep) if x]:
        if not os.path.exists(path):
            continue
        with open(path, "rb") as f:
            for line in f:
                if line[:2] == b"SE":
                    rows, kt = se[line[S_KEY]], line[S_KETTO]
                    for i, r in enumerate(rows):
                        if r[S_KETTO] == kt:
                            rows[i] = line
                            break
                    else:
                        rows.append(line)
    n = n_h = n_zero = 0
    chk = collections.Counter()
    with open(OUT + ".odds", "w", encoding="utf-8") as fo:
        for k in sorted(se, key=lambda k: (k[:8].decode(), k[14:16].decode())):
            rid = k[:8].decode() + k[8:10].decode() + f"{int(k[14:16]):02d}"
            d = {}
            for r in se[k]:
                if not num(r[S_FIN]):
                    continue
                o = num(r[S_ODDS])
                n_h += 1
                if not o:
                    n_zero += 1
                    continue
                d[str(num(r[S_UMA]))] = o / 10
                # 形の確かめ: 人気1位のオッズがそのレースで最小か（位置が合っていれば ほぼ100%）
                if num(r[S_POP]) == 1 and k[:4] >= b"2023":
                    chk["fav"] += 1
            if d:
                if k[:4] >= b"2023":
                    fav = [num(r[S_ODDS]) for r in se[k] if num(r[S_FIN]) and num(r[S_POP]) == 1 and num(r[S_ODDS])]
                    if fav:
                        chk["fav_is_min"] += min(fav) / 10 <= min(d.values()) + 1e-9
                fo.write(json.dumps([rid, d]) + "\n")
                n += 1
    print(f"出力 {os.path.basename(OUT)}.odds  {n:,}レース  着順のある馬 {n_h:,}  オッズなし {n_zero:,}")
    print(f"確かめ(2023年〜): 1番人気のオッズがレース内で最小 {chk['fav_is_min']:,} / {chk['fav']:,}")


if __name__ == "__main__":
    main()
