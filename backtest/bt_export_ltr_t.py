# -*- coding: utf-8 -*-
"""時計つきモデル（mv 2.3・地方）を JS 用に書き出す。

入力: backtest/ltr_model_t.txt（順位学習43列）/ backtest/ltr_res_model_t.txt（補助43列）
出力: core/ltr_model_t.js（LTR_MODEL に narT / narTR を足す。core/ltr_model.js の後に読み込む）
★core/ltr_model.js は作り直さない★ 中に入っている narM / jraM の元ファイルがリポに無く、作り直すと消えるため。
使い方: python3 backtest/bt_export_ltr_t.py
"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from bt_export_ltr import load_model

OUT = os.path.join(ROOT, "core", "ltr_model_t.js")


def main():
    t = load_model(os.path.join(HERE, "ltr_model_t.txt"))
    r = load_model(os.path.join(HERE, "ltr_res_model_t.txt"))
    if not t or not r:
        print("モデルが無い（先に bt_time_feats.py final backtest）"); return 1
    if t["feats"] != r["feats"]:
        print("!! 順位学習と補助モデルの列が一致しない。中止"); return 1
    body = json.dumps({"narT": t, "narTR": r}, separators=(",", ":"), ensure_ascii=False)
    js = (
        "/* 自動生成（backtest/bt_export_ltr_t.py）。手で編集しない。\n"
        " * 時計つきモデル（mv 2.3・地方）。narT=順位学習43列 / narTR=補助43列。\n"
        " * ltrScoreT(f, 'narT'|'narTR')。木のたどり方は core/ltr_model.js の ltrScore と同じ。 */\n"
        "(function (root) {\n"
        "  var M = " + body + ";\n"
        "  function ltrScoreT(f, key) {\n"
        "    var m = M[key]; if (!m) return null;\n"
        "    var F = m.feats, trees = m.trees, s = 0;\n"
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
        "  var api = { LTR_MODEL_T: M, ltrScoreT: ltrScoreT };\n"
        "  if (typeof module !== 'undefined' && module.exports) module.exports = api;\n"
        "  else { root.LTR_MODEL_T = M; root.ltrScoreT = ltrScoreT; }\n"
        "})(typeof globalThis !== 'undefined' ? globalThis : this);\n"
    )
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(js)
    print(f"出力: {os.path.relpath(OUT, ROOT)} 順位学習{len(t['trees'])}本 / 補助{len(r['trees'])}本 / {len(t['feats'])}列 / {os.path.getsize(OUT)/1024:.0f}KB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
