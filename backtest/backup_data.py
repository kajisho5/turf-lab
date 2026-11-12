# -*- coding: utf-8 -*-
"""ローカルにしか無いデータをサーバーへ退避する

★方針★（2026-07-30 ユーザー指示「基本的にデータは全てサーバーに残してね」）
  ローカルPCは飛ぶ・環境が変わる。取得したデータと生成したモデルは
  サーバーに置いておく。サーバーの空きは14.3TBあり容量は問題ない（実測）。

★優先順位★ 上から順に価値が高い（=失うと痛い）
  1. tier1 「取ってきた生データ」… 源が死ぬと二度と手に入らない
       backtest/nardata/race_*.zip      keiba.go.jp 月次ZIP（182MB・163本）
       backtest/nardata/weather/*.json  Open-Meteo 24場×13年の降水量（1.8MB）
  2. tier2 「学習済みモデルと索引の材料」… 再学習できるが時間と再現性のコスト
       backtest/ltr_model*.txt          本番モデルとロールバック用バックアップ
       backtest/nardata/*.jockeys|trainers|sires  索引のサイドカー
  3. tier3 「派生データ」… tier1から再生成できる（1.8GB）
       bt_all.jsonl / bt_jra.jsonl / bt_banei.jsonl / bt_debut.jsonl
  ※ backtest/jvdata（3.3GB・JV-Link由来）は tier4 として別途（回線を長時間占有する）

★公開されないようにする★
  この置き場は /backup/ 配下で、.htaccess で全拒否する。
  keiba.go.jp / JV-Data 由来のデータをそのまま誰でも落とせる状態にしてはいけない。

使い方:
  python backtest/backup_data.py            # 何を上げるか一覧（上げない）
  python backtest/backup_data.py --push     # tier1+tier2 を上げる
  python backtest/backup_data.py --push --tier 3   # tier3 まで
"""
import argparse
import glob
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from deploy import winscp  # noqa: E402  認証はWinSCPの保存セッション（こちらは持たない）

REMOTE = "/seventh-well.com/backup"

HTACCESS = "Order deny,allow\nDeny from all\n"


def tiers():
    t1 = sorted(glob.glob(os.path.join(ROOT, "backtest", "nardata", "race_*.zip"))) \
        + sorted(glob.glob(os.path.join(ROOT, "backtest", "nardata", "weather", "*.json")))
    t2 = sorted(glob.glob(os.path.join(ROOT, "backtest", "ltr_model*.txt"))) \
        + sorted(glob.glob(os.path.join(ROOT, "backtest", "nardata", "*.jockeys"))) \
        + sorted(glob.glob(os.path.join(ROOT, "backtest", "nardata", "*.trainers"))) \
        + sorted(glob.glob(os.path.join(ROOT, "backtest", "nardata", "*.sires")))
    t3 = [p for p in glob.glob(os.path.join(ROOT, "backtest", "nardata", "*.jsonl"))]
    # tier4: JV-Link由来のダンプ（3.3GB）。再取得できるが手間なので最後に送る
    t4 = sorted(glob.glob(os.path.join(ROOT, "backtest", "jvdata", "*.txt")))
    return {1: t1, 2: t2, 3: t3, 4: t4}


def rel(p):
    return os.path.relpath(p, ROOT).replace("\\", "/")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--push", action="store_true")
    ap.add_argument("--tier", type=int, default=2, help="どのtierまで上げるか（既定2）")
    ap.add_argument("--from", dest="frm", type=int, default=1,
                    help="どのtierから上げるか（既定1）。送信済みを再送しないために使う")
    a = ap.parse_args()

    T = tiers()
    targets = []
    for t in range(a.frm, a.tier + 1):
        targets += T.get(t, [])
    total = sum(os.path.getsize(p) for p in targets if os.path.exists(p))

    for t in sorted(T):
        n = len(T[t])
        mb = sum(os.path.getsize(p) for p in T[t] if os.path.exists(p)) / 1048576
        mark = "→上げる" if (a.frm <= t <= a.tier) else "（対象外）"
        print(f"  tier{t}: {n:>4}本 {mb:>8.1f}MB  {mark}")
    print(f"\n合計 {len(targets)}本 / {total/1048576:.1f}MB → {REMOTE}")

    if not a.push:
        print("\n（--push で実行。まず一覧だけ出している）")
        return 0

    # .htaccess を先に置く（データより先に公開拒否を効かせる）
    ht = os.path.join(HERE, "_backup_htaccess.tmp")
    with open(ht, "w", encoding="ascii", newline="\n") as f:
        f.write(HTACCESS)
    cmds = [f'option batch continue', f'mkdir "{REMOTE}"',
            f'put -nopermissions "{ht}" "{REMOTE}/.htaccess"']
    # ディレクトリ構成をローカルと同じにする（後で取り戻すときに迷わない）
    dirs = sorted({os.path.dirname(rel(p)) for p in targets})
    for d in dirs:
        cur = ""
        for part in d.split("/"):
            cur = f"{cur}/{part}" if cur else part
            cmds.append(f'mkdir "{REMOTE}/{cur}"')
    for p in targets:
        cmds.append(f'put -nopermissions "{p}" "{REMOTE}/{rel(p)}"')
    out = winscp(cmds)
    os.unlink(ht)
    ok = out.count("100%")
    err = [ln for ln in out.splitlines()
           if ("error" in ln.lower() or "失敗" in ln) and "mkdir" not in ln.lower()]
    print(f"\n転送完了の行数: {ok}")
    if err:
        print("エラー行:")
        for ln in err[:10]:
            print("  " + ln)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
