# -*- coding: utf-8 -*-
"""毎日データを自分で取って蓄積する（netkeiba 依存を切るための土台）

★なぜ要るか★
  いまサイトのレース表示は netkeiba から都度取得している。
  ・第三者のコンテンツに依存しており、AdSense の規約上のリスクがある
  ・相手のHTML改修でいつでも壊れる（今日だけで落とし穴を9件踏んだ）
  ・レート制限や遮断をされたら何も出せなくなる

  過去分は JV-Link のセットアップ（中央）と keiba.go.jp の月次ZIP（地方）で
  手元に取り切れる。**あとは毎日その日ぶんを追記していけば、自前のデータになる。**

★取り方★
  中央 JV-Link option=1（通常データ）… JVOpen が 200ms 前後で返る軽い経路。
       セットアップと違い、直近ぶんを差分で取るための正規の方法。
  地方 keiba.go.jp の月次ZIP … 当月ぶんを取り直す（確定後に払戻が入るため）。

★積み方★
  取得した生データは日付ごとに残し、**上書きしない**。
  レース結果は後から確定するので、同じ日を何度取り直しても良いように
  「取得時刻つきで保存 → 最新を採用」とする。

出力:
  backtest/store/jra/YYYYMMDD.txt   中央の生レコード
  backtest/store/nar/YYYYMM.zip     地方の月次ZIP
  backtest/store/_collect.log       実行記録

使い方:
  python backtest/collect_daily.py            # 当日ぶん
  python backtest/collect_daily.py --days 7   # 直近7日を取り直す
"""
import argparse
import os
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HERE = os.path.join(ROOT, "backtest")
STORE = os.path.join(HERE, "store")
JRA_DIR = os.path.join(STORE, "jra")
NAR_DIR = os.path.join(STORE, "nar")
# ★正典★ バックテスト・gen_record_page.py が実際に読むのはこちら（race_YYYYMM.zip）
NARDATA_DIR = os.path.join(HERE, "nardata")
LOG = os.path.join(STORE, "_collect.log")
PS32 = r"C:\Windows\SysWOW64\WindowsPowerShell\v1.0\powershell.exe"
DUMP = os.path.join(HERE, "jvlink_dump.ps1")

NAR_URL = ("https://www.keiba.go.jp/KeibaWeb/DataDownload/RaceDataDownload"
           "?type=monthly&k_year={y}&k_month={m}")


def log(msg):
    line = time.strftime("[%m-%d %H:%M:%S] ") + msg
    print(line, flush=True)
    os.makedirs(STORE, exist_ok=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def jv_busy():
    """★JV-Link を同時に2つ動かさない★
    COMを二重に掴むと壊れる。過去分のセットアップ取得(jvlink_setup.ps1)や
    日次のダンプ自体(jvlink_dump.ps1)が既に走っている間は、日次収集の
    中央分を飛ばす（地方分は keiba.go.jp なので影響しない）。

    ★2026-07-26修正★ 旧実装は `Get-Process powershell` で名前が一致する
    プロセスを**マシン上の全部**数えていたため、JV-Linkと無関係な
    powershell.exe（他のスクリプト・エディタ・このチェック自身が起動する
    プロセスなど）が1つでもあれば常に「使用中」と誤判定していた。
    結果、_collect.logで2026-07-19〜07-25の7日間連続で中央収集が
    スキップされ続けるが誰も気づかない、という実害が出ていた
    （supervisor自体は07-19に終了済みで、その後は本当は空いていた）。
    CommandLineでjvlink_setup.ps1/jvlink_dump.ps1を名指しして絞り込む。
    """
    try:
        out = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command",
             "(Get-CimInstance Win32_Process -Filter \"Name='powershell.exe'\" | "
             "Where-Object { $_.CommandLine -match 'jvlink_setup\\.ps1' -or "
             "$_.CommandLine -match 'jvlink_dump\\.ps1' } | Measure-Object).Count"],
            capture_output=True, text=True, timeout=30).stdout.strip()
        return int(out or 0) > 0
    except Exception:
        return False


