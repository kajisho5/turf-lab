# -*- coding: utf-8 -*-
"""馬ごとの「当地複勝率」「当距離複勝率」を自前で作って公開用JSONに落とす

★なぜ必要か★
  personas.js の 実績重視 / 条件適性 / 総合 は wr（当地複勝率）と dr（当距離複勝率）を使う。
  この2つは keiba.go.jp が配信している値で、netkeiba の出馬表からは復元できない。
  「近5走から推定」だと母数が小さすぎて別物になり、公開しているバックテスト成績が
  当てはまらなくなる。
  → **手元に13年分の生データがあるのだから、自分で同じものを計算すればいい。**

★定義（keiba.go.jp の値と揃える）★
  wr = その競馬場での複勝率（3着以内 / 出走）
  dr = その距離帯での複勝率
  いずれも **そのレースより前** の成績だけを使う（当日を含めるとリークになる）。
  ここで作るのは「今日時点」のスナップショットなので、全履歴を素直に集計する。

★出力を軽くする工夫★
  ・直近 ACTIVE_DAYS 日に出走した馬だけを対象にする（引退馬を落とす）
  ・距離は 200m 刻みの帯にまとめる
  ・率は 0-100 の整数（小数を持つとJSONが倍近くなる）
  ・出走数が少ない馬は率が暴れるので、件数も一緒に持たせて画面側で判断できるようにする

出力: deploy/data/horses.json    { "馬名": {"t":{場:[複勝率,出走数]}, "d":{距離帯:[率,数]}} }
"""
import csv, glob, io, json, os, re, sys, zipfile
from collections import defaultdict
from datetime import datetime, timedelta

# ★2026-07-30拡張★ LTR(v2.0)が使う列を索引に同梱する。
#   通算成績(cn/ct3/owr/o2r/swin)・季節適性(四半期別複勝率)・
#   前走の着差(馬身)とクラス序数。定義は backtest/build_dataset.py と同一。
_MARGIN = {"ハナ": 0.05, "アタマ": 0.1, "クビ": 0.25, "同着": 0.0, "大差": 10.0}
def _margin(t):
    t = (t or "").strip()
    if not t:
        return None
    if t in _MARGIN:
        return _MARGIN[t]
    m = re.match(r"^(\d+)?(?:\.(\d)/(\d))?$", t)
    if m and (m.group(1) or m.group(2)):
        v = float(m.group(1) or 0)
        if m.group(2):
            v += float(m.group(2)) / float(m.group(3))
        return v
    m2 = re.match(r"^(\d)/(\d)$", t)
    if m2:
        return float(m2.group(1)) / float(m2.group(2))
    return None

_CLV_PAT = re.compile(r"(?<![A-Za-z])([A-C])[1-3]?(?![A-Za-z])")
def _clv(name):
    import unicodedata
    n = unicodedata.normalize("NFKC", name or "").replace(" ", "")
    if "新馬" in n or "未勝利" in n:
        return 0
    m = _CLV_PAT.search(n)
    if m:
        return {"C": 2, "B": 3, "A": 4}[m.group(1)]
    if re.match(r"^[23]歳", n):
        return 1
    return None

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORK = os.path.join(ROOT, "backtest", "nardata")
OUT = os.path.join(ROOT, "deploy", "data", "horses.json")

ACTIVE_DAYS = 400          # これより古い馬は載せない
MIN_RUNS = 1               # 1走でも載せる（件数を併記するので判断は画面側）
DIST_STEP = 200            # 距離帯の刻み


def read_zip_csv(z, suffix):
    for n in z.namelist():
        if n.endswith(suffix):
            return list(csv.reader(io.StringIO(z.read(n).decode("utf-8-sig", errors="replace"))))
    return []


