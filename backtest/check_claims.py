# -*- coding: utf-8 -*-
"""★嘘検出CI★ 公開している実測数字と台帳(claims_registry.json)の突き合わせ

なぜ要るか（実際に起きた事故2件の恒久対策）:
  - 「複勝ROI 89%」…一度82.8%と測り直したのに、フォロワーに配る文面だけ89%のまま残った
  - 「高知⭐回収156%」…再現できない数字が7ページに残り続けた
  数字は測った瞬間から腐り始めるのに、HTMLのあちこちに散らばると人間は追い切れない。
  → 台帳を単一の正とし、(1)台帳の数字がHTMLに存在するか (2)撤回済みの数字が
    肯定文脈で再混入していないか、を機械で検査する。

使い方: python backtest/check_claims.py   （npm run check に組込み）
更新手順: 測り直し → claims_registry.json → HTML の順。逆順は事故のもと。
"""
import io
import json
import os
import re
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REG = os.path.join(ROOT, "backtest", "claims_registry.json")

def in_comment(s, pos):
    """pos が JSの行/ブロックコメント・HTMLコメントの中なら True。
    行コメント判定は「その行の pos より前に // がある」: URLの // を誤検知しうるが、
    数字の直前10文字に限る正規表現と組み合わせる限り実害は出ていない。"""
    line = s[s.rfind("\n", 0, pos) + 1: pos]
    if "//" in line:
        return True
    if s.rfind("/*", 0, pos) > s.rfind("*/", 0, pos):
        return True
    if s.rfind("<!--", 0, pos) > s.rfind("-->", 0, pos):
        return True
    return False


def selftest():
    """検出器自身の故障を検出する（正規表現やコメント判定が壊れると
    「何も見つからない=全部OK」に化けて静かに死ぬため、毎回最初に回す）"""
    pat = re.compile(r"(複勝率|的中率|回収率|回収|ROI|複ROI|単ROI)[^%<>{}\n]{0,10}?(\d{2,3}(?:\.\d)?)%")
    s = "<div>複勝率99.9%</div>\n// 複勝率88.8%\n/* ROI77.7% */\n<!-- 回収66.6% -->\ntitle=\"単ROI55.5%\""
    vis = {m.group(2) for m in pat.finditer(s) if not in_comment(s, m.start())}
    assert vis == {"99.9", "55.5"}, f"自己診断失敗: 表示検出={vis}（期待は 99.9 と 55.5）"


def main():
    selftest()
    reg = json.load(open(REG, encoding="utf-8"))
    ng = 0
    cache = {}
    def read(p):
        if p not in cache:
            cache[p] = open(os.path.join(ROOT, p), encoding="utf-8").read()
        return cache[p]

    # (1) 台帳の数字がHTMLに実在するか（=HTMLだけ勝手に変わっていないか）
    for c in reg["claims"]:
        for path, pat in c["files"]:
            try:
                s = read(path)
            except OSError:
                print(f"NG [{c['id']}] ファイルが無い: {path}")
                ng += 1
                continue
            if not re.search(pat, s):
                print(f"NG [{c['id']}] {path} に台帳の数字({c['value']} {c['desc']})が見つからない")
                print(f"    → HTMLを変えたなら台帳も更新する。台帳が正 ({c['source']} / {c['measured']}測定)")
                ng += 1

    # (2) 撤回済みの数字が肯定文脈で再混入していないか
    for f in reg.get("forbidden", []):
        pat = re.compile(f["pattern"])
        allow = re.compile(f["allow_context"]) if f.get("allow_context") else None
        for path in f["files"]:
            try:
                s = read(path)
            except OSError:
                continue
            for m in pat.finditer(s):
                ctx = s[max(0, m.start()-60): m.end()+60]
                if allow and allow.search(ctx):
                    continue          # 「撤回した」等の説明文脈はOK
                print(f"NG [撤回済み再混入] {path}: {m.group(0)!r}")
                print(f"    → {f['desc']}")
                ng += 1

    # (3) ★登録漏れ検出★ HTMLの【表示に出る】実測数字が台帳に無ければ落とす。
    #     コメント（// と /* */ と <!-- -->）内は検査しない: あれは監査の歴史であって
    #     公開数字ではない。title属性はhoverで見えるので検査対象。
    #     基準線=claims_legacy_allowlist.json（2026-08-04に表示のみへ棚卸し済み）。
    #     新数字は「測る→claims_registryに登録→HTMLに書く」の順を強制する。
    legacy_path = os.path.join(ROOT, "backtest", "claims_legacy_allowlist.json")
    if os.path.exists(legacy_path):
        legacy = json.load(open(legacy_path, encoding="utf-8"))["files"]
        reg_vals = {c["value"] for c in reg["claims"]}
        pat_stat = re.compile(r"(複勝率|的中率|回収率|回収|ROI|複ROI|単ROI)[^%<>{}\n]{0,10}?(\d{2,3}(?:\.\d)?)%")
        for path in legacy.keys():
            try:
                s = read(path)
            except OSError:
                continue
            known = set(legacy.get(path, [])) | reg_vals
            new = {m.group(2) for m in pat_stat.finditer(s)
                   if not in_comment(s, m.start())} - known
            for v in sorted(new, key=float):
                print(f"NG [未登録の新数字] {path}: {v}% が表示に出るのに台帳にもレガシー凍結リストにも無い")
                print("    → 実測の出典を claims_registry.json に登録してからHTMLに書くこと")
                ng += 1

    if ng:
        print(f"\n公開数字の検査: {ng}件の乖離。台帳(backtest/claims_registry.json)と揃えること。")
        return 1
    print(f"OK  公開数字の検査: 台帳{len(reg['claims'])}件一致・撤回済み再混入なし・未登録の新数字なし")
    return 0

if __name__ == "__main__":
    sys.exit(main())
