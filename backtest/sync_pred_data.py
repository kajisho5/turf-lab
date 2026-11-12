# -*- coding: utf-8 -*-
"""本番の pred_data/（予想の生データ）をローカルへ同期する

★なぜ要るか★
  「予想の記録」ページ（/record/）は、外れも隠さず全件載せる、このサイトの
  信頼性の核。その入力が backtest/store/pred_data/ で、本番の
  predictions.php が書き溜めたものをローカルへ落として使う。

  ところがこの同期は今まで**手作業（WinSCPのsynchronize）**だった。
  2026-07-24に、同期を忘れていたせいで記録ページが**約1ヶ月古いまま
  公開され続けていた**のが発覚している（1,137レース〜7/17で停止していた。
  詳細は docs/SCORING_AUDIT.md 2026-07-24）。
  「検証を全部出す」を看板にしているサイトで結果ページが古いのは
  自己矛盾なので、日次で自動化する。

★取得のみ・削除しない★
  synchronize local は既定でローカル側の余分なファイルを消しうるため、
  -delete は付けない。本番の30日削除で消えた古い予想もローカルには温存する
  （過去の実績を失わないため。前回の手動同期でも同じ方針を採った）。

使い方: python backtest/sync_pred_data.py
        （daily.py から毎日呼ばれる）
"""
import os
import sys

import deploy   # winscp() と SESSION を再利用する（認証情報は WinSCP 側が持つ）

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCAL = os.path.join(ROOT, "backtest", "store", "pred_data")
REMOTE = "/seventh-well.com/odds/pred_data"


def _use_cloudflare():
    """切替後は Cloudflare(D1) から取る（cloudflare/deploy_cf.json の use_cloudflare）"""
    p = os.path.join(ROOT, "cloudflare", "deploy_cf.json")
    try:
        import json
        c = json.load(open(p, encoding="utf-8"))
        # odds_cloudflare: /odds だけ先に Cloudflare へ移した状態（公開サイトは旧サーバーのまま）
        return bool(c.get("use_cloudflare") or c.get("odds_cloudflare"))
    except Exception:
        return False


def main():
    if _use_cloudflare():
        sys.path.insert(0, os.path.join(ROOT, "cloudflare"))
        import sync_pred_cf
        return sync_pred_cf.main()
    os.makedirs(LOCAL, exist_ok=True)
    before = len(os.listdir(LOCAL))
    # -delete は付けない（★上のコメント参照★）
    out = deploy.winscp([f'synchronize local "{os.path.normpath(LOCAL)}" "{REMOTE}"'])
    after = len(os.listdir(LOCAL))
    added = after - before
    if "Error" in out or "error" in out.lower() and "0 errors" not in out.lower():
        # WinSCP は握りつぶさず出力を残す。判断材料として全文を出す
        print(out.strip()[-800:])
    print(f"pred_data 同期: {before} -> {after} 件（+{added}）")
    # 同期できた件数が0でも「今日は新しい予想が無い」だけの場合があるので失敗にしない。
    # ローカルが空のままなら明らかにおかしいのでそこだけ失敗扱いにする。
    if after == 0:
        print("!! pred_data が空。WinSCPのセッション設定かリモートパスを確認すること。")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
