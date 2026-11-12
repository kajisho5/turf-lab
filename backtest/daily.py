# -*- coding: utf-8 -*-
"""毎日の更新をまとめて回す（Task Scheduler から呼ぶ）

順番に意味がある:
  1. データ収集（地方の月次ZIP／中央はJV-Linkが空いていれば）
  2. 馬別の当地・当距離複勝率を作り直す   ← 開催のたびに古くなるので毎日
  3. 公開サイトへ反映

★1つ失敗しても残りは進める★
  収集が失敗した日でも、既存データでの再生成と反映はできる。
  全部止めると、古いまま放置されるほうが害が大きい。

使い方: python backtest/daily.py
"""
import os, subprocess, sys, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HERE = os.path.join(ROOT, "backtest")
LOG = os.path.join(HERE, "store", "_daily.log")

# ★子プロセスの黒い窓を出さない（2026-09-14）★
#   このタスクを pythonw.exe（窓なし）で回すと、親に無い「コンソール」を
#   子(node/python)が自前で新規に開いてしまい、逆に窓が乱立する。
#   CREATE_NO_WINDOW を付けると子も窓なしで走る。Windows専用フラグなので他OSでは0。
NOWIN = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0

STEPS = [
    # ★2026-07-28追加★ 定期実行が「静かに止まる」のを見張る。
    #   /ai/が7日・オッズ記録が9日止まっていたのに、どちらもログには何も出ず、
    #   画面をたまたま見て気づいた。失敗より「実行されなかった」ほうが危ない。
    #   先頭に置くのは、他のステップが動く前に異常を記録に残したいから。
    ("定期実行の点検",  [sys.executable, os.path.join(HERE, "check_tasks.py")]),
    # ★2026-08-04追加★ netkeibaのHTML構造が変わると、オッズ取得は例外ではなく
    #   「静かに空」を返す。実際 chk_b2_ が消えて複勝オッズが常に0件になっていたのを
    #   実データを見て偶然発見した。正規表現が当たるかを毎日2リクエストだけで見張る。
    ("netkeiba構造の点検", [sys.executable, os.path.join(HERE, "check_netkeiba_layout.py")]),
    ("データ収集",      [sys.executable, os.path.join(HERE, "collect_daily.py")]),
    # ★2026-08-04追加★ 答え合わせの自動化。結果保存が「ユーザーが答え合わせした日」
    #   だけで、8/3は46R予想中5Rしか結果が無かった（シャドー/プラシーボ/週間画像が飢餓に）。
    #   公式ZIPから同じ形で自動保存する（既存保存はnoclobber）。ZIP取得の直後・
    #   シャドー(配車係)より前に置く必要がある。
    ("結果の自動保存",  [sys.executable, os.path.join(HERE, "push_results.py")]),
    ("馬データ再生成",  [sys.executable, os.path.join(HERE, "build_horse_index.py")]),
    # ★2026-07-26追加★ 「予想の記録」(/record/)は外れも全件載せる信頼性の核。
    #   入力の pred_data はサーバーのpredictions.phpが書き溜めたもので、
    #   同期もページ再生成もこれまで手作業だった。2026-07-24に同期忘れで
    #   1ヶ月古いまま公開されていたのが発覚しているので日次に載せる。
    ("予想データ同期",  [sys.executable, os.path.join(HERE, "sync_pred_data.py")]),
    ("記録ページ再生成", [sys.executable, os.path.join(HERE, "gen_record_page.py")]),
    # ★2026-07-28追加★ bt_all.jsonl（440MB・全17.8万R）も日次に載せる。
    #   これまで手動更新で、人格成績も記事もDBページも「最後に手で回した日」で
    #   止まっていた。実測77秒しかかからない（数十分という見積もりが誤っていた）。
    #   一時ファイルに書いてから差し替えるので、途中で落ちても既存ファイルは無傷。
    ("学習用データ再構築", [sys.executable, os.path.join(HERE, "build_dataset.py")]),
    # ★2026-07-30追加★ 騎手・厩舎・父の事前複勝率の索引。
    #   これは**採点に使う**（LTRのjkr/trr/sir列）ので、止まると予想が
    #   古い率で動く。build_dataset.py が書くサイドカーを読むので直後に置く。
    #   ★入れ忘れると静かに劣化する★ 索引が古くても画面はエラーを出さない。
    ("騎手/厩舎/父の索引", [sys.executable, os.path.join(HERE, "build_jockey_index.py")]),
    # 中央データも日次で（馬場状態・全券種払戻が入っている。/ai/の中央成績が読む）
    ("中央データ再構築",  [sys.executable, os.path.join(HERE, "build_jra_dataset.py")]),
    # ◎複勝見込みの較正表（tweet.htmlの表示用。モデルを変えたら作り直す必要がある）
    ("複勝見込みの較正",  [sys.executable, os.path.join(HERE, "calib_ltr.py")]),
    # 配車係シャドー(#91+#55): 公開予想を読める/半読み/読めないに分類し影ログへ蓄積。
    # 本番表示は変えない。N>=500たまったら分類境界を評価し表示昇格を判断する。
    ("配車係シャドー",    [sys.executable, os.path.join(HERE, "haisha_shadow.py"), "3"]),
    # プラシーボ対照(#193): 毎月1日に先月30日分を research_log.md へ（実測◎ vs ランダム vs 1番人気）
    ("プラシーボ月次",    [sys.executable, os.path.join(HERE, "monthly_placebo.py")]),
    # ★2026-08-03追加★ 週間成績のツイート用画像（月曜のみ・先週月〜日の実測を1200x675で生成）。
    #   数字は本番の predictions/results 蓄積そのまま＝盛れない。投稿は手動。
    ("週間成績の画像",    [sys.executable, os.path.join(HERE, "weekly_image.py")]),
    # ★2026-07-28追加★ /ai/（万馬券的中・高回収・AI別成績）が7日間止まっていた。
    #   「最新確定(7/20)」と表示したまま7/28を迎えていたのを指摘されて発覚。
    #   日次は動いていたが、このチェーンがSTEPSに入っていなかった。
    #   personas_stats.json → persona_bets.json → /ai/ の順に依存する。
    #   実測: bt_personas 2分31秒 / bt_persona_bets 45秒（bt_all.jsonl 440MB を走査）。
    # ★2026-08-04追加★ 人格の確定印（公式データ計算）を公開ファイルに書き出す。
    #   レースページは確定印があるレースでは必ずこちらを表示＝的中カードと単一の正。
    #   bt_all/bt_jra の再構築後に回す必要がある。
    ("人格の確定印",    ["node", os.path.join(HERE, "bt_persona_marks.js")]),
    ("AI成績の再計測",  ["node", os.path.join(HERE, "bt_personas.js")]),
    ("AI買い目の再計測", ["node", os.path.join(HERE, "bt_persona_bets.js")]),
    ("AIページ再生成",  [sys.executable, os.path.join(HERE, "gen_ai_page.py")]),
    ("AI個別ページ再生成", [sys.executable, os.path.join(HERE, "gen_ai_detail_pages.py")]),
    # ★2026-07-29追加★ 金沢・最終R・⭐単勝の前向き検証を毎日積む。
    #   過去604RでROI107.9%（95%区間 71.1〜155.2%）＝偶然とも本物とも言えない。
    #   過去データでは決着しないので、新しいデータを貯めて判定する。
    #   予想を保存した後・結果が入った後に回す必要があるのでこの位置。
    ("⭐の前向き検証", [sys.executable, os.path.join(HERE, "fwd_star_watch.py")]),
    # ★bt_all.jsonl を日次で作り直す副作用★
    #   それを読んでいる生成物（記事・DBページ・データ入口）が毎日「古い」判定になる。
    #   放置すると check_stale が毎日赤くなり、そのうち誰も見なくなる（警報疲れ）。
    #   なので同じ日次の中で作り直しまでやりきる。--fix は古いものだけ回すので軽い。
    ("古い生成物の作り直し", [sys.executable, os.path.join(HERE, "check_stale.py"), "--fix"]),
    ("公開サイトへ反映", [sys.executable, os.path.join(HERE, "deploy.py"),
                          "--site", "public", "--push", "--yes"]),
]

