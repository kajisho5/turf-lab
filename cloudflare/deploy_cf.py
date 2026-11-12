# -*- coding: utf-8 -*-
"""Cloudflare への本番デプロイ（deploy.py の置き換え。やることは同じ）

  1. dist を作り直す（--site で選んだサイトだけ。他は前回のまま）
  2. 前回デプロイした中身と比べて、変わったファイルを一覧
  3. 安全ゲート（deploy.py と同じ: ブランド名の漏れ / lab のパス漏れ / 未定義識別子 / 採点の二重管理）
  4. /odds/ の画面が変わったら sw.js のキャッシュトークンを +1
  5. 確認を取って `wrangler deploy`
  6. 本番から取り直してハッシュ照合

使い方:
  python cloudflare/deploy_cf.py                       # 差分表示のみ（公開サイト）
  python cloudflare/deploy_cf.py --site legacy --push  # 運営用(/odds/)を確認つきで反映
  python cloudflare/deploy_cf.py --site public --push --yes   # daily.py から
  python cloudflare/deploy_cf.py --setup               # 初回だけ: D1作成・表の作成・合言葉の登録

認証: 環境変数 CLOUDFLARE_API_TOKEN（または `npx wrangler login` 済み）。このスクリプトは読まない・持たない。
"""
import argparse
import hashlib
import json
import os
import re
import secrets
import subprocess
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "backtest"))
import build as B  # noqa: E402
import deploy as D  # noqa: E402

DEPLOYED = os.path.join(HERE, ".deployed.json")       # 最後にデプロイした dist のハッシュ一覧
CONF = os.path.join(HERE, "deploy_cf.json")           # 確認に使うURL（切替前は workers.dev）
WIN = os.name == "nt"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"


def npx(args, **kw):
    return subprocess.run(["npx.cmd" if WIN else "npx", "wrangler"] + args, cwd=HERE, **kw)


def conf():
    c = {"bases": {"k": "https://kajikeiba.com", "odds": "https://seventh-well.com/odds", "lab": "https://seventh-well.com/lab"}}
    if os.path.exists(CONF):
        c.update(json.load(open(CONF, encoding="utf-8")))
    return c


def setup():
    """初回だけ。D1を作ってIDを wrangler.jsonc に書き、表を作り、管理口の合言葉を登録する"""
    wj = os.path.join(HERE, "wrangler.jsonc")
    s = open(wj, encoding="utf-8").read()
    if "00000000-0000-0000-0000-000000000000" in s:
        r = npx(["d1", "create", "kajikeiba"], capture_output=True, text=True, encoding="utf-8")
        print(r.stdout[-800:], r.stderr[-800:])
        m = re.search(r'"?database_id"?\s*[:=]\s*"([0-9a-f-]{36})"', r.stdout + r.stderr)
        if not m:
            r2 = npx(["d1", "list", "--json"], capture_output=True, text=True, encoding="utf-8")
            for d in json.loads(r2.stdout or "[]"):
                if d.get("name") == "kajikeiba":
                    m = re.match(r"(.*)", d["uuid"])
        if not m:
            print("!! D1 のIDが取れなかった。上の出力を確認する。")
            return 1
        s = s.replace("00000000-0000-0000-0000-000000000000", m.group(1))
        open(wj, "w", encoding="utf-8", newline="\n").write(s)
        print("D1 を作成:", m.group(1))
    r = npx(["d1", "migrations", "apply", "kajikeiba", "--remote"])
    if r.returncode:
        return 1
    tp = os.path.join(HERE, ".admin_token")
    if not os.path.exists(tp):
        open(tp, "w", encoding="utf-8").write(secrets.token_urlsafe(32))
    tok = open(tp, encoding="utf-8").read().strip()
    # 先に1回デプロイしないと secret を置けない
    B.build(["k", "odds", "lab"])
    if npx(["deploy"]).returncode:
        return 1
    p = subprocess.run(["npx.cmd" if WIN else "npx", "wrangler", "secret", "put", "ADMIN_TOKEN"], cwd=HERE, input=tok, text=True)
    if p.returncode:
        return 1
    print("\n初回準備おわり。管理口の合言葉は cloudflare/.admin_token（gitに入れない）。")
    print("LINE配信を本番で使う時だけ: npx wrangler secret put LINE_CHANNEL_TOKEN")
    json.dump(B.manifest(), open(DEPLOYED, "w"), indent=0)
    return 0


