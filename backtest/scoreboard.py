# -*- coding: utf-8 -*-
"""実運用の成績表を作る（Python 標準ライブラリだけ）

本番に保存された予想（predictions）と、keiba.go.jp 公式の着順・払戻を突き合わせて、
「実際に出した予想がどうだったか」を毎朝まとめ直す。公開の前に動く（.github/workflows/deploy-site.yml）。

出すもの:
  deploy/data/scoreboard.json   機械で読む用
  deploy/data/scoreboard.txt    人が読む用（https://seventh-well.com/odds/data/scoreboard.txt）

決まり（docs/SCORING_AUDIT.md の鉄則どおり）:
  ・回収率は「買った全レース」が分母。◎を1頭100円ずつ買ったものとして数える
  ・対象は地方（ばんえい除く）・新方式 C12 の 2026-09-28 以降・予想が保存されていて払戻が出ているレース
  ・幅は、レース単位で並べ直して出した95%の幅（乱数の種は固定）。件数が少ない行は当てにしない
  ・保存された予想は手動のやり直しで上書きされ得る。「朝の自動保存のまま」の行も別に出す

使い方:
  python3 backtest/scoreboard.py --cache backtest/nardata_zip           # 作って deploy/data/ に書く
  python3 backtest/scoreboard.py --cache ... --print                    # 書かずに表示だけ
"""
import argparse
import collections
import csv
import datetime
import io
import json
import os
import random
import sys
import time
import urllib.request
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(ROOT, "deploy", "data")
BASE = "https://seventh-well.com/odds"
START = "20260928"            # C12 に切り替えた日
INDEX_FIXED = "20261113"      # 止まっていた成績索引を直した日（この日の予想から新しい索引）
TC = {"30": "門別", "35": "盛岡", "36": "水沢", "42": "浦和", "43": "船橋", "44": "大井", "45": "川崎",
      "46": "金沢", "47": "笠松", "48": "名古屋", "50": "園田", "51": "姫路", "54": "高知", "55": "佐賀"}
UA = "Mozilla/5.0 turf-lab-scoreboard"


def log(*a):
    print(*a, file=sys.stderr, flush=True)


def get(url, timeout=120):
    last = None
    for i in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except Exception as e:      # noqa: BLE001
            last = e
            time.sleep(2 + 3 * i)
    raise RuntimeError("取得できませんでした: %s（%s）" % (url, last))


def today_jst():
    return datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))).strftime("%Y%m%d")


def day_add(d, n):
    x = datetime.date(int(d[:4]), int(d[4:6]), int(d[6:])) + datetime.timedelta(days=n)
    return x.strftime("%Y%m%d")


# ---------- 公式データ（着順・人気・払戻） ----------
def load_official(cache):
    rank, pop, pay = {}, {}, {}
    names = sorted(f for f in os.listdir(cache) if f.startswith("r") and f.endswith(".zip") and f[1:7] >= START[:6])
    if not names:
        raise RuntimeError("公式データのZIPが %s にありません（先に build_nar_index.py を動かす）" % cache)
    for f in names:
        zf = zipfile.ZipFile(os.path.join(cache, f))
        for n in zf.namelist():
            if n.endswith("_horselist.csv"):
                rd = csv.reader(io.TextIOWrapper(zf.open(n), encoding="utf-8-sig"))
                h = next(rd)
                ix = {k: i for i, k in enumerate(h)}
                for r in rd:
                    if len(r) < len(h):
                        continue
                    k = (r[ix["競馬場"]], r[ix["競走年月日"]], r[ix["レース番号"]], r[ix["馬番"]])
                    if r[ix["着順"]].isdigit():
                        rank[k] = int(r[ix["着順"]])
                    if r[ix["人気"]].isdigit():
                        pop[k] = int(r[ix["人気"]])
            elif n.endswith("_payback.csv"):
                rd = csv.reader(io.TextIOWrapper(zf.open(n), encoding="utf-8-sig"))
                h = next(rd)
                ix = {k: i for i, k in enumerate(h)}
                need = ["単勝組番", "単勝払戻金（円）", "複勝組番1", "複勝払戻金1（円）", "複勝組番2", "複勝払戻金2（円）", "複勝組番3", "複勝払戻金3（円）"]
                miss = [k for k in need if k not in ix]
                if miss:
                    raise RuntimeError("払戻データの列が変わっています（%s が無い）" % "・".join(miss))
                for r in rd:
                    if len(r) <= ix["複勝払戻金3（円）"]:
                        continue
                    k = (r[ix["競馬場"]], r[ix["競走年月日"]], r[ix["レース番号"]])
                    d = pay.setdefault(k, {"t": {}, "f": {}})
                    if r[ix["単勝払戻金（円）"]].isdigit():
                        d["t"][r[ix["単勝組番"]]] = int(r[ix["単勝払戻金（円）"]])
                    for i in ("1", "2", "3"):
                        v = r[ix["複勝払戻金%s（円）" % i]]
                        if v.isdigit():
                            d["f"][r[ix["複勝組番%s" % i]]] = int(v)
    return rank, pop, pay


