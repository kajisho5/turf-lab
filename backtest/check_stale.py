# -*- coding: utf-8 -*-
"""生成物が入力データより古くないかを見る

★これが無くて2回やらかした★
  1. 中央データを1年分→13.9万レースに増やしたのに /data/jra/ が古いまま残り、
     「中央1年 vs 地方13年」を同じ式で比べたと書いていた。
     しかも1年分では結論が逆になる券種があった（3連複 47.7%→54.6%）。
  2. 検証で偽物と判定して人格を4つ削除したのに、紹介ページ /ai/ には
     「内枠」「馬体重」「差し追込型」「キャリア」が残ったままだった。

  どちらも「データを更新したら、それを読んでいる生成物を全部たどる」を
  やらなかったのが原因。覚えているだけでは抜けるので機械に見せる。

使い方:
  python backtest/check_stale.py          # 古い生成物を一覧
  python backtest/check_stale.py --fix    # 古いものだけ作り直す
"""
import argparse
import glob
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 生成物が依存しうるデータ。ここに載っていないと検出できない。
# ★具体的なファイル名（拡張子つき）だけを見る★
#   最初 "nardata" をフォルダ名で拾っていたため、そのフォルダに無関係な
#   ファイル（ばんえいデータ・索引）を足しただけで record ページが「古い」と
#   誤検出された。中身の予想データは変わっていないのに誤爆する。
#   フォルダ名(pred_data/nardata)ではなく、参照される .jsonl/.json に限定する。
#   ★2026-07-27拡張★ 「要目視確認」に15個の生成器が並び続けていた
#   （birthday_bet_stats.json 等が固定リストに無いため）。実害として、
#   bt_all.jsonl を作り直しても誕生日ページの入力は追跡されず、
#   ページが古い件数（176,054レース）を出したままだった。
#   *_stats.json 系はここで一括で拾う。generic な index.json は
#   どこにでもあり誤検出するので、あえて拾わない。
DATA_HINT = re.compile(
    r'["\']([\w/\.]*(?:bt_all|bt_jra|jra_all|jra_races|jra_nar_compare|'
    r'jra_leading|jra_sire_leading|jra_pedigree|'
    r'horses_search|target_all|'
    r'\w*_stats|jockey_rules|front_value|roi_mine2|memo_data|'
    r'jockey_change|trainer_change|jra_combo|nar_combo|'
    r'jra_trainer_homeaway|nar_trainer_homeaway)\.jsonl?)["\']')

# ★フォルダ丸ごとが入力の場合★（pred_data等・日付ごとに個別ファイルが積まれる形）
#   単一ファイル名の正規表現では拾えないため別枠で扱う。
#   nardata等の雑多フォルダと違い、pred_data配下は予想データの.jsonのみ＝
#   フォルダ丸ごとの最新更新日時を「入力の新しさ」として使っても誤検出しない
#   （コメント参照: フォルダ名で拾うと事故った過去があるため、対象は個別に絞る）。
DIR_HINT = re.compile(r'os\.path\.join\(ROOT,\s*"backtest",\s*"store",\s*"pred_data"\)')


def newest_in_dir(path, pattern="*.json"):
    files = glob.glob(os.path.join(path, pattern))
    return max(files, key=os.path.getmtime) if files else None


# ★DATA_HINT/DIR_HINTの対象漏れを見つけるための緩い検出★
#   pred_data（gen_record_page.py）が1ヶ月古いまま公開され続けたのは、
#   DATA_HINTの固定リストに載っていない入力だったため。同じ穴が他の
#   gen_*.pyにも無いか、「.json/.jsonlへの参照はあるのに厳密なDATA_HINT/
#   DIR_HINTのどちらにも拾われていない」ケースを警告として出す
#   （自動判定はしない＝誤検出を避けるため、目視確認を促すだけ）。
LOOSE_DATA_REF = re.compile(r'["\']([\w/\.\-]+\.jsonl?)["\']')


def loose_refs(src):
    return {m.group(1) for m in LOOSE_DATA_REF.finditer(src)
            if "deploy" not in m.group(1)}


def resolve(rel):
    # ★nardata/配下も探索する★ gen_data_page.py等は
    #   os.path.join(ROOT, "backtest", "nardata", "bt_all.jsonl") のように
    #   3引数に分けて書くため、DATA_HINTは末尾の"bt_all.jsonl"だけを拾う。
    #   nardata/を探索パスに足さないと常に見つからず「未検知」のまま残った
    #   （2026-07-24、pred_data検知漏れの調査中に発覚）。
    for c in (rel.replace("/", os.sep),
              os.path.join("backtest", rel.replace("/", os.sep)),
              os.path.join("backtest", "nardata", rel.replace("/", os.sep))):
        p = os.path.join(ROOT, c)
        if os.path.exists(p):
            return p
    return None


