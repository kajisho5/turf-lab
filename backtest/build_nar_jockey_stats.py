# -*- coding: utf-8 -*-
"""地方(NAR)騎手の成績テーブルを、公式データ(keiba.go.jp)から騎手名キーで作る

★なぜ要るか★
  本番の JOCKEY_STATS は netkeiba の騎手ID をキーにしている（206人・
  db.netkeiba の個別ページから収集）。ところが地方の騎手は netkeiba 側で
  **jockeyId が "00000"** になることが多く、テーブルを引けない。
  実測（races_cache.jsonl 72,706頭）:

      jockeyId=00000 : 32.3%   ← 加点が一切入らない
      jockeyId=null  :  1.0%
      正常           : 66.8%

  騎手成績factorは実測で効いている（NAR 7,080レースのA/Bで
  複勝率 66.34% → 64.92%、+1.42pt）。それを3頭に1頭へ適用できていない。
  しかも「レース内で一部の馬だけ加点される」ため、情報が無いのではなく
  **systematicに不利**になる（2026-07-27 盛岡1Rで、岩手リーディングの
  山本聡哉が加点0のまま1番人気になっていたのが発覚のきっかけ）。

★騎手名で突き合わせる★
  netkeiba も公式も騎手名を略すが、略し方が違う:
      公式    : 必ず3文字 = 姓の先頭2文字 + 名の先頭1文字（山本聡哉→山本聡）
      netkeiba: 2文字姓なら姓+名1文字（山本聡）、3文字姓なら姓のみ（佐々木）
  よって**2文字姓は完全一致し、3文字姓は一致しない**。
  実測カバー率 90.3%（65,052/72,006頭）。

  ★誤マッチは構造的に起きない★ netkeibaの「佐々木」は公式の
  「佐々志」「佐々世」のどちらとも文字列が違うので、別人の成績が
  紛れ込むことはない（一致しない＝従来通り加点なしに落ちるだけ）。
  3文字姓は netkeiba 側の表示が原理的に曖昧（佐々木志超と佐々木世麗が
  どちらも「佐々木」）なので、名前だけでの解決は諦める。

★リーク防止★
  --until で集計期間の終わりを切る。検証キャッシュ(races_cache.jsonl)は
  2026-02-01〜2026-07-20 なので、既定は 202602 未満だけを集計する。

出力: backtest/nar_jockey_stats.json   { "山本聡": [複勝率%, 騎乗数], ... }
使い方: python backtest/build_nar_jockey_stats.py [--from 202402] [--until 202602]
"""
import argparse
import collections
import csv
import glob
import io
import json
import os
import re
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NARD = os.path.join(ROOT, "backtest", "nardata")
OUT = os.path.join(ROOT, "backtest", "nar_jockey_stats.json")

MIN_RIDES = 30   # 本番の scoring と同じ足切り（サンプル不足の誤作動防止）


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="ym_from", default="202402")
    ap.add_argument("--until", dest="ym_until", default="202602",
                    help="この年月は含めない（検証期間へのリークを防ぐ）")
    a = ap.parse_args()

    stat = collections.defaultdict(lambda: [0, 0])   # name -> [rides, top3]
    months = 0
    for zp in sorted(glob.glob(os.path.join(NARD, "race_*.zip"))):
        m = re.search(r"race_(\d{6})\.zip$", os.path.basename(zp))
        if not m:
            continue
        ym = m.group(1)
        if not (a.ym_from <= ym < a.ym_until):
            continue
        try:
            z = zipfile.ZipFile(zp)
        except Exception:
            continue
        hl = [n for n in z.namelist() if n.endswith("_horselist.csv")]
        if not hl:
            continue
        rows = list(csv.reader(io.StringIO(
            z.read(hl[0]).decode("utf-8-sig", "replace"))))
        for r in rows[1:]:
            if len(r) < 36:
                continue
            # ★帯広(ばんえい)は平地と別競技★ 同じ騎手の腕として混ぜない
            if r[0] == "帯広ば":
                continue
            jk = (r[14] or "").strip()
            if not jk:
                continue
            rank = r[31].strip()
            if not rank.isdigit():
                continue          # 取消・除外は分母に入れない
            s = stat[jk]
            s[0] += 1
            if int(rank) <= 3:
                s[1] += 1
        months += 1

    table = {}
    for jk, (rides, top3) in stat.items():
        if rides < MIN_RIDES:
            continue
        table[jk] = [round(100.0 * top3 / rides, 1), rides]

    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        json.dump(table, f, ensure_ascii=False, sort_keys=True)
    print(f"集計 {months}ヶ月分（{a.ym_from} 〜 {a.ym_until} 未満）")
    print(f"騎手 {len(stat):,}人 → {MIN_RIDES}騎乗以上に絞って {len(table):,}人")
    print(f"出力: {os.path.relpath(OUT, ROOT)}")
    top = sorted(table.items(), key=lambda kv: -kv[1][0])[:5]
    print("複勝率上位: " + " / ".join(f"{k} {v[0]}%({v[1]})" for k, v in top))
    return 0


if __name__ == "__main__":
    sys.exit(main())
