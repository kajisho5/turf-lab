# -*- coding: utf-8 -*-
"""地方の成績索引を keiba.go.jp の公式データから作る（Python 標準ライブラリだけ）

作るもの（予想ページの並べ替えモデルが読む。tweet.html の loadLtrHorseIndex / loadLtrJockeyIndex）:
  deploy/data/horses.json    馬名 → {t:場別[複勝率%,走数], d:距離帯別[複勝率%,走数],
                                      c:[通算走数,複勝率%,勝率%,連対率%,最後に勝ってからの走数],
                                      p:[前走の着差(馬身×100),前走クラス序数], q:四半期別[複勝率%,走数]×4}
  deploy/data/jockeys.json   騎手名(3文字) → [複勝率%(小数1桁), 件数]
  deploy/data/trainers.json  調教師名(3文字) → 同上
  deploy/data/sires.json     父馬名(空白除去) → 同上

★この作り方は、2026-09-13 時点の本番の索引を公式データから再現して確かめた定義★（2026-11-13）
  馬     : 2013-01-01 以降・ばんえい除く・着順が数字の出走だけ。率は四捨五入した整数。
           収録するのは「結果の入っている最後の日」から400日以内に走った馬。
           当時の索引 16,630頭の全項目が一致。
  騎手ほか: 2013-01-01 以降・ばんえいと福山を除く・取消や未確定の行も件数に入れる・50件以上だけ収録。
           収録される名前は一致（501/668/835）。値は当時の出走予定の入り方の差で平均0.01ポイントのずれ。
  元の道具（パソコン側の build_horse_index.py / build_jockey_index.py）は手元に無いので作り直した。
  中央（jra_*.json）は JV-Data が要るのでここでは作らない。

使い方:
  python3 backtest/build_nar_index.py                      # 取得して deploy/data/ に書く
  python3 backtest/build_nar_index.py --check              # 書かずに、今の deploy/data/ との違いだけ表示
  python3 backtest/build_nar_index.py --asof 20260913 --entries-to 20260916 --check   # 過去の時点を再現
"""
import argparse
import collections
import csv
import datetime
import io
import json
import os
import re
import sys
import time
import unicodedata
import urllib.request
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(ROOT, "deploy", "data")
URL = "https://www.keiba.go.jp/KeibaWeb/DataDownload/RaceDataDownload?type=monthly&k_year={y}&k_month={m}"
START = "20130101"          # 集計の開始日
BANEI = "帯広ば"
KEEP_DAYS = 400             # 馬の索引に残す期間（最後の出走からの日数）
MIN_N = 50                  # 騎手・調教師・父の索引に載せる最低件数
MARGIN = {"ハナ": 5, "アタマ": 10, "クビ": 25, "大差": 1000, "同着": 0}


def log(*a):
    print(*a, file=sys.stderr, flush=True)


def months(first, last):
    y, m = int(first[:4]), int(first[4:6])
    while (y, m) <= (int(last[:4]), int(last[4:6])):
        yield y, m
        y, m = (y, m + 1) if m < 12 else (y + 1, 1)


def fetch(cache, today, refresh_months=2):
    """月ごとのZIPを cache に置く。直近 refresh_months か月ぶんは毎回取り直す（結果が日々足されるため）"""
    os.makedirs(cache, exist_ok=True)
    recent = set()
    y, m = int(today[:4]), int(today[4:6])
    for _ in range(refresh_months):
        recent.add((y, m))
        y, m = (y, m - 1) if m > 1 else (y - 1, 12)
    paths = []
    for y, m in months(START, today):
        p = os.path.join(cache, "r%04d%02d.zip" % (y, m))
        if (y, m) in recent or not os.path.exists(p) or os.path.getsize(p) < 1000:
            last_err = None
            for attempt in range(3):
                try:
                    req = urllib.request.Request(URL.format(y=y, m=m), headers={"User-Agent": "Mozilla/5.0 turf-lab-index"})
                    with urllib.request.urlopen(req, timeout=120) as r:
                        data = r.read()
                    zipfile.ZipFile(io.BytesIO(data)).namelist()      # 壊れていないか
                    with open(p, "wb") as f:
                        f.write(data)
                    last_err = None
                    break
                except Exception as e:                               # noqa: BLE001
                    last_err = e
                    time.sleep(2 + attempt * 3)
            if last_err is not None:
                raise SystemExit("公式データを取得できませんでした（%04d年%02d月）: %s" % (y, m, last_err))
            time.sleep(0.3)
        paths.append(p)
    return paths


