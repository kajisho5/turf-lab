-- kajikeiba-turf D1 スキーマ（PHP時代のJSONファイルを1行1件で持つ）
-- 本文(body)は PHP が書いていた JSON をそのまま文字列で保存する。
-- 2MB を超える本文だけ gzip して body_gz に入れる（D1の1行上限が2MBのため）。

-- predictions.php（pred_data/）
CREATE TABLE IF NOT EXISTS predictions (
  k        TEXT PRIMARY KEY,          -- ファイル名と同じ（記号は _ に置換済み）
  date     TEXT NOT NULL DEFAULT '',  -- $j['date'] ?? ''
  mode_raw TEXT,                      -- $j['mode']（無ければ NULL）
  ts       REAL NOT NULL DEFAULT 0,   -- $j['ts'] ?? 0
  body     TEXT,
  body_gz  BLOB
);
CREATE INDEX IF NOT EXISTS ix_pred_date_ts ON predictions(date DESC, ts DESC);

-- predictions.php のロック（lock_data/）
CREATE TABLE IF NOT EXISTS locks (
  k        TEXT PRIMARY KEY,
  date     TEXT NOT NULL DEFAULT '',
  mode_raw TEXT,
  body     TEXT NOT NULL
);

-- kaiko.php（1本のJSON配列だったので並び順 seq を持つ）
CREATE TABLE IF NOT EXISTS kaiko (
  k    TEXT PRIMARY KEY,
  seq  INTEGER NOT NULL,
  body TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_kaiko_seq ON kaiko(seq);

-- results.php（result_data/）
CREATE TABLE IF NOT EXISTS results (
  k    TEXT PRIMARY KEY,
  body TEXT NOT NULL
);

-- horse.php / jockey.php
CREATE TABLE IF NOT EXISTS horses  (hid  TEXT PRIMARY KEY, body TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS jockeys (jkid TEXT PRIMARY KEY, body TEXT NOT NULL);

-- bias.php（bias_data/）
CREATE TABLE IF NOT EXISTS bias (
  k        TEXT PRIMARY KEY,
  date     TEXT NOT NULL DEFAULT '',
  mode_raw TEXT,
  races    INTEGER NOT NULL DEFAULT 0,
  body     TEXT NOT NULL
);

-- oddslog.php（odds_data/{date}/{rid}.json）
CREATE TABLE IF NOT EXISTS odds_snaps (
  date TEXT NOT NULL,
  rid  TEXT NOT NULL,
  n    INTEGER NOT NULL DEFAULT 0,
  body TEXT NOT NULL,
  PRIMARY KEY (date, rid)
);
CREATE INDEX IF NOT EXISTS ix_odds_rid ON odds_snaps(rid);

-- odds-log.php（data/odds_log_{jra|nar}.json・最大5000件の配列）
CREATE TABLE IF NOT EXISTS oddslog_old (
  mode TEXT NOT NULL,
  id   TEXT NOT NULL,
  seq  INTEGER NOT NULL,
  body TEXT NOT NULL,
  PRIMARY KEY (mode, id)
);
CREATE INDEX IF NOT EXISTS ix_oddslog_old_seq ON oddslog_old(mode, seq);

-- 小物（cronの途中状態・sitemapの完成品・公式dailyの5分キャッシュ等）
CREATE TABLE IF NOT EXISTS kv (
  k  TEXT PRIMARY KEY,
  v  TEXT,
  at INTEGER NOT NULL DEFAULT 0       -- 保存時刻(秒)
);

-- proxy.php のキャッシュ（cache/proxy/）
CREATE TABLE IF NOT EXISTS proxy_cache (
  k     TEXT PRIMARY KEY,             -- sha1(url)
  code  INTEGER NOT NULL,
  ctype TEXT NOT NULL DEFAULT '',
  body  BLOB NOT NULL,
  at    INTEGER NOT NULL              -- 保存時刻(秒) = filemtime
);
CREATE INDEX IF NOT EXISTS ix_proxy_at ON proxy_cache(at);

-- race.php / nar_official.php のHTMLキャッシュ（cache/*.html）
CREATE TABLE IF NOT EXISTS page_cache (
  k    TEXT PRIMARY KEY,
  body TEXT NOT NULL,
  at   INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_page_at ON page_cache(at);

-- sitemap 用のレースID（cronが毎日netkeibaの一覧から貯める）
CREATE TABLE IF NOT EXISTS race_index (
  rid TEXT PRIMARY KEY,
  day TEXT NOT NULL                   -- 一覧を取った日 YYYYMMDD
);
CREATE INDEX IF NOT EXISTS ix_race_day ON race_index(day);

-- stats.php（logs/YYYYMMDD.tsv）
CREATE TABLE IF NOT EXISTS pv (
  id   INTEGER PRIMARY KEY AUTOINCREMENT,
  site TEXT NOT NULL,                 -- k(公開) / lab
  day  TEXT NOT NULL,
  t    TEXT NOT NULL,
  path TEXT NOT NULL,
  ref  TEXT NOT NULL,
  dev  TEXT NOT NULL,
  vid  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_pv ON pv(site, day);

-- error_log.php（logs/errors_YYYYMMDD.jsonl）
CREATE TABLE IF NOT EXISTS js_errors (
  id   INTEGER PRIMARY KEY AUTOINCREMENT,
  site TEXT NOT NULL,                 -- k / lab / odds
  day  TEXT NOT NULL,
  body TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_err ON js_errors(site, day);

-- line_push.php（line_outbox/ と line_sent/）
CREATE TABLE IF NOT EXISTS line_outbox (
  name TEXT PRIMARY KEY,              -- {rid}.txt / {rid}.dry.txt
  text TEXT NOT NULL,
  at   INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS line_sent (
  rid TEXT PRIMARY KEY,
  at  TEXT NOT NULL
);

-- nardata.php collect（official_results/YYYYMMDD.json）
CREATE TABLE IF NOT EXISTS official_results (
  day  TEXT PRIMARY KEY,
  body TEXT NOT NULL
);

-- nardata.php get/batch（nardata/hist_XX.json・今は0頭）
CREATE TABLE IF NOT EXISTS nar_hist (
  name TEXT PRIMARY KEY,
  hist TEXT NOT NULL
);
