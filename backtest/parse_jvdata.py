# -*- coding: utf-8 -*-
"""JV-Link で落とした蓄積系ダンプ（RA/SE/HR）を JSONL に変換する

★フィールド位置は仕様書ではなく実データから同定した★
  probe_se_layout.py / probe_hr_layout.py 参照。
  同定に使った制約:
    SE 確定着順(334) : レース内で 1..N の順列
    SE 単勝オッズ(359): 人気順に単調増加
    SE 単勝人気(363) : レース内で 1..N の順列
    HR 単勝(102)     : 勝ち馬の馬番 + 払戻額が SE のオッズ×100 と一致（200/200）
  さらに --verify で「馬連の組=着順上位2頭」「3連単の組=上位3頭の順序通り」を
  照合する。ここがずれていたら位置が間違っているので必ず落ちる。

出力 1行 = 1レース:
  {"rid","date","jyo","race","tosu","entries":[{u,fin,odds,pop}],"pay":{...}}

使い方:
  python parse_jvdata.py jvdata/race_2025.txt jvdata/race_2026.txt -o jra_races.jsonl
"""
import argparse, collections, json, os, sys

SE_KEY, SE_UMA, SE_FIN, SE_ODDS, SE_POP = slice(11, 27), slice(28, 30), slice(334, 336), slice(359, 363), slice(363, 365)
RA_KEY = slice(11, 27)

# HR: (先頭位置, 件数, 組の桁数, 1件の長さ)。払戻9桁・人気は残り
HR_BLOCKS = [
    ("tan",   102, 3, 2, 13),   # 単勝
    ("fuku",  141, 5, 2, 13),   # 複勝
    ("waku",  206, 3, 2, 13),   # 枠連
    ("umaren", 245, 3, 4, 16),  # 馬連
    ("wide",  293, 10, 4, 16),  # ワイド（★7枠ではなく10枠。ここを7と誤ると以降が全部ずれる）
    ("umatan", 453, 6, 4, 16),  # 馬単
    ("sanpuku", 549, 3, 6, 18), # 3連複  人気は3桁（最大816通り）
    # ★3連単だけ1件19バイト★ 組合せが最大4,896通りなので人気欄が4桁必要。
    #   18バイトで読むと2件目以降が1バイトずつずれ、1億円のような払戻が混入して
    #   全通り買いROIが1580%になった。603 + 6*19 = 717 でレコード長と一致する。
    ("santan", 603, 6, 6, 19),  # 3連単
]

JYO = {"01": "札幌", "02": "函館", "03": "福島", "04": "新潟", "05": "東京",
       "06": "中山", "07": "中京", "08": "京都", "09": "阪神", "10": "小倉"}


def parse_hr(rec):
    """券種ごとに [(組, 払戻円, 人気), ...] を返す。未確定(0円)は捨てる"""
    out = {}
    for name, base, cnt, kw, size in HR_BLOCKS:
        rows = []
        for i in range(cnt):
            p = base + i * size
            kumi = rec[p:p + kw].decode("ascii", "replace")
            pay = rec[p + kw:p + kw + 9]
            nin = rec[p + kw + 9:p + size]
            if not pay.isdigit():
                continue
            v = int(pay)
            if v == 0 or not kumi.strip():
                continue
            rows.append((kumi, v, int(nin) if nin.isdigit() else 0))
        out[name] = rows
    return out


