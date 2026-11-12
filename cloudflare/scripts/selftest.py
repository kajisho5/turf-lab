# -*- coding: utf-8 -*-
"""ローカル（wrangler dev）の Worker に、PHP版と同じ応答になるかを当てる試験。
架空データだけを使う（実在の日付・レースIDは使わない）。

  npx wrangler dev --port 8787   を別窓で起動してから
  python cloudflare/scripts/selftest.py [http://127.0.0.1:8787]
"""
import json
import sys
import urllib.request


class _NoRedir(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


urllib.request.install_opener(urllib.request.build_opener(_NoRedir))

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8787").rstrip("/")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36"
NG = []


def call(path, body=None, method=None, ua=UA, headers=None, raw=False):
    data = None
    if body is not None:
        data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode()
    h = {"User-Agent": ua, "Content-Type": "text/plain"}
    h.update(headers or {})
    req = urllib.request.Request(BASE + path, data=data, method=method or ("POST" if data is not None else "GET"), headers=h)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            b, st, hd = r.read(), r.status, r.headers
    except urllib.error.HTTPError as e:
        b, st, hd = e.read(), e.code, e.headers
    if raw:
        return st, b, hd
    try:
        return st, json.loads(b), hd
    except Exception:
        return st, b.decode("utf-8", "replace"), hd


def check(name, cond, info=""):
    print(("OK  " if cond else "NG  ") + name + ("" if cond else f"   → {info}"))
    if not cond:
        NG.append(name)


O = "/odds"
# ---------------- predictions
D = "19990101"
st, j, h = call(f"{O}/predictions.php?action=save", {"date": D, "mode": "nar", "tc": "99", "ts": 5, "races": []})
check("pred save", st == 200 and j == {"ok": True, "key": f"{D}_nar_99"}, j)
check("pred no-store", "no-store" in (h.get("Cache-Control") or ""), h.get("Cache-Control"))
st, j, _ = call(f"{O}/predictions.php?action=save", {"date": D, "mode": "nar", "tc": "99", "ts": 6, "noclobber": True})
check("pred noclobber kept", j == {"ok": True, "kept": True, "key": f"{D}_nar_99"}, j)
st, j, _ = call(f"{O}/predictions.php?action=save", {"date": D, "tc": 98, "ts": 7})
check("pred mode既定nar", j.get("key") == f"{D}_nar_98", j)
st, j, _ = call(f"{O}/predictions.php?action=save", {"date": "", "tc": "1"})
check("pred invalid 400", st == 400 and j == {"ok": False, "error": "invalid payload"}, (st, j))
st, j, _ = call(f"{O}/predictions.php?action=get&date={D}&tc=99")
check("pred get", j.get("ts") == 5 and j.get("savedAt", "").endswith("+09:00"), j)
st, j, _ = call(f"{O}/predictions.php?action=get&date={D}&tc=77")
check("pred get miss", j == {"miss": True}, j)
st, j, _ = call(f"{O}/predictions.php?action=list&date={D}")
check("pred list 並び(ts降順)", [r["ts"] for r in j["records"]] == [7, 5], j)
st, j, _ = call(f"{O}/predictions.php?action=list&date={D}&mode=nar")
check("pred list mode=nar（mode無しは除外）", [r["ts"] for r in j["records"]] == [5], j)
st, j, _ = call(f"{O}/predictions.php?action=dates")
it = [x for x in j["items"] if x["date"] == D]
check("pred dates（mode無しはjra扱い）", sorted((x["mode"], x["ts"]) for x in it) == [("jra", 7), ("nar", 5)], it)
st, j, _ = call(f"{O}/predictions.php?action=savelock", {"date": D, "tc": "99", "firm": [], "ovr": {"1": "aim"}})
check("lock save", j == {"ok": True}, j)
st, j, _ = call(f"{O}/predictions.php?action=listlocks&date={D}")
check("lock list", len(j["locks"]) == 1 and j["locks"][0]["ovr"] == {"1": "aim"}, j)
st, j, _ = call(f"{O}/predictions.php?action=deletelock&date={D}&tc=99")
st, j, _ = call(f"{O}/predictions.php?action=listlocks&date={D}")
check("lock delete", j == {"locks": []}, j)
st, j, _ = call(f"{O}/predictions.php?action=delete&date={D}&tc=99")
check("pred delete", j == {"ok": True}, j)
st, j, _ = call(f"{O}/predictions.php?action=delete&date={D}&tc=99")
check("pred delete 2回目 false", j == {"ok": False}, j)
call(f"{O}/predictions.php?action=delete&date={D}&tc=98&mode=nar")
st, j, _ = call(f"{O}/predictions.php?action=zzz")
check("pred unknown 400", st == 400 and j == {"ok": False, "error": "unknown action"}, (st, j))
st, b, h = call(f"{O}/predictions.php", method="OPTIONS", raw=True)
check("pred OPTIONS 204", st == 204, st)

# ---------------- results
import random
RID = "1999%08d" % random.randint(0, 99999999)
st, j, _ = call(f"{O}/results.php?action=savebatch", {"items": [{"race_id": RID, "ranks": {"1": 1}}, {"x": 1}]})
check("results savebatch", j == {"ok": True, "saved": 1}, j)
st, j, _ = call(f"{O}/results.php?action=get&ids={RID},199999010102")
check("results get", list(j["results"].keys()) == [RID] and "at" in j["results"][RID], j)
st, j, _ = call(f"{O}/results.php?action=get", {"ids": ["199999010199"]})
check("results get 空は[]", j == {"results": []}, j)

# ---------------- horse / jockey
st, j, _ = call(f"{O}/horse.php?action=save", {"records": [{"hid": "1999000001", "races": [{"d": 1}]}, {"hid": "x", "races": []}]})
check("horse save", j == {"saved": 1}, j)
st, j, _ = call(f"{O}/horse.php?action=get&hid=1999000001")
check("horse get", j.get("hid") == "1999000001" and isinstance(j.get("updated"), int), j)
st, j, _ = call(f"{O}/horse.php?action=get&hid=1999000002")
check("horse miss", j == {"hid": "1999000002", "miss": True}, j)
st, j, _ = call(f"{O}/horse.php?action=get&hid=ab")
check("horse bad hid", j == {"error": "bad hid"}, j)
st, j, _ = call(f"{O}/horse.php?action=getbatch&hids=1999000001,1999000009")
check("horse getbatch", list(j["records"].keys()) == ["1999000001"], j)
st, j, _ = call(f"{O}/horse.php?action=nope")
check("horse unknown 200", st == 200 and j == {"error": "unknown action"}, (st, j))
st, j, _ = call(f"{O}/jockey.php?action=save", {"jkid": "a0001", "name": "テスト騎手", "tracks": {"大井": {"n": 1}}})
check("jockey save", j == {"saved": 1}, j)
st, j, _ = call(f"{O}/jockey.php?action=getbatch&ids=a0001")
check("jockey getbatch", j["records"]["a0001"]["name"] == "テスト騎手", j)

# ---------------- bias
st, j, _ = call(f"{O}/bias.php?action=save", {"date": D, "races": [1, 2, 3]})
check("bias save", j == {"ok": True, "key": f"{D}_nar", "races": 3}, j)
st, j, _ = call(f"{O}/bias.php?action=list&from={D}&to={D}")
check("bias list", len(j["records"]) == 1, j)
st, j, _ = call(f"{O}/bias.php?action=dates")
check("bias dates", {"date": D, "mode": "nar", "races": 3} in j["items"], j)

# ---------------- oddslog
st, j, _ = call(f"{O}/oddslog.php?action=save", {"rid": RID, "date": D, "ts": 60000 * 100 + 5, "mode": "nar", "post": "15:30", "mtp": "7", "odds": {"1": {"odds": 2.5}}})
check("oddslog save", j == {"ok": True, "rid": RID, "snapshots": 1}, j)
st, j, _ = call(f"{O}/oddslog.php?action=save", {"rid": RID, "date": D, "ts": 60000 * 100 + 30000, "odds": {"1": {"odds": 2.4}}})
check("oddslog 同一分は上書き", j.get("snapshots") == 1, j)
st, j, _ = call(f"{O}/oddslog.php?action=save", {"rid": RID, "date": D, "ts": 60000 * 101, "odds": {"1": {"odds": 2.3}}})
check("oddslog 次の分は追記", j.get("snapshots") == 2, j)
st, j, _ = call(f"{O}/oddslog.php?action=get&rid={RID}")
check("oddslog get", len(j) == 2 and j[0]["mode"] == "" and j[0]["post"] is None, j)
st, j, _ = call(f"{O}/oddslog.php?action=list&date={D}")
check("oddslog list", {"rid": RID, "snapshots": 2} in j["races"], j)
st, j, _ = call(f"{O}/oddslog.php?action=save", {"rid": RID, "date": D, "odds": {}})
check("oddslog 空odds 400", st == 400 and j == {"error": "bad payload"}, (st, j))

# ---------------- kaiko
st, j, _ = call(f"{O}/kaiko.php?action=put", {"key": f"{D}_99", "date": D, "ts": 1})
st, j2, _ = call(f"{O}/kaiko.php?action=put", {"key": f"{D}_98", "date": D, "ts": 2})
st, j3, _ = call(f"{O}/kaiko.php?action=put", {"key": f"{D}_99", "date": D, "ts": 3})
st, j, _ = call(f"{O}/kaiko.php?action=list")
mine = [r for r in j["records"] if r["date"] == D]
check("kaiko 上書きは位置そのまま", [(r["key"], r["ts"]) for r in mine] == [(f"{D}_99", 3), (f"{D}_98", 2)], mine)

# ---------------- odds-log（旧）
st, j, _ = call(f"{O}/odds-log.php?action=put&mode=nar", {"id": RID, "picks": [], "result": {"win": "3"}})
st, j, _ = call(f"{O}/odds-log.php?action=put&mode=nar", {"id": RID, "picks": [1], "result": None})
st, j, _ = call(f"{O}/odds-log.php?action=list&mode=nar")
r = [x for x in j["records"] if x["id"] == RID][0]
check("odds-log result保持", r["result"] == {"win": "3"} and r["picks"] == [1], r)
st, j, _ = call(f"{O}/odds-log.php?action=stats&mode=nar")
check("odds-log stats", j.get("settled", 0) >= 1, j)

# ---------------- line_push（ドライランのみ）
st, j, _ = call(f"{O}/line_push.php", {"race_id": RID, "text": "テスト", "dry": 1})
check("line dry", j == {"ok": True, "dry": True}, j)

# ---------------- error_log / view
st, j, _ = call(f"{O}/error_log.php", {"page": "/t", "msg": "テストエラー"})
check("error_log", j == {"ok": True}, j)
st, b, h = call(f"{O}/errlog_view.php", raw=True)
check("errlog_view", "テストエラー" in b.decode(), b[:200])

# ---------------- cleanup
st, j, _ = call(f"{O}/cleanup.php")
check("cleanup 形", set(j["dirs"].keys()) == {"odds_data", "horse_data", "jockey_data", "result_data", "pred_data", "lock_data"}, j)

# ---------------- サイト振り分け・htaccess相当
st, b, h = call("/", ua="curl/8.0", raw=True)
check("公開: curlは403", st == 403, st)
st, b, h = call("/odds/tweet.html", ua="curl/8.0", raw=True)
check("運営: curlも200（.htaccess無し）", st == 200, st)
st, b, h = call("/lab/", ua="python-requests/2", raw=True)
check("lab: ボット403", st == 403, st)
st, b, h = call("/db/horses_search.json", headers={"Referer": "https://evil.example/"}, raw=True)
check("直リンク403", st == 403, st)
st, b, h = call("/db/horses_search.json", raw=True)
check("Refererなしは200", st == 200, st)
st, b, h = call("/about", raw=True)
check("/about → 301 /about/", st == 301 and h.get("Location", "").endswith("/about/"), (st, h.get("Location")))
st, b, h = call("/odds", raw=True)
check("/odds → 301 /odds/", st == 301, st)
st, b, h = call("/cache/x", raw=True)
check("/cache/ 404", st == 404, st)
st, b, h = call("/nope.php", raw=True)
check("無いPHPは404", st == 404, st)
st, b, h = call("/lab/race.php?id=1", raw=True)
check("lab race 404 はlab向け文言", st == 404 and "SW TURF LAB" in b.decode() and 'href="/lab/"' in b.decode(), b[:300])
st, b, h = call("/proxy.php?url=https://example.com/", raw=True)
check("proxy 白リスト外は400", st == 400 and b == b"bad url", (st, b))
st, j, _ = call("/proxy_seed.php?t=wrong", {"url": "x"})
check("seed 合言葉違い403", st == 403, st)

print()
print("NG:", len(NG), NG)
sys.exit(1 if NG else 0)
