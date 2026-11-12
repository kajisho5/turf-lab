# -*- coding: utf-8 -*-
"""旧サーバー（お名前.com）のデータを Cloudflare D1 へ写す

2段階でやる。①旧サーバーから手元の写し（.mirror/）へ集める → ②写しを Worker の管理口へ送る。
何度流しても同じ結果になる（同じキーは上書き）。切替の直前にもう一度流せば最新分が入る。

  ① 集める（どちらか。両方やってもよい）
     python cloudflare/migrate.py ftp-pull     PCで実行。WinSCPの保存セッションでサーバーのフォルダを丸ごと写す
                                               （★全部取れる。こちらが本命★）
     python cloudflare/migrate.py http-pull    どこでも実行可。公開APIから集める
                                               （騎手キャッシュ・アクセス記録・LINE履歴は取れない）
  ② 送る
     python cloudflare/migrate.py push  --url https://kajikeiba-turf.XXXX.workers.dev
  ③ 確かめる（件数と、同じ問い合わせへの新旧の応答を比べる）
     python cloudflare/migrate.py verify --url https://kajikeiba-turf.XXXX.workers.dev

管理口の合言葉は環境変数 KAJI_ADMIN_TOKEN か cloudflare/.admin_token（gitに入れない）から読む。
"""
import argparse
import concurrent.futures as cf
import glob
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
MIRROR = os.path.join(HERE, ".mirror")
OLD = "https://seventh-well.com/odds"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"

# サーバー上のフォルダ → 写しのフォルダ（ftp-pull 用）
FTP_DIRS = [
    ("/seventh-well.com/odds/pred_data", "odds/pred_data"),
    ("/seventh-well.com/odds/lock_data", "odds/lock_data"),
    ("/seventh-well.com/odds/result_data", "odds/result_data"),
    ("/seventh-well.com/odds/horse_data", "odds/horse_data"),
    ("/seventh-well.com/odds/jockey_data", "odds/jockey_data"),
    ("/seventh-well.com/odds/bias_data", "odds/bias_data"),
    ("/seventh-well.com/odds/odds_data", "odds/odds_data"),
    ("/seventh-well.com/odds/data", "odds/data"),
    ("/seventh-well.com/odds/logs", "odds/logs"),
    ("/seventh-well.com/odds/line_outbox", "odds/line_outbox"),
    ("/seventh-well.com/odds/line_sent", "odds/line_sent"),
    ("/seventh-well.com/odds/official_results", "odds/official_results"),
    ("/seventh-well.com/odds/nardata", "odds/nardata"),
    ("/kajikeiba.com/logs", "k/logs"),
    ("/seventh-well.com/lab/logs", "lab/logs"),
    ("/seventh-well.com/odds/kaiko_data", "odds/kaiko_data"),
]


def safe_key(s):
    return re.sub(r"[^A-Za-z0-9_\-]", "_", s)


def php_str(v):
    if v is None or v is False:
        return ""
    if v is True:
        return "1"
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


def dumps(o):
    return json.dumps(o, ensure_ascii=False, separators=(",", ":"))


def get(url, tries=3):
    sep = "&" if "?" in url else "?"
    for i in range(tries):
        try:
            req = urllib.request.Request(f"{url}{sep}_={int(time.time() * 1000)}", headers={"User-Agent": UA, "Referer": OLD + "/"})
            with urllib.request.urlopen(req, timeout=180) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001
            if i == tries - 1:
                raise
            print(f"  再試行 {url[:80]} ({e})", flush=True)
            time.sleep(2 + i * 3)


def wfile(rel, data):
    p = os.path.join(MIRROR, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "wb") as f:
        f.write(data if isinstance(data, bytes) else data.encode("utf-8"))


# ------------------------------------------------------------------ ① 集める
def ftp_pull():
    sys.path.insert(0, os.path.join(ROOT, "backtest"))
    import deploy  # WinSCP の保存セッションを使う（認証情報はこちらで持たない）
    for remote, local in FTP_DIRS:
        lp = os.path.normpath(os.path.join(MIRROR, local))
        os.makedirs(lp, exist_ok=True)
        print(f"取得: {remote}", flush=True)
        out = deploy.winscp([f'synchronize local "{lp}" "{remote}"'])
        if "rror" in out and "0 errors" not in out.lower():
            print(out.strip()[-500:])
    # kaiko.php は保存場所が分からない（ソースがリポに無い）ので公開APIから
    pull_kaiko()
    print("完了 →", MIRROR)