# ★Cloudflare 切替後は反映先を Cloudflare に替える★（docs/CLOUDFLARE_MIGRATION.md）
#   cloudflare/deploy_cf.json の use_cloudflare を true にした時だけ。既定は今まで通り FTP。
try:
    import json as _json
    if _json.load(open(os.path.join(ROOT, "cloudflare", "deploy_cf.json"), encoding="utf-8")).get("use_cloudflare"):
        STEPS[-1] = ("公開サイトへ反映", [sys.executable, os.path.join(ROOT, "cloudflare", "deploy_cf.py"),
                                      "--site", "public", "--push", "--yes"])
except Exception:
    pass


def log(msg):
    line = time.strftime("[%m-%d %H:%M:%S] ") + msg
    print(line, flush=True)
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def main():
    log("=== 日次更新 開始 ===")
    ng = 0
    for name, cmd in STEPS:
        log(f"--- {name}")
        try:
            r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=5400,
                               creationflags=NOWIN)
            tail = "\n".join((r.stdout or "").strip().splitlines()[-3:])
            log(f"    rc={r.returncode} {tail[:200]}")
            if r.returncode != 0:
                # ★stderrも残す★ 例外で落ちたステップはstdoutが空のことが多く、
                #   rc=1だけ記録されて原因が消えていた（2026-08-04の⭐検証rc=1が特定不能に）
                err = "\n".join((r.stderr or "").strip().splitlines()[-4:])
                if err:
                    log(f"    !! stderr: {err[:400]}")
                ng += 1
        except Exception as e:
            log(f"    !! 失敗 {e}")
            ng += 1
    log(f"=== 日次更新 終了 失敗{ng}/{len(STEPS)} ===")
    return 0 if ng < len(STEPS) else 1


if __name__ == "__main__":
    sys.exit(main())
