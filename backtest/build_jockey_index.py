# -*- coding: utf-8 -*-
"""騎手の事前複勝率の索引を作る（tweet.html / race.html がLTRのjkr列に使う）

★なぜ要るか★
  jkr（騎手の通算複勝率）は2026-07-30に採用した列。実測で
  地方 66.6→67.8%（+1.27pt / 95%CI [+0.97,+1.55]・14場全部プラス）、
  中央 56.1→58.3%（+2.2pt・重要度1位）。
  ブラウザ側は出馬表の騎手名しか持たないので、名前→複勝率の辞書を配る。

★学習時との一致★
  学習は「そのレースより前の騎乗だけ」で作ったローリング値（リークなし）。
  配布用は**最新時点の累積値**になる（未来のレースを予想するので、
  最新までの成績を使うのは正しい＝リークではない）。
  50騎乗未満は学習時と同じく欠損にする（率が暴れるため）。

★名前の正規化★
  netkeibaは「◇」「☆」「▲」「△」などの見習マークや空白を騎手名に付ける。
  keiba.go.jp/JV-Data側は付かないので、両方から取り除いて突き合わせる。

出力:
  deploy/data/jockeys.json      地方 {"騎手名":[複勝率%, 騎乗数]}
  deploy/data/jra_jockeys.json  中央 同形式
使い方: python backtest/build_jockey_index.py
"""
import collections
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MIN_RIDES = 50          # ★bt_train_ltr.py / build_*_dataset.py と必ず揃える★

JOBS = [
    ("nar", os.path.join(ROOT, "backtest", "nardata", "bt_all.jsonl"),
     os.path.join(ROOT, "deploy", "data", "jockeys.json"), ".jockeys"),
    ("jra", os.path.join(ROOT, "backtest", "nardata", "bt_jra.jsonl"),
     os.path.join(ROOT, "deploy", "data", "jra_jockeys.json"), ".jockeys"),
    # ★2026-07-30 調教師も採用（16券種中14でROIプラス）★
    ("nar厩", os.path.join(ROOT, "backtest", "nardata", "bt_all.jsonl"),
     os.path.join(ROOT, "deploy", "data", "trainers.json"), ".trainers"),
    ("jra厩", os.path.join(ROOT, "backtest", "nardata", "bt_jra.jsonl"),
     os.path.join(ROOT, "deploy", "data", "jra_trainers.json"), ".trainers"),
    # 血統（父・母父）。地方のみ（中央のSEレコードに父馬名が無い）
    ("nar父", os.path.join(ROOT, "backtest", "nardata", "bt_all.jsonl"),
     os.path.join(ROOT, "deploy", "data", "sires.json"), ".sires"),
    # ★母父は却下★ 公式データの母父名は18.1%が英字表記でnetkeibaのカナと
    # 突き合わせられず、本番で18%欠損する。モデルからも外した（LTR_NODMS）。
    # 索引を配ると「使えると誤解して配線される」ので生成しない。
]

_MARK = re.compile(r"[▲△☆★◇◎<>\s　]")


def norm(s):
    return _MARK.sub("", str(s or ""))


def main():
    # bt_*.jsonl には騎手名の列が無い（jkrの値だけ）。
    # 名前を持っているのは元データなので、ここでは
    # 「jkrの値と騎乗数」を復元できない。→ 元データから作り直す必要がある。
    # ただし jkchg 用に history へ騎手名を積んでいるので、
    # データセット生成と同じ手順を踏む代わりに、
    # build_dataset.py / build_jra_dataset.py が書き出した集計を使う。
    for mode, src, out, suffix in JOBS:
        agg = collections.defaultdict(lambda: [0, 0])
        path = src + suffix              # 各builderが書き出すサイドカー
        if not os.path.exists(path):
            print(f"  [{mode}] サイドカーが無い: {os.path.basename(path)}"
                  f" → builderを再実行して作る必要がある")
            continue
        with open(path, encoding="utf-8") as f:
            for line in f:
                try:
                    nm, n, t3 = json.loads(line)
                except (json.JSONDecodeError, ValueError):
                    continue
                a = agg[norm(nm)]
                a[0] += n
                a[1] += t3
        idx = {nm: [round(100.0 * a[1] / a[0], 1), a[0]]
               for nm, a in agg.items() if a[0] >= MIN_RIDES}
        os.makedirs(os.path.dirname(out), exist_ok=True)
        tmp = out + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(idx, f, ensure_ascii=False, separators=(",", ":"))
        os.replace(tmp, out)
        kb = os.path.getsize(out) / 1024
        top = sorted(idx.items(), key=lambda x: -x[1][0])[:5]
        print(f"  [{mode}] {len(idx):,}人  {kb:.0f}KB → {os.path.relpath(out, ROOT)}")
        print("     上位: " + " / ".join(f"{k} {v[0]}%({v[1]}騎乗)" for k, v in top))


if __name__ == "__main__":
    main()
