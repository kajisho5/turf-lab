# -*- coding: utf-8 -*-
"""毎朝: JRA-VANから最新を取り、netkeiba形式のページ(pages.json)を作って PC に残す。

並走運用用（本番はまだnetkeiba）。出力: backtest/store/jra_pages/YYYYMMDD.json
  python backtest/jra_daily.py            # 今日
  python backtest/jra_daily.py --date 20261122
血統(父・母父)は backtest/jvdata/ped_um.json を使う。7日より古ければ UM を取り直して足す。
"""
import argparse
import glob
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
JV = os.path.join(HERE, "jvdata")
STORE = os.path.join(HERE, "store")
LOG = os.path.join(STORE, "_jra_daily.log")
PS32 = r"C:\Windows\SysWOW64\WindowsPowerShell\v1.0\powershell.exe"


def log(msg):
    line = "[%s] %s" % (datetime.now().strftime("%m-%d %H:%M:%S"), msg)
    print(line, flush=True)
    os.makedirs(STORE, exist_ok=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True, errors="replace")
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def refresh_pedigree():
    p = os.path.join(JV, "ped_um.json")
    if os.path.exists(p) and time.time() - os.path.getmtime(p) < 7 * 86400:
        return
    log("血統(UM)を取り直す")
    since = (datetime.now() - timedelta(days=60)).strftime("%Y%m%d000000")
    out = os.path.join(JV, "um_new.txt")
    rc, o = run([PS32, "-STA", "-ExecutionPolicy", "Bypass", "-File", os.path.join(HERE, "jvlink_dump.ps1"),
                 "-DataSpec", "DIFN", "-FromTime", since, "-Out", out, "-Option", "4", "-Kinds", "UM"])
    log("  UM取得 rc=%s %s" % (rc, o.strip()[:120].replace("\n", " ")))
    if not os.path.exists(out):
        return
    sys.path.insert(0, HERE)
    import jra_make_pages as g
    ped = json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {}
    n0 = len(ped)
    g.load_um([out], ped)
    json.dump(ped, open(p, "w", encoding="utf-8"), ensure_ascii=False)
    log("  血統 %d → %d頭" % (n0, len(ped)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=datetime.now().strftime("%Y%m%d"))
    a = ap.parse_args()
    log("=== 開始 %s ===" % a.date)
    rc, o = run([sys.executable, os.path.join(HERE, "collect_daily.py"), "--days", "2", "--months", "0"])
    log("中央データ取得 rc=%s %s" % (rc, o.strip().splitlines()[-1][:120] if o.strip() else ""))
    refresh_pedigree()
    dumps = [os.path.join(JV, "setup_2024.txt"), os.path.join(JV, "race_2026.txt")]
    dumps += sorted(glob.glob(os.path.join(STORE, "jra", "*.txt")))
    dumps = [d for d in dumps if os.path.exists(d)]
    outdir = os.path.join(STORE, "jra_pages")
    os.makedirs(outdir, exist_ok=True)
    tmp = os.path.join(outdir, "_tmp_" + a.date)
    os.makedirs(tmp, exist_ok=True)
    rc, o = run([sys.executable, os.path.join(HERE, "jra_make_pages.py"), "--date", a.date, "--dump", *dumps,
                 "--pedigree", os.path.join(JV, "ped_um.json"), "-o", tmp])
    log("ページ生成 rc=%s %s" % (rc, o.strip().splitlines()[-1][:120] if o.strip() else ""))
    src = os.path.join(tmp, "pages.json")
    if rc == 0 and os.path.exists(src):
        os.replace(src, os.path.join(outdir, a.date + ".json"))
        log("保存 jra_pages/%s.json" % a.date)
    try:
        os.rmdir(tmp)
    except OSError:
        pass
    log("=== 終了 ===")


if __name__ == "__main__":
    main()
