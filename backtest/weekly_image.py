# -*- coding: utf-8 -*-
"""毎週月曜にだけ gen_weekly_image.js（先週月〜日）を回すラッパー。
daily.py のSTEPSは静的コマンドしか持てないため、曜日判定はこちらで行う。
月曜以外は即0で終了（日次を汚さない）。

出力: backtest/store/weekly/weekly_<開始>_<終了>.png（ツイート添付用・投稿は手動）"""
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone

JST = timezone(timedelta(hours=9))
now = datetime.now(JST)
if now.weekday() != 0:  # 0=月曜
    print("月曜ではないので週間成績画像はスキップ")
    sys.exit(0)
end = (now - timedelta(days=1)).strftime("%Y%m%d")  # 昨日=日曜
HERE = os.path.dirname(os.path.abspath(__file__))
sys.exit(subprocess.run(["node", os.path.join(HERE, "gen_weekly_image.js"), end, "7"]).returncode)
