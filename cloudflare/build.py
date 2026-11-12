# -*- coding: utf-8 -*-
"""Cloudflare 用の配信物（cloudflare/dist/）と、Worker が使う表（src/gen/meta.ts）を作る

★置き場所の一覧は backtest/deploy.py の MAP / PUBLIC_MAP / LAB_MAP をそのまま使う★
  一覧を2系統にすると必ず片方に足し忘れる（deploy.py の LAB_MAP の教訓）。
  ここでは「どこに置くか」を一切持たない。

dist の形:
  dist/k/...        kajikeiba.com（PUBLIC_MAP）
  dist/s/odds/...   seventh-well.com/odds（MAP ＋ static_extra/odds）
  dist/s/lab/...    seventh-well.com/lab（LAB_MAP を lab_transform で書き換えたもの ＋ MAPのlab行 ＋ static_extra/lab）
  PHP と .htaccess は置かない（Worker が同じURLで答える）

--site で作り直す範囲を選ぶ（deploy.py と同じ意味）。選ばなかったサイトは前回の dist をそのまま使う
＝毎晩の daily.py（public だけ）が、作業途中の tweet.html を勝手に本番へ出さない。

使い方:
  python cloudflare/build.py --site public|legacy|lab|both
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "backtest"))
import deploy as D  # noqa: E402  置き場所の一覧はここだけが持つ

DIST = os.path.join(HERE, "dist")
EXTRA = os.path.join(HERE, "static_extra")
META = os.path.join(HERE, "src", "gen", "meta.ts")

SKIP_EXT = (".php",)
SKIP_NAMES = (".htaccess",)


def _skip(remote):
    b = os.path.basename(remote)
    return remote.endswith(SKIP_EXT) or b in SKIP_NAMES


def _put(dst_root, rel, data):
    p = os.path.join(dst_root, rel.lstrip("/"))
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "wb") as f:
        f.write(data)


def _read(local):
    with open(os.path.join(ROOT, local), "rb") as f:
        return f.read()


def plan():
    """{site: {rel: (local, transform)}} を返す。同じ置き場所に2つ来たら警告"""
    out = {"k": {}, "odds": {}, "lab": {}}
    warn = []

    def add(site, rel, local, lab):
        if rel in out[site] and out[site][rel][0] != local:
            warn.append(f"{site}{rel}: {out[site][rel][0]} と {local} が重なる（後者を採用）")
        out[site][rel] = (local, lab)

    for local, remote in D.PUBLIC_MAP:
        if _skip(remote):
            continue
        add("k", remote[len("/kajikeiba.com"):], local, False)
    for local, remote in D.LAB_MAP:
        if _skip(remote):
            continue
        add("lab", remote[len("/seventh-well.com/lab"):], local, True)
    for local, remote in D.MAP:
        if _skip(remote):
            continue
        if remote.startswith("/seventh-well.com/odds/"):
            add("odds", remote[len("/seventh-well.com/odds"):], local, False)
        elif remote.startswith("/seventh-well.com/lab/"):
            add("lab", remote[len("/seventh-well.com/lab"):], local, False)
    # サーバーにだけ置いてあった物（2026-10-29 に本番から取得して static_extra へ保存）
    for site in ("odds", "lab"):
        base = os.path.join(EXTRA, site)
        for r, _ds, fs in os.walk(base):
            for f in fs:
                full = os.path.join(r, f)
                rel = "/" + os.path.relpath(full, base).replace("\\", "/")
                if rel not in out[site]:
                    out[site][rel] = (os.path.relpath(full, ROOT).replace("\\", "/"), False)
    return out, warn


def build(sites):
    pl, warn = plan()
    roots = {"k": os.path.join(DIST, "k"), "odds": os.path.join(DIST, "s", "odds"), "lab": os.path.join(DIST, "s", "lab")}
    missing = []
    for site in sites:
        shutil.rmtree(roots[site], ignore_errors=True)
        for rel, (local, lab) in sorted(pl[site].items()):
            lp = os.path.join(ROOT, local)
            if not os.path.exists(lp):
                missing.append(local)
                continue
            data = _read(local)
            if lab:
                data = D.lab_transform(local, data)
            _put(roots[site], rel, data)
    write_meta(roots)
    return pl, warn, missing


def _js_regex(pat):
    return pat


def _js_repl(rep):
    return re.sub(r"\\(\d)", r"$\1", rep)


def av_hashes(root):
    """race.php の av(): core/ の中身の md5 先頭8桁"""
    out = {}
    core = os.path.join(root, "core")
    if os.path.isdir(core):
        for f in sorted(os.listdir(core)):
            p = os.path.join(core, f)
            if os.path.isfile(p):
                out[f] = hashlib.md5(open(p, "rb").read()).hexdigest()[:8]
    return out


def sitemap_urls():
    p = os.path.join(ROOT, "php", "sitemap_urls.php")
    if not os.path.exists(p):
        return []
    s = open(p, encoding="utf-8").read()
    return [list(m) for m in re.findall(r"\['([^']*)',\s*'([^']*)',\s*'([^']*)'\]", s)]


def jusho_keys():
    p = os.path.join(ROOT, "deploy", "data", "jusho", "data.json")
    try:
        return list(json.load(open(p, encoding="utf-8")).keys())
    except Exception:
        return []


def write_meta(roots):
    meta = {
        "AV": {"k": av_hashes(roots["k"]), "lab": av_hashes(roots["lab"])},
        "JUSHO_KEYS": jusho_keys(),
        "SITEMAP_URLS": sitemap_urls(),
        "LAB_SUBS": [[a, b] for a, b in D.LAB_SUBS],
        "LAB_PATH": [[_js_regex(p), "g", _js_repl(r)] for p, r in D.LAB_PATH_PATTERNS],
        "LAB_ADSENSE": D.LAB_ADSENSE_RE.pattern,
    }
    os.makedirs(os.path.dirname(META), exist_ok=True)
    body = "/* 自動生成: cloudflare/build.py ★手で編集しない★ */\n"
    body += f"export const AV: {{ k: Record<string, string>; lab: Record<string, string> }} = {json.dumps(meta['AV'], ensure_ascii=False)};\n"
    body += f"export const JUSHO_KEYS: string[] = {json.dumps(meta['JUSHO_KEYS'], ensure_ascii=False)};\n"
    body += f"export const SITEMAP_URLS: [string, string, string][] = {json.dumps(meta['SITEMAP_URLS'], ensure_ascii=False)};\n"
    body += f"export const LAB_SUBS: [string, string][] = {json.dumps(meta['LAB_SUBS'], ensure_ascii=False)};\n"
    body += f"export const LAB_PATH: [string, string, string][] = {json.dumps(meta['LAB_PATH'], ensure_ascii=False)};\n"
    body += f"export const LAB_ADSENSE: string = {json.dumps(meta['LAB_ADSENSE'], ensure_ascii=False)};\n"
    with open(META, "w", encoding="utf-8", newline="\n") as f:
        f.write(body)


def manifest():
    """dist の全ファイルのハッシュ（デプロイの差分判定・検証に使う）"""
    out = {}
    for r, _ds, fs in os.walk(DIST):
        for f in fs:
            p = os.path.join(r, f)
            out[os.path.relpath(p, DIST).replace("\\", "/")] = hashlib.sha256(open(p, "rb").read()).hexdigest()
    return out


SITES = {"public": ["k"], "legacy": ["odds"], "lab": ["lab"], "both": ["k", "odds", "lab"]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--site", default="both", choices=list(SITES))
    a = ap.parse_args()
    sites = SITES[a.site]
    # 初回は全部作る（dist が無いと選ばなかったサイトが空になる）
    for s, sub in (("k", "k"), ("odds", "s/odds"), ("lab", "s/lab")):
        if not os.path.isdir(os.path.join(DIST, sub)) and s not in sites:
            sites.append(s)
    pl, warn, missing = build(sites)
    n = {s: len(pl[s]) for s in pl}
    print(f"dist を作成: 公開 {n['k']} / 運営(odds) {n['odds']} / lab {n['lab']} 件（作り直し: {', '.join(sites)}）")
    for w in warn:
        print("  [重なり] " + w)
    for m in missing:
        print("  [無い] " + m)
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
