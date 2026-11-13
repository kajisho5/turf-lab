#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""投稿の回の前後は公開しないための待ち時間（秒）を出す。0 なら今すぐ公開してよい。

2026-11-13 19:10 の事故（自動投稿のプログラムを公開した直後に、夜の答え合わせが誤って投稿された）の再発防止。
「気をつける」ではなく、公開の手順そのものが投稿の回を避ける。

避ける時間帯（日本時間）:
  6:20〜6:45   朝の前の点検（6:30）
  8:15〜9:35   朝の予想（8:30）・やり直し（9:00・9:20）・週間／月間まとめ（9:00・9:10）
  22:15〜23:25 夜の答え合わせ（22:30）・やり直し（22:50・23:10）

使い方: python3 tools/deploy_window.py            → 今から待つ秒数
        python3 tools/deploy_window.py --now 08:20 → その時刻だった場合（試験用）
"""
import datetime
import sys

WINDOWS = [((6, 20), (6, 45)), ((8, 15), (9, 35)), ((22, 15), (23, 25))]


def wait_seconds(h, m, s=0):
    now = h * 3600 + m * 60 + s
    for (a, b), (c, d) in WINDOWS:
        lo, hi = a * 3600 + b * 60, c * 3600 + d * 60
        if lo <= now < hi:
            return hi - now
    return 0


def main():
    if len(sys.argv) >= 3 and sys.argv[1] == "--now":
        h, m = sys.argv[2].split(":")
        print(wait_seconds(int(h), int(m)))
        return
    j = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9)))
    print(wait_seconds(j.hour, j.minute, j.second))


if __name__ == "__main__":
    main()
