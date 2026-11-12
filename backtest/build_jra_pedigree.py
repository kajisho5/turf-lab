# -*- coding: utf-8 -*-
"""中央競馬の血統索引と馬検索データを作る

★地方のデータベースにあって中央に無いものを埋める★
  地方: 馬検索 / 騎手 / 調教師 / 種牡馬 / 母父
  中央: 騎手 / 調教師 / 馬主  ← 馬検索・種牡馬・母父が無かった

  血統は SE レコードに入っていない。TARGET の UM_DATA（馬マスタ）にある。

★UM（馬マスタ）の列位置は実データで同定した★
  レコード長 1609B。3代血統が 46バイト×14世代 で並ぶ。
    11-21   血統登録番号（SE の 30-40 と一致する。ここで結合する）
    38-46   生年月日
    46-82   馬名
    204-250 父   （先頭10桁は繁殖登録番号、名前は 214-250）
    250-296 母
    296-342 父父
    342-388 父母
    388-434 母父 （名前は 398-434）
  確認: 母父の上位が ディープインパクト / キングカメハメハ / ロードカナロア
        となり実態と一致した。

出力:
  backtest/jra_pedigree.json    血統登録番号 -> [馬名, 父, 母父, 生年, 性, 毛色]
  backtest/jra_sire_leading.json 種牡馬・母父リーディング
  deploy/db/jra/horses_search.json 馬検索の索引
"""
import collections
import glob
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UMDIR = r"C:\TFJV\UM_DATA"
DUMP = [os.path.join(ROOT, "backtest", "jvdata", "target_all.txt"),
        os.path.join(ROOT, "backtest", "jvdata", "setup_2026.txt")]
OUT_PED = os.path.join(ROOT, "backtest", "jra_pedigree.json")
OUT_SIRE = os.path.join(ROOT, "backtest", "jra_sire_leading.json")
OUT_SEARCH = os.path.join(ROOT, "deploy", "db", "jra", "horses_search.json")

UM_RL = 1609
U_KEY, U_BIRTH, U_NAME = slice(11, 21), slice(38, 46), slice(46, 82)
U_SIRE, U_DSIRE = slice(214, 250), slice(398, 434)
U_BREEDER = slice(890, 962)   # build_jra_breeder.py と同じオフセット（実データで同定済み）
# ★3代血統は 46バイト×14世代★ 先頭10桁が繁殖登録番号、残り36バイトが名前
PED_START, PED_STEP, PED_N = 204, 46, 14
PED_LABEL = ["父", "母", "父父", "父母", "母父", "母母",
             "父父父", "父父母", "父母父", "父母母",
             "母父父", "母父母", "母母父", "母母母"]
S_KEY, S_UMA, S_FIN, S_KETTO = slice(11, 27), slice(28, 30), slice(334, 336), slice(30, 40)
S_WAKU, S_JK = slice(27, 28), slice(306, 314)
S_WT, S_WD, S_POP = slice(324, 327), slice(327, 331), slice(363, 365)
H_KEY = slice(11, 27)
H_FUKU = (141, 5, 2, 13)
JYO = {f"{i:02d}" for i in range(1, 11)}
JYO_NAME = {"01": "札幌", "02": "函館", "03": "福島", "04": "新潟", "05": "東京",
            "06": "中山", "07": "中京", "08": "京都", "09": "阪神", "10": "小倉"}
# RA（レース詳細）: 競走名本題32-92 / 距離697-701 / トラック705-707 / 格付け614-615
R_KEY, R_NAME, R_DIST, R_TRACK, R_GRADE = (slice(11, 27), slice(32, 92), slice(697, 701),
                                             slice(705, 707), slice(614, 615))
ACTIVE_FROM = "20230101"        # 馬検索に載せるのは直近3年に走った馬
GRADE = {"A": "GI", "B": "GII", "C": "GIII",
          "D": "重賞", "F": "障害GI", "G": "障害GII", "H": "障害GIII"}
OUT_SIRE_DETAIL = os.path.join(ROOT, "deploy", "db", "jra", "s", "index.json")
OUT_DSIRE_DETAIL = os.path.join(ROOT, "deploy", "db", "jra", "ds", "index.json")


def surf_of(track):
    """トラックコード → 芝/ダ。障害・海外は空。"""
    try:
        t = int(track)
    except (TypeError, ValueError):
        return ""
    if 10 <= t <= 22:
        return "芝"
    if 23 <= t <= 29:
        return "ダ"
    return ""


