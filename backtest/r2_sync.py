# -*- coding: utf-8 -*-
"""データを Cloudflare の非公開の倉庫（R2・バケット turf-lab-data）へ上げる／取ってくる

★なぜ要るか★（2026-11-21 本人の方針）
  ・中央・地方の元データと学習用データを PC だけに置かない（消えたら作り直せないものがある）。
  ・バックテストを GitHub の自動実行で回せるようにする（倉庫から取って回す）。
  ・JRA-VAN の生データは公開リポに入れない。置き場所はこの非公開の倉庫だけ。

★鍵★
  PC では odds/r2_key.txt（ACCESS_KEY_ID=… / SECRET_ACCESS_KEY=… の2行。.gitignore 済み）。
  GitHub では環境変数 R2_ACCESS_KEY_ID / R2_SECRET_ACCESS_KEY（リポの秘密の値）。
  ★鍵の値は表示もしない・記録にも書かない★

標準ライブラリだけで動く（PC の Python にも GitHub にも追加で入れるものが無い）。

使い方:
  python backtest/r2_sync.py test                      つながるかだけ試す（小さなファイルを置いて消す）
  python backtest/r2_sync.py ls [前置き]                倉庫の中身の一覧
  python backtest/r2_sync.py put <ファイル> <置く名前>   1つ上げる（同じ大きさのものが既にあれば飛ばす）
  python backtest/r2_sync.py get <置いた名前> <保存先>   1つ取ってくる
  python backtest/r2_sync.py getdir <前置き> <フォルダ>  前置きの下を全部取ってくる
  python backtest/r2_sync.py push-all                  決まった一式を上げる（下の PUSH の表）
"""
import datetime
import hashlib
import hmac
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ACCOUNT = "78ef1242bb9514e7f6ccf32f9f94e744"
BUCKET = "turf-lab-data"
HOST = f"{ACCOUNT}.r2.cloudflarestorage.com"
PART = 32 * 1024 * 1024          # 分けて上げる時の1つの大きさ
SINGLE_MAX = 64 * 1024 * 1024    # これ以下は1回で上げる

# 上げる一式（PC の中の場所 → 倉庫での名前）。フォルダは中のファイルを全部
PUSH = [
    ("backtest/jvdata/target_all.txt", "jra/raw/target_all.txt"),
    ("backtest/jvdata/setup_2026.txt", "jra/raw/setup_2026.txt"),
    ("backtest/store/jra", "jra/store"),
    ("backtest/nardata/bt_jra.jsonl", "jra/bt_jra.jsonl"),
    ("backtest/nardata/bt_jra.jsonl.jockeys", "jra/bt_jra.jsonl.jockeys"),
    ("backtest/nardata/bt_jra.jsonl.trainers", "jra/bt_jra.jsonl.trainers"),
    ("backtest/nardata/bt_all.jsonl", "nar/bt_all.jsonl"),
    ("backtest/nardata/bt_banei.jsonl", "nar/bt_banei.jsonl"),
    ("backtest/nardata/bt_debut.jsonl", "nar/bt_debut.jsonl"),
    ("backtest/nardata", "nar/raw"),          # 月ごとの zip（race_*.zip / odds_*.zip）だけ。下の only で絞る
]
ONLY_ZIP = {"backtest/nardata"}


def keys():
    a, s = os.environ.get("R2_ACCESS_KEY_ID"), os.environ.get("R2_SECRET_ACCESS_KEY")
    if a and s:
        return a.strip(), s.strip()
    p = os.path.join(ROOT, "r2_key.txt")
    if not os.path.exists(p):
        sys.exit("鍵が無い: odds/r2_key.txt を作るか、R2_ACCESS_KEY_ID / R2_SECRET_ACCESS_KEY を設定する")
    kv = {}
    lines = [ln.strip() for ln in open(p, encoding="utf-8-sig", errors="replace") if ln.strip()]
    for ln in lines:
        if "=" in ln:
            k, v = ln.split("=", 1)
            kv[k.strip().upper()] = v.strip()
    a, s = kv.get("ACCESS_KEY_ID"), kv.get("SECRET_ACCESS_KEY")
    if not (a and s) and len(lines) >= 2 and "=" not in lines[0]:
        a, s = lines[0], lines[1]            # 2行だけ書いた形にも対応
    if not (a and s):
        sys.exit("odds/r2_key.txt の形が違う（ACCESS_KEY_ID=… と SECRET_ACCESS_KEY=… の2行）")
    return a, s


def _sign(key, msg):
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


