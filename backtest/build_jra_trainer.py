# -*- coding: utf-8 -*-
"""中央の調教師インデックス（場別・年別・重賞の内訳つき）— build_jra_jockey.py と同形式

★狙い★
  騎手と同じ深掘り（場別・年別・G1/G2/G3）を調教師でも見られるようにする。
  形式を揃えてページ生成(gen_profile_pages.pyのJOCKEY_JS)をそのまま使い回す。

★調教師は略称で束ねる★ 中央SEの調教師略称(90-98)。実測260種。

出力: deploy/db/jra/t/index.json
  { 調教師名: {n, w, t3, roi, tr:{場:[n,w,t3]}, yr:{年:[n,w,t3]}, gr:{G1/G2/G3/重賞:[n,w]}} }
"""
import collections
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DUMP = [os.path.join(ROOT, "backtest", "jvdata", "target_all.txt"),
        os.path.join(ROOT, "backtest", "jvdata", "setup_2026.txt")]
OUT = os.path.join(ROOT, "deploy", "db", "jra", "t", "index.json")

S_KEY, S_UMA, S_FIN, S_TR = slice(11, 27), slice(28, 30), slice(334, 336), slice(90, 98)
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

    tr_agg = collections.defaultdict(lambda: {
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
                name = line[S_TR].decode("cp932", "replace").strip()
                if not name:
                    continue
                rk = int(fin)
                uma = str(int(line[S_UMA].decode("ascii", "replace") or 0))
                ret = (pays.get(k) or {}).get(uma, 0)
                e = tr_agg[name]
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
        print(f"  読了 {os.path.basename(path)}  調教師 {len(tr_agg):,}", flush=True)

    out = {}
    for name, e in tr_agg.items():
        if e["n"] < 50:
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
    print(f"\n中央調教師 {len(out):,}人 / {os.path.getsize(OUT)/1024:.0f}KB")
    print(f"出力: {os.path.relpath(OUT, ROOT)}")
    top = sorted(out.items(), key=lambda x: -x[1]["w"])[:3]
    for n, e in top:
        print(f"  {n}: {e['w']:,}勝 / 複勝率 {100*e['t3']/e['n']:.0f}%")
    print("\n  GI勝利数トップ10:")
    gi_top = sorted(out.items(), key=lambda x: -x[1]["gr"].get("GI", [0, 0])[1])[:10]
    for n, e in gi_top:
        gi = e["gr"].get("GI", [0, 0])
        print(f"    {n}: GI {gi[1]}勝/{gi[0]}出走")
    return 0


if __name__ == "__main__":
    sys.exit(main())