def load_breeder_keys():
    """build_jra_breeder.py の出力キー集合。旧表記→統合後表記の対応に使う。

    ★ビツグレツドファーム↔ビッグレッドファームのような大書き/小書き仮名統合は
    br/index.json 側で既に済んでいる（証拠ベースの統合。build_jra_breeder.py参照）。
    馬詳細ページのリンク先が統合後の名前と食い違うとリンク切れになるため、
    ここでも同じ変換で統合後の表記に揃える。
    """
    p = os.path.join(ROOT, "deploy", "db", "jra", "br", "index.json")
    if not os.path.exists(p):
        return set()
    with open(p, encoding="utf-8") as f:
        return set(json.load(f).keys())


BIG2SMALL = str.maketrans("ツアイウエオヤユヨ", "ッァィゥェォャュョ")


def norm_breeder(name, keys):
    name = name.replace("フアーム", "ファーム")
    small = name.translate(BIG2SMALL)
    if small != name and small in keys:
        return small
    return name


def load_um():
    ped = {}
    keys = load_breeder_keys()
    fs = sorted(glob.glob(os.path.join(UMDIR, "**", "UM*.DAT"), recursive=True))
    for f in fs:
        b = open(f, "rb").read()
        if len(b) % UM_RL:
            continue
        for i in range(0, len(b), UM_RL):
            r = b[i:i + UM_RL]
            if r[:2] != b"UM":
                continue
            k = r[U_KEY].decode("ascii", "replace")
            if not k.isdigit():
                continue
            # 3代ぶん全部持つ（血統図に使う）
            gen = []
            for g in range(PED_N):
                q = PED_START + g * PED_STEP
                gen.append(r[q + 10:q + PED_STEP].decode("cp932", "replace").strip())
            breeder = r[U_BREEDER].decode("cp932", "replace").replace("　", " ").strip()
            ped[k] = [r[U_NAME].decode("cp932", "replace").strip(),
                      gen[0], gen[4],
                      r[U_BIRTH].decode("ascii", "replace")[:4],
                      gen,
                      norm_breeder(breeder, keys) if breeder else ""]
    print(f"  UM {len(fs)}本 → {len(ped):,}頭", flush=True)
    return ped


def fuku_of(rec):
    out = {}
    start, cnt, kd, ln = H_FUKU
    for i in range(cnt):
        p = start + i * ln
        k = rec[p:p + kd].decode("ascii", "replace").strip()
        y = rec[p + kd:p + kd + 9].decode("ascii", "replace").strip()
        if k and y.isdigit() and int(y) > 0:
            out[str(int(k))] = int(y)
    return out


