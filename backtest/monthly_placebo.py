# -*- coding: utf-8 -*-
"""毎月1日にだけ placebo_check.py（先月30日分）を回すラッパー。
daily.py のSTEPSは静的コマンドしか持てないため、日付判定はこちらで行う。
1日以外は即0で終了（日次を汚さない）。"""
import subprocess
import sys
from datetime import datetime, timedelta, timezone

JST = timezone(timedelta(hours=9))
if datetime.now(JST).day != 1:
    print("月初ではないのでプラシーボ月次はスキップ")
    sys.exit(0)
sys.exit(subprocess.run([sys.executable, __file__.replace("monthly_placebo", "placebo_check"),
                         "30", "both"]).returncode)
