# -*- coding: utf-8 -*-
"""重賞ごとの過去データを集計する（枠別・人気別・脚質別・配当傾向）

★狙い★
  「有馬記念 データ」「皐月賞 枠順」のような検索需要は巨大。
  中央の全データ(1986-)を持っているので、重賞ごとの傾向ページを量産する。
  重賞カレンダーの各レースから個別ページに飛べるようにする。

★集計は生ダンプから★
  jra_all.jsonl には枠・コーナー通過順が無い（parse_jvdata が最小限にした）。
  target_all.txt / setup_2026.txt の生SEレコードから直接作る。

  レース名の表記ゆれは gen_calendar_page.norm() と同じ扱いにする。
  中央（場コード01-10）の重賞（格付けA/B/C/D/F/G/H）だけ。

★脚質＝そのレースでどう走ったか★
  最初のコーナー通過順 ÷ 頭数。過去3走平均ではなく「この重賞での走り」。
  重賞ページで知りたいのは「このレースは逃げ・先行が有利か（コースのクセ）」なので、
  当該レースでの隊列で見るのが正しい。しきい値は personas.js と揃える。

出力: deploy/data/jusho/data.json  { レース名: {runnings, pop, waku, style, ...} }
"""
import collections
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gen_calendar_page import norm, GRADE, JYO         # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DUMP = [os.path.join(ROOT, "backtest", "jvdata", "target_all.txt"),
        os.path.join(ROOT, "backtest", "jvdata", "setup_2026.txt")]
OUT = os.path.join(ROOT, "deploy", "data", "jusho", "data.json")

R_KEY, R_NAME, R_GRADE = slice(11, 27), slice(32, 92), slice(614, 615)
R_DIST, R_TRACK = slice(697, 701), slice(705, 707)
S_KEY, S_WK, S_UMA = slice(11, 27), slice(27, 28), slice(28, 30)
S_NAME, S_FIN = slice(40, 76), slice(334, 336)
S_C1, S_POP = slice(351, 353), slice(363, 365)
H_KEY, H_TAN = slice(11, 27), (102, 3, 2, 13)

# 脚質しきい値（personas.js と同じ・最初のコーナー位置率）
STYLE = [(0.20, "逃げ"), (0.45, "先行"), (0.75, "差し"), (9, "追込")]
SINCE = "20150101"          # 過去10年ぶんに絞る（傾向は最近が効く）


def num(b):
    s = b.decode("ascii", "replace").strip()
    return int(s) if s.lstrip("+-").isdigit() else None


def style_of(ratio):
    for cut, name in STYLE:
        if ratio <= cut:
            return name
    return "追込"


def tan_of(rec):
    p = H_TAN[0]
    u = rec[p:p + 2].decode("ascii", "replace").strip()
    y = rec[p + 2:p + 11].decode("ascii", "replace").strip()
    return (str(int(u)), int(y)) if u and y.isdigit() else (None, 0)