# ---------- 保存された予想 ----------
def slim_day(date, recs):
    """1日ぶんの保存記録 → 成績表に要る項目だけ"""
    out = []
    for rec in recs:
        tc = str(rec.get("tc"))
        if tc not in TC:
            continue
        for m in rec.get("races") or []:
            if m.get("skip") or not m.get("marks"):
                continue
            rk = [x for x in (m.get("ranked") or []) if isinstance(x.get("s"), (int, float))]
            ss = sorted((x["s"] for x in rk), reverse=True)
            sh = m.get("shadow") if isinstance(m.get("shadow"), dict) else None
            out.append({
                "date": date, "tc": tc, "no": str(m.get("no")), "rid": m.get("race_id"),
                "o": str(m["marks"][0].get("num")), "n": len(rk),
                "gap": round(ss[0] - ss[1], 1) if len(ss) >= 2 else None,
                "auto": bool(rec.get("noclobber")), "mv": rec.get("mv"),
                "adj": (sh.get("adj") or [None])[0] if sh else None,
                "nok": (sh.get("nokoryu") or [None])[0] if sh else None,
                "koryu": sh.get("koryu") if sh else None,
            })
    return out


def load_predictions(cache, base, today):
    """日付ごとに取得。3日より前の日は cache に残したものを使う（予想は発走後に動かない）"""
    pdir = os.path.join(cache, "pred_rows")
    os.makedirs(pdir, exist_ok=True)
    dates = json.loads(get(base + "/predictions.php?action=dates&_=%d" % int(time.time())))
    days = sorted({str(it["date"]) for it in dates.get("items", []) if it.get("mode") == "nar" and START <= str(it["date"]) <= today})
    fresh_from = day_add(today, -3)
    rows = []
    for d in days:
        p = os.path.join(pdir, d + ".json")
        if d < fresh_from and os.path.exists(p):
            with open(p, encoding="utf-8") as fh:
                rows.extend(json.load(fh))
            continue
        j = json.loads(get("%s/predictions.php?action=list&date=%s&mode=nar&_=%d" % (base, d, int(time.time()))))
        day = slim_day(d, j.get("records") or [])
        with open(p, "w", encoding="utf-8") as fh:
            json.dump(day, fh, ensure_ascii=False)
        rows.extend(day)
        time.sleep(0.2)
    return rows


def load_t10(base, today):
    try:
        j = json.loads(get("%s/t10.php?from=%s&to=%s&_=%d" % (base, START, today, int(time.time())), timeout=60))
        return j.get("rows") or []
    except Exception as e:      # noqa: BLE001
        log("10分前の記録は読めませんでした:", e)
        return []


# ---------- 集計 ----------
def stat(bets, rnd):
    """bets = [(単勝払戻, 複勝払戻)]。払戻は100円あたり。外れは0"""
    n = len(bets)
    if n == 0:
        return {"n": 0}
    t = sum(b[0] for b in bets) / n
    f = sum(b[1] for b in bets) / n
    hit = 100.0 * sum(1 for b in bets if b[1] > 0) / n
    win = 100.0 * sum(1 for b in bets if b[0] > 0) / n
    out = {"n": n, "hit3": round(hit, 1), "win": round(win, 1), "tan": round(t, 1), "fuku": round(f, 1)}
    if n >= 30:
        bt, bf = [], []
        for _ in range(600):
            s = [bets[rnd.randrange(n)] for _ in range(n)]
            bt.append(sum(b[0] for b in s) / n)
            bf.append(sum(b[1] for b in s) / n)
        bt.sort(); bf.sort()
        out["tan_ci"] = [round(bt[15], 1), round(bt[584], 1)]
        out["fuku_ci"] = [round(bf[15], 1), round(bf[584], 1)]
    return out