def outputs_of(src):
    """OUT... = os.path.join(ROOT, "deploy", ...) の形を拾う"""
    out = []
    for m in re.finditer(r'OUT\w*\s*=\s*os\.path\.join\(ROOT,\s*(.*?)\)', src):
        parts = re.findall(r'"([^"]+)"', m.group(1))
        if parts and parts[0] == "deploy":
            out.append(os.path.join(ROOT, *parts))
    # ★画像も見る★ OGPは card(os.path.join(out, "ogp.png"), ...) の形で
    #   OUT変数を通らないため検出できず、古い数字のまま公開されていた。
    for m in re.finditer(r'card\(os\.path\.join\((\w+)(.*?)\)', src):
        parts = re.findall(r'"([^"]+)"', m.group(2))
        if parts and parts[-1].endswith(".png"):
            out.append(os.path.join(ROOT, "deploy", "data", *parts))
    return out


def out_mtime(o):
    """出力の新しさ。★ディレクトリは中の最新ファイルを見る★

    gen_articles.py の OUTDIR のように、出力がフォルダのことがある。
    フォルダの mtime は「直下にファイルを足し引きした時」しか動かないため、
    中身を全部作り直しても古いままになり、--fix を回しても
    永久に「古い」と言い続ける偽陽性になっていた（2026-07-27発覚）。
    赤が消えないチェックは、そのうち誰も見なくなるので必ず直す。
    """
    if not os.path.isdir(o):
        return os.path.getmtime(o)
    ts = [os.path.getmtime(os.path.join(r, f))
          for r, _, fs in os.walk(o) for f in fs]
    return max(ts) if ts else os.path.getmtime(o)


def scan():
    stale, missing, unrecognized = [], [], []
    for g in sorted(glob.glob(os.path.join(ROOT, "backtest", "gen_*.py"))):
        src = open(g, encoding="utf-8").read()
        ins = {p for p in (resolve(m.group(1)) for m in DATA_HINT.finditer(src)) if p}
        has_dir_hint = bool(DIR_HINT.search(src))
        if has_dir_hint:
            nf = newest_in_dir(os.path.join(ROOT, "backtest", "store", "pred_data"))
            if nf:
                ins.add(nf)
        outs = outputs_of(src)
        if not ins and outs:
            loose = loose_refs(src)
            if loose:
                unrecognized.append((g, sorted(loose)))
        if not ins or not outs:
            continue
        newest = max(os.path.getmtime(i) for i in ins)
        for o in outs:
            if not os.path.exists(o):
                missing.append((g, o))
            elif out_mtime(o) < newest:
                stale.append((g, o, max(ins, key=os.path.getmtime)))
    return stale, missing, unrecognized


# ★中間データの鮮度★（2026-07-27追加）
#   scan() は gen_*.py（ページ生成）しか見ていないため、
#   「生データ → 中間データセット」の段が丸ごと監視の外だった。
#   実際 2026-07-27 時点で、地方ZIPが当日更新されているのに
#   bt_all.jsonl は6日前、bt_jra/bt_banei は7日前のままだった。
#   ページ側は「中間データより新しい」ので check_stale は何も言わない。
#   つまり**チェックは通るのに、公開している数字は最新ではない**という
#   一番たちの悪い状態になる。ここを明示的に見る。
#
#   再生成は重い（bt_all.jsonl は440MB・数十分）ので --fix の対象にはしない。
#   「古い」と知らせるところまでが役目。
BUILD_CHAINS = [
    ("backtest/build_dataset.py",       "backtest/nardata/race_*.zip",
     "backtest/nardata/bt_all.jsonl"),
    ("backtest/build_jra_dataset.py",   "backtest/jvdata/*.txt",
     "backtest/nardata/bt_jra.jsonl"),
    ("backtest/build_banei_dataset.py", "backtest/nardata/race_*.zip",
     "backtest/nardata/bt_banei.jsonl"),
    # ★2026-07-28追加★ /ai/ が7日間「最新確定(7/20)」のまま止まっていた。
    #   daily.py に載っておらず、しかも出力(ai/index.html)は入力
    #   (personas_stats.json)より新しかったので既存の鮮度チェックを素通りしていた。
    #   生データ(bt_all.jsonl)まで遡って比べないとこの手の停止は見つからない。
    ("backtest/bt_personas.js",      "backtest/nardata/bt_all.jsonl",
     "backtest/personas_stats.json"),
    ("backtest/bt_persona_bets.js",  "backtest/nardata/bt_all.jsonl",
     "backtest/persona_bets.json"),
    ("backtest/gen_ai_page.py",      "backtest/personas_stats.json",
     "deploy/ai/index.html"),
    # ★2026-08-04追加★ 人格の確定印。古いまま放置されると、レースページが
    #   ✅確定印として**古い計算の印**を出し続ける（しかも画面はエラーを出さない）。
    #   /ai/の的中カードとの不一致を防ぐために入れた仕組みなので、鮮度が命。
    ("backtest/bt_persona_marks.js", "backtest/nardata/bt_all.jsonl",
     "deploy/data/pmarks.json"),
]


