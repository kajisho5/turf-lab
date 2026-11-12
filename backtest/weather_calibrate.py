# -*- coding: utf-8 -*-
"""降水量→馬場状態の変換表を実測で作る

★何のため★
  tweet.html に「天気予報＋馬場見込み」を付ける（2026-07-30 ユーザー発案）。
  馬場状態そのものは当日発表＝事前予想では見えないが、天気予報は前夜に取れる。
  「予報降水量→馬場の見込み」の変換を、適当な閾値ではなく
  **過去13年の実降水量×実馬場状態**で較正する。

★精度への寄与はゼロと実測済み★
  実測goingをモデルに入れるceilingテストで NAR 66.6→66.4% / JRA 56.1→56.1%。
  馬場はレース内全馬に同じにかかる定数なので順位学習には効かない。
  これは**表示（読み物）用**であって、スコアリングには入れない。

データ源: Open-Meteo Archive API（無料・過去の日次降水量）
  https://archive-api.open-meteo.com/v1/archive
実馬場: backtest/nardata/bt_all.jsonl / bt_jra.jsonl の going列

出力（★取得データは必ず保存する★）:
  backtest/nardata/weather/rain_<場コード>.json  … 日次降水量（再取得不要に）
  deploy/data/going_by_rain.json                … 降水量帯→馬場分布の変換表
使い方: python backtest/weather_calibrate.py [--fetch-only|--calib-only]
"""
import json
import os
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WDIR = os.path.join(ROOT, "backtest", "nardata", "weather")
OUT = os.path.join(ROOT, "deploy", "data", "going_by_rain.json")

# 競馬場の座標（日次降水量なので10km精度で十分）
TRACKS = {
    # NAR（tc = netkeiba/keiba.go.jp場コード）
    "30": ("門別", 42.49, 142.05), "35": ("盛岡", 39.78, 141.20),
    "36": ("水沢", 39.14, 141.14), "42": ("浦和", 35.86, 139.65),
    "43": ("船橋", 35.70, 139.99), "44": ("大井", 35.59, 139.74),
    "45": ("川崎", 35.53, 139.71), "46": ("金沢", 36.60, 136.68),
    "47": ("笠松", 35.36, 136.76), "48": ("名古屋", 35.08, 136.80),
    "50": ("園田", 34.72, 135.43), "51": ("姫路", 34.84, 134.67),
    "54": ("高知", 33.53, 133.47), "55": ("佐賀", 33.31, 130.42),
    # JRA（tc = 01..10）
    "01": ("札幌", 43.06, 141.35), "02": ("函館", 41.77, 140.73),
    "03": ("福島", 37.75, 140.47), "04": ("新潟", 37.94, 139.06),
    "05": ("東京", 35.66, 139.48), "06": ("中山", 35.72, 139.96),
    "07": ("中京", 35.07, 136.99), "08": ("京都", 34.90, 135.77),
    "09": ("阪神", 34.72, 135.36), "10": ("小倉", 33.89, 130.88),
}
START, END = "2013-01-01", "2026-07-28"   # archiveは数日遅れまで


def fetch_rain():
    os.makedirs(WDIR, exist_ok=True)
    for tc, (name, lat, lon) in TRACKS.items():
        path = os.path.join(WDIR, f"rain_{tc}.json")
        if os.path.exists(path) and os.path.getsize(path) > 10000:
            print(f"  {name}: 取得済みスキップ")
            continue
        url = ("https://archive-api.open-meteo.com/v1/archive"
               f"?latitude={lat}&longitude={lon}"
               f"&start_date={START}&end_date={END}"
               "&daily=precipitation_sum&timezone=Asia%2FTokyo")
        req = urllib.request.Request(url, headers={"User-Agent": "sw-turf-lab-calib"})
        with urllib.request.urlopen(req, timeout=60) as r:
            data = json.loads(r.read().decode("utf-8"))
        days = data["daily"]["time"]
        prec = data["daily"]["precipitation_sum"]
        # {YYYYMMDD: mm} に圧縮して保存
        out = {d.replace("-", ""): (p if p is not None else None)
               for d, p in zip(days, prec)}
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(out, f, separators=(",", ":"))
        os.replace(tmp, path)
        print(f"  {name}: {len(out):,}日分 保存")
        time.sleep(1.2)   # 無料APIに礼儀