def build(rows, t10, rank, pop, pay, today):
    rnd = random.Random(20261113)
    seen, races = set(), []
    for r in rows:
        if r["tc"] not in TC:
            continue
        k = (TC[r["tc"]], r["date"], r["no"])
        if k in seen or k not in pay or not pay[k]["f"]:
            continue
        seen.add(k)
        p = pay[k]

        def bet(num, p=p):
            return (p["t"].get(str(num), 0), p["f"].get(str(num), 0))
        races.append(dict(r, k=k, bet=bet(r["o"]), pop=pop.get(k + (r["o"],)),
                          adj_bet=bet(r["adj"]) if r.get("adj") else None,
                          nok_bet=bet(r["nok"]) if r.get("nok") else None))
    last_day = max((r["date"] for r in races), default=None)
    sec = collections.OrderedDict()

    def add(title, items):
        sec[title] = [dict(label=lab, **stat([x["bet"] for x in sel], rnd)) for lab, sel in items]

    add("全体", [
        ("新方式になってから全部（9/28〜）", races),
        ("索引を直す前（〜11/12）", [x for x in races if x["date"] < INDEX_FIXED]),
        ("索引を直した後（11/13〜）", [x for x in races if x["date"] >= INDEX_FIXED]),
        ("直近7日", [x for x in races if last_day and x["date"] > day_add(last_day, -7)]),
        ("直近30日", [x for x in races if last_day and x["date"] > day_add(last_day, -30)]),
        ("朝の自動保存のまま（全期間）", [x for x in races if x["auto"]]),
    ])
    add("◎の人気別（確定の人気）", [
        ("◎が1番人気", [x for x in races if x["pop"] == 1]),
        ("◎が2〜3番人気", [x for x in races if x["pop"] in (2, 3)]),
        ("◎が4番人気以下", [x for x in races if x["pop"] and x["pop"] >= 4]),
    ])
    add("今の判定別（◎と○の点差）", [
        ("点差8以上（★勝負にあたる）", [x for x in races if x["gap"] is not None and x["gap"] >= 8 and x["n"] < 14]),
        ("点差4〜8（狙い目にあたる）", [x for x in races if x["gap"] is not None and 4 <= x["gap"] < 8 and x["n"] < 14]),
        ("点差4未満", [x for x in races if x["gap"] is not None and x["gap"] < 4 and x["n"] < 14]),
        ("14頭以上（見送り）", [x for x in races if x["n"] >= 14]),
    ])
    weeks = collections.OrderedDict()
    for x in sorted(races, key=lambda z: z["date"]):
        d = datetime.date(int(x["date"][:4]), int(x["date"][4:6]), int(x["date"][6:]))
        wk = (d - datetime.timedelta(days=d.weekday())).strftime("%m/%d")
        weeks.setdefault(wk + "の週", []).append(x)
    add("週ごと", list(weeks.items())[-10:])

    # 裏の記録（同じレースで本番と比べる）
    sh = [x for x in races if x.get("adj_bet") is not None]
    ko = [x for x in races if x.get("nok_bet") is not None and x.get("koryu") == 1]
    sec["裏の記録（同じレースで比べる）"] = [
        dict(label="本番の◎（裏の記録があるレース）", **stat([x["bet"] for x in sh], rnd)),
        dict(label="消えている補正を足した場合の◎", **stat([x["adj_bet"] for x in sh], rnd)),
        dict(label="　うち◎が本番と違ったレース：本番", **stat([x["bet"] for x in sh if x["adj"] != x["o"]], rnd)),
        dict(label="　うち◎が本番と違ったレース：補正あり", **stat([x["adj_bet"] for x in sh if x["adj"] != x["o"]], rnd)),
        dict(label="JRA馬+6 が当たったレース：本番", **stat([x["bet"] for x in ko], rnd)),
        dict(label="JRA馬+6 が当たったレース：+6なし", **stat([x["nok_bet"] for x in ko], rnd)),
    ]

    # 10分前の記録
    by_rid = {x["rid"]: x for x in races if x.get("rid")}
    tt = []
    for t in t10:
        x = by_rid.get(t.get("rid"))
        if not x or t.get("mode") != "nar" or t.get("o_num") is None:
            continue
        p = pay[x["k"]]
        tt.append(dict(t, bet=(p["t"].get(str(t["o_num"]), 0), p["f"].get(str(t["o_num"]), 0))))
    sec["10分前のオッズで選んだ場合"] = [
        dict(label="10分前の記録がある全レース", **stat([x["bet"] for x in tt], rnd)),
        dict(label="10分前に◎が1番人気", **stat([x["bet"] for x in tt if x.get("fav") == 1], rnd)),
        dict(label="10分前に鉄板（1番人気・1.9倍以下・10頭以下）", **stat([x["bet"] for x in tt if x.get("iron") == 1], rnd)),
        dict(label="10分前に◎が4番人気以下", **stat([x["bet"] for x in tt if (x.get("o_pop") or 0) >= 4], rnd)),
    ]
    return {"built": today, "from": START, "to": last_day, "races": len(races), "days": len({x["date"] for x in races}),
            "t10_rows": len(t10), "sections": sec}


