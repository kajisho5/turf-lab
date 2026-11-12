# -*- coding: utf-8 -*-
"""学習済み LTR（LightGBM ranker）を JS 推論用の入れ子配列に変換する。

入力 : backtest/ltr_model.txt（bt_train_ltr.py が出力）
出力 : core/ltr_model.js（window.LTR_MODEL ＋ ltrScore()。Node と ブラウザ両対応）

木の形式（GBM本体 core/scoring.js と揃える）:
  分岐ノード = [featIdx, threshold, defaultLeft(0/1), 左, 右]
  葉        = [value]
  走査      : v = f[feats[idx]]; 欠損なら defaultLeft 方向、そうでなければ v<=threshold で左。
  スコア    = 全木の葉値の合計（ranker の raw 予測＝そのまま順位付けに使える）
"""
import json
import os
import sys

import lightgbm as lgb

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_NAR = os.path.join(ROOT, "backtest", "ltr_model.txt")
SRC_JRA = os.path.join(ROOT, "backtest", "ltr_model_jra.txt")
# ★2026-07-30: LINE配信用の市場込みモデル（pop入り34列）★
#   発走5分前にオッズを見て採点する別プロダクト用。
#   ★tweet.htmlの事前予想には絶対に使わない★（narM = market の M）
SRC_MKT = os.path.join(ROOT, "backtest", "exp_market.txt")
# ★中央版（2026-07-31）★ 中央は土日だけ開催なので、LINE配信は地方と別タブで回す。
SRC_MKT_JRA = os.path.join(ROOT, "backtest", "exp_jra_market.txt")
# ★C12（2026-09-27採用・地方のみ）★ 「市場を学習時だけの先生にする」補助回帰モデル。
#   目的変数 = 3着内 − E[3着内 | 人気(12打切), 頭数帯]（人気は学習ラベル作成にだけ使用）。
#   推論は地方LTRと同じ事前33列だけ＝オッズ前に出せる。
#   本番の◎ = レース内z化して z(nar) + 2.0·z(narR) の最大。検証: docs/FACTS.md / research_log.md
SRC_RES = os.path.join(ROOT, "backtest", "ltr_res_model.txt")
OUT = os.path.join(ROOT, "core", "ltr_model.js")

# ★特徴量リストはモデル自身から取る★
#   以前はここに手書きのFEATSがあり、学習側と食い違うと壊れた。
#   さらに地方（事前専用24列）と中央（旧16列）で構成が違うため、
#   1本のリストでは表せない。dump_model の feature_names を正とする。

def conv(node):
    """LightGBM dump_model の 1ノード → 入れ子配列。"""
    if "leaf_value" in node:
        # 葉値も丸めない（400本の合計で誤差が2e-5まで積み上がった）
        return [float(node["leaf_value"])]
    # ★閾値を丸めてはいけない★
    #   LightGBMは整数特徴を 2.9999999999999996 のような閾値で割る。
    #   6桁に丸めると 3.0 になり、値がちょうど3の馬が反対側の枝に落ちる。
    #   実際、履歴系（rest/prk/cn等の整数列）を足した途端に
    #   Python と JS の予測が 1501ケース中981件ズレた（最大差0.133）。
    # ★カテゴリ分岐（場コードtc等）★ decision_type=="==" で
    #   threshold が '42||43||44' 形式。値が集合に入っていれば左。
    #   JS側は「閾値が配列ならカテゴリ」で見分ける。
    if node.get("decision_type") == "==":
        thr = [int(float(x)) for x in str(node["threshold"]).split("||")]
    else:
        thr = float(node["threshold"])
    return [
        int(node["split_feature"]),
        thr,
        1 if node.get("default_left") else 0,
        conv(node["left_child"]),
        conv(node["right_child"]),
    ]