def req(method, name, query=None, body=None, headers=None, timeout=600, stream_to=None):
    """署名つきで1回呼ぶ。戻り値は (状態, ヘッダ, 本文)。本文の署名は省く（UNSIGNED-PAYLOAD）"""
    ak, sk = keys()
    now = datetime.datetime.now(datetime.timezone.utc)
    amz, day = now.strftime("%Y%m%dT%H%M%SZ"), now.strftime("%Y%m%d")
    path = "/" + BUCKET + ("/" + urllib.parse.quote(name, safe="/-_.~") if name else "")
    q = sorted((query or {}).items())
    cq = "&".join(f"{urllib.parse.quote(str(k), safe='-_.~')}={urllib.parse.quote(str(v), safe='-_.~')}" for k, v in q)
    h = {"host": HOST, "x-amz-content-sha256": "UNSIGNED-PAYLOAD", "x-amz-date": amz}
    for k, v in (headers or {}).items():
        h[k.lower()] = str(v)
    sh = ";".join(sorted(h))
    canon = "\n".join([method, path, cq, "".join(f"{k}:{h[k]}\n" for k in sorted(h)), sh, "UNSIGNED-PAYLOAD"])
    scope = f"{day}/auto/s3/aws4_request"
    sts = "\n".join(["AWS4-HMAC-SHA256", amz, scope, hashlib.sha256(canon.encode()).hexdigest()])
    k = _sign(_sign(_sign(_sign(("AWS4" + sk).encode(), day), "auto"), "s3"), "aws4_request")
    sig = hmac.new(k, sts.encode(), hashlib.sha256).hexdigest()
    h["authorization"] = f"AWS4-HMAC-SHA256 Credential={ak}/{scope}, SignedHeaders={sh}, Signature={sig}"
    url = f"https://{HOST}{path}" + ("?" + cq if cq else "")
    r = urllib.request.Request(url, data=body, method=method, headers={k: v for k, v in h.items() if k != "host"})
    try:
        with urllib.request.urlopen(r, timeout=timeout) as res:
            if stream_to:
                with open(stream_to, "wb") as f:
                    while True:
                        b = res.read(1 << 20)
                        if not b:
                            break
                        f.write(b)
                return res.status, dict(res.headers), b""
            return res.status, dict(res.headers), res.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()


def remote_size(name):
    st, hd, _ = req("HEAD", name, timeout=60)
    if st == 200:
        return int(hd.get("Content-Length") or hd.get("content-length") or -1)
    return None


def _retry(fn, what, n=5):
    for i in range(n):
        try:
            st, hd, body = fn()
            if st in (200, 204):
                return st, hd, body
            err = f"状態 {st} {body[:200]!r}"
        except Exception as e:                 # 回線の切れなど
            err = str(e)
        if i < n - 1:
            time.sleep(3 * (i + 1))
    sys.exit(f"失敗: {what}: {err}")


def put(local, name, force=False):
    size = os.path.getsize(local)
    if not force and remote_size(name) == size:
        print(f"  済み  {name}  ({size / 1e6:,.1f}MB)")
        return "skip"
    t0 = time.time()
    if size <= SINGLE_MAX:
        data = open(local, "rb").read()
        _retry(lambda: req("PUT", name, body=data, headers={"content-length": len(data)}), name)
    else:
        st, _, body = _retry(lambda: req("POST", name, query={"uploads": ""}), name + "（開始）")
        uid = ET.fromstring(body).find("{*}UploadId").text
        parts, n = [], 0
        with open(local, "rb") as f:
            while True:
                chunk = f.read(PART)
                if not chunk:
                    break
                n += 1
                _, hd, _ = _retry(lambda: req("PUT", name, query={"partNumber": n, "uploadId": uid}, body=chunk,
                                              headers={"content-length": len(chunk)}), f"{name}（{n}個目）")
                parts.append((n, hd.get("ETag") or hd.get("etag")))
                print(f"    {name}  {min(n * PART, size) / 1e6:,.0f} / {size / 1e6:,.0f}MB", flush=True)
        xml = "<CompleteMultipartUpload>" + "".join(
            f"<Part><PartNumber>{i}</PartNumber><ETag>{e}</ETag></Part>" for i, e in parts) + "</CompleteMultipartUpload>"
        _retry(lambda: req("POST", name, query={"uploadId": uid}, body=xml.encode(),
                           headers={"content-length": len(xml.encode()), "content-type": "application/xml"}), name + "（仕上げ）")
    if remote_size(name) != size:
        sys.exit(f"上げたあとの大きさが合わない: {name}")
    print(f"  上げた {name}  ({size / 1e6:,.1f}MB・{time.time() - t0:.0f}秒)", flush=True)
    return "put"


