# -*- coding: utf-8 -*-
"""オッズ時系列の記録（地方競馬 / keiba.go.jp 当日ファイル）

★なぜこれが最優先か★
  17万Rの検証で分かったこと（FACTS.md）:
  - 回収率100%超は1つも無い。天井92.2%
  - モデルの◎は「1番人気を買う」に負けている
  - 近走・先行力・当地成績は全て市場に織り込み済み（残差モデルで k=0 が最良）

  → **市場がまだ織り込んでいない情報**だけがエッジになる。
     その筆頭が「締切に向かうオッズの動き」。
     そして **過去に遡って取得する手段は存在しない**（公式は確定値のみ）。
     記録していない日は永久に取り返せない。だから今日から貯める。

仕組み:
  keiba.go.jp の当日オッズは1リクエストで全場・全レース・全券種が返る（約2分毎に更新）。
  これをそのまま時刻つきで保存するだけ。加工は後からいくらでもできる。

  保存先: backtest/odds_snapshots/YYYYMMDD/HHMM.zip
  中身が前回と同一なら保存しない（サーバー側が未更新の時は無駄になるため）。

使い方:
  python backtest/odds_recorder.py            # 1回だけ取得
  python backtest/odds_recorder.py --loop 300 # 300秒間隔で回し続ける（Ctrl-Cで停止）
  python backtest/odds_recorder.py --stats    # 貯まっている量を表示

タスクスケジューラに登録する場合は --loop を使わず、5分間隔で単発実行するのが安全
（プロセスが死んでも次回で復帰するため）。
"""
import argparse, datetime, hashlib, os, sys, time, urllib.error, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTDIR = os.path.join(ROOT, "backtest", "odds_snapshots")
URL = "https://www.keiba.go.jp/KeibaWeb/DataDownload/OddsDataDownload?type=daily"
UA = "Mozilla/5.0 (compatible; swturf-oddsrec/1.0)"
MIN_BYTES = 1000          # これ未満は「発売前 or 開催なし」


def jst_now():
    return datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=9)


def fetch():
    req = urllib.request.Request(URL, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read()


def last_hash(daydir):
    """その日の最後に保存したファイルのハッシュ（重複保存を避ける）"""
    if not os.path.isdir(daydir):
        return None
    files = sorted(f for f in os.listdir(daydir) if f.endswith(".zip"))
    if not files:
        return None
    with open(os.path.join(daydir, files[-1]), "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def once(quiet=False):
    now = jst_now()
    daydir = os.path.join(OUTDIR, now.strftime("%Y%m%d"))
    try:
        data = fetch()
    except (urllib.error.URLError, TimeoutError) as e:
        print(f"[{now:%H:%M}] 取得失敗: {e}")
        return "error"

    if len(data) < MIN_BYTES:
        if not quiet:
            print(f"[{now:%H:%M}] 発売前 or 本日開催なし（{len(data)}B）")
        return "empty"

    h = hashlib.sha256(data).hexdigest()
    if h == last_hash(daydir):
        if not quiet:
            print(f"[{now:%H:%M}] 前回と同一（サーバー未更新）— 保存しない")
        return "same"

    os.makedirs(daydir, exist_ok=True)
    path = os.path.join(daydir, now.strftime("%H%M") + ".zip")
    with open(path, "wb") as f:
        f.write(data)
    print(f"[{now:%H:%M}] 保存 {len(data)//1024}KB -> {os.path.relpath(path, ROOT)}")
    return "saved"


def stats():
    if not os.path.isdir(OUTDIR):
        print("まだ何も記録されていない。")
        return
    days = sorted(d for d in os.listdir(OUTDIR) if d.isdigit())
    total_n = total_b = 0
    print(f"{'日付':<12}{'スナップ数':>10}{'サイズ':>12}{'最初':>8}{'最後':>8}")
    print("-" * 52)
    for d in days:
        p = os.path.join(OUTDIR, d)
        fs = sorted(f for f in os.listdir(p) if f.endswith(".zip"))
        if not fs:
            continue
        b = sum(os.path.getsize(os.path.join(p, f)) for f in fs)
        total_n += len(fs)
        total_b += b
        print(f"{d:<12}{len(fs):>10}{b//1024:>10}KB{fs[0][:-4]:>8}{fs[-1][:-4]:>8}")
    print("-" * 52)
    print(f"{'合計':<12}{total_n:>10}{total_b//1024//1024:>10}MB")
    print()
    print("※ 同一内容は保存しないので、スナップ数 = 実際にオッズが動いた回数。")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--loop", type=int, metavar="SEC", help="この秒数の間隔で回し続ける")
    ap.add_argument("--stats", action="store_true", help="貯まっている量を表示")
    ap.add_argument("--quiet", action="store_true", help="保存した時だけ出力")
    a = ap.parse_args()

    if a.stats:
        stats()
        return 0

    if not a.loop:
        once(a.quiet)
        return 0

    print(f"{a.loop}秒間隔で記録を開始。Ctrl-C で停止。")
    try:
        while True:
            once(a.quiet)
            time.sleep(a.loop)
    except KeyboardInterrupt:
        print("\n停止した。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
