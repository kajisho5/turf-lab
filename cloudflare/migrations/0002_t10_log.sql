-- 発走10分前の記録（src/t10.ts）。本番では Worker が最初の記録の前に同じ文で作る
CREATE TABLE IF NOT EXISTS t10_log (
  rid    TEXT PRIMARY KEY,
  date   TEXT NOT NULL,
  mode   TEXT NOT NULL,
  track  TEXT,
  no     INTEGER,
  post   TEXT,
  ts     INTEGER NOT NULL,
  mtp    INTEGER NOT NULL,
  field  INTEGER NOT NULL,
  o_num  TEXT,
  o_odds REAL,
  o_pop  INTEGER,
  gap    REAL,
  fav    INTEGER,
  iron   INTEGER,
  mv     TEXT,
  body   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_t10_date ON t10_log(date);