def main():
    zips = sorted(glob.glob(os.path.join(WORK, "race_*.zip")))
    if not zips:
        sys.exit("race_*.zip が無い。nar_data_pipeline.py で取得すること")
    print(f"ZIP {len(zips)}本を読む...", flush=True)

    # 馬名 -> 場 -> [複勝, 出走] / 馬名 -> 距離帯 -> [複勝, 出走]
    tr = defaultdict(lambda: defaultdict(lambda: [0, 0]))
    dr = defaultdict(lambda: defaultdict(lambda: [0, 0]))
    last = {}                      # 馬名 -> 最終出走日
    runs = defaultdict(list)       # 馬名 -> [(ymd, 着順, 着差, クラス序数)]  ※swin/前走情報用
    quart = defaultdict(lambda: [[0, 0], [0, 0], [0, 0], [0, 0]])   # 季節(四半期)別 [複勝,出走]
    nrow = 0

    for i, zp in enumerate(zips):
        try:
            z = zipfile.ZipFile(zp)
        except zipfile.BadZipFile:
            print(f"  !! 壊れている: {os.path.basename(zp)}")
            continue
        rl = {}
        for r in read_zip_csv(z, "_racelist.csv"):
            if len(r) > 26 and r[1].isdigit():
                # (場, 年月日, R) -> (距離, レース名)   ※レース名はクラス序数用
                rl[(r[0], r[1], r[2])] = (r[23] if len(r) > 23 else "",
                                          r[5] if len(r) > 5 else "")
        for r in read_zip_csv(z, "_horselist.csv"):
            if len(r) < 30 or not r[1].isdigit():
                continue
            jyo, ymd, rno, name = r[0], r[1], r[2], r[6].strip()
            if not name:
                continue
            # ばんえいは平地と性質が全く違うので除外（公開ページの集計と揃える）
            if "ば" in jyo:
                continue
            # ★着順は 31 列目★（29=最高タイム, 30=最高タイム良馬場 で、そちらを見ると0件になる）
            #   列定義は docs/DATA_SOURCES.md 参照。中止・除外は数字でないので出走に数えない。
            c = r[31] if len(r) > 31 else ""
            if not c.isdigit():
                continue
            rank = int(c)
            nrow += 1
            last[name] = max(last.get(name, ""), ymd)
            hit = 1 if rank <= 3 else 0
            e = tr[name][jyo]; e[0] += hit; e[1] += 1
            q = quart[name][(int(ymd[4:6]) - 1) // 3]
            q[0] += hit; q[1] += 1
            d, rname = rl.get((jyo, ymd, rno), ("", ""))
            runs[name].append((ymd, rank,
                               _margin(r[33] if len(r) > 33 else ""),
                               _clv(rname)))
            dm = "".join(ch for ch in d if ch.isdigit())
            if dm:
                band = int(dm) // DIST_STEP * DIST_STEP
                e2 = dr[name][band]; e2[0] += hit; e2[1] += 1
        if (i + 1) % 24 == 0:
            print(f"  {i+1}/{len(zips)}  馬 {len(last):,}", flush=True)

    if not last:
        sys.exit("1行も読めなかった。列位置を docs/DATA_SOURCES.md で確認すること")

    newest = max(last.values())
    cutoff = (datetime.strptime(newest, "%Y%m%d") - timedelta(days=ACTIVE_DAYS)).strftime("%Y%m%d")
    print(f"\n最新日 {newest} / 対象は {cutoff} 以降に出走した馬")

    out = {}
    for name, d in last.items():
        if d < cutoff:
            continue
        t = {k: [round(100 * v[0] / v[1]), v[1]] for k, v in tr[name].items() if v[1] >= MIN_RUNS}
        s = {str(k): [round(100 * v[0] / v[1]), v[1]] for k, v in dr[name].items() if v[1] >= MIN_RUNS}
        if t or s:
            rec = {"t": t, "d": s}
            # ---- 通算 c:[出走, 複勝率%, 勝率%, 連対率%, 勝ってからの走数] ----
            rs = sorted(runs[name])          # (ymd,rank,margin,clv) 時系列
            n = len(rs)
            if n:
                win = sum(1 for x in rs if x[1] == 1)
                ren = sum(1 for x in rs if x[1] <= 2)
                t3 = sum(1 for x in rs if x[1] <= 3)
                lastwin = max((i for i, x in enumerate(rs) if x[1] == 1), default=-1)
                swin = (n - 1 - lastwin) if lastwin >= 0 else n
                rec["c"] = [n, round(100 * t3 / n), round(100 * win / n),
                            round(100 * ren / n), swin]
                # ---- 前走 p:[着差(馬身×100の整数), クラス序数] 無い値は-1 ----
                mg, cv = rs[-1][2], rs[-1][3]
                rec["p"] = [int(round(mg * 100)) if mg is not None else -1,
                            cv if cv is not None else -1]
            # ---- 季節 q: 四半期別 [複勝率%, 出走数] ----
            rec["q"] = [[round(100 * v[0] / v[1]) if v[1] else 0, v[1]]
                        for v in quart[name]]
            out[name] = rec

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    sz = os.path.getsize(OUT)
    print(f"出力: {os.path.relpath(OUT, ROOT)}")
    print(f"  延べ出走 {nrow:,} 行 / 全馬 {len(last):,} 頭 / 現役 {len(out):,} 頭 / {sz/1024/1024:.1f}MB")
    if sz > 8 * 1024 * 1024:
        print("  !! 8MB超。ACTIVE_DAYS を短くするか、頭文字でシャードすること")


if __name__ == "__main__":
    main()
