# -*- coding: utf-8 -*-
"""JRA-VAN（JV-Link）のダンプから、netkeiba と同じ書き方の出馬表ページを作る

設計: docs/design/JRA_VAN_PIPELINE_DESIGN.md の案1
  採点には一切さわらない。入口（出馬表ページ）だけを自前で作って差し替える。

作るもの（url → html）
  https://race.netkeiba.com/race/shutuba_past.html?race_id=RID   … 各馬の過去5走つき
  https://race.netkeiba.com/top/race_list_sub.html?kaisai_date=YYYYMMDD … 開催一覧

使い方
  python jra_make_pages.py --date 20261122 --dump DUMP... [--pedigree ped.json] -o OUTDIR
    OUTDIR/pages.json に {url: html} を書く（生データはここに置かない・リポに入れない）

★JV-Data のバイト位置は実データで確かめたもの（2026-11-22）★
  SE: 枠番28 馬番29-30 血統登録番号30:40 馬名40:76 性別78 馬齢82:84 東西84
      調教師コード85:90 調教師名略称90:98 負担重量288:291 ブリンカー294
      騎手コード296:301 騎手名略称306:314 馬体重324:327 増減327:331 異常区分331
      確定着順334:336 走破タイム338:342 1-4角351:359 単勝オッズ359:363 人気363:365
      後3F 390:393
  RA: 競走名32:92 重賞回次611:614 グレード614 競走種別616:618 重量種別621
      競走条件コード(2歳..最若年 3桁×5)622:637 距離697:701 トラック705:707
      発走時刻873:877 登録頭数881:883 出走頭数883:885 入線頭数885:887
"""
import argparse
import unicodedata
import collections
import html
import json
import os
import re
import sys

JYO = {"01": "札幌", "02": "函館", "03": "福島", "04": "新潟", "05": "東京",
       "06": "中山", "07": "中京", "08": "京都", "09": "阪神", "10": "小倉"}
KUBUN_RANK = {b"0": 0, b"9": 0, b"1": 1, b"2": 2, b"3": 3, b"4": 4, b"5": 5, b"6": 6,
              b"7": 7, b"A": 8, b"B": 9}
SEX = {b"1": "牡", b"2": "牝", b"3": "セ"}
TOZAI = {b"1": "美浦", b"2": "栗東", b"3": "地方", b"4": "海外"}
GRADE_ICON = {"A": 1, "B": 2, "C": 3, "D": 4, "F": 5}   # G1,G2,G3,重賞,Listed


NAMES_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "jra_names.json")


def load_names(path=NAMES_PATH):
    """騎手・調教師のコード → netkeiba の表記。JV の略称は netkeiba と書き方が違う（古川吉洋→古川吉）"""
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
    except Exception:
        d = {}
    d.setdefault("j", {})
    d.setdefault("t", {})
    return d


def learn_names(html_paths, path=NAMES_PATH):
    """本物の出馬表ページから、コード→表記を覚える（増えるだけ・消さない）"""
    d = load_names(path)
    n0 = len(d["j"]) + len(d["t"])
    for hp in html_paths:
        h = open(hp, encoding="utf-8", errors="replace").read()
        for code, nm in re.findall(r'/jockey/(?:result/recent/)?(\w{4,6})/?"[^>]*>\s*([^<]{1,16}?)\s*<', h):
            if nm and code != "result":
                d["j"][code] = nm
        for code, nm in re.findall(r'/trainer/(?:result/recent/)?(\w{4,6})/?"[^>]*>\s*([^<]{1,20}?)\s*<', h):
            if nm and code != "result" and "・" in nm:
                d["t"][code] = nm.split("・", 1)[1].strip().replace("&nbsp;", "")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=0, sort_keys=True)
    return len(d["j"]) + len(d["t"]) - n0