def get(name, local):
    os.makedirs(os.path.dirname(os.path.abspath(local)) or ".", exist_ok=True)
    # 大きいものは <名前>.part00, .part01 … に分けて置いてある（PC から1回45秒までしか上げられないため）。
    #   本体が無くて分割があれば、順に取ってつなぐ。
    have = dict(ls(name))
    parts = sorted(k for k in have if k.startswith(name + ".part") and k[len(name) + 5:].isdigit())
    if name not in have and parts:
        if [int(k[len(name) + 5:]) for k in parts] != list(range(len(parts))):
            sys.exit(f"分割の番号が抜けている: {name} {parts}")
        tmp = local + ".part"
        with open(tmp, "wb") as fo:
            for k in parts:
                st, _, body = _retry(lambda k=k: req("GET", k, stream_to=tmp + ".one"), f"取る {k}")
                if st != 200 or os.path.getsize(tmp + ".one") != have[k]:
                    sys.exit(f"取れない: {k} 状態 {st}")
                with open(tmp + ".one", "rb") as fi:
                    while True:
                        b = fi.read(1 << 24)
                        if not b:
                            break
                        fo.write(b)
                os.remove(tmp + ".one")
        os.replace(tmp, local)
        print(f"  取った {name}（分割 {len(parts)} 個）→ {local}  ({os.path.getsize(local) / 1e6:,.1f}MB)")
        return
    tmp = local + ".part"
    st, hd, body = req("GET", name, stream_to=tmp)
    if st != 200:
        if os.path.exists(tmp):
            os.remove(tmp)
        sys.exit(f"取れない: {name} 状態 {st} {body[:200]!r}")
    os.replace(tmp, local)
    print(f"  取った {name} → {local}  ({os.path.getsize(local) / 1e6:,.1f}MB)")


def ls(prefix=""):
    out, token = [], None
    while True:
        q = {"list-type": "2", "prefix": prefix}
        if token:
            q["continuation-token"] = token
        st, _, body = req("GET", "", query=q, timeout=60)
        if st != 200:
            sys.exit(f"一覧が取れない: 状態 {st} {body[:200]!r}")
        x = ET.fromstring(body)
        for c in x.findall("{*}Contents"):
            out.append((c.find("{*}Key").text, int(c.find("{*}Size").text)))
        if (x.findtext("{*}IsTruncated") or "").lower() != "true":
            break
        token = x.findtext("{*}NextContinuationToken")
    return out


def push_all():
    n_put = n_skip = 0
    for src, dst in PUSH:
        p = os.path.join(ROOT, *src.split("/"))
        if not os.path.exists(p):
            print(f"  無い  {src}")
            continue
        if os.path.isdir(p):
            for fn in sorted(os.listdir(p)):
                fp = os.path.join(p, fn)
                if not os.path.isfile(fp) or fn.startswith("_"):
                    continue
                if src in ONLY_ZIP and not fn.endswith(".zip"):
                    continue
                r = put(fp, dst + "/" + fn)
                n_put += r == "put"; n_skip += r == "skip"
        else:
            r = put(p, dst)
            n_put += r == "put"; n_skip += r == "skip"
    tot = ls()
    print(f"完了: 上げた {n_put} / 済みで飛ばした {n_skip}。倉庫の合計 {len(tot)} 個・{sum(s for _, s in tot) / 1e9:.2f}GB")


def main():
    a = sys.argv[1:]
    if not a:
        sys.exit(__doc__)
    if a[0] == "test":
        name = "_test/hello.txt"
        _retry(lambda: req("PUT", name, body=b"ok", headers={"content-length": 2}), "試しに置く")
        ok = remote_size(name) == 2
        _retry(lambda: req("DELETE", name), "試しを消す")
        print("つながった（置く・確かめる・消すが通った）" if ok else "置けたが確かめられなかった")
    elif a[0] == "ls":
        rows = ls(a[1] if len(a) > 1 else "")
        for k, s in rows:
            print(f"{s / 1e6:>10,.1f}MB  {k}")
        print(f"合計 {len(rows)} 個・{sum(s for _, s in rows) / 1e9:.2f}GB")
    elif a[0] == "put" and len(a) == 3:
        put(a[1], a[2])
    elif a[0] == "get" and len(a) == 3:
        get(a[1], a[2])
    elif a[0] == "getdir" and len(a) == 3:      # 前置きの下を全部、フォルダへ（名前は最後の部分だけ使う）
        for k, _ in ls(a[1]):
            get(k, os.path.join(a[2], k.rsplit("/", 1)[-1]))
    elif a[0] == "push-all":
        push_all()
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