def main():
    # RA: レースキー -> (レース名, 距離, トラック). 中央の重賞のみ
    ra = {}
    tan = {}
    for path in DUMP:
        if not os.path.exists(path):
            continue
        with open(path, "rb") as f:
            for line in f:
                t = line[:2]
                if t == b"RA":
                    k = line[R_KEY]
                    if k[8:10].decode("ascii", "replace") not in JYO:
                        continue
                    g = line[R_GRADE].decode("cp932", "replace")
                    if g not in GRADE:
                        continue
                    if k[:8].decode() < SINCE:
                        continue
                    tr = line[R_TRACK].decode("ascii", "replace")
                    ra[bytes(k)] = {
                        "name": norm(line[R_NAME].decode("cp932", "replace")),
                        "g": g, "dist": num(line[R_DIST]),
                        "surf": "芝" if tr[:1] == "1" else ("ダ" if tr[:1] == "2" else "障"),
                        "date": k[:8].decode(),
                    }
                elif t == b"HR":
                    u, y = tan_of(line)
                    if u:
                        tan[bytes(line[H_KEY])] = (u, y)
        print(f"  読了 {os.path.basename(path)}  重賞RA {len(ra):,}", flush=True)

    # レース名ごとに集計
    #   pop[p]=[n,win,place] / waku[w]=[...] / style[s]=[...]
    def blank():
        return {
            "runnings": [],
            "pop": collections.defaultdict(lambda: [0, 0, 0]),
            "waku": collections.defaultdict(lambda: [0, 0, 0]),
            "style": collections.defaultdict(lambda: [0, 0, 0]),
            "grade": "", "surf": "", "dist": 0, "jyo": set(),
        }
    agg = collections.defaultdict(blank)

    # SE をレース単位でまとめる
    se_by_race = collections.defaultdict(list)
    for path in DUMP:
        if not os.path.exists(path):
            continue
        with open(path, "rb") as f:
            for line in f:
                if line[:2] != b"SE":
                    continue
                k = bytes(line[S_KEY])
                if k in ra:
                    se_by_race[k].append(line[:600])
        print(f"  SE収集 {os.path.basename(path)}  {len(se_by_race):,}レース", flush=True)

    for k, rows in se_by_race.items():
        meta = ra[k]
        name = meta["name"]
        a = agg[name]
        a["grade"] = meta["g"]
        a["surf"] = meta["surf"]
        a["dist"] = meta["dist"]
        a["jyo"].add(JYO.get(k[8:10].decode(), "?"))

        live = [r for r in rows if (num(r[S_FIN]) or 0) >= 1]
        fn = len(live)
        if fn < 5:
            continue
        winner = None
        for r in live:
            fin = num(r[S_FIN])
            pop = num(r[S_POP])
            wk = num(r[S_WK])
            c1 = num(r[S_C1])
            hit1 = fin == 1
            hit3 = fin <= 3
            if pop:
                e = a["pop"][pop]
                e[0] += 1; e[1] += hit1; e[2] += hit3
            if wk:
                e = a["waku"][wk]
                e[0] += 1; e[1] += hit1; e[2] += hit3
            if c1 and fn:
                st = style_of(c1 / fn)
                e = a["style"][st]
                e[0] += 1; e[1] += hit1; e[2] += hit3
            if hit1:
                winner = {"name": r[S_NAME].decode("cp932", "replace").strip(),
                          "pop": pop}
        u_y = tan.get(k, (None, 0))
        a["runnings"].append({
            "date": meta["date"],
            "winner": winner["name"] if winner else "",
            "wpop": winner["pop"] if winner else None,
            "tan": u_y[1],
            "fn": fn,
        })

    # 出力（過去10年に3回以上施行された重賞だけ）
    out = {}
    for name, a in agg.items():
        runs = sorted(a["runnings"], key=lambda x: x["date"], reverse=True)
        if len(runs) < 3:
            continue
        def pack(tbl, keys):
            return {str(kk): tbl[kk] for kk in keys if tbl[kk][0] > 0}
        out[name] = {
            "grade": GRADE[a["grade"]][0] if a["grade"] in GRADE else "重賞",
            "surf": a["surf"], "dist": a["dist"],
            "jyo": sorted(a["jyo"]),
            "runs": len(runs),
            "runnings": runs[:12],
            "pop": pack(a["pop"], range(1, 19)),
            "waku": pack(a["waku"], range(1, 9)),
            "style": {s: a["style"][s] for s, _ in ((x[1], x[0]) for x in STYLE)
                      if a["style"][s][0] > 0},
        }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    print(f"\n重賞 {len(out)}レース / {os.path.getsize(OUT)/1024:.0f}KB")
    print(f"出力: {os.path.relpath(OUT, ROOT)}")
    # サンプル
    for nm in ("有馬記念", "皐月賞", "高松宮記念"):
        if nm in out:
            o = out[nm]
            p1 = o["pop"].get("1", [0, 0, 0])
            print(f"  {nm}: {o['runs']}回 / 1番人気 複勝率 "
                  f"{100*p1[2]/p1[0]:.0f}%（{p1[0]}回中）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