def sha_file(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--site", default="public", choices=list(B.SITES))
    ap.add_argument("--push", action="store_true")
    ap.add_argument("--yes", action="store_true")
    ap.add_argument("--no-bump", action="store_true")
    ap.add_argument("--setup", action="store_true")
    a = ap.parse_args()
    if a.setup:
        return setup()

    sites = list(B.SITES[a.site])
    old = json.load(open(DEPLOYED)) if os.path.exists(DEPLOYED) else {}
    pl, warn, missing = B.build(sites)
    for w in warn:
        print("  [重なり] " + w)
    if missing:
        print("!! ローカルに無いファイル:", missing[:10])
        return 1
    new = B.manifest()
    prefix = {"k": "k/", "odds": "s/odds/", "lab": "s/lab/"}
    changed = sorted(k for k, v in new.items() if old.get(k) != v)
    gone = sorted(k for k in old if k not in new)

    # ---- 安全ゲート ----
    if "k" in sites:
        leaks = D.brand_leaks(D.PUBLIC_MAP)
        if leaks:
            print("!! 公開サイトに lab 用のブランド名が混じっている:", leaks[:5])
            return 1
    if "lab" in sites:
        bad = []
        for local, remote in D.LAB_MAP:
            lp = os.path.join(ROOT, local)
            if os.path.exists(lp):
                lo = D.lab_leftovers(local, D.lab_transform(local, open(lp, "rb").read()))
                if lo:
                    bad.append((local, lo))
        if bad:
            print("!! /lab/ に寄せられていない絶対パスがある:", bad[:5])
            return 1

    def local_of(dist_rel):
        for site, pre in prefix.items():
            if dist_rel.startswith(pre):
                rel = "/" + dist_rel[len(pre):]
                hit = pl[site].get(rel)
                return hit[0] if hit else None
        return None

    changed_local = [l for l in (local_of(c) for c in changed) if l]
    html = sorted({l for l in changed_local if l.endswith(".html") and l.startswith("deploy/")})
    if a.push and html:
        print(f"安全ゲート: check_undefined.js ({len(html)}件)", flush=True)
        if subprocess.run(["node", os.path.join(ROOT, "backtest", "check_undefined.js")] + html, cwd=ROOT).returncode:
            print("!! 未定義の識別子が見つかった。中止した。")
            return 1
        if "deploy/tweet.html" in html:
            if subprocess.run([sys.executable, os.path.join(ROOT, "backtest", "check_scoring_sync.py")], cwd=ROOT).returncode:
                print("!! tweet.html と core/scoring.js がズレている。中止した。")
                return 1

    # ---- sw.js のトークン（/odds/ の画面が変わった時だけ）----
    bumped = None
    shell = [c for c in changed if c.startswith("s/odds/") and c.endswith((".html", ".js")) and c != "s/odds/sw.js"]
    if a.push and "odds" in sites and shell and not a.no_bump:
        bumped = D.bump_sw_token()
        if bumped:
            print(f"キャッシュトークン: {bumped[0]} -> {bumped[1]}")
            B.build(["odds"])
            new = B.manifest()
            changed = sorted(k for k, v in new.items() if old.get(k) != v)

    print("=" * 70)
    print(f"変わったファイル {len(changed)} 件 / 消えるファイル {len(gone)} 件")
    for c in changed[:80]:
        print("  [差分] " + c)
    if len(changed) > 80:
        print(f"  …ほか {len(changed) - 80} 件")
    for g in gone[:20]:
        print("  [削除] " + g)
    if not a.push:
        print("（表示のみ。反映するには --push）")
        return 0
    if not changed and not gone and old:
        print("差分なし。Worker のコードだけ更新する場合も含め、そのまま deploy する。")
    if not a.yes:
        if input("本番に反映する。よろしいか [yes/N]: ").strip().lower() != "yes":
            print("中止した。")
            return 1

    r = npx(["deploy"])
    if r.returncode:
        print("!! wrangler deploy が失敗した。")
        return 1

    # ---- 本番から取り直して照合（キャッシュ反映に数秒かかることがある）----
    bases = conf()["bases"]
    time.sleep(3)
    ng = 0
    targets = changed[:200]
    for c in targets:
        site = next(s for s, pre in prefix.items() if c.startswith(pre))
        rel = c[len(prefix[site]):]
        url = f"{bases[site]}/{rel}"
        if url.endswith("/index.html"):
            url = url[: -len("index.html")]
        try:
            req = urllib.request.Request(f"{url}?_={int(time.time() * 1000)}", headers={"User-Agent": UA, "Referer": bases[site] + "/"})
            with urllib.request.urlopen(req, timeout=120) as resp:
                got = hashlib.sha256(resp.read()).hexdigest()
        except Exception as e:  # noqa: BLE001
            got = f"ERR {e}"
        ok = got == new[c]
        ng += 0 if ok else 1
        if not ok:
            print(f"  NG  {c}  ({got[:20]})")
    print(f"照合 {len(targets) - ng}/{len(targets)} 件一致")
    if ng:
        return 1
    json.dump(new, open(DEPLOYED, "w"), indent=0)
    print("完了。")
    if bumped:
        print(f"※ SCORING_AUDIT.md に {bumped[1]} として追記すること。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