def collect_jra(days):
    """中央: JV-Link の通常データ（option=1）で直近ぶんを取る"""
    if jv_busy():
        log("  中央: JV-Link が使用中のため今回は飛ばす（次回に取る）")
        return False
    os.makedirs(JRA_DIR, exist_ok=True)
    frm = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d") + "000000"
    out = os.path.join(JRA_DIR, datetime.now().strftime("%Y%m%d") + ".txt")
    log(f"中央 JV-Link option=1 FromTime={frm}")
    try:
        r = subprocess.run(
            [PS32, "-NoProfile", "-STA", "-ExecutionPolicy", "Bypass",
             "-File", DUMP, "-DataSpec", "RACE", "-FromTime", frm,
             "-Out", out, "-Kinds", "RA,SE,HR"],
            cwd=HERE, capture_output=True, text=True,
            encoding="cp932", errors="replace", timeout=1800)
        n = os.path.getsize(out) if os.path.exists(out) else 0
        log(f"  中央 完了 {n:,}B  {(r.stdout or '').strip()[:120]}")
        return n > 0
    except subprocess.TimeoutExpired:
        log("  !! 中央 タイムアウト（30分）")
        return False
    except Exception as e:
        log(f"  !! 中央 失敗 {e}")
        return False


def collect_nar(months):
    """地方: keiba.go.jp の月次ZIP。当月は結果確定で中身が変わるので毎回取り直す

    ★2026-07-26修正: 保存先が誰も読まない場所だった★
      従来は backtest/store/nar/YYYYMM.zip にだけ落としていたが、
      **このフォルダを読むスクリプトは1つも無かった**（write-onlyの行き止まり）。
      バックテストも gen_record_page.py も、実際に読むのは
      nar_data_pipeline.py が作る backtest/nardata/race_YYYYMM.zip の方。
      そのため毎日取得していたのに「予想の記録」ページの結果照合には
      5日前のZIPが使われ、照合不能が積み上がっていた（発覚時452件）。
      正典である nardata/race_YYYYMM.zip にも同じ中身を書く。
    """
    os.makedirs(NAR_DIR, exist_ok=True)
    os.makedirs(NARDATA_DIR, exist_ok=True)
    ok = 0
    now = datetime.now()
    for i in range(months):
        d = now.replace(day=1) - timedelta(days=1) * (0 if i == 0 else 1)
        y, m = (now.year, now.month) if i == 0 else (
            (now.year, now.month - i) if now.month - i > 0
            else (now.year - 1, now.month - i + 12))
        url = NAR_URL.format(y=y, m=m)
        dst = os.path.join(NAR_DIR, f"{y}{m:02d}.zip")
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
            with urllib.request.urlopen(req, timeout=120) as r:
                body = r.read()
            if len(body) < 1000:
                log(f"  !! 地方 {y}-{m:02d} 応答が小さい {len(body)}B")
                continue
            # ★取れた時だけ上書きする★ 失敗時に既存を壊さない
            with open(dst, "wb") as f:
                f.write(body)
            # 正典側（バックテスト・記録ページが実際に読む方）にも書く
            with open(os.path.join(NARDATA_DIR, f"race_{y}{m:02d}.zip"), "wb") as f:
                f.write(body)
            log(f"  地方 {y}-{m:02d} {len(body):,}B")
            ok += 1
        except Exception as e:
            log(f"  !! 地方 {y}-{m:02d} 失敗 {e}")
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=3, help="中央を何日ぶん遡って取るか")
    ap.add_argument("--months", type=int, default=2, help="地方を何か月ぶん取り直すか")
    ap.add_argument("--skip-jra", action="store_true")
    args = ap.parse_args()

    log("=== 収集開始 ===")
    jra = True if args.skip_jra else collect_jra(args.days)
    nar = collect_nar(args.months)
    log(f"=== 完了 中央={'OK' if jra else 'NG'} 地方={nar}か月 ===")
    # どちらかが取れていれば成功扱い（片方の障害で全部止めない）
    return 0 if (jra or nar) else 1


if __name__ == "__main__":
    sys.exit(main())
