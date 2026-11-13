-- 自動投稿の記録（朝の投稿のID 'm:日付:mode'／★勝負の的中速報を見たレース 'h:レースID'）
-- kajikeiba-autopost が最初に使う時にも同じ文で作る（tools/x-autopost/src/hits.js の HITS_DDL）
CREATE TABLE IF NOT EXISTS xpost_log (
  k TEXT PRIMARY KEY, date TEXT NOT NULL, mode TEXT NOT NULL, tweet_id TEXT, body TEXT, ts INTEGER NOT NULL);