# 降水量の帯（当日+前日の合計mm）。表示用なので粗くてよい
BINS = [(0.0, 0.5, "0"), (0.5, 3, "1-3"), (3, 10, "3-10"),
        (10, 25, "10-25"), (25, 1e9, "25+")]
GK = ["良", "稍", "重", "不"]
GMAP = {"良": "良", "稍": "稍", "稍重": "稍", "重": "重", "不": "不", "不良": "不"}


def calibrate():
    rain = {}
    for tc in TRACKS:
        path = os.path.join(WDIR, f"rain_{tc}.json")
        if os.path.exists(path):
            rain[tc] = json.load(open(path, encoding="utf-8"))
    # (surface区分, 帯) -> {going: レース数}
    # 芝とダートで水の効き方が違う。JRA芝 / JRAダ / NARダ の3区分
    tab = {}
    n_used = 0
    for fn, seg_of in [
        (os.path.join(ROOT, "backtest", "nardata", "bt_all.jsonl"),
         lambda rc: "narD" if rc.get("surf") != "芝" else None),
        (os.path.join(ROOT, "backtest", "nardata", "bt_jra.jsonl"),
         lambda rc: {"芝": "jraT", "ダート": "jraD"}.get(rc.get("surf"))),
    ]:
        if not os.path.exists(fn):
            continue
        with open(fn, encoding="utf-8") as f:
            for line in f:
                try:
                    rc = json.loads(line)
                except json.JSONDecodeError:
                    continue
                seg = seg_of(rc)
                g = GMAP.get(str(rc.get("going") or "")[:2].strip() or
                             str(rc.get("going") or ""))
                if not g:
                    g = GMAP.get(str(rc.get("going") or "")[:1])
                tc, d = str(rc.get("tc")), str(rc.get("d"))
                if not seg or not g or tc not in rain:
                    continue
                r0 = rain[tc].get(d)
                prev = str(int(d) - 1) if d[6:8] != "01" else None  # 月初は簡略に当日のみ
                r1 = rain[tc].get(prev) if prev else 0
                if r0 is None:
                    continue
                mm = r0 + (r1 or 0)
                for lo, hi, label in BINS:
                    if lo <= mm < hi:
                        key = (seg, label)
                        tab.setdefault(key, {k: 0 for k in GK})
                        tab[key][g] += 1
                        n_used += 1
                        break
    # 出力: {seg: {帯: {"n":件数, "p":{良:%,稍:%,重:%,不:%}}}}
    out = {}
    for (seg, label), cnt in sorted(tab.items()):
        n = sum(cnt.values())
        out.setdefault(seg, {})[label] = {
            "n": n, "p": {k: round(100 * v / n, 1) for k, v in cnt.items()}}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    tmp = OUT + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"bins": [b[2] for b in BINS], "note":
                   "当日+前日の降水量mm→馬場分布(実測2013-2026)。表示用・採点には不使用",
                   "seg": out}, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, OUT)
    print(f"較正 {n_used:,}R → {os.path.relpath(OUT, ROOT)}")
    for seg in out:
        print(f"  [{seg}]")
        for label in [b[2] for b in BINS]:
            if label in out[seg]:
                e = out[seg][label]
                print(f"    {label}mm: {e['p']} ({e['n']:,}R)")


if __name__ == "__main__":
    if "--calib-only" not in sys.argv:
        print("降水量を取得中…")
        fetch_rain()
    if "--fetch-only" not in sys.argv:
        calibrate()
