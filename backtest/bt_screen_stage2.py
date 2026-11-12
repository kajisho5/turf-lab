# -*- coding: utf-8 -*-
"""ふるい通過項目の本検証（第2段）— 年別の一貫性

★第1段（bt_feature_screen.py）が確かめたこと★
  人気×頭数で説明できない残差を、その項目が説明できるか。
  17項目中14項目が補正済み |z|>=3.5 で通過した。

★この第2段で確かめること★
  その残差効果が **年をまたいで安定しているか**。
  全期間の合算で有意でも、特定の年だけで作られた効果なら使えない。
  （前半/後半の固定分割は市場の非定常性で本物を捨てるため使わない。
    年ごとの符号の一貫性で見る。）

  判定:
    - 14年のうち、残差の符号が全体と同じ年の割合（sign consistency）
    - 直近5年（2022-2026）だけで再計算した残差
    - 両方が立てば「採用候補」、直近で消えていれば「過去の遺物」

使い方: python backtest/bt_screen_stage2.py
出力  : backtest/screen_stage2.json
"""
import collections
import json
import math
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "backtest", "nardata", "bt_all.jsonl")
OUT = os.path.join(ROOT, "backtest", "screen_stage2.json")

MIN_YEAR_N = 800     # 年あたりこの頭数未満なら符号判定から除外
RECENT = "2022"

# 第1段を通過した項目のうち、群として意味を持つもの。
# (名前, 判定関数: (h, ctx) -> True/False, 期待する向き +1/-1)
# ctx: {"senko": レース内の先行馬数, "wtorder": 馬体重降順の並び, "fb": 頭数帯}
def _wt_third(h, ctx):
    order = ctx.get("wtorder")
    if not order or h.get("wt") is None:
        return None
    k = len(order)
    i = order.index(id(h))
    return 0 if i < k / 3 else (1 if i < 2 * k / 3 else 2)


CHECKS = [
    ("前走かなり後方(lpf>=0.8)",
     lambda h, c: (h["lpf"] >= 0.8) if h.get("lpf") is not None else None, -1),
    ("近走平均8着以下(ar>=8)",
     lambda h, c: (h["ar"] >= 8) if h.get("ar") is not None else None, -1),
    ("馬体重微減(-9〜-1kg)",
     lambda h, c: (-9 <= h["wd"] <= -1) if h.get("wd") is not None else None, +1),
    ("馬体重が軽い1/3",
     lambda h, c: (_wt_third(h, c) == 2) if _wt_third(h, c) is not None else None, -1),
    ("先行力上位が4頭以上いる",
     lambda h, c: (sum(1 for o in c["hs"] if o.get("fpf") is not None
                       and h.get("fpf") is not None and o["fpf"] < h["fpf"]) >= 4)
     if h.get("fpf") is not None else None, -1),
    ("外枠×先行(枠6-8×fpf<=0.35)",
     lambda h, c: (h.get("wk", 0) >= 6 and h["fpf"] <= 0.35)
     if h.get("fpf") is not None and h.get("wk") else None, +1),
    ("短距離×先行(<1400m×fpf<=0.35)",
     lambda h, c: (c["dist"] and c["dist"] < 1400 and h["fpf"] <= 0.35)
     if h.get("fpf") is not None else None, +1),
    ("8歳以上",
     lambda h, c: (h["age"] >= 8) if h.get("age") else None, -1),
    ("8枠",
     lambda h, c: (h["wk"] == 8) if h.get("wk") else None, +1),
    ("単騎逃げ候補(fpf<=0.25×先行1頭)",
     lambda h, c: (h["fpf"] <= 0.25 and c["senko"] == 1)
     if h.get("fpf") is not None else None, +1),
    ("中頭数×先行(9-11頭×fpf<=0.35)",
     lambda h, c: (c["fb"] == "9〜11" and h["fpf"] <= 0.35)
     if h.get("fpf") is not None else None, +1),
]


def fbucket(n):
    return "〜8" if n <= 8 else ("9〜11" if n <= 11 else ("12〜13" if n <= 13 else "14〜"))


