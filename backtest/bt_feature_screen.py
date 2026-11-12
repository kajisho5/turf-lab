# -*- coding: utf-8 -*-
"""候補の特徴量を1パスで一斉にふるいにかける

★なぜ一斉にやるのか★
  100個を1個ずつバックテストすると、本当は効かなくても偶然100%を超えるものが
  5個前後は出る。実際このセッションでは当地実績・当距離実績・近走数・
  騎手×調教師の相性が、生の集計では大きな差に見えたのに人気で統制したら全部消えた。

  なので先に**同じ土俵で全部同時に測り、生き残ったものだけ本検証に回す**。

★測るもの＝人気で説明できない部分★
  各馬の「複勝に入ったか」を、**人気と頭数から決まる期待値**と比べて残差を出す。
    residual = 実際に複勝圏内か(0/1) − その人気・頭数での平均的な複勝率
  候補の値でグループに分け、残差の平均が0から離れていれば、
  **人気が知らない情報を持っている**ということ。

  期待値は同じデータから作るので、全体の残差平均は必ず0になる。
  よって「どの群がプラスか」だけが意味を持つ。

★リーク防止★
  履歴から作る特徴量（前走からの間隔、距離変化など）は、
  レースを日付順に処理し、そのレースを処理した**後**に履歴を更新する。

★判定★
  各特徴量について、群ごとの残差を出し、標準誤差で割ってzにする。
  |z| が大きいものだけが第2段（本検証）に進む。
  102個試すので、5%水準をそのまま使うと5個は誤検出になる。
  ボンフェローニで z の閾値を上げる（0.05/102 → 両側で |z| >= 3.5 相当）。

使い方: python backtest/bt_feature_screen.py
出力  : backtest/feature_screen.json
"""
import collections
import json
import math
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "backtest", "nardata", "bt_all.jsonl")
AUX = os.path.join(ROOT, "backtest", "nardata", "aux")
OUT = os.path.join(ROOT, "backtest", "feature_screen.json")

MIN_N = 2000          # この頭数に満たない群は判定しない
N_TESTS = 102         # 候補の数。ボンフェローニ補正に使う
Z_GATE = 3.5          # 0.05/102 の両側に相当するおおよその閾値


def bucket_days(d):
    if d is None:
        return None
    return ("中1週未満" if d < 10 else "10〜20日" if d < 21 else
            "21〜35日" if d < 36 else "36〜90日" if d < 91 else "91日以上")


def bucket_dist_change(c):
    if c is None:
        return None
    if c == 0:
        return "同距離"
    if c > 0:
        return "延長200m以内" if c <= 200 else "延長300m以上"
    return "短縮200m以内" if c >= -200 else "短縮300m以上"


def sign_bucket(v, lo, hi, labels):
    if v is None:
        return None
    return labels[0] if v < lo else (labels[1] if v <= hi else labels[2])