def pull_kaiko():
    try:
        d = json.loads(get(f"{OLD}/kaiko.php?action=list"))
    except Exception as e:  # noqa: BLE001  切替後は旧URLが引けない。手元の写しがあればそれを使う
        if os.path.exists(os.path.join(MIRROR, "odds", "kaiko.json")):
            print(f"  回顧: 旧URLが引けない（{e}）。手元の写し odds/kaiko.json をそのまま使う")
            return
        raise
    wfile("odds/kaiko.json", dumps(d.get("records") or []))
    print(f"  回顧 {len(d.get('records') or [])} 件")


def http_pull():
    t0 = time.time()
    pull_kaiko()
    # 予想（日付ごとに取る。全件一括は60MB近くあり重い）
    dates = [str(x) for x in json.loads(get(f"{OLD}/predictions.php?action=dates"))["dates"]]
    rids, hids, n = set(), set(), 0
    for d in dates:
        recs = json.loads(get(f"{OLD}/predictions.php?action=list&date={urllib.parse.quote(d)}"))["records"]
        for r in recs:
            mode = php_str(r.get("mode")) if r.get("mode") is not None else "nar"
            k = safe_key(f"{php_str(r.get('date'))}_{mode}_{php_str(r.get('tc'))}")
            s = dumps(r)
            wfile(f"odds/pred_data/{k}.json", s)
            rids.update(re.findall(r'"race_id":"?(\d{12})', s))
            hids.update(re.findall(r'"hid":"?(\d{6,14})"?', s))
            n += 1
    print(f"  予想 {n} 件（{len(dates)} 日）")
    locks = json.loads(get(f"{OLD}/predictions.php?action=listlocks"))["locks"]
    for r in locks:
        mode = php_str(r.get("mode")) if r.get("mode") is not None else "nar"
        wfile(f"odds/lock_data/{safe_key(php_str(r.get('date')) + '_' + mode + '_' + php_str(r.get('tc')))}.json", dumps(r))
    print(f"  ロック {len(locks)} 件")
    bias = json.loads(get(f"{OLD}/bias.php?action=list"))["records"]
    for r in bias:
        mode = php_str(r.get("mode")) if r.get("mode") is not None else "nar"
        wfile(f"odds/bias_data/{safe_key(php_str(r.get('date')) + '_' + mode)}.json", dumps(r))
    print(f"  バイアス {len(bias)} 件")
    # 結果（予想に出てくるレースIDで引く）
    got = 0
    rl = sorted(rids)
    for i in range(0, len(rl), 80):
        res = json.loads(get(f"{OLD}/results.php?action=get&ids={','.join(rl[i:i + 80])}"))["results"]
        if isinstance(res, dict):
            for rid, v in res.items():
                wfile(f"odds/result_data/{safe_key(rid)}.json", dumps(v)); got += 1
    print(f"  結果 {got} 件（予想に出てくる {len(rl)} レース中）")
    # 馬キャッシュ（予想に出てくる馬IDで引く）
    got = 0
    hl = sorted(hids)
    def one(chunk):
        return json.loads(get(f"{OLD}/horse.php?action=getbatch&hids={','.join(chunk)}"))["records"]
    with cf.ThreadPoolExecutor(4) as ex:
        for res in ex.map(one, [hl[i:i + 60] for i in range(0, len(hl), 60)]):
            if isinstance(res, dict):
                for hid, v in res.items():
                    wfile(f"odds/horse_data/{hid}.json", dumps(v)); got += 1
    print(f"  馬 {got} 件（予想に出てくる {len(hl)} 頭中）")
    # オッズ時系列
    od = json.loads(get(f"{OLD}/oddslog.php?action=dates"))["dates"]
    got = 0
    for d in od:
        lst = json.loads(get(f"{OLD}/oddslog.php?action=list&date={d['date']}"))["races"]
        def g(rid, date=d["date"]):
            return rid, get(f"{OLD}/oddslog.php?action=get&rid={rid}&date={date}")
        with cf.ThreadPoolExecutor(6) as ex:
            for rid, body in ex.map(g, [x["rid"] for x in lst]):
                wfile(f"odds/odds_data/{d['date']}/{rid}.json", body); got += 1
    print(f"  オッズ時系列 {got} 件（{len(od)} 日）")
    # 旧オッズ異常ログ（anomaly.html）
    for m in ("jra", "nar"):
        recs = json.loads(get(f"{OLD}/odds-log.php?action=list&mode={m}"))["records"]
        wfile(f"odds/data/odds_log_{m}.json", dumps(recs))
        print(f"  旧オッズ異常ログ {m} {len(recs)} 件")
    print(f"完了（{time.time() - t0:.0f}秒）→ {MIRROR}")
    print("※ 騎手キャッシュ・アクセス記録・JSエラー・LINE履歴は公開APIで取れない。PCで ftp-pull を流すこと。")