def load_model(src):
    """モデル1本 → {feats, trees}。特徴量リストはモデル自身から取る。"""
    if not os.path.exists(src):
        return None
    dump = lgb.Booster(model_file=src).dump_model()
    return {"feats": dump.get("feature_names") or [],
            "trees": [conv(t["tree_structure"]) for t in dump["tree_info"]]}


def main():
    nar = load_model(SRC_NAR)
    jra = load_model(SRC_JRA)
    if not nar:
        print(f"地方モデルが無い: {SRC_NAR}（先に bt_train_ltr.py）")
        return 1
    # ★モードごとに特徴量リストを分けて持つ★
    #   地方=事前専用24列（wt/wd/wma/goingは当日情報なので学習から除外済み）
    #   中央=旧16列（bt_jra.jsonl 未拡張のため。要対応）
    payload = {"nar": nar}
    if jra:
        payload["jra"] = jra
    mkt = load_model(SRC_MKT)
    if mkt:
        payload["narM"] = mkt
    mkt_jra = load_model(SRC_MKT_JRA)
    if mkt_jra:
        payload["jraM"] = mkt_jra
    res = load_model(SRC_RES)
    if res:
        # 補助モデルの列はLTRと完全一致が前提（違えば本番で黙って欠損推論になる）
        if res["feats"] != nar["feats"]:
            print("!! 補助モデル(narR)の特徴量が地方LTRと一致しない。書き出しを中止")
            return 1
        payload["narR"] = res
    body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)

    js = (
        "/* 自動生成（backtest/bt_export_ltr.py）。手で編集しない。\n"
        " * LTR = Learning to Rank（LambdaMART）。全頭の着順を直接学習した順位モデル。\n"
        " * nar=地方（事前専用: 当日情報 wt/wd/馬場 を使わない）/ jra=中央。\n"
        " * モードごとに特徴量リストを持つ。ltrScore(f, mode) で切替（既定 'nar'）。 */\n"
        "(function (root) {\n"
        "  var LTR_MODEL = " + body + ";\n"
        "  function ltrScore(f, mode) {\n"
        "    var m = (mode === 'jra' && LTR_MODEL.jra) ? LTR_MODEL.jra\n"
        "          : (mode === 'narR' && LTR_MODEL.narR) ? LTR_MODEL.narR : LTR_MODEL.nar;\n"
        "    if (mode === 'narR' && !LTR_MODEL.narR) return null;   // 補助が無ければC12を使わない\n"
        "    var F = m.feats, trees = m.trees;\n"
        "    var s = 0;\n"
        "    for (var i = 0; i < trees.length; i++) {\n"
        "      var n = trees[i];\n"
        "      while (n.length > 1) {\n"
        "        var v = f[F[n[0]]];\n"
        "        var miss = (v === null || v === undefined || v !== v);\n"
        "        var goLeft;\n"
        "        if (miss) goLeft = (n[2] === 1);\n"
        "        else if (n[1] instanceof Array) goLeft = n[1].indexOf(Math.round(+v)) >= 0;\n"
        "        else goLeft = (+v <= n[1]);\n"
        "        n = goLeft ? n[3] : n[4];\n"
        "      }\n"
        "      s += n[0];\n"
        "    }\n"
        "    return s;\n"
        "  }\n"
        "  var api = { LTR_MODEL: LTR_MODEL, ltrScore: ltrScore };\n"
        "  if (typeof module !== 'undefined' && module.exports) module.exports = api;\n"
        "  else { root.LTR_MODEL = LTR_MODEL; root.ltrScore = ltrScore; }\n"
        "})(typeof globalThis !== 'undefined' ? globalThis : this);\n"
    )
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(js)
    kb = os.path.getsize(OUT) / 1024
    print(f"出力: {os.path.relpath(OUT, ROOT)}  "
          f"地方{len(nar['trees'])}本({len(nar['feats'])}列) / "
          f"中央{len(jra['trees']) if jra else 0}本 / "
          f"市場込み{len(mkt['trees']) if mkt else 0}本({len(mkt['feats']) if mkt else 0}列)  {kb:.0f}KB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