def main():
    print("血統マスタを読む...", flush=True)
    ped = load_um()

    pays = {}
    races = {}                      # レースキー -> (競走名, 距離文字列)
    grades = {}                      # レースキー -> 格付け(GI/GII/GIII/重賞)
    field = collections.Counter()   # レースキー -> 出走頭数（実出走で数える）
    for path in DUMP:
        if os.path.exists(path):
            with open(path, "rb") as f:
                for line in f:
                    t = line[:2]
                    if t == b"HR":
                        pays[line[H_KEY]] = fuku_of(line)
                    elif t == b"RA":
                        nm = line[R_NAME].decode("cp932", "replace").strip()
                        nm = re.sub(r"競走$", "", nm)      # 末尾の「競走」を落とす
                        dist = line[R_DIST].decode("ascii", "replace").strip()
                        surf = surf_of(line[R_TRACK].decode("ascii", "replace"))
                        d = str(int(dist)) if dist.isdigit() and int(dist) else ""
                        races[line[R_KEY]] = (nm, (surf + d) if d else "")
                        g = line[R_GRADE].decode("ascii", "replace")
                        if g in GRADE:
                            grades[line[R_KEY]] = GRADE[g]
                    elif t == b"SE" and line[334:336].decode("ascii", "replace").strip().isdigit():
                        field[line[S_KEY]] += 1
    print(f"  払戻 {len(pays):,} / RA {len(races):,} / 重賞 {len(grades):,} / 頭数 {len(field):,}レース", flush=True)

    # 種牡馬・母父の集計 / 馬ごとの成績
    sire = collections.defaultdict(lambda: [0, 0, 0, 0])
    dsire = collections.defaultdict(lambda: [0, 0, 0, 0])
    # ★産駒の場別・年別・重賞内訳★ jockey/trainer/owner detail と同形式にして
    #   ページ生成(JOCKEY_JS)をそのまま使い回す。
    sire_d = collections.defaultdict(lambda: {
        "n": 0, "w": 0, "t3": 0, "ret": 0,
        "tr": collections.defaultdict(lambda: [0, 0, 0]),
        "yr": collections.defaultdict(lambda: [0, 0, 0]),
        "gr": collections.defaultdict(lambda: [0, 0])})
    dsire_d = collections.defaultdict(lambda: {
        "n": 0, "w": 0, "t3": 0, "ret": 0,
        "tr": collections.defaultdict(lambda: [0, 0, 0]),
        "yr": collections.defaultdict(lambda: [0, 0, 0]),
        "gr": collections.defaultdict(lambda: [0, 0])})
    horse = collections.defaultdict(lambda: [0, 0, 0, 0, ""])   # n,win,top3,ret,最終出走日
    runs = collections.defaultdict(list)                        # 血統番号 -> 走記録
    miss = 0

    for path in DUMP:
        if not os.path.exists(path):
            continue
        with open(path, "rb") as f:
            for line in f:
                if line[:2] != b"SE":
                    continue
                k = line[S_KEY]
                if k[8:10].decode("ascii", "replace") not in JYO:
                    continue
                fin = line[S_FIN].decode("ascii", "replace").strip()
                if not fin.isdigit():
                    continue
                rk = int(fin)
                kt = line[S_KETTO].decode("ascii", "replace")
                p = ped.get(kt)
                if not p:
                    miss += 1
                    continue
                uma = str(int(line[S_UMA].decode("ascii", "replace") or 0))
                ret = (pays.get(k) or {}).get(uma, 0)
                d = k[:8].decode()
                jyo = k[8:10].decode()

                e = horse[kt]
                e[0] += 1
                e[1] += (rk == 1)
                e[2] += (rk <= 3)
                e[3] += ret
                if d > e[4]:
                    e[4] = d
                # ★1走の記録は地方バッグと同じ15列にそろえる★（馬詳細で統合表示するため）
                #   [0日付 1場 2R 3レース名 4頭数 5枠 6馬番 7人気 8着順
                #    9騎手 10斤量 11馬体重 12増減 13複勝払戻 14距離]
                rname, dist = races.get(k, ("", ""))
                jk = line[S_JK].decode("cp932", "replace").strip()
                wt = line[S_WT].decode("ascii", "replace").strip()
                wd = line[S_WD].decode("ascii", "replace").strip()
                pop = line[S_POP].decode("ascii", "replace").strip()
                runs[kt].append([d, JYO_NAME.get(jyo, jyo), int(k[14:16]), rname,
                                 int(field.get(k, 0)), int(line[S_WAKU] or 0), int(uma),
                                 int(pop or 0), rk, jk, "", wt, wd, ret, dist])
                if len(runs[kt]) > 80:
                    runs[kt] = runs[kt][-80:]

                for name, tbl in ((p[1], sire), (p[2], dsire)):
                    if not name:
                        continue
                    t = tbl[name]
                    t[0] += 1
                    t[1] += (rk == 1)
                    t[2] += (rk <= 3)
                    t[3] += ret

                trk_name = JYO_NAME.get(jyo, jyo)
                grd = grades.get(k)
                for name, dtbl in ((p[1], sire_d), (p[2], dsire_d)):
                    if not name:
                        continue
                    e2 = dtbl[name]
                    e2["n"] += 1
                    e2["w"] += (rk == 1)
                    e2["t3"] += (rk <= 3)
                    e2["ret"] += ret
                    tt = e2["tr"][trk_name]
                    tt[0] += 1; tt[1] += (rk == 1); tt[2] += (rk <= 3)
                    yy = e2["yr"][d[:4]]
                    yy[0] += 1; yy[1] += (rk == 1); yy[2] += (rk <= 3)
                    if grd:
                        gg = e2["gr"][grd]
                        gg[0] += 1; gg[1] += (rk == 1)
        print(f"  読了 {os.path.basename(path)}", flush=True)

    print(f"\n血統が引けなかった出走 {miss:,}")
    with open(OUT_SIRE, "w", encoding="utf-8") as f:
        json.dump({"sire": dict(sire), "damsire": dict(dsire)}, f,
                  ensure_ascii=False, separators=(",", ":"))

    # ★種牡馬・母父の詳細（場別/年別/重賞）★ jockey/trainer/ownerと同形式で出力
    def finalize_detail(dtbl, minimum=30):
        out = {}
        for name, e in dtbl.items():
            if e["n"] < minimum:
                continue
            out[name] = {
                "n": e["n"], "w": e["w"], "t3": e["t3"],
                "roi": round(100 * e["ret"] / (100 * e["n"]), 1),
                "tr": {kk: v for kk, v in sorted(e["tr"].items(), key=lambda x: -x[1][0])},
                "yr": {kk: v for kk, v in sorted(e["yr"].items())},
                "gr": {kk: v for kk, v in sorted(e["gr"].items(), key=lambda x: -x[1][1])},
            }
        return out

    sire_detail_out = finalize_detail(sire_d)
    dsire_detail_out = finalize_detail(dsire_d)
    os.makedirs(os.path.dirname(OUT_SIRE_DETAIL), exist_ok=True)
    os.makedirs(os.path.dirname(OUT_DSIRE_DETAIL), exist_ok=True)
    with open(OUT_SIRE_DETAIL, "w", encoding="utf-8") as f:
        json.dump(sire_detail_out, f, ensure_ascii=False, separators=(",", ":"))
    with open(OUT_DSIRE_DETAIL, "w", encoding="utf-8") as f:
        json.dump(dsire_detail_out, f, ensure_ascii=False, separators=(",", ":"))
    print(f"出力: {os.path.relpath(OUT_SIRE_DETAIL, ROOT)}  種牡馬詳細{len(sire_detail_out):,}")
    print(f"出力: {os.path.relpath(OUT_DSIRE_DETAIL, ROOT)}  母父詳細{len(dsire_detail_out):,}")
    gi_top = sorted(sire_detail_out.items(), key=lambda x: -x[1]["gr"].get("GI", [0, 0])[1])[:5]
    print("  種牡馬 産駒GI勝利数トップ5:")
    for n, e in gi_top:
        gi = e["gr"].get("GI", [0, 0])
        print(f"    {n}: GI {gi[1]}勝/{gi[0]}出走")
    print(f"出力: {os.path.relpath(OUT_SIRE, ROOT)}  種牡馬{len(sire):,} 母父{len(dsire):,}")

    # 馬検索の索引（地方版と同じ並びにする。列を揃えないと画面を作り分けることになる）
    # [馬名, 父, 母父, 毛色, 性, 生年, 出走, 勝利, 複勝率%, 複ROI%, 主戦場, 所属, 最終出走日]
    rows = []
    for kt, (n, win, t3, ret, last) in horse.items():
        if last < ACTIVE_FROM or n < 1:
            continue
        p = ped.get(kt)
        if not p:
            continue
        rows.append([p[0], p[1], p[2], "", "", p[3], n, win,
                     round(100 * t3 / n), round(100 * ret / (100 * n)),
                     "", "JRA", last])
    rows.sort(key=lambda x: -x[6])

    # ★血統図＋戦績を袋に分けて書き出す★
    #   地方と同じく馬名のMD5先頭2桁で256分割（同じページで読めるようにする）
    import hashlib
    buckets = collections.defaultdict(dict)
    for kt, (n, win, t3, ret, last) in horse.items():
        if last < ACTIVE_FROM:
            continue
        p2 = ped.get(kt)
        if not p2:
            continue
        nm = p2[0]
        rs = sorted(runs.get(kt, []), reverse=True)
        buckets[hashlib.md5(nm.encode("utf-8")).hexdigest()[:2]][nm] = {
            "p": [p2[3], p2[1], p2[2], p2[5]],  # 生年, 父, 母父, 生産者
            "g": p2[4],                          # 3代血統14頭
            "r": rs,
        }
    outh = os.path.join(ROOT, "deploy", "db", "jra", "h")
    os.makedirs(outh, exist_ok=True)
    tot = 0
    for b, dct in buckets.items():
        fp = os.path.join(outh, f"{b}.json")
        with open(fp, "w", encoding="utf-8") as f:
            json.dump(dct, f, ensure_ascii=False, separators=(",", ":"))
        tot += os.path.getsize(fp)
    print(f"出力: deploy/db/jra/h/  {len(buckets)}袋 / "
          f"{sum(len(d) for d in buckets.values()):,}頭 / {tot/1024/1024:.1f}MB")
    os.makedirs(os.path.dirname(OUT_SEARCH), exist_ok=True)
    with open(OUT_SEARCH, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, separators=(",", ":"))
    sz = os.path.getsize(OUT_SEARCH)
    print(f"出力: {os.path.relpath(OUT_SEARCH, ROOT)}  "
          f"全{len(horse):,}頭 → 直近 {len(rows):,}頭 / {sz/1024/1024:.1f}MB")

    # 検算
    top = sorted(sire.items(), key=lambda x: -x[1][1])[:6]
    print("\n種牡馬リーディング（通算勝利数）※ディープ・キンカメ・サンデーが上位なら妥当")
    for name, (n, w, t3, ret) in top:
        print(f"  {name:<16} {n:>7,}戦 {w:>5,}勝  複勝率{100*t3/n:>5.1f}%  複ROI{100*ret/(100*n):>6.1f}%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
