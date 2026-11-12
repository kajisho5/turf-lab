# -*- coding: utf-8 -*-
"""★ハロンタイム（ラップ）索引を作る★（2026-08-04・未活用データの発掘）

なぜ:
  docs/DATA_SOURCES.md に「ハロンタイム1-15（ペース質の分析用・**未活用**）」とある。
  精度を上げる道は「新しいデータ」しか残っていない（research_log.md）ので、
  手元にあって使っていないデータをまず棚から下ろす。

実測したカバレッジ（2013-2026）:
  収録は南関4場（大井・川崎・浦和・船橋）と園田のみ。他場は全欠損。
  全期間で安定して 21-22%（44,079R / 202,599R）。★欠損は「場」で決まる★ので、
  検証は収録場だけを分母にすること（全場で混ぜると場の差を因子の効果と誤認する）。

出力: backtest/nardata/lap_index.json  { rid: [ハロンタイム(秒)...] }
使い方: python backtest/build_lap_index.py
"""
import csv
import glob
import io
import json
import os
import re
import sys
import zipfile

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NARD = os.path.join(ROOT, "backtest", "nardata")
OUT = os.path.join(NARD, "lap_index.json")
TRACK_CODE = {'門別': '30', '盛岡': '35', '水沢': '36', '浦和': '42', '船橋': '43',
              '大井': '44', '川崎': '45', '金沢': '46', '笠松': '47', '名古屋': '48',
              '園田': '50', '姫路': '51', '高知': '54', '佐賀': '55', '帯広ば': '65'}


def main():
    out = {}
    files = sorted(glob.glob(os.path.join(NARD, "race_*.zip")))
    for i, zp in enumerate(files, 1):
        try:
            z = zipfile.ZipFile(zp)
        except zipfile.BadZipFile:
            continue
        for name in z.namelist():
            if not name.endswith("_racelist.csv"):
                continue
            text = z.read(name).decode("utf-8-sig", errors="replace")
            for r in list(csv.reader(io.StringIO(text)))[1:]:
                if len(r) < 50 or not r[1].isdigit():
                    continue
                laps = []
                for x in r[35:50]:
                    x = x.strip()
                    if not x:
                        break              # 途中で切れたらそこまで（末尾の空欄は無効値）
                    try:
                        laps.append(float(x))
                    except ValueError:
                        break
                if len(laps) < 3:
                    continue               # 3ハロン未満は使い道が無い
                tc = TRACK_CODE.get(r[0])
                if not tc:
                    continue
                rid = f"{r[1][:4]}{tc}{r[1][4:]}{int(r[2]):02d}"
                out[rid] = laps
        if i % 40 == 0:
            print(f"  {i}/{len(files)}  {len(out):,}レース")
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        json.dump(out, f, separators=(",", ":"))
    mb = os.path.getsize(OUT) / 1024 / 1024
    tcs = {}
    for rid in out:
        tcs[rid[4:6]] = tcs.get(rid[4:6], 0) + 1
    print(f"出力: {os.path.relpath(OUT, ROOT)}  {len(out):,}レース ({mb:.1f}MB)")
    print("場コード別:", dict(sorted(tcs.items(), key=lambda kv: -kv[1])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
