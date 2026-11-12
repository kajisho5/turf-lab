# -*- coding: utf-8 -*-
"""定期実行が「静かに止まっていないか」を見張る

★なぜ要るのか★
  2026-07-28に、止まっていた定期実行が2つ同時に見つかった。
    ・/ai/ の成績更新が7日停止（daily.py のSTEPSに入っていなかった）
    ・オッズ記録が9日停止（トリガーが1回きりで期限切れ＋バッテリー制約）
  どちらも**失敗ではなく「動かない」**形なので、ログにエラーが残らない。
  そして両方とも、たまたま画面を見て気づいただけだった。

  失敗は気づける。気づけないのは「実行されなかった」ほう。
  だから「最後にいつ動いたか」を毎日点検する。

見るもの:
  1. タスクの NextRunTime が空でないか
     ★これが今回の直接原因★ トリガーが期限切れになると
     State は Ready のまま・LastTaskResult も 0 のままで、
     NextRunTime だけが空になる。ここを見ないと絶対に気づけない。
  2. LastRunTime が想定より古くないか
  3. そのタスクが実際に作っているはずの成果物が増えているか
     （タスクが走っていても中身が空回りしている場合を拾う）

使い方: python backtest/check_tasks.py
        （daily.py と npm run check から呼ばれる）
"""
import datetime
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# タスク名 -> (何をするものか, 最終実行がこの時間を超えて古かったら警告)
TASKS = {
    "SWTURF_Daily": ("日次更新（データ収集〜公開）", 36),
    "SWTURF_OddsRecorder": ("オッズ記録（9-23時・5分間隔）", 26),
    # 2026-07-30追加。毎朝9:20にヘッドレスEdgeでtweet.html?auto=lineを開き
    # LINE配信は2026-08-02にユーザー判断で終了（タスクはDisabled）。
    # 再開するなら Enable-ScheduledTask KajiKeiba-LINE-Runner ＋この行を復活。
    # "KajiKeiba-LINE-Runner": ("LINE配信の無人運転（毎朝9:20）", 30),
}

PS = ("Get-ScheduledTask -TaskName {names} -ErrorAction SilentlyContinue | "
      "ForEach-Object {{ $i = $_ | Get-ScheduledTaskInfo; "
      "[PSCustomObject]@{{ Name=$_.TaskName; State=[string]$_.State; "
      "Last=if($i.LastRunTime){{$i.LastRunTime.ToString('s')}}else{{''}}; "
      "Result=$i.LastTaskResult; "
      "Next=if($i.NextRunTime){{$i.NextRunTime.ToString('s')}}else{{''}} }} }} | "
      # ★-AsArray は PowerShell 5.1 に無い★ 付けるとエラーで出力が空になり
#   「タスクが登録されていない」と誤診断する。1件のときは辞書で返るので
#   受け取り側で吸収する。
      "ConvertTo-Json -Compress")


def query():
    names = ",".join(f"'{n}'" for n in TASKS)
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command",
             PS.format(names=names)],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=90)
    except Exception as e:
        print(f"[警告] タスク情報を取得できなかった: {e}")
        return None
    out = (r.stdout or "").strip()
    if not out:
        err = (r.stderr or "").strip()
        print("[警告] タスク情報が空だった（タスクが登録されていない可能性）"
              + (f" / stderr: {err[:200]}" if err else ""))
        return None
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        print(f"[警告] タスク情報を解釈できなかった: {out[:200]}")
        return None


def snapshot_check(problems):
    """オッズ記録が実際にファイルを増やしているか（前日ぶんで見る）。

    タスクが動いていても、取得に失敗し続けていれば0本のままになる。
    「動いた」と「仕事をした」は別なので分けて見る。
    """
    d = os.path.join(ROOT, "backtest", "odds_snapshots")
    if not os.path.isdir(d):
        return
    y = (datetime.date.today() - datetime.timedelta(days=1)).strftime("%Y%m%d")
    day = os.path.join(d, y)
    n = len([f for f in os.listdir(day)
             if f.endswith(".zip")]) if os.path.isdir(day) else 0
    # 地方競馬はほぼ毎日どこかで開催しているが、稀に全休の日がある。
    # 0本なら知らせる（全休なら無視してよい、と読み手が判断できるよう理由を書く）。
    if n == 0:
        problems.append(f"オッズ記録: 前日({y})のスナップショットが0本。"
                        "全休日なら問題ないが、そうでなければ取得が失敗している")
    else:
        print(f"  オッズ記録: 前日({y}) {n}本 取得済み")


def main():
    print("定期実行の点検")
    problems = []
    rows = query()
    if rows is None:
        # 取得できない環境（サーバー上など）では点検を諦めるが、落とさない
        return 0
    if isinstance(rows, dict):
        rows = [rows]

    seen = set()
    now = datetime.datetime.now()
    for r in rows:
        name = r.get("Name")
        seen.add(name)
        label, max_h = TASKS.get(name, (name, 48))
        last = r.get("Last") or ""
        nxt = r.get("Next") or ""
        res = r.get("Result")

        age = None
        if last:
            try:
                age = (now - datetime.datetime.fromisoformat(last)).total_seconds() / 3600
            except ValueError:
                pass

        agestr = f"{age:.1f}時間前" if age is not None else "実行履歴なし"
        print(f"  {label}: 最終 {agestr} / 次回 {nxt or '（無し）'} / 結果 {res}")

        # ★これが今回の事故の直接原因★ 次回予定が空＝もう二度と動かない
        if not nxt:
            problems.append(f"{label}: 次回実行の予定が無い。"
                            "トリガーが期限切れか無効になっている"
                            "（Stateは Ready のままなので状態だけ見ても分からない）")
        if age is not None and age > max_h:
            problems.append(f"{label}: 最終実行が{age:.0f}時間前"
                            f"（{max_h}時間以内であるべき）")
        # ★267009 (0x41301) = 「現在実行中」★ この点検は日次の先頭ステップとして
        #   走るので、日次タスク自身は必ず実行中＝毎朝の偽警報になっていた
        #   （2026-08-03/04のrc=1の正体。8/2の本物の警告に紛れて気づかなかった）。
        if res not in (0, None, 267009):
            problems.append(f"{label}: 前回の終了コードが {res}")

    for name, (label, _) in TASKS.items():
        if name not in seen:
            problems.append(f"{label}: タスク自体が登録されていない（{name}）")

    snapshot_check(problems)

    if problems:
        print("\n[要対応] 定期実行に問題がある:")
        for p in problems:
            print(f"  - {p}")
        return 1
    print("定期実行に問題なし。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