def load(paths):
    """(出走行のリスト, レース情報) を返す"""
    rows, races = [], {}
    for p in paths:
        zf = zipfile.ZipFile(p)
        for n in zf.namelist():
            if n.endswith("_horselist.csv"):
                rd = csv.reader(io.TextIOWrapper(zf.open(n), encoding="utf-8-sig"))
                h = next(rd)
                ix = {k: i for i, k in enumerate(h)}
                need = ("競馬場", "競走年月日", "レース番号", "馬名", "騎手名", "調教師", "父馬名", "着順", "着差")
                miss = [k for k in need if k not in ix]
                if miss:
                    raise SystemExit("公式データの列が変わっています（%s に %s が無い）" % (n, "・".join(miss)))
                for r in rd:
                    if len(r) < len(h):
                        continue
                    rows.append(tuple(r[ix[k]] for k in need))
            elif n.endswith("_racelist.csv"):
                rd = csv.reader(io.TextIOWrapper(zf.open(n), encoding="utf-8-sig"))
                h = next(rd)
                ix = {k: i for i, k in enumerate(h)}
                for k in ("競馬場", "競走年月日", "レース番号", "距離", "レース名"):
                    if k not in ix:
                        raise SystemExit("公式データの列が変わっています（%s に %s が無い）" % (n, k))
                for r in rd:
                    if len(r) <= max(ix["距離"], ix["レース名"]):
                        continue
                    races[(r[ix["競馬場"]], r[ix["競走年月日"]], r[ix["レース番号"]])] = (r[ix["距離"]], r[ix["レース名"]])
    return rows, races


def clv(name):
    """クラス序数（tweet.html の _clvBuild と同じ考え方。全角英数は半角にそろえてから見る）"""
    n = re.sub(r"\s", "", unicodedata.normalize("NFKC", name or ""))
    if re.search("新馬|未勝利", n):
        return 0
    m = re.search(r"(^|[^A-Za-z])([A-C])[1-3]?([^A-Za-z]|$)", n)
    if m:
        return {"C": 2, "B": 3, "A": 4}[m.group(2)]
    if re.match("[23]歳", n):
        return 1
    return -1


def margin(text, rank):
    """着差の表記 → 馬身×100。1着や不明は -1"""
    t = (text or "").strip()
    if t in MARGIN:
        return MARGIN[t]
    if rank == 1 or not t:
        return -1
    m = re.fullmatch(r"(?:(\d+)\.)?(\d+)/(\d+)", t)
    if m:
        return int(round((int(m.group(1) or 0) + int(m.group(2)) / int(m.group(3))) * 100))
    if t.isdigit():
        return min(1000, int(t) * 100)
    return -1


def pct(a, b):
    return int(round(100 * a / b)) if b else 0