def main():
    if not os.path.exists(DATA):
        print(f"見つからない: {DATA}")
        return 1

    # 期待値表: (人気, 頭数帯) -> [頭数, 複勝数]
    # 1パス目で作る（同じデータから作るので残差の全体平均は0になる）
    exp = collections.defaultdict(lambda: [0, 0])

    def fbucket(n):
        return "〜8" if n <= 8 else ("9〜11" if n <= 11 else ("12〜13" if n <= 13 else "14〜"))

    print("1パス目: 人気×頭数の期待複勝率を作る...", flush=True)
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

    # 特徴量ごと: 名前 -> 群 -> [頭数, 残差合計, 残差二乗和]
    agg = collections.defaultdict(lambda: collections.defaultdict(lambda: [0, 0.0, 0.0]))

    # 馬ごとの履歴（リーク防止のためレース処理後に更新する）
    last_race = {}       # 馬名 -> (日付, 距離, 場, 着順, 人気, 騎手, 体重)
    career = collections.defaultdict(lambda: [0, 0])   # 馬名 -> [出走, 複勝]

    print("2パス目: 候補ごとに残差を集める...", flush=True)
    cur_ym, aux = None, {}
    nrace = 0
    with open(DATA, encoding="utf-8") as f:
        for line in f:
            rc = json.loads(line)
            ym = rc["d"][:6]
            if ym != cur_ym:
                cur_ym = ym
                p = os.path.join(AUX, f"{ym}.json")
                aux = json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {}
            amap = aux.get(rc["rid"]) or {}
            hs = [h for h in rc["h"] if h.get("rk") is not None and h.get("pop")]
            if len(hs) < 6:
                continue
            nrace += 1
            fb = fbucket(len(hs))
            dist = rc.get("dist")
            tc = rc.get("tc")

            # レース内の先行馬の数（C群）
            senko = sum(1 for h in hs if h.get("fpf") is not None and h["fpf"] <= 0.35)

            after = []
            for h in hs:
                base = expected(h["pop"], fb)
                if base is None:
                    continue
                resid = (1 if h["rk"] <= 3 else 0) - base
                a = amap.get(str(h["n"])) or [None, None, None, None]
                key = a[3] and (a[0] or "") and None   # 馬名は無いので騎手等で代用
                # ★馬名がデータに無い★ 個体の履歴が要る候補（1〜12など）は
                #   このデータセットでは作れない。ここでは作れるものだけ測る。

                def put(name, grp):
                    if grp is None:
                        return
                    e = agg[name][grp]
                    e[0] += 1
                    e[1] += resid
                    e[2] += resid * resid

                # --- C群: ペース・展開（今あるデータだけで作れる） ---
                put("28 先行馬の数", ("0頭" if senko == 0 else "1頭" if senko == 1
                                    else "2〜3頭" if senko <= 3 else "4頭以上"))
                if h.get("fpf") is not None:
                    faster = sum(1 for o in hs if o.get("fpf") is not None
                                 and o["fpf"] < h["fpf"])
                    put("29 自分より先行力が上の頭数",
                        ("0頭" if faster == 0 else "1頭" if faster == 1
                         else "2〜3頭" if faster <= 3 else "4頭以上"))
                    put("30 単騎逃げ候補",
                        "単騎候補" if (h["fpf"] <= 0.25 and senko == 1) else "それ以外")
                    if h.get("wk"):
                        inner = h["wk"] <= 3
                        fast = h["fpf"] <= 0.35
                        put("32 枠×脚質",
                            ("内枠×先行" if inner and fast else
                             "内枠×差し" if inner else
                             "外枠×先行" if fast else "外枠×差し"))
                    put("33 頭数×脚質", fb + ("×先行" if h["fpf"] <= 0.35 else "×差し"))
                    if dist:
                        dl = "短" if dist < 1400 else ("中" if dist < 1800 else "長")
                        put("34 距離×脚質", dl + ("×先行" if h["fpf"] <= 0.35 else "×差し"))
                if h.get("lpf") is not None and h.get("bpf") is not None:
                    put("36 先行度のばらつき",
                        sign_bucket(h["lpf"] - h["bpf"], 0.05, 0.20,
                                    ["安定", "やや変動", "大きく変動"]))
                    put("37 前走で後方だった馬",
                        "前走かなり後方" if h["lpf"] >= 0.8 else "それ以外")

                # --- 今あるスカラー列（既存因子の再確認も兼ねる） ---
                if h.get("wt"):
                    order = sorted([x for x in hs if x.get("wt")], key=lambda x: -x["wt"])
                    if len(order) >= 6:
                        i = order.index(h)
                        k = len(order)
                        put("6 馬体重のレース内順位",
                            "重い1/3" if i < k / 3 else ("中位" if i < 2 * k / 3 else "軽い1/3"))
                if h.get("wd") is not None:
                    put("8 馬体重増減",
                        ("-10kg以下" if h["wd"] <= -10 else "-9〜-1" if h["wd"] < 0
                         else "増減なし" if h["wd"] == 0 else "+1〜+9" if h["wd"] < 10
                         else "+10kg以上"))
                if h.get("age"):
                    put("9 馬齢", f'{h["age"]}歳' if h["age"] <= 7 else "8歳以上")
                if h.get("np"):
                    put("10 近走データ数", f'{min(h["np"],3)}走ぶん')
                if h.get("ar") is not None:
                    put("12 近走平均着順",
                        ("1〜3着平均" if h["ar"] < 3.5 else "3.5〜5.5" if h["ar"] < 5.5
                         else "5.5〜8" if h["ar"] < 8 else "8着より下"))
                if h.get("wk"):
                    put("32b 枠", f'{h["wk"]}枠')

                # --- ★2026-07-29追加：履歴系の新列（P2）★ ---
                # これらは build_dataset.py で新設した、モデルが持っていない情報。
                if h.get("rest") is not None:
                    put("1 前走からの間隔", bucket_days(h["rest"]))
                    put("2 連闘(9日以内)", "連闘" if h["rest"] <= 9 else "それ以外")
                if h.get("dchg") is not None:
                    put("16 距離変化", bucket_dist_change(h["dchg"]))
                if h.get("tchg") is not None:
                    put("20 場替わり", "場替わり" if h["tchg"] else "同場")
                if h.get("prk") is not None:
                    put("77a 前走着順",
                        ("前走1着" if h["prk"] == 1 else "前走2-3着" if h["prk"] <= 3
                         else "前走4-6着" if h["prk"] <= 6 else "前走7着以下"))
                if h.get("ppop") is not None:
                    put("77b 前走人気",
                        ("前走1人気" if h["ppop"] == 1 else "前走2-3人気" if h["ppop"] <= 3
                         else "前走4-6人気" if h["ppop"] <= 6 else "前走7人気以下"))
                if h.get("pmiss") is not None:
                    put("77c 前走の裏切り度(着順-人気)",
                        ("大幅に好走(-3以下)" if h["pmiss"] <= -3
                         else "やや好走(-2〜-1)" if h["pmiss"] < 0
                         else "人気どおり(0)" if h["pmiss"] == 0
                         else "やや裏切り(1〜2)" if h["pmiss"] <= 2 else "大幅裏切り(3+)"))
                if h.get("trend") is not None:
                    put("12b 着順トレンド",
                        ("急上昇(+3超)" if h["trend"] > 3 else "上向き(+1〜3)" if h["trend"] > 1
                         else "横ばい" if h["trend"] >= -1
                         else "下向き(-1〜-3)" if h["trend"] >= -3 else "急降下(-3未満)"))
                if h.get("vrank") is not None:
                    put("11 着順の振れ幅",
                        ("安定(〜2)" if h["vrank"] <= 2 else "普通(3〜5)" if h["vrank"] <= 5
                         else "気分屋(6〜9)" if h["vrank"] <= 9 else "極端(10+)"))
                if h.get("cn") is not None:
                    put("10b 通算出走数",
                        ("〜5走" if h["cn"] <= 5 else "6〜15走" if h["cn"] <= 15
                         else "16〜40走" if h["cn"] <= 40 else "41走以上"))
                if h.get("ct3") is not None:
                    put("77d 通算複勝率",
                        ("〜15%" if h["ct3"] < 0.15 else "15〜30%" if h["ct3"] < 0.30
                         else "30〜50%" if h["ct3"] < 0.50 else "50%以上"))
                if h.get("wma") is not None:
                    put("7 体重の自己平均比",
                        ("-10kg以下" if h["wma"] <= -10 else "-9〜-4" if h["wma"] <= -4
                         else "±3" if h["wma"] < 4 else "+4〜+9" if h["wma"] < 10
                         else "+10kg以上"))
                if h.get("swin") is not None:
                    put("77e 勝ってからの走数",
                        ("前走勝ち(0)" if h["swin"] == 0 else "1〜3走" if h["swin"] <= 3
                         else "4〜10走" if h["swin"] <= 10 else "11走以上"))

                # --- ★2026-07-30追加：第2弾の5列★ ---
                if h.get("jkchg") is not None:
                    put("47 乗り替わり", "乗り替わり" if h["jkchg"] else "継続騎乗")
                if h.get("pgap") is not None:
                    put("13 前走の着差",
                        ("僅差(1馬身以内)" if h["pgap"] <= 1 else
                         "2〜3馬身" if h["pgap"] <= 3 else
                         "4〜9馬身" if h["pgap"] < 10 else "大差負け"))
                if h.get("restdev") is not None:
                    put("5 間隔の自分基準ズレ",
                        ("いつもより早い(-7日超)" if h["restdev"] < -7 else
                         "ほぼ普段どおり(±7日)" if h["restdev"] <= 7 else
                         "やや延びた(8〜30日)" if h["restdev"] <= 30 else "大きく延びた"))
                if h.get("clvchg") is not None:
                    put("83 クラス昇降",
                        ("昇級" if h["clvchg"] > 0 else "降級" if h["clvchg"] < 0 else "同級"))
                if h.get("sqr") is not None:
                    put("15 季節適性(同四半期の複勝率)",
                        ("〜15%" if h["sqr"] < 0.15 else "15〜30%" if h["sqr"] < 0.30
                         else "30〜50%" if h["sqr"] < 0.50 else "50%以上"))

                # --- 騎手・調教師・血統（期待薄だが確認のため） ---
                if a[0]:
                    put("43 騎手（上位20人のみ）", a[0])
                if a[1]:
                    put("55 調教師（上位20人のみ）", a[1])
                if a[2]:
                    put("63 種牡馬（上位20頭のみ）", a[2])

                after.append(h)

            # 履歴更新はレース処理の後（このデータセットには馬名が無いので現状は未使用）
            del after

    print(f"  {nrace:,}レース\n", flush=True)

    # --- 判定 ---
    rows = []
    for name, groups in agg.items():
        gs = []
        for g, (n, s, s2) in groups.items():
            if n < MIN_N:
                continue
            mean = s / n
            var = max(s2 / n - mean * mean, 1e-12)
            se = math.sqrt(var / n)
            gs.append({"group": g, "n": n, "resid": 100 * mean, "z": mean / se})
        if len(gs) < 2:
            continue
        gs.sort(key=lambda x: -x["z"])
        # 群の中で最も強い（絶対値の大きい）zを、その特徴量の代表値にする
        top = max(gs, key=lambda x: abs(x["z"]))
        rows.append({"feature": name, "groups": gs[:20],
                     "best_group": top["group"], "best_z": top["z"],
                     "best_resid": top["resid"],
                     "spread": gs[0]["resid"] - gs[-1]["resid"],
                     "pass": abs(top["z"]) >= Z_GATE})
    rows.sort(key=lambda r: -abs(r["best_z"]))

    print(f'{"候補":30s}{"最強の群":22s}{"残差":>8s}{"z":>8s}{"群内の開き":>10s}  判定')
    print("-" * 88)
    for r in rows:
        print(f'{r["feature"]:30s}{str(r["best_group"])[:20]:22s}'
              f'{r["best_resid"]:+7.1f}%{r["best_z"]:+8.1f}{r["spread"]:9.1f}pt  '
              + ("★通過" if r["pass"] else "—"))

    json.dump({"races": nrace, "min_n": MIN_N, "z_gate": Z_GATE,
               "n_tests": N_TESTS, "rows": rows},
              open(OUT, "w", encoding="utf-8", newline="\n"),
              ensure_ascii=False, indent=1)
    npass = sum(1 for r in rows if r["pass"])
    print(f"\n通過 {npass} / {len(rows)}（|z| >= {Z_GATE}：102回試す前提のボンフェローニ補正）")
    print(f"出力: {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