def load_um(paths, ped=None):
    """UM（競走馬マスタ）レコード(1609バイト)から 血統登録番号 → 父・母父 を作る
    位置は build_jra_pedigree.py が実データで同定したもの: 登録番号11:21 / 父名214:250 / 母父名398:434
    ファイルは JV-Link のダンプ（1行1レコード）でも TARGET の UM*.DAT（連結）でも読める"""
    ped = {} if ped is None else ped
    for p in paths:
        b = open(p, "rb").read()
        recs = []
        if len(b) % 1609 == 0 and b[:2] == b"UM":
            recs = [b[i:i + 1609] for i in range(0, len(b), 1609)]
        else:
            recs = [ln for ln in b.split(b"\n") if ln[:2] == b"UM" and len(ln) >= 434]
        for r in recs:
            if r[:2] != b"UM" or len(r) < 434:
                continue
            hid = r[11:21].decode("ascii", "replace")
            if not hid.isdigit():
                continue
            ped[hid] = {"sire": s(r[214:250]).replace(" ", ""), "damsire": s(r[398:434]).replace(" ", "")}
    return ped


def s(b):
    """cp932 の固定長欄を文字列にして、前後の（全角含む）空白を取る"""
    return b.decode("cp932", "replace").replace("　", " ").strip()


def num(b):
    t = b.decode("ascii", "replace").strip()
    return int(t) if t.isdigit() else None


def load(paths):
    """RA/SE を読む。同じ（レース,馬番）は、確定に近い区分のものを残す"""
    ra, se = {}, {}
    for p in paths:
        with open(p, "rb") as f:
            for line in f:
                t = line[:2]
                if t == b"RA" and len(line) > 890:
                    k = line[11:27]
                    r = KUBUN_RANK.get(line[2:3], 0)
                    if k not in ra or r >= ra[k][0]:
                        ra[k] = (r, line)
                elif t == b"SE" and len(line) > 400:
                    k = (line[11:27], line[28:30])
                    r = KUBUN_RANK.get(line[2:3], 0)
                    if k not in se or r >= se[k][0]:
                        se[k] = (r, line)
    return ra, se


def rid_of(key):
    """JV のレースキー(年月日場回日R 16桁) → netkeiba の race_id(年場回日R 12桁)"""
    k = key.decode("ascii")
    return k[:4] + k[8:16]


def race_info(line):
    key = line[11:27].decode("ascii")
    d = {
        "key": key, "date": key[:8], "jyo": key[8:10], "kai": key[10:12], "nichi": key[12:14],
        "r": int(key[14:16]), "rid": key[:4] + key[8:16],
        "name": s(line[32:92]),
        "short": unicodedata.normalize("NFKC", s(line[592:604])),
        "grade": line[614:615].decode("ascii", "replace").strip(),
        "shubetsu": line[616:618].decode("ascii", "replace"),
        "jouken": [line[622 + 3 * i:625 + 3 * i].decode("ascii", "replace") for i in range(5)],
        "dist": num(line[697:701]),
        "track": num(line[705:707]),
        "post": line[873:877].decode("ascii", "replace"),
        "toroku": num(line[881:883]), "shusso": num(line[883:885]), "nyusen": num(line[885:887]),
        "turf_going": line[888:889].decode("ascii", "replace"),
        "dirt_going": line[889:890].decode("ascii", "replace"),
    }
    t = d["track"] or 0
    d["surf"] = "芝" if 10 <= t <= 22 else ("ダ" if 23 <= t <= 29 else ("障" if 51 <= t <= 59 else None))
    return d


def cond_code(d):
    j = [x for x in d["jouken"] if x not in ("000", "   ")]
    youngest = d["jouken"][4]
    return youngest if youngest not in ("000", "   ") else (j[0] if j else "")


def class_text(d):
    """レース名が無い（条件戦）ときの表示。netkeiba の書き方に合わせる（年齢＋クラス）"""
    if d["name"]:
        return d["short"] or d["name"]
    age = {"11": "2歳", "12": "3歳", "13": "3歳以上", "14": "4歳以上"}.get(d["shubetsu"], "")
    lab = {"701": "新馬", "703": "未勝利", "005": "1勝クラス", "010": "2勝クラス",
           "016": "3勝クラス", "999": "オープン"}.get(cond_code(d))
    return age + lab if lab else age