# この日数以上ずれていたら「放置」とみなして失敗にする。
# 1日程度のずれは日次運用の途中経過なので落とさない。
FAIL_DAYS = 14


def check_build_chains():
    """生データより古い中間データセットを返す [(builder, out, newest_in, 日数)]"""
    out = []
    for builder, raw_glob, target in BUILD_CHAINS:
        raws = glob.glob(os.path.join(ROOT, raw_glob))
        tgt = os.path.join(ROOT, target)
        if not raws or not os.path.exists(tgt):
            continue
        newest = max(raws, key=os.path.getmtime)
        gap = os.path.getmtime(newest) - os.path.getmtime(tgt)
        if gap > 86400:          # 1日以上開いたら知らせる（当日ぶんの誤差は無視）
            out.append((builder, target, newest, gap / 86400))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fix", action="store_true", help="古い生成物を作り直す")
    a = ap.parse_args()

    # ★警告と失敗を分ける★
    #   中間データの古さは「数字が間違っている」のではなく「最新ではない」状態。
    #   再生成は重い（bt_all.jsonl は440MB・数十分）ので、少し古いだけで
    #   npm run check を赤にし続けると、そのうち誰も見なくなる（警報疲れ）。
    #   なので **常に表示はする / 落とすのは明らかに放置されている時だけ** にする。
    chains = check_build_chains()
    bad_chains = [c for c in chains if c[3] >= FAIL_DAYS]
    if chains:
        print("[中間データが古い] 生データの方が新しい。ページを作り直しても数字は最新にならない:")
        for builder, target, newest, days in chains:
            mark = " ★" if days >= FAIL_DAYS else ""
            print(f"  {target}  … {os.path.relpath(newest, ROOT)} より {days:.0f}日古い{mark}")
            print(f"      作り直す: python {builder}")
        if bad_chains:
            print(f"  ★ = {FAIL_DAYS}日以上放置。これがあるとこのチェックは失敗扱いにする。")
        print()

    stale, missing, unrecognized = scan()

    if unrecognized:
        print("[要目視確認] DATA_HINT/DIR_HINTが拾えていない可能性のある入力"
              "（自動判定はしない。過去にpred_dataがこれで1ヶ月古いまま公開された）:")
        for g, refs in unrecognized:
            print(f"  {os.path.relpath(g, ROOT)}: {', '.join(refs)}")
        print()

    if not stale and not missing:
        print("入力より古い生成物は無い。")
        # 中間データが古い場合は、ページ側が揃っていても「最新ではない」ので
        # 緑にはしない（ここを0で返すと npm run check が通ってしまい、
        # 古い数字のまま公開する事故に戻る）
        return 1 if bad_chains else 0

    for g, o in missing:
        print(f"[出力なし] {os.path.relpath(g, ROOT)} → {os.path.relpath(o, ROOT)}")
    for g, o, i in stale:
        print(f"[古い]     {os.path.relpath(o, ROOT)}")
        print(f"           作り直す: {os.path.relpath(g, ROOT)}"
              f"（{os.path.relpath(i, ROOT)} の方が新しい）")

    if not a.fix:
        print("\n（--fix を付けると作り直す）")
        return 1

    for g, o, _ in stale:
        print(f"\n=== {os.path.relpath(g, ROOT)} ===", flush=True)
        r = subprocess.run([sys.executable, g], cwd=os.path.dirname(g),
                           capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        # ★子プロセスの出力をそのまま print すると落ちる★
        #   errors="replace" で U+FFFD が混ざった文字列を、cp932 の標準出力へ
        #   書こうとして UnicodeEncodeError になり、--fix が途中で死んでいた
        #   （2026-07-27、実際に1本目の再生成直後で止まった）。
        #   端末が出せない文字は捨ててから表示する。
        tail = (r.stdout or r.stderr)[-600:]
        enc = sys.stdout.encoding or "utf-8"
        print(tail.encode(enc, "replace").decode(enc, "replace"))
    print("\n作り直した。デプロイし直すこと。")
    # --fix はページしか作り直さない。中間データが古いままなら、
    # ページを作り直しても中身は古い（＝ここで0を返すと「直った」と誤認する）
    if chains:
        print("※ ただし中間データが古いままなので、数字は最新になっていない。"
              "上の build_*.py を先に回すこと。")
    return 1 if bad_chains else 0


if __name__ == "__main__":
    sys.exit(main())
