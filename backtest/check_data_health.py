# -*- coding: utf-8 -*-
"""入力データ（生データ）自体の健全性を見る。

★これが無くて1回やらかした（2026-07-26）★
  jvdata/race_2024.txt と race_2025.txt が完全に同一ファイルだった。
  JV-Link(jvlink_fetch_all.ps1)のoption=1が指定FromTimeを無視して
  「直近優先で最大約1,370ファイル」しか返さない仕様のため、年を変えても
  同じ直近期間に頭打ちして同じ中身になっていた。これに気づかず
  「2025年データ」として使い、バックテストで2024年が二重計上・2025年が
  不在という状態で結論(地方転厩馬-15pt)を出しかけた。

  check_stale.py は「生成物が入力より古くないか」を見るが、
  「入力データ自体が重複・欠損していないか」は誰も見ていなかった。
  中身が壊れていても数字は普通に出てしまう＝気づけない。機械に見せる。

見るもの:
  1. jvdata/*.txt の重複（別名なのに中身が同一のファイル）。
     大きいので全ハッシュは避け、同サイズのファイルだけ
     「先頭1MB+末尾1MB+サイズ」のフィンガープリントで突合する。
  2. nardata/race_YYYYMM.zip の欠け月（min〜maxの間に穴がないか）。

使い方:
  python backtest/check_data_health.py
  （npm run check から呼ばれる。問題があれば exit 1）
"""
import glob
import hashlib
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JVDIR = os.path.join(ROOT, "backtest", "jvdata")
NARDIR = os.path.join(ROOT, "backtest", "nardata")

CHUNK = 1 << 20  # 1MB


def fingerprint(path):
    """先頭1MB + 末尾1MB + サイズ の軽量指紋。同サイズ同指紋なら実質同一とみなす。"""
    size = os.path.getsize(path)
    h = hashlib.md5()
    h.update(str(size).encode())
    with open(path, "rb") as f:
        h.update(f.read(CHUNK))
        if size > CHUNK:
            f.seek(max(0, size - CHUNK))
            h.update(f.read(CHUNK))
    return h.hexdigest()


def check_jvdata_dupes():
    """別名なのに中身が同一のjvdataファイルを検出。同サイズのものだけ指紋照合。"""
    problems = []
    files = sorted(glob.glob(os.path.join(JVDIR, "*.txt")))
    if not files:
        return problems
    by_size = {}
    for p in files:
        by_size.setdefault(os.path.getsize(p), []).append(p)
    for size, group in by_size.items():
        if len(group) < 2:
            continue
        # ★命名で意図的に重なるものは除外★
        #   target.txt と target_all.txt のような「全部入り」系は
        #   別の年別ファイルと部分的に一致してもおかしくない。ここで見たいのは
        #   「race_2024 と race_2025 のように別の年を指す名前なのに同一」ケース。
        by_fp = {}
        for p in group:
            by_fp.setdefault(fingerprint(p), []).append(p)
        for fp, same in by_fp.items():
            if len(same) < 2:
                continue
            names = [os.path.basename(p) for p in same]
            # 年（4桁）を名前から拾い、違う年を指しているのに同一ならNG
            years = set()
            for nm in names:
                m = re.search(r"(19|20)\d{2}", nm)
                if m:
                    years.add(m.group(0))
            if len(years) >= 2:
                problems.append((names, size, years))
    return problems


def check_nar_months():
    """nardata/race_YYYYMM.zip の欠け月を検出。"""
    zips = glob.glob(os.path.join(NARDIR, "race_*.zip"))
    months = sorted(int(m.group(1)) for m in
                    (re.search(r"race_(\d{6})\.zip$", os.path.basename(z)) for z in zips) if m)
    if len(months) < 2:
        return []
    have = set(months)
    lo, hi = months[0], months[-1]
    missing = []
    y, mo = lo // 100, lo % 100
    while y * 100 + mo <= hi:
        if y * 100 + mo not in have:
            missing.append(y * 100 + mo)
        mo += 1
        if mo > 12:
            mo = 1
            y += 1
    return missing


def main():
    ng = 0

    dupes = check_jvdata_dupes()
    if dupes:
        ng += 1
        print("!! jvdata に「別の年を指す名前なのに中身が同一」のファイルがある")
        for names, size, years in dupes:
            print(f"   {' == '.join(names)}  （{size:,}B・年{'/'.join(sorted(years))}）")
        print("   JV-Link option=1 は直近優先で頭打ちする。過去の特定年は")
        print("   jvlink_supervisor.py(option=4)経由の target_all.txt を使うこと。")
    else:
        print("jvdata: 別名同一ファイルなし。")

    missing = check_nar_months()
    if missing:
        ng += 1
        print(f"!! nardata の月次ZIPに欠けがある: {', '.join(str(m) for m in missing)}")
        print("   python backtest/nar_data_pipeline.py で該当月を取り直すこと。")
    else:
        print("nardata: 月次ZIPの連続性に問題なし。")

    return 1 if ng else 0


if __name__ == "__main__":
    sys.exit(main())
