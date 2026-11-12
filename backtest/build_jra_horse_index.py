# -*- coding: utf-8 -*-
"""中央競馬の馬インデックス（当地複勝率 wr / 当距離複勝率 dr）

★地方と同じ形式にする★
  地方は build_horse_index.py が deploy/data/horses.json を作っている。
  中央も**まったく同じ形**（{"馬名": {"t":{場:[率,数]}, "d":{距離帯:[率,数]}}}）で
  deploy/data/jra_horses.json を作る。
  race_app.js は rid で中央/地方を見分けて読むファイルを変えるだけで済む。

  これで人格の「条件適性(dr)」「実績重視(wr)」が中央でも動く。

★推定で埋めない★
  wr/dr は netkeiba には無い値。13.9万レースの公式データから作る。
  推定を混ぜると、公開しているバックテスト成績と当てはまらない別物になる。

出力: deploy/data/jra_horses.json
"""
import collections
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DUMP = [os.path.join(ROOT, "backtest", "jvdata", "target_all.txt"),
        os.path.join(ROOT, "backtest", "jvdata", "setup_2026.txt")]
OUT = os.path.join(ROOT, "deploy", "data", "jra_horses.json")

S_KEY, S_UMA, S_NAME, S_FIN = slice(11, 27), slice(28, 30), slice(40, 76), slice(334, 336)
R_KEY, R_DIST = slice(11, 27), slice(697, 701)
JYO = {"01": "札幌", "02": "函館", "03": "福島", "04": "新潟", "05": "東京",
       "06": "中山", "07": "中京", "08": "京都", "09": "阪神", "10": "小倉"}
DIST_STEP = 200
ACTIVE_FROM = "20230101"       # 直近3年に走った馬だけ載せる（索引を軽く）
MIN_KEEP = 3                   # 3走未満の率は暴れるので、そもそも載せない


def main():
    # レースごとの距離（RAから）
    dist = {}
    for path in DUMP:
        if os.path.exists(path):
            with open(path, "rb") as f:
                for line in f:
                    if line[:2] == b"RA":
                        k = line[R_KEY]
                        if k[8:10].decode("ascii", "replace") in JYO:
                            d = line[R_DIST].decode("ascii", "replace").strip()
                            dist[k[:16]] = int(d) if d.isdigit() else 0
    print(f"レース距離 {len(dist):,}", flush=True)

    # 馬名 -> 場 -> [複勝数, 出走数] / 距離帯 -> [複勝数, 出走数]
    trk = collections.defaultdict(lambda: collections.defaultdict(lambda: [0, 0]))
    dst = collections.defaultdict(lambda: collections.defaultdict(lambda: [0, 0]))
    last = collections.defaultdict(str)
    # ★2026-07-30拡張★ LTR用: 通算(c)・季節(q)。定義は build_jra_dataset.py と同一
    runs = collections.defaultdict(list)     # 馬名 -> [(ymd, 着順)]
    quart = collections.defaultdict(lambda: [[0, 0], [0, 0], [0, 0], [0, 0]])

    for path in DUMP:
        if not os.path.exists(path):
            continue
        with open(path, "rb") as f:
            for line in f:
                if line[:2] != b"SE":
                    continue
                k = line[S_KEY]
                jyo = k[8:10].decode("ascii", "replace")
                if jyo not in JYO:
                    continue
                fin = line[S_FIN].decode("ascii", "replace").strip()
                if not fin.isdigit():
                    continue
                name = line[S_NAME].decode("cp932", "replace").strip()
                if not name:
                    continue
                hit = int(fin) <= 3
                d = k[:8].decode()
                if d > last[name]:
                    last[name] = d

                t = trk[name][JYO[jyo]]
                t[0] += hit
                t[1] += 1
                runs[name].append((d, int(fin)))
                q = quart[name][(int(d[4:6]) - 1) // 3]
                q[0] += hit
                q[1] += 1
                band = dist.get(k[:16], 0) // DIST_STEP * DIST_STEP
                if band:
                    s = dst[name][str(band)]
                    s[0] += hit
                    s[1] += 1
        print(f"  読了 {os.path.basename(path)}  馬 {len(trk):,}", flush=True)

    out = {}
    for name in trk:
        if last[name] < ACTIVE_FROM:
            continue
        t = {k: [round(100 * v[0] / v[1]), v[1]]
             for k, v in trk[name].items() if v[1] >= MIN_KEEP}
        s = {k: [round(100 * v[0] / v[1]), v[1]]
             for k, v in dst[name].items() if v[1] >= MIN_KEEP}
        if t or s:
            rec = {"t": t, "d": s}
            rs = sorted(runs[name])
            n2 = len(rs)
            if n2:
                win = sum(1 for x in rs if x[1] == 1)
                ren = sum(1 for x in rs if x[1] <= 2)
                t3 = sum(1 for x in rs if x[1] <= 3)
                lastwin = max((i for i, x in enumerate(rs) if x[1] == 1), default=-1)
                swin = (n2 - 1 - lastwin) if lastwin >= 0 else n2
                rec["c"] = [n2, round(100 * t3 / n2), round(100 * win / n2),
                            round(100 * ren / n2), swin]
            rec["q"] = [[round(100 * v[0] / v[1]) if v[1] else 0, v[1]]
                        for v in quart[name]]
            out[name] = rec

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    sz = os.path.getsize(OUT)
    print(f"\n出力: {os.path.relpath(OUT, ROOT)}  {len(out):,}頭 / {sz/1024/1024:.1f}MB")

    # 検算: 東京・芝1600での成績が妥当な馬を1頭出す
    sample = next((n for n in out if out[n]["t"].get("東京")), None)
    if sample:
        print(f"例 {sample}: 場別={out[sample]['t']}  距離別={out[sample]['d']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