# ------------------------------------------------------------------ ② 送る
def token():
    t = os.environ.get("KAJI_ADMIN_TOKEN")
    if not t:
        p = os.path.join(HERE, ".admin_token")
        if os.path.exists(p):
            t = open(p, encoding="utf-8").read().strip()
    if not t:
        sys.exit("管理口の合言葉が無い（環境変数 KAJI_ADMIN_TOKEN か cloudflare/.admin_token）")
    return t


def post_ndjson(base, table, rows, tok):
    """4MB 程度ずつ送る"""
    buf, size, sent, errs = [], 0, 0, []
    def flush():
        nonlocal buf, size, sent
        if not buf:
            return
        body = ("\n".join(buf) + "\n").encode("utf-8")
        req = urllib.request.Request(f"{base}/__admin/import?table={table}", data=body, method="POST",
                                     headers={"X-Admin-Token": tok, "Content-Type": "application/x-ndjson", "User-Agent": UA})
        for i in range(3):
            try:
                with urllib.request.urlopen(req, timeout=300) as r:
                    j = json.loads(r.read())
                break
            except Exception as e:  # noqa: BLE001
                if i == 2:
                    raise
                print(f"  再送 {table} ({e})"); time.sleep(3)
        sent += j.get("n", 0)
        errs.extend(j.get("errors") or [])
        buf, size = [], 0
    for r in rows:
        line = dumps(r)
        buf.append(line); size += len(line.encode("utf-8"))
        if size > 3_500_000 or len(buf) >= 400:
            flush()
    flush()
    return sent, errs


def read_text(p):
    with open(p, "rb") as f:
        b = f.read()
    return b.decode("utf-8", "replace")


def valid_json(s):
    try:
        json.loads(s)
        return True
    except Exception:
        return False


def files(rel, pat="*.json"):
    return sorted(glob.glob(os.path.join(MIRROR, rel, pat)))


def rows_simple(rel, keycol):
    for p in files(rel):
        s = read_text(p)
        if not s.strip() or not valid_json(s):     # 0バイト・壊れたファイルは PHP の一覧でも飛ばされていた
            continue
        yield {keycol: os.path.basename(p)[:-5], "body": s}