def grade_icon(d):
    """netkeiba の Icon_GradeType 番号と表示。
    ★1=GI 2=GII 3=GIII 5=OP/L 16=3勝 17=2勝 18=1勝（本物のページから確認）。
      名前のある条件戦だけに付く。読み取り側は先頭1桁で級を見るため 16〜18 は GI 扱いになる（本物と同じ挙動なのでそのまま写す）"""
    g = d["grade"]
    if g in ("A", "B", "C"):
        n = {"A": 1, "B": 2, "C": 3}[g]
        return n, ["", "GI", "GII", "GIII"][n]
    if not d["name"]:
        return None
    if g == "F":
        return 5, "L"
    c = cond_code(d)
    if c == "999":
        return 5, "OP"
    return {"016": (16, "3勝"), "010": (17, "2勝"), "005": (18, "1勝")}.get(c)


GOING = {"1": "良", "2": "稍", "3": "重", "4": "不"}


def time_text(b):
    t = b.decode("ascii", "replace")
    if not t.isdigit() or int(t) == 0:
        return ""
    return "%d:%02d.%d" % (int(t[0]), int(t[1:3]), int(t[3]))


def passing_text(line):
    cs = [num(line[351 + 2 * i:353 + 2 * i]) for i in range(4)]
    cs = [c for c in cs if c]
    return "-".join(str(c) for c in cs)


def past_cell(ra_line, se_line, nfield_fallback=None):
    d = race_info(ra_line)
    fin = num(se_line[334:336])
    abnorm = se_line[331:332]
    if fin and fin > 0:
        rank = str(fin)
    else:
        rank = {b"1": "取", b"2": "除", b"3": "除", b"4": "中", b"5": "失", b"6": "落"}.get(abnorm, "中")
    nfield = d["nyusen"] or d["shusso"] or nfield_fallback or ""
    uma = num(se_line[28:30])
    pop = num(se_line[363:365])
    kin = num(se_line[288:291])
    jockey = s(se_line[306:314]).replace(" ", "")
    d3 = "%s頭&nbsp;%s番&nbsp;%s人 %s %s" % (nfield, uma, pop if pop else "", jockey,
                                          ("%.1f" % (kin / 10)) if kin else "")
    ttxt = time_text(se_line[338:342])
    surf = d["surf"] or ""
    going = GOING.get(d["turf_going"] if surf == "芝" else d["dirt_going"], "")
    d5 = "%s%s %s" % (surf, d["dist"] or "", ttxt)
    l3 = num(se_line[390:393])
    d6 = "%s&nbsp;(%s)" % (passing_text(se_line), ("%.1f" % (l3 / 10)) if l3 else "0.0")
    wt = num(se_line[324:327])
    if wt:
        sg = se_line[327:328].decode("ascii", "replace")
        df = num(se_line[328:331]) or 0
        d6 += "&nbsp;%d(%s%d)" % (wt, "-" if sg == "-" else "+", df) if df else "&nbsp;%d(0)" % wt
    gi = grade_icon(d)
    icon = ('<span class="Icon_GradeType Icon_GradeType%d">%s</span>' % gi) if gi else ""
    y, m, dd = d["date"][:4], d["date"][4:6], d["date"][6:8]
    cls = ""
    if fin and 1 <= fin <= 3:
        cls = " Ranking_%d" % fin
    return (
        '<td class="Past%s" id="myhorse_%s">\n<div class="Data_Item">\n<div class="Data01">\n'
        '<span>%s.%s.%s&nbsp;%s</span>\n<span class="Num">%s</span>\n</div>\n'
        '<div class="Data02">\n<a href="https://db.netkeiba.com/race/%s">%s\n%s\n</a>\n</div>\n'
        '<div class="Data05">%s <strong>%s</strong></div>\n<div class="Data03">%s</div>\n'
        '<div class="Data06">%s</div>\n</div>\n</td>\n'
    ) % (cls, d["rid"], y, m, dd, JYO.get(d["jyo"], d["jyo"]), rank, d["rid"],
         html.escape(class_text(d)), icon, d5, going, d3, d6)