def load(paths):
    """★SE は (レース, 馬番) で一意化する★
    JVOpen option=1 は FromTime 以降を丸ごと返すため、年をまたいで取ると
    ファイル間で期間が重なる。素朴に append すると同じ馬が2回入り、
    着順リストが壊れる（これで検証が落ちた。2026年分だけ全滅した）。
    """
    se_u = {}
    hr, ra = {}, {}
    for path in paths:
        with open(path, "rb") as f:
            for line in f:
                t = line[:2]
                if t == b"SE":
                    se_u[(line[SE_KEY], line[SE_UMA])] = line
                elif t == b"HR":
                    hr[line[SE_KEY]] = line
                elif t == b"RA":
                    ra[line[RA_KEY]] = line
    se = collections.defaultdict(list)
    for (key, _), line in se_u.items():
        se[key].append(line)
    return se, hr, ra


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("-o", "--out", default="jra_races.jsonl")
    ap.add_argument("--verify", action="store_true", help="組と着順の整合を照合する")
    args = ap.parse_args()

    se, hr, ra = load(args.files)
    print(f"読み込み: SE {sum(len(v) for v in se.values()):,}行 / HR {len(hr):,} / RA {len(ra):,}")

    n, skipped = 0, collections.Counter()
    vok, vng = collections.Counter(), collections.Counter()
    with open(args.out, "w", encoding="utf-8") as fo:
        for key in sorted(se):
            if key not in hr:
                skipped["払戻なし"] += 1
                continue
            k = key.decode()
            entries = []
            for r in se[key]:
                fin, odds, pop = r[SE_FIN], r[SE_ODDS], r[SE_POP]
                if not (fin.isdigit() and odds.isdigit() and pop.isdigit()):
                    continue          # 取消・除外
                f_, o_, p_ = int(fin), int(odds), int(pop)
                if f_ == 0:
                    continue
                entries.append({"u": r[SE_UMA].decode(), "fin": f_,
                                "odds": o_ / 10, "pop": p_})
            if len(entries) < 5:
                skipped["出走5頭未満"] += 1
                continue
            pay = parse_hr(hr[key])

            if args.verify:
                order = [e["u"] for e in sorted(entries, key=lambda e: e["fin"])]
                if pay["umaren"]:
                    exp = "".join(sorted(order[:2]))
                    (vok if pay["umaren"][0][0] == exp else vng)["馬連"] += 1
                if pay["umatan"]:
                    (vok if pay["umatan"][0][0] == order[0] + order[1] else vng)["馬単"] += 1
                if pay["santan"]:
                    (vok if pay["santan"][0][0] == "".join(order[:3]) else vng)["3連単"] += 1
                if pay["sanpuku"]:
                    exp = "".join(sorted(order[:3]))
                    (vok if pay["sanpuku"][0][0] == exp else vng)["3連複"] += 1
                if pay["tan"]:
                    (vok if pay["tan"][0][0] == order[0] else vng)["単勝"] += 1

                # ★1件目だけ見ていると2件目以降のずれを見逃す★
                #   3連単の1件19バイトを18と誤ったとき、1件目は正しく読めていた。
                #   全行について「組が出走馬番の重複なしの並び」であることを確かめる。
                live = {e["u"] for e in entries}
                for name, w in (("umaren", 2), ("wide", 2), ("umatan", 2),
                                ("sanpuku", 3), ("santan", 3)):
                    for kumi, yen, _ in pay[name]:
                        nums = [kumi[i * 2:i * 2 + 2] for i in range(w)]
                        bad = (len(set(nums)) != w or not set(nums) <= live
                               # 上限は「桁ずれの検出」用。実在の最高配当を弾かない値にする
                               # （2026-01-31 小倉3R の3連単 58,367,060円=人気4851/4896 は本物）
                               or not 100 <= yen <= 200_000_000)
                        (vng if bad else vok)["全行:" + name] += 1

            fo.write(json.dumps({
                "rid": k, "date": k[:8], "jyo": JYO.get(k[8:10], k[8:10]),
                "race": int(k[14:16]), "tosu": len(entries),
                "entries": entries, "pay": pay,
            }, ensure_ascii=False) + "\n")
            n += 1

    print(f"出力: {args.out}  {n:,}レース")
    for k, v in skipped.items():
        print(f"  スキップ {k}: {v:,}")
    if args.verify:
        print("\n=== 整合検証（組 vs 着順）===")
        for k in sorted(set(vok) | set(vng)):
            o, g = vok[k], vng[k]
            mark = "OK" if g == 0 else "NG"
            print(f"  [{mark}] {k:<6} 一致 {o:,} / 不一致 {g:,}")
        if sum(vng.values()):
            print("\n!! 不一致がある。フィールド位置が間違っている。使ってはいけない。")
            return 1
        print("\n全券種で組と着順が一致した。位置は正しい。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
