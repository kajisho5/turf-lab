# -*- coding: utf-8 -*-
"""公式(keiba.go.jp)に当日結果が載るまでの遅延を実測する

★なぜ測るのか★
  「公式から当日結果が取れる」ことは確認できたが、
  **発走から何分で着順が載るか**が分からない。
  ここが分からないまま表示を切り替えると
  「レースが終わったのに結果が出ない」という苦情になる。推測で決めず実測する。

★測り方★
  1. TodayRaceInfoTop から今日の開催場を動的に拾う（ハードコードしない）。
     過去に4場を決め打ちして、開催が違う日に空振りした反省。
  2. 各場の RaceList から (R番号 → 発走時刻) を取る。
  3. 発走を過ぎたレースだけ RaceMarkTable を1分ごとに見に行き、
     「着順が初めて載った時刻」を記録する。一度載ったらもう見ない。
  遅延(分) = 載った時刻 − 発走時刻。

出力: backtest/store/latency.csv
  日付, 場コード, 場名, R, 発走, 掲載時刻, 遅延(分)

使い方:
  python backtest/measure_latency.py            # 今日を最後まで見張る
  python backtest/measure_latency.py --once     # 1周だけ（動作確認）
  python backtest/measure_latency.py --date 20260720
"""
import argparse
import csv
import html
import os
import re
import sys
import time
import urllib.request
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "backtest", "store", "latency.csv")
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
BASE = "https://www.keiba.go.jp/KeibaWeb/TodayRaceInfo"


def get(url):
    try:
        return urllib.request.urlopen(
            urllib.request.Request(url, headers=UA), timeout=25
        ).read().decode("utf-8", "replace")
    except Exception:
        return ""


def discover_tracks(date):
    """今日の開催場 {babaCode: 場名} を TodayRaceInfoTop から拾う"""
    h = get(f"{BASE}/TodayRaceInfoTop")
    out = {}
    # <a ... k_babaCode=NN>場名</a> の形で場名が近くにある
    for m in re.finditer(r'k_babaCode=(\d+)[^>]*>\s*([^<>\d][^<>]{0,10})', h):
        code, name = m.group(1), m.group(2).strip()
        name = re.sub(r"\s+", "", name)
        if name and code not in out:
            out[code] = name
    return out


def post_times(date, baba):
    """RaceList から {R番号(int): '発走 HH:MM'} を取る"""
    d = f"{date[:4]}%2F{date[4:6]}%2F{date[6:]}"
    h = get(f"{BASE}/RaceList?k_raceDate={d}&k_babaCode={baba}")
    out = {}
    for rn, t in re.findall(r'k_raceNo=(\d+)[^>]*>.*?(\d{1,2}:\d{2})', h, re.S):
        r = int(rn)
        if r not in out:
            out[r] = t
    return out


def is_done(date, baba, race):
    """RaceMarkTable に着順が載っていれば True。未発走は '情報がありません'"""
    d = f"{date[:4]}%2F{date[4:6]}%2F{date[6:]}"
    h = get(f"{BASE}/RaceMarkTable?k_raceDate={d}&k_raceNo={race}&k_babaCode={baba}")
    if not h or "情報がありません" in h:
        return False
    rows = [c for c in (
        [re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", cc))).strip()
         for cc in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.S)]
        for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", h, re.S))
        if len(c) >= 10 and c and re.match(r"^\d+$", c[0])]
    return ("着順" in h) and bool(rows)


def lag_minutes(now, post):
    ph, pm = map(int, post.split(":"))
    return (now.hour * 60 + now.minute) - (ph * 60 + pm)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--date", default=datetime.now().strftime("%Y%m%d"))
    args = ap.parse_args()

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    if not os.path.exists(OUT):
        with open(OUT, "w", encoding="utf-8", newline="") as f:
            csv.writer(f).writerow(
                ["日付", "場コード", "場名", "R", "発走", "掲載時刻", "遅延分", "種別"])

    tracks = discover_tracks(args.date)
    if not tracks:
        print("今日は開催が見つからない（または取得失敗）。終了")
        return 0
    posts = {}          # baba -> {race: 'HH:MM'}
    for baba in tracks:
        posts[baba] = post_times(args.date, baba)
    total = sum(len(v) for v in posts.values())
    print(f"開催 {len(tracks)}場 / 全{total}レース: "
          + " ".join(f"{n}({len(posts[c])}R)" for c, n in tracks.items()), flush=True)

    # ★真の遅延は「未掲載→掲載」の遷移を捉えた時だけ分かる★
    #   監視開始時点で既に掲載済みのレースは「発走から今までの経過」しか出ず、
    #   遅延の上限にしかならない。両者を種別で区別して記録する。
    #     clean  = いちど未掲載を確認してから掲載に変わった（＝本物の遅延）
    #     baseline = 初回から掲載済み（＝上限。ヘッドラインには使わない）
    seen = set()
    pending = set()     # 未掲載を確認済み（次に掲載されたら clean 計測）
    while True:
        now = datetime.now()
        checked = 0
        for baba, name in tracks.items():
            for race, post in sorted(posts[baba].items()):
                key = (baba, race)
                if key in seen:
                    continue
                if lag_minutes(now, post) < 0:      # 発走前は見ない
                    continue
                checked += 1
                done = is_done(args.date, baba, race)
                time.sleep(1.2)                     # 連打しない
                if not done:
                    pending.add(key)
                    continue
                lag = lag_minutes(now, post)
                kind = "clean" if key in pending else "baseline"
                with open(OUT, "a", encoding="utf-8", newline="") as f:
                    csv.writer(f).writerow(
                        [args.date, baba, name, race, post,
                         now.strftime("%H:%M"), lag, kind])
                tag = "★実測" if kind == "clean" else "（開始時点で既済=上限）"
                print(f"  {name}{race}R 発走{post} → 掲載{now:%H:%M}  遅延{lag}分 {tag}",
                      flush=True)
                seen.add(key)
        remaining = total - len(seen)
        print(f"  [{now:%H:%M}] 掲載済 {len(seen)}/{total} / "
              f"未掲載を監視中 {len(pending - seen)}", flush=True)
        if args.once:
            break
        if remaining == 0:
            print("全レース掲載済み。終了")
            break
        time.sleep(60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