def push(base):
    tok = token()
    base = base.rstrip("/")
    plan = [
        ("predictions", rows_simple("odds/pred_data", "k")),
        ("locks", rows_simple("odds/lock_data", "k")),
        ("results", rows_simple("odds/result_data", "k")),
        ("horses", rows_simple("odds/horse_data", "hid")),
        ("jockeys", rows_simple("odds/jockey_data", "jkid")),
        ("bias", rows_simple("odds/bias_data", "k")),
    ]
    def odds_rows():
        for p in sorted(glob.glob(os.path.join(MIRROR, "odds/odds_data/*/*.json"))):
            s = read_text(p)
            if valid_json(s):
                yield {"date": os.path.basename(os.path.dirname(p)), "rid": os.path.basename(p)[:-5], "body": s}
    plan.append(("odds_snaps", odds_rows()))
    def kaiko_rows():
        p = os.path.join(MIRROR, "odds/kaiko.json")
        if os.path.exists(p):
            for i, r in enumerate(json.load(open(p, encoding="utf-8"))):
                if isinstance(r, dict) and r.get("key") is not None:
                    yield {"k": php_str(r["key"]), "seq": i + 1, "body": dumps(r)}
    plan.append(("kaiko", kaiko_rows()))
    def old_rows():
        for m in ("jra", "nar"):
            p = os.path.join(MIRROR, f"odds/data/odds_log_{m}.json")
            if os.path.exists(p):
                arr = json.loads(read_text(p) or "[]")
                for i, r in enumerate(arr if isinstance(arr, list) else []):
                    if isinstance(r, dict) and r.get("id") is not None:
                        yield {"mode": m, "id": php_str(r["id"]), "seq": i + 1, "body": dumps(r)}
    plan.append(("oddslog_old", old_rows()))
    def kv_rows():
        p = os.path.join(MIRROR, "odds/data/odds_snaps.json")
        if os.path.exists(p) and valid_json(read_text(p)):
            yield {"k": "odds_snaps", "v": read_text(p), "at": int(os.path.getmtime(p))}
    plan.append(("kv", kv_rows()))
    def official():
        for p in files("odds/official_results"):
            s = read_text(p)
            if valid_json(s):
                yield {"day": os.path.basename(p)[:-5], "body": s}
    plan.append(("official_results", official()))
    def nar_hist():
        for p in files("odds/nardata", "hist_*.json"):
            d = json.loads(read_text(p) or "{}")
            for name, h in (d.items() if isinstance(d, dict) else []):
                yield {"name": name, "hist": dumps(h)}
    plan.append(("nar_hist", nar_hist()))
    def line_rows():
        for p in sorted(glob.glob(os.path.join(MIRROR, "odds/line_outbox/*.txt"))):
            yield {"name": os.path.basename(p), "text": read_text(p), "at": int(os.path.getmtime(p))}
    plan.append(("line_outbox", line_rows()))
    def sent_rows():
        for p in sorted(glob.glob(os.path.join(MIRROR, "odds/line_sent/*.sent"))):
            yield {"rid": os.path.basename(p)[:-5], "at": read_text(p).strip()}
    plan.append(("line_sent", sent_rows()))
    # ★アクセス記録・JSエラーは「足すだけ」の表なので、2回流すと二重になる★ 空の時だけ送る
    have = count(base, tok)
    def pv_rows():
        for site, rel in (("k", "k/logs"), ("lab", "lab/logs")):
            for p in files(rel, "[0-9]*.tsv"):
                day = os.path.basename(p)[:8]
                for line in read_text(p).splitlines():
                    c = line.split("\t")
                    if len(c) >= 5:
                        yield {"site": site, "day": day, "t": c[0], "path": c[1], "ref": c[2], "dev": c[3], "vid": c[4]}
    def err_rows():
        for site, rel in (("k", "k/logs"), ("lab", "lab/logs"), ("odds", "odds/logs")):
            for p in files(rel, "errors_*.jsonl"):
                day = os.path.basename(p)[7:15]
                for line in read_text(p).splitlines():
                    if line.strip():
                        yield {"site": site, "day": day, "body": line}
    if have.get("pv", 0) == 0:
        plan.append(("pv", pv_rows()))
    else:
        print("  アクセス記録は送信済みなので飛ばす（二重防止）")
    if have.get("js_errors", 0) == 0:
        plan.append(("js_errors", err_rows()))
    else:
        print("  JSエラー記録は送信済みなので飛ばす（二重防止）")
    for table, rows in plan:
        n, errs = post_ndjson(base, table, rows, tok)
        print(f"  {table:<17} {n:>7} 件" + (f"  ★エラー {errs[:2]}" if errs else ""), flush=True)


def count(base, tok):
    req = urllib.request.Request(f"{base.rstrip('/')}/__admin/count", headers={"X-Admin-Token": tok, "User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


# ------------------------------------------------------------------ ③ 確かめる
def norm(b):
    """JSONとして比べる（PHPの \\/ や 1.0 の書き方の差は無視）"""
    try:
        return json.loads(b)
    except Exception:
        return b


def verify(base):
    tok = token()
    base = base.rstrip("/")
    print("件数:", json.dumps(count(base, tok), ensure_ascii=False))
    new = base + "/odds"
    dates = [str(x) for x in json.loads(get(f"{OLD}/predictions.php?action=dates"))["dates"][:5]]
    checks = ["predictions.php?action=dates", "predictions.php?action=listlocks", "bias.php?action=dates",
              "oddslog.php?action=dates", "kaiko.php?action=list"]
    checks += [f"predictions.php?action=list&date={d}" for d in dates]
    checks += [f"bias.php?action=list&from={dates[-1]}"]
    ng = 0
    for q in checks:
        a, b = norm(get(f"{OLD}/{q}")), norm(get(f"{new}/{q}"))
        ok = a == b
        if not ok and isinstance(a, dict) and isinstance(b, dict):
            # 移行後に旧側へ新しい保存が入った等、件数の差だけなら注記
            pass
        print(f"  {'OK ' if ok else 'NG '} {q}")
        ng += 0 if ok else 1
    print("一致しない問い合わせ:", ng, "件（移行後に旧サーバーへ新しい保存があれば差が出る。その場合は push を流し直す）")
    return 1 if ng else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["ftp-pull", "http-pull", "push", "verify"])
    ap.add_argument("--url", help="Worker のURL（push / verify）")
    a = ap.parse_args()
    if a.cmd == "ftp-pull":
        return ftp_pull()
    if a.cmd == "http-pull":
        return http_pull()
    if not a.url:
        sys.exit("--url を指定する")
    if a.cmd == "push":
        return push(a.url)
    return verify(a.url)


if __name__ == "__main__":
    sys.exit(main() or 0)