def horse_row(se_line, past_html, ped, names=None):
    names = names or {"j": {}, "t": {}}
    hid = se_line[30:40].decode("ascii")
    waku = se_line[27:28].decode("ascii")
    uma = int(se_line[28:30])
    name = html.escape(s(se_line[40:76]))
    sex = SEX.get(se_line[78:79], "")
    age = num(se_line[82:84])
    tz = TOZAI.get(se_line[84:85], "")
    tcode = se_line[85:90].decode("ascii")
    tname = html.escape(names["t"].get(tcode) or s(se_line[90:98]).replace(" ", ""))
    jcode = se_line[296:301].decode("ascii")
    jname = html.escape(names["j"].get(jcode) or s(se_line[306:314]).replace(" ", ""))
    mk = se_line[76:78]
    belong_icon = ('<span class="Icon_HorseMark Icon_MaruChi"></span>' if mk == b"05" else
                   ('<span class="Icon_HorseMark Icon_MaruGai"></span>' if mk == b"06" else ""))
    kin = num(se_line[288:291])
    blinker = se_line[294:295] == b"1"
    p = ped.get(hid) or {}
    sire, dam = p.get("sire") or "", p.get("damsire") or ""
    mark = '<span class="Mark">B</span>' if blinker else ""
    return (
        '<tr class="HorseList" id="tr_%d">\n<td class="Waku%s">%s</td>\n<td class="Waku">%d</td>\n'
        '<td class="Horse_Info" id="Horse_Info_Data">\n<div class="fc">\n'
        '<div class="Horse01 fc">%s</div>\n<div class="Horse02">\n'
        '<a href="https://db.netkeiba.com/horse/%s" target="_blank">%s%s</a>%s\n</div>\n'
        '<div class="Horse04">%s</div>\n'
        '<div class="Horse05"><a href="https://db.netkeiba.com/trainer/result/recent/%s" target="_blank">%s・%s</a>&nbsp;&nbsp;</div>\n'
        '</div>\n</td>\n<td class="Jockey">\n<span class="Barei">%s%s</span>\n'
        '<a href="https://db.netkeiba.com/jockey/result/recent/%s" target="_blank">%s</a><br />\n'
        '<span>%s</span>\n</td>\n%s</tr>\n'
    ) % (uma, waku, waku, uma, html.escape(sire), hid, belong_icon, name, mark,
         ("(%s)" % html.escape(dam)) if dam else "", tcode, tz, tname, sex, age if age is not None else "",
         jcode, jname, ("%.1f" % (kin / 10)) if kin else "", past_html)


