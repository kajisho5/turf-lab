# -*- coding: utf-8 -*-
"""中央の騎手インデックス（場別・年別の内訳つき）— 地方の db/j/index.json と同形式

★狙い★
  出馬表の騎手名から中央でも個別ページに飛べるようにする。
  地方は build_profiles.py が db/j/index.json を作っている。中央も同じ形にして
  ページ生成を使い回す。

★騎手は略称で束ねる★
  中央SEの騎手略称(306-314)。IDは無いが略称で十分区別できる（実測240種）。

★重賞(G1/G2/G3)はRAレコードの格付けコード(614-615)から★
  docs/DATA_SOURCES.md で検算済み。A=GI B=GII C=GIII（D/F/G/H=障害等は「重賞」に
  まとめる）。レースキー(11-27)でSEと結合する。海外レース・地方交流重賞が
  混ざるので、場コード01-10（中央開催）だけに絞る＝SE側の絞り込みと同じ条件で
  自然に排除される。

出力: deploy/db/jra/j/index.json
  { 騎手名: {n, w, t3, roi, tr:{場:[n,w,t3]}, yr:{年:[n,w,t3]}, gr:{G1/G2/G3/重賞:[n,w]}} }
"""
import collections
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DUMP = [os.path.join(ROOT, "backtest", "jvdata", "target_all.txt"),
        os.path.join(ROOT, "backtest", "jvdata", "setup_2026.txt")]
OUT = os.path.join(ROOT, "deploy", "db", "jra", "j", "index.json")

S_KEY, S_UMA, S_FIN, S_JK = slice(11, 27), slice(28, 30), slice(334, 336), slice(306, 314)
H_KEY, H_FUKU = slice(11, 27), (141, 5, 2, 13)
R_KEY, R_GRADE = slice(11, 27), slice(614, 615)
JYO = {"01": "札幌", "02": "函館", "03": "福島", "04": "新潟", "05": "東京",
       "06": "中山", "07": "中京", "08": "京都", "09": "阪神", "10": "小倉"}
GRADE = {"A": "GI", "B": "GII", "C": "GIII",
          "D": "重賞", "F": "障害GI", "G": "障害GII", "H": "障害GIII"}


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
    grades = {}
    for path in DUMP:
        if os.path.exists(path):
            with open(path, "rb") as f:
                for line in f:
                    if line[:2] == b"HR":
                        pays[bytes(line[H_KEY])] = fuku_of(line)
                    elif line[:2] == b"RA":
                        g = line[R_GRADE].decode("ascii", "replace")
                        if g in GRADE:
                            grades[bytes(line[R_KEY])] = GRADE[g]
    print(f"  重賞レース: {len(grades):,}件（RA格付けコードより）", flush=True)

    jk = collections.defaultdict(lambda: {
        "n": 0, "w": 0, "t3": 0, "ret": 0,
        "tr": collections.defaultdict(lambda: [0, 0, 0]),
        "yr": collections.defaultdict(lambda: [0, 0, 0]),
        "gr": collections.defaultdict(lambda: [0, 0])})

    for path in DUMP:
        if not os.path.exists(path):
            continue
        with open(path, "rb") as f:
            for line in f:
                if line[:2] != b"SE":
                    continue
                k = bytes(line[S_KEY])
                jyo = k[8:10].decode("ascii", "replace")
                if jyo not in JYO:
                    continue
                fin = line[S_FIN].decode("ascii", "replace").strip()
                if not fin.isdigit():
                    continue
                name = line[S_JK].decode("cp932", "replace").strip()
                if not name:
                    continue
                rk = int(fin)
                uma = str(int(line[S_UMA].decode("ascii", "replace") or 0))
                ret = (pays.get(k) or {}).get(uma, 0)
                e = jk[name]
                e["n"] += 1
                e["w"] += (rk == 1)
                e["t3"] += (rk <= 3)
                e["ret"] += ret
                t = e["tr"][JYO[jyo]]
                t[0] += 1; t[1] += (rk == 1); t[2] += (rk <= 3)
                y = e["yr"][k[:4].decode()]
                y[0] += 1; y[1] += (rk == 1); y[2] += (rk <= 3)
                g = grades.get(k)
                if g:
                    gg = e["gr"][g]
                    gg[0] += 1; gg[1] += (rk == 1)
        print(f"  読了 {os.path.basename(path)}  騎手 {len(jk):,}", flush=True)

    out = {}
    for name, e in jk.items():
        if e["n"] < 50:            # 騎乗が極端に少ない人は載せない
            continue
        out[name] = {
            "n": e["n"], "w": e["w"], "t3": e["t3"],
            "roi": round(100 * e["ret"] / (100 * e["n"]), 1),
            "tr": {kk: v for kk, v in sorted(e["tr"].items(), key=lambda x: -x[1][0])},
            "yr": {kk: v for kk, v in sorted(e["yr"].items())},
            "gr": {kk: v for kk, v in sorted(e["gr"].items(), key=lambda x: -x[1][1])},
        }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    print(f"\n中央騎手 {len(out):,}人 / {os.path.getsize(OUT)/1024:.0f}KB")
    print(f"出力: {os.path.relpath(OUT, ROOT)}")
    # 検算
    top = sorted(out.items(), key=lambda x: -x[1]["w"])[:3]
    for n, e in top:
        print(f"  {n}: {e['w']:,}勝 / 複勝率 {100*e['t3']/e['n']:.0f}%")
    # GI勝利数トップ（実在の名手が上位に来るか目視確認する用）
    print("\n  GI勝利数トップ10:")
    gi_top = sorted(out.items(), key=lambda x: -x[1]["gr"].get("GI", [0, 0])[1])[:10]
    for n, e in gi_top:
        gi = e["gr"].get("GI", [0, 0])
        print(f"    {n}: GI {gi[1]}勝/{gi[0]}騎乗")
    return 0


if __name__ == "__main__":
    sys.exit(main())