def main():
    # 期待複勝率（人気×頭数帯）
    exp = collections.defaultdict(lambda: [0, 0])
    with open(DATA, encoding="utf-8") as f:
        for line in f:
            rc = json.loads(line)
            hs = [h for h in rc["h"] if h.get("rk") is not None and h.get("pop")]
            if len(hs) < 6:
                continue
            fb = fbucket(len(hs))
            for h in hs:
                e = exp[(min(h["pop"], 12), fb)]
                e[0] += 1
                e[1] += (h["rk"] <= 3)

    def expected(pop, fb):
        e = exp[(min(pop, 12), fb)]
        return (e[1] / e[0]) if e[0] >= 50 else None

    # 項目 -> 年 -> [n, 残差合計]
    agg = {name: collections.defaultdict(lambda: [0, 0.0]) for name, _, _ in CHECKS}

    with open(DATA, encoding="utf-8") as f:
        for line in f:
            rc = json.loads(line)
            hs = [h for h in rc["h"] if h.get("rk") is not None and h.get("pop")]
            if len(hs) < 6:
                continue
            fb = fbucket(len(hs))
            yr = rc["d"][:4]
            senko = sum(1 for h in hs if h.get("fpf") is not None and h["fpf"] <= 0.35)
            wts = [h for h in hs if h.get("wt")]
            wtorder = [id(x) for x in sorted(wts, key=lambda x: -x["wt"])] if len(wts) >= 6 else None
            ctx = {"hs": hs, "senko": senko, "wtorder": wtorder,
                   "fb": fb, "dist": rc.get("dist")}
            for h in hs:
                base = expected(h["pop"], fb)
                if base is None:
                    continue
                resid = (1 if h["rk"] <= 3 else 0) - base
                for name, fn, _sign in CHECKS:
                    try:
                        v = fn(h, ctx)
                    except Exception:
                        v = None
                    if v:                    # 条件に該当した馬だけ
                        e = agg[name][yr]
                        e[0] += 1
                        e[1] += resid

    rows = []
    for name, _fn, sign in CHECKS:
        years = {y: v for y, v in agg[name].items() if v[0] >= MIN_YEAR_N}
        if len(years) < 6:
            rows.append({"name": name, "verdict": "年別サンプル不足", "years": len(years)})
            continue
        per_year = {y: 100 * v[1] / v[0] for y, v in sorted(years.items())}
        same = sum(1 for r in per_year.values() if (r > 0) == (sign > 0))
        # 直近だけ
        rec = [(v[0], v[1]) for y, v in years.items() if y >= RECENT]
        rec_n = sum(r[0] for r in rec)
        rec_resid = 100 * sum(r[1] for r in rec) / rec_n if rec_n else None
        total_n = sum(v[0] for v in years.values())
        total_resid = 100 * sum(v[1] for v in years.values()) / total_n
        # 直近の標準誤差（p(1-p)近似ではなく残差の粗い誤差: 0.45/sqrt(n)*100）
        rec_se = 45.0 / math.sqrt(rec_n) if rec_n else None
        alive = (rec_resid is not None and rec_se is not None
                 and (rec_resid > 2 * rec_se if sign > 0 else rec_resid < -2 * rec_se))
        consistent = same / len(per_year) >= 0.75
        verdict = ("採用候補" if (alive and consistent) else
                   "直近で消滅" if (consistent and not alive) else
                   "年別が不安定")
        rows.append({
            "name": name, "sign": sign, "n": total_n,
            "resid_all": total_resid, "resid_recent": rec_resid,
            "recent_n": rec_n, "years": len(per_year),
            "sign_match": same, "per_year": {y: round(r, 2) for y, r in per_year.items()},
            "verdict": verdict,
        })

    rows.sort(key=lambda r: (r.get("verdict") != "採用候補",
                             -abs(r.get("resid_recent") or 0)))

    def pad(s, w):
        s = str(s)
        x = sum(2 if ord(c) > 255 else 1 for c in s)
        return s + " " * max(0, w - x)

    print(pad("項目", 34) + "全期間残差".rjust(9) + "直近残差".rjust(9)
          + "直近n".rjust(9) + "符号一致".rjust(9) + "  判定")
    print("-" * 84)
    for r in rows:
        if "sign" not in r:
            print(pad(r["name"], 34) + " " * 27 + f'({r["verdict"]})')
            continue
        print(pad(r["name"], 34)
              + f'{r["resid_all"]:+8.2f}%'
              + f'{r["resid_recent"]:+8.2f}%'
              + f'{r["recent_n"]:9,}'
              + f'{r["sign_match"]}/{r["years"]}'.rjust(9)
              + "  " + r["verdict"])

    json.dump({"min_year_n": MIN_YEAR_N, "recent_from": RECENT, "rows": rows},
              open(OUT, "w", encoding="utf-8", newline="\n"),
              ensure_ascii=False, indent=1)
    print(f"\n出力: {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