def build_horses(rows, races, asof):
    runs = collections.defaultdict(list)
    for v, d, no, name, _jk, _tr, _si, rk, mg in rows:
        if v == BANEI or not (START <= d <= asof) or not rk.isdigit():
            continue
        rc = races.get((v, d, no)) or ("", "")
        runs[name].append((d, int(no) if no.isdigit() else 0, v, int(rk), rc[0], mg, rc[1]))
    a = datetime.date(int(asof[:4]), int(asof[4:6]), int(asof[6:]))
    keep_from = (a - datetime.timedelta(days=KEEP_DAYS)).strftime("%Y%m%d")
    out = {}
    for name, rs in runs.items():
        rs.sort()
        if rs[-1][0] < keep_from:
            continue
        n = len(rs)
        t = collections.OrderedDict()
        dd = collections.OrderedDict()
        q = [[0, 0] for _ in range(4)]
        t3 = w = r2 = 0
        sw = n
        for i, (d, _no, v, rk, dist, _mg, _nm) in enumerate(rs):
            top = rk <= 3
            t3 += top
            w += rk == 1
            r2 += rk <= 2
            if rk == 1:
                sw = n - 1 - i
            x = t.setdefault(v, [0, 0]); x[0] += top; x[1] += 1
            if dist.isdigit():
                x = dd.setdefault(str(int(dist) // 200 * 200), [0, 0]); x[0] += top; x[1] += 1
            x = q[(int(d[4:6]) - 1) // 3]; x[0] += top; x[1] += 1
        last = rs[-1]
        out[name] = {
            "t": {k: [pct(a_, b_), b_] for k, (a_, b_) in t.items()},
            "d": {k: [pct(a_, b_), b_] for k, (a_, b_) in dd.items()},
            "c": [n, pct(t3, n), pct(w, n), pct(r2, n), sw],
            "p": [margin(last[5], last[3]), clv(last[6])],
            "q": [[pct(a_, b_), b_] for a_, b_ in q],
        }
    return out


def build_people(rows, asof, entries_to, col):
    ev = collections.defaultdict(lambda: [0, 0])
    for r in rows:
        v, d, rk = r[0], r[1], r[7]
        if v in (BANEI, "福山") or d < START or d > entries_to:
            continue
        k = re.sub(r"\s", "", r[col])
        if not k:
            continue
        ev[k][1] += 1
        if d <= asof and rk in ("1", "2", "3"):
            ev[k][0] += 1
    return {k: [round(100 * a / b, 1), b] for k, (a, b) in sorted(ev.items()) if b >= MIN_N}


def last_result_day(rows):
    return max((r[1] for r in rows if r[7].isdigit() and r[0] != BANEI), default=None)


def dump(obj):
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def compare(name, new, old):
    """違いの要約を1行で返す"""
    ks_new, ks_old = set(new), set(old)
    both = ks_new & ks_old
    same = sum(1 for k in both if new[k] == old[k])
    return "%s: 新 %d件 / 今 %d件 / 両方にある %d件のうち同じ %d件 / 新だけ %d件 / 今だけ %d件" % (
        name, len(new), len(old), len(both), same, len(ks_new - ks_old), len(ks_old - ks_new))


def main():
    ap = argparse.ArgumentParser(description="地方の成績索引を公式データから作る")
    ap.add_argument("--cache", default=os.path.join(HERE, "nardata_zip"), help="月ごとのZIPを置く場所")
    ap.add_argument("--out", default=OUT, help="書き出し先（既定: deploy/data）")
    ap.add_argument("--asof", default="", help="この日までの結果で作る（YYYYMMDD。省略＝結果が入っている最後の日）")
    ap.add_argument("--entries-to", default="", help="騎手ほかの件数に入れる出走予定の最後の日（省略＝取得したデータ全部）")
    ap.add_argument("--check", action="store_true", help="書かずに、今あるファイルとの違いだけ表示")
    ap.add_argument("--no-fetch", action="store_true", help="取得せず cache にあるものだけ使う")
    ap.add_argument("--soft", action="store_true", help="取得に失敗しても止めない（今ある索引のまま進める。警告は出す）")
    a = ap.parse_args()

    today = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))).strftime("%Y%m%d")
    if a.no_fetch:
        paths = sorted(os.path.join(a.cache, f) for f in os.listdir(a.cache) if re.fullmatch(r"r\d{6}\.zip", f) and f[1:7] >= START[:6])
    else:
        try:
            paths = fetch(a.cache, today)
        except SystemExit as e:
            if not a.soft:
                raise
            print("::warning::索引を更新できませんでした。今ある索引のまま進めます: %s" % e)
            return
    rows, races = load(paths)
    if len(rows) < 1000000:
        raise SystemExit("公式データの行数が少なすぎます（%d行）。取得に失敗している可能性があるので中止" % len(rows))
    asof = a.asof or last_result_day(rows)
    entries_to = a.entries_to or max(r[1] for r in rows)
    log("結果は %s まで / 出走予定は %s まで / 出走行 %d" % (asof, entries_to, len(rows)))

    made = {
        "horses.json": build_horses(rows, races, asof),
        "jockeys.json": build_people(rows, asof, entries_to, 4),
        "trainers.json": build_people(rows, asof, entries_to, 5),
        "sires.json": build_people(rows, asof, entries_to, 6),
    }
    # ★時計の値（2026-11-13）★ 近3走の時計指数・上がり指数（s）と、場×距離ごとの持ち時計の指数（b）。
    #   学習データ（build_time_feats.py）と同じ関数で作る＝本番と学習で値がずれない。
    from build_time_feats import index_time
    tm = index_time(sorted(paths), asof, names=set(made["horses.json"]))
    for nm, v in tm.items():
        made["horses.json"][nm]["s"] = v["s"]
        if v["b"]:
            made["horses.json"][nm]["b"] = v["b"]
    have = sum(1 for v in made["horses.json"].values() if v.get("s") and v["s"][0] is not None)
    log("時計の値つき %d / %d 頭" % (have, len(made["horses.json"])))
    if have < len(made["horses.json"]) * 0.8:
        raise SystemExit("時計の値が付いた馬が8割未満です。壊れている可能性があるので中止")

    # ★空・激減では上書きしない★（取得や列の読み違いで索引が静かに壊れるのを防ぐ）
    floor = {"horses.json": 10000, "jockeys.json": 300, "trainers.json": 400, "sires.json": 500}
    for f, obj in made.items():
        if len(obj) < floor[f]:
            raise SystemExit("%s が %d件しかありません（下限 %d）。壊れている可能性があるので中止" % (f, len(obj), floor[f]))

    for f, obj in made.items():
        p = os.path.join(a.out, f)
        old = {}
        if os.path.exists(p):
            with open(p, encoding="utf-8") as fh:
                old = json.load(fh)
        print(compare(f, obj, old))
        if old and len(obj) < len(old) * 0.7:
            raise SystemExit("%s の件数が今の7割未満です。壊れている可能性があるので中止" % f)
        if not a.check:
            tmp = p + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                fh.write(dump(obj))
            os.replace(tmp, p)
    if not a.check:
        with open(os.path.join(a.out, "nar_index_asof.json"), "w", encoding="utf-8") as fh:
            fh.write(dump({"asof": asof, "entries_to": entries_to, "built": today}))
        print("書き出しました（結果は %s まで）" % asof)


if __name__ == "__main__":
    main()
