# -*- coding: utf-8 -*-
"""★答え合わせの自動化★ 公式ZIPの確定結果を results.php に自動保存する（地方）

なぜ要るか（2026-08-04発覚）:
  結果保存はこれまで「ユーザーがtweet.htmlで答え合わせした時」だけだった。
  8/3は46レース予想したのに結果保存は5件。配車係シャドー・プラシーボ・週間成績画像は
  全部 results.php を読むので、答え合わせをサボった日はデータが穴になる。
  keiba.go.jp公式ZIP（毎朝4:30のデータ収集で取得済み）から同じ形で自動保存する。

守ること:
  - ★既存の保存は上書きしない★（答え合わせ由来の保存が正。predictions同様のnoclobber）
  - 保存する形は tweet.html の答え合わせ保存と完全に同一（results.php の実レコードを写した）
  - 予想が存在するレースだけ保存する（全レースを積むとサーバーの120日キャッシュを汚す）

使い方: python backtest/push_results.py [日数(既定4)]
実行: daily.py（データ収集の後）
"""
import csv
import io
import json
import sys
import urllib.request
import zipfile
import glob
import os
from datetime import datetime, timedelta, timezone

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NARD = os.path.join(ROOT, "backtest", "nardata")
BASE = "https://seventh-well.com/odds"
JST = timezone(timedelta(hours=9))
TRACK_CODE = {'門別': '30', '盛岡': '35', '水沢': '36', '浦和': '42', '船橋': '43',
              '大井': '44', '川崎': '45', '金沢': '46', '笠松': '47', '名古屋': '48',
              '園田': '50', '姫路': '51', '高知': '54', '佐賀': '55', '帯広ば': '65'}


def get(url):
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def post(url, obj):
    req = urllib.request.Request(url, json.dumps(obj, ensure_ascii=False).encode("utf-8"),
                                 {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def read_zip_csv(z, suffix):
    for name in z.namelist():
        if name.endswith(suffix):
            for row in csv.reader(io.StringIO(z.read(name).decode("utf-8-sig", errors="replace"))):
                yield row


def sval(row, i):
    return row[i].strip() if i < len(row) and row[i].strip() else None


def build_from_zips(months):
    """月ZIP → rid -> レコード（tweet.htmlの答え合わせ保存と同じ形・at無し）"""
    horses, races, pays = {}, {}, {}
    for ym in months:
        zp = os.path.join(NARD, f"race_{ym}.zip")
        if not os.path.exists(zp):
            continue
        z = zipfile.ZipFile(zp)
        for r in read_zip_csv(z, "_horselist.csv"):
            tc = TRACK_CODE.get(r[0]) if r else None
            if not tc or len(r) < 36 or not r[1].isdigit():
                continue
            rid = f"{r[1][:4]}{tc}{r[1][4:]}{int(r[2]):02d}"
            rk = r[31].strip()
            if not rk.isdigit():
                continue          # 取消・除外・競走中止コードは着順に入れない
            pop = r[35].strip()
            horses.setdefault(rid, []).append({
                "num": str(int(r[5])), "rank": int(rk), "name": r[6].strip(),
                "jockey": r[14].strip() or None,
                "pop": int(pop) if pop.isdigit() else None,
                "waku": int(r[3]) if r[3].strip().isdigit() else None})
        for r in read_zip_csv(z, "_racelist.csv"):
            tc = TRACK_CODE.get(r[0]) if r else None
            if not tc or len(r) < 28 or not r[1].isdigit():
                continue
            rid = f"{r[1][:4]}{tc}{r[1][4:]}{int(r[2]):02d}"
            surf = (r[21] or "").strip()
            races[rid] = {"raceName": (sval(r, 5) or sval(r, 4) or ""),
                          "surface": "芝" if "芝" in surf else "ダ",
                          "dist": int(r[23]) if r[23].strip().isdigit() else None,
                          "date": r[1]}
        for r in read_zip_csv(z, "_payback.csv"):
            tc = TRACK_CODE.get(r[0]) if r else None
            if not tc or len(r) < 54 or not r[1].isdigit():
                continue
            rid = f"{r[1][:4]}{tc}{r[1][4:]}{int(r[2]):02d}"
            def one(nums_idx, yen_idx, sort=True):
                nums = [str(int(r[i])) for i in nums_idx if sval(r, i) and r[i].strip().isdigit()]
                yen = sval(r, yen_idx)
                if len(nums) != len(nums_idx) or not yen or not yen.isdigit():
                    return None
                if sort:
                    nums.sort(key=int)
                return {"nums": nums, "yen": int(yen)}
            p = {"tansho": [one([4], 5)],
                 "fukusho": [one([7], 8), one([10], 11), one([13], 14)],
                 "umaren": [one([24, 25], 26)],
                 "umatan": [one([28, 29], 30, sort=False)],
                 "wide": [one([32, 33], 34), one([36, 37], 38), one([40, 41], 42)],
                 "fuku3": [one([44, 45, 46], 47)],
                 "tan3": [one([49, 50, 51], 52, sort=False)]}
            pays[rid] = {k: [x for x in v if x] for k, v in p.items()}
    out = {}
    for rid, hs in horses.items():
        if rid not in pays or not pays[rid].get("fukusho"):
            continue
        meta = races.get(rid) or {}
        out[rid] = {
            "race_id": rid,
            "ranks": {h["num"]: h["rank"] for h in hs},
            "finishers": sorted(hs, key=lambda h: h["rank"]),
            "pays": pays[rid],
            "raceName": meta.get("raceName", ""),
            "surface": meta.get("surface", "ダ"),
            "dist": meta.get("dist"),
            "date": meta.get("date", rid[:4] + rid[6:10]),
            "mode": "nar",
            "auto": True,          # 答え合わせ由来と区別できるように印を付けておく
        }
    return out


def main():
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 4
    today = datetime.now(JST)
    dates = [(today - timedelta(days=i)).strftime("%Y%m%d") for i in range(1, days + 1)]
    months = sorted({d[:6] for d in dates})
    built = build_from_zips(months)

    pushed = kept = nores = 0
    for d in dates:
        try:
            pj = get(f"{BASE}/predictions.php?action=list&date={d}&mode=nar")
        except Exception as e:
            print(f"{d}: predictions取得失敗 {e}")
            continue
        rids = sorted({str(r["race_id"]) for rec in (pj.get("records") or [])
                       for r in (rec.get("races") or []) if r.get("race_id")})
        if not rids:
            continue
        try:
            rj = get(f"{BASE}/results.php?action=get&ids={','.join(rids)}")
        except Exception as e:
            print(f"{d}: results取得失敗 {e}")
            continue
        existing = rj.get("results") or {}
        items = []
        for rid in rids:
            ex = existing.get(rid)
            if ex and ex.get("ranks"):
                kept += 1          # ★答え合わせ由来の既存保存には触らない★
                continue
            rec = built.get(rid)
            if not rec:
                nores += 1         # ZIPにまだ無い（当日レース・月初の未取得など）
                continue
            items.append(rec)
        for i in range(0, len(items), 30):
            r = post(f"{BASE}/results.php?action=savebatch", {"items": items[i:i + 30]})
            pushed += r.get("saved", 0)
        if items:
            print(f"{d}: {len(items)}R 保存")
    print(f"完了: 保存{pushed}R / 既存維持{kept}R / ZIP未収載{nores}R")
    return 0


if __name__ == "__main__":
    sys.exit(main())
