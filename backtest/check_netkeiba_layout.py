# -*- coding: utf-8 -*-
"""★netkeibaのHTML構造が変わったら気づく★（2026-08-04）

なぜ要るか（実際に起きた）:
  NARのオッズページから投票チェックボックス(chk_b2_)が消え、
  それだけを見ていた tweet.html の fetchExoticOdds は
  **複勝オッズが常に0件 → 毎回null → 全レース見送り** になっていた。
  画面にもログにもエラーは出ない。今日たまたま実データを見て気づいた。
  取得系は「取れなかった」ではなく「静かに空を返す」壊れ方をするので、
  正規表現がヒットするかを機械で毎日見張る。

やること: 直近の確定済みレース1つに対して2リクエストだけ投げ、
  各パーサが期待するパターンが1つでもヒットするかを確認する。
  ★大量取得はしない★（本番proxyの連投でnetkeibaにIPを止められた前科がある）

使い方: python backtest/check_netkeiba_layout.py   （daily.py に組込み）
"""
import io
import json
import re
import sys
import time
import urllib.request

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
BASE = "https://seventh-well.com/odds"
UA = {"User-Agent": "Mozilla/5.0 layout-check"}

# 各パターンは「実装のどこが使っているか」とセットで持つ。
# 複数挙げたものは **どれか1つ当たればOK**（レイアウトが2系統あるため）。
CHECKS = [
    {"name": "複勝オッズ(b1)", "type": "b1",
     "used_by": "tweet.html fetchExoticOdds / race.html fetchOddsBoard",
     "any": [r'id="chk_b2_(\d+)"[\s\S]{0,400}?class="Odds\s*">([\d.]+)',
             r'id\s*=\s*"mymarkb2_(\d+)"[\s\S]{0,400}?class="Odds\s*">([\d.]+)']},
    {"name": "馬連オッズ(b4)", "type": "b4",
     "used_by": "同上",
     "any": [r'id="chk_[^"]*_b\d_c0_(\d+)_(\d+)"[^>]*>\s*([\d.]+)']},
]


def fetch(url):
    req = urllib.request.Request(f"{BASE}/proxy.php?u=" + b64url(url), headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", errors="replace")


def b64url(s):
    import base64
    return base64.urlsafe_b64encode(s.encode()).decode().rstrip("=")


def recent_rid():
    """直近で結果が確定している地方レースのridを1つ取る（自前の保存から）"""
    from datetime import datetime, timedelta, timezone
    jst = timezone(timedelta(hours=9))
    for i in range(1, 8):
        d = (datetime.now(jst) - timedelta(days=i)).strftime("%Y%m%d")
        try:
            req = urllib.request.Request(
                f"{BASE}/predictions.php?action=list&date={d}&mode=nar", headers=UA)
            with urllib.request.urlopen(req, timeout=30) as r:
                j = json.loads(r.read().decode("utf-8"))
        except Exception:
            continue
        for rec in (j.get("records") or []):
            for rr in (rec.get("races") or []):
                if rr.get("race_id"):
                    return str(rr["race_id"])
    return None


def main():
    rid = recent_rid()
    if not rid:
        print("[skip] 直近の保存済み予想が見つからないので判定しない")
        return 0
    ng = 0
    for c in CHECKS:
        url = (f"https://nar.netkeiba.com/odds/odds_get_form.html"
               f"?type={c['type']}&race_id={rid}")
        time.sleep(0.5)                      # WAF対策。連投しない
        try:
            html = fetch(url)
        except Exception as e:
            print(f"[skip] {c['name']}: 取得できず（{e}）。ネットワーク都合なので失敗にはしない")
            continue
        hits = [len(re.findall(p, html)) for p in c["any"]]
        if max(hits) == 0:
            print(f"NG [{c['name']}] 期待するパターンが1つも当たらない（rid={rid}）")
            print(f"    使っている場所: {c['used_by']}")
            print( "    → netkeibaのHTML構造が変わった可能性が高い。"
                   "正規表現を直さないと、オッズが静かに空になる")
            ng += 1
        else:
            print(f"OK  {c['name']}: ヒット {hits}（rid={rid}）")
    if ng:
        print(f"\nnetkeibaレイアウト検査: {ng}件が不一致。取得コードの見直しが要る。")
        return 1
    print("netkeibaレイアウト検査: 問題なし")
    return 0


if __name__ == "__main__":
    sys.exit(main())