def to_text(sb):
    L = []
    L.append("カジ競馬 実運用の成績表")
    L.append("作成 %s ／ 対象 %s〜%s ／ %dレース（%d日）" % (sb["built"], sb["from"], sb["to"] or "-", sb["races"], sb["days"]))
    L.append("地方（ばんえい除く）。◎を100円ずつ買った場合。回収率は買った全レースが分母。")
    L.append("［ ］は95%の幅。30レース未満は幅を出さない。件数が少ない行は当てにしない。")
    L.append("")
    for title, items in sb["sections"].items():
        L.append("■ " + title)
        for it in items:
            if not it.get("n"):
                L.append("  %s：まだ0レース" % it["label"])
                continue
            ci = ""
            if "fuku_ci" in it:
                ci = "［%.1f〜%.1f］" % tuple(it["fuku_ci"])
            L.append("  %s" % it["label"])
            L.append("    %dレース ／ ◎3着内 %.1f%% ／ 単勝回収 %.1f%% ／ 複勝回収 %.1f%% %s" % (it["n"], it["hit3"], it["tan"], it["fuku"], ci))
        L.append("")
    L.append("注意：保存された予想は手動のやり直しで上書きされ得る。人気別は確定の人気。")
    L.append("過去の検証（49,323レース）：◎3着内 59.6% ／ 単勝回収 82.0% ／ 複勝回収 86.4%")
    return "\n".join(L) + "\n"


def main():
    ap = argparse.ArgumentParser(description="実運用の成績表を作る")
    ap.add_argument("--cache", default=os.path.join(HERE, "nardata_zip"), help="公式データのZIPがある場所（build_nar_index.py と同じ）")
    ap.add_argument("--base", default=BASE, help="予想の保存口があるサイト")
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--print", action="store_true", help="書かずに表示だけ")
    a = ap.parse_args()
    today = today_jst()
    rank, pop, pay = load_official(a.cache)
    rows = load_predictions(a.cache, a.base, today)
    if len(rows) < 500:
        raise SystemExit("保存された予想が %d レースしか読めません。取得に失敗している可能性があるので中止" % len(rows))
    t10 = load_t10(a.base, today)
    sb = build(rows, t10, rank, pop, pay, today)
    if sb["races"] < 500:
        raise SystemExit("突き合わせできたレースが %d しかありません。壊れている可能性があるので中止" % sb["races"])
    txt = to_text(sb)
    if not a.print:
        txt = "\ufeff" + txt      # 先頭に目印を付ける（iPhone のブラウザで文字化けしないように）
    if a.print:
        print(txt)
        return
    for name, data in (("scoreboard.json", json.dumps(sb, ensure_ascii=False, separators=(",", ":"))), ("scoreboard.txt", txt)):
        tmp = os.path.join(a.out, name + ".tmp")
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(data)
        os.replace(tmp, os.path.join(a.out, name))
    print("成績表を書き出しました（%s〜%s・%dレース）" % (sb["from"], sb["to"], sb["races"]))


if __name__ == "__main__":
    main()