def build(date, paths, ped, names=None):
    names = names or load_names()
    ra, se = load(paths)
    # 馬ごとの過去走（確定成績のあるものだけ）
    hist = collections.defaultdict(list)
    for (key, _), (r, line) in se.items():
        if r >= 7:
            hid = line[30:40].decode("ascii", "replace")
            hist[hid].append((key.decode("ascii"), line))
    for h in hist:
        hist[h].sort(reverse=True)
    pages, races = {}, []
    for key, (r, rl) in sorted(ra.items()):
        if key[:8].decode() != date or KUBUN_RANK.get(rl[2:3], 0) >= 7 and False:
            continue
        if key[:8].decode() != date:
            continue
        d = race_info(rl)
        if d["jyo"] not in JYO:
            continue
        entries = sorted([ln for (k, _), (rr, ln) in se.items() if k == key], key=lambda l: int(l[28:30]))
        # 枠順が決まっていない（馬番00）ものは作らない
        entries = [l for l in entries if num(l[28:30])]
        if not entries or any(l[27:28] in (b"0", b" ") for l in entries):
            continue
        # 出走取消・除外（異常区分1,2,3）は netkeiba と同様、行を残して取消の印をつける対応は後で
        rows = []
        for l in entries:
            hid = l[30:40].decode("ascii", "replace")
            cells = []
            for k2, hl in hist.get(hid, []):
                if k2 >= key.decode():
                    continue
                rk = ra.get(k2.encode())
                if not rk:
                    continue
                cells.append(past_cell(rk[1], hl))
                if len(cells) >= 5:
                    break
            rows.append(horse_row(l, "".join(cells), ped, names))
        nm = html.escape(class_text(d))
        gi = GRADE_ICON.get(d["grade"])
        gicon = ('<span class="Icon_GradeType Icon_GradeType%d"></span>' % gi) if gi and gi <= 3 else ""
        post = "%s:%s" % (d["post"][:2], d["post"][2:]) if d["post"].isdigit() else ""
        page = (
            '<!DOCTYPE html>\n<html>\n<head><meta charset="utf-8"></head>\n<body>\n'
            '<div class="RaceList_Item02">\n<h1 class="RaceName">%s%s</h1>\n'
            '<div class="RaceData01">\n%s発走 /<span> %s%sm</span>\n</div>\n'
            '<div class="RaceData02">\n<span>%s回</span>\n<span>%s</span>\n<span>%s日目</span>\n'
            '<span>%d頭</span>\n</div>\n</div>\n'
            '<table class="Shutuba_Table"><tbody>\n%s</tbody></table>\n</body>\n</html>\n'
        ) % (nm, gicon, post, d["surf"] or "", d["dist"] or "", int(d["kai"]), JYO[d["jyo"]],
             int(d["nichi"]), len(entries), "".join(rows))
        pages["https://race.netkeiba.com/race/shutuba_past.html?race_id=" + d["rid"]] = page
        races.append(d)
    # 開催一覧
    items = []
    for d in sorted(races, key=lambda x: (x["jyo"], x["r"])):
        gi = GRADE_ICON.get(d["grade"])
        gicon = ('<span class="Icon_GradeType Icon_GradeType%d"></span>' % gi) if gi and gi <= 3 else ""
        post = "%s:%s" % (d["post"][:2], d["post"][2:]) if d["post"].isdigit() else ""
        items.append(
            '<li class="RaceList_DataItem">\n<a href="../race/shutuba.html?race_id=%s">\n'
            '<div class="Race_Num"><span>%dR</span></div>\n<div class="RaceList_ItemContent">\n'
            '<div class="RaceList_ItemTitle"><span class="ItemTitle">%s</span>%s</div>\n'
            '<div class="RaceData"><span class="RaceList_Itemtime">%s</span>'
            '<span class="RaceList_ItemLong">%s%sm</span><span class="RaceList_Itemnumber">%d頭</span></div>\n'
            '</div>\n</a>\n</li>\n' % (d["rid"], d["r"], html.escape(class_text(d)), gicon, post,
                                       d["surf"] or "", d["dist"] or "", d["shusso"] or d["toroku"] or 0))
    if items:
        pages["https://race.netkeiba.com/top/race_list_sub.html?kaisai_date=" + date] = (
            '<ul>\n' + "".join(items) + '</ul>\n')
    return pages, races


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date")
    ap.add_argument("--dump", nargs="*")
    ap.add_argument("--learn", nargs="+", help="本物の出馬表ページ(html)から騎手・調教師の表記を覚える")
    ap.add_argument("--pedigree")
    ap.add_argument("--um", nargs="*", help="UM（競走馬マスタ）のダンプ。父・母父をここから引く")
    ap.add_argument("-o", "--outdir")
    a = ap.parse_args()
    if a.learn:
        print("覚えた表記 +%d 件" % learn_names(a.learn))
        return
    if not (a.date and a.dump):
        ap.error("--date と --dump が要る")
    if not a.outdir:
        ap.error("-o が要る")
    ped = json.load(open(a.pedigree, encoding="utf-8")) if a.pedigree and os.path.exists(a.pedigree) else {}
    if a.um:
        load_um(a.um, ped)
    pages, races = build(a.date, a.dump, ped)
    os.makedirs(a.outdir, exist_ok=True)
    with open(os.path.join(a.outdir, "pages.json"), "w", encoding="utf-8") as f:
        json.dump({"date": a.date, "pages": pages}, f, ensure_ascii=False)
    print("作ったレース %d  ページ %d" % (len(races), len(pages)))


if __name__ == "__main__":
    main()
