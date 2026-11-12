<?php
/* =====================================================================
   ODDS ANOMALY — 自動収集 cron スクリプト
   お名前.com 等の共有ホスティングで cron から定期実行する。

   推奨 cron 設定（日中のみ・5分おき）:
     # 9:00〜23:00 の毎5分（5分間隔の指定は「スラッシュ5」）
     [毎5分] 9-22 * * *  /usr/bin/php /home/.../odds/odds-cron.php >/dev/null 2>&1
   ※ cron の分フィールドは「アスタリスク・スラッシュ・5」で5分おき。

   動作:
     1. JST当日の開催一覧を取得（JRA+NAR両方）
     2. 発走が近いレース(締切前後の時間帯)だけオッズ取得→スナップ追記
     3. 異常検知して学習ログ(data/odds_log.json)へ upsert
     4. 発走を過ぎたレースは結果照合（着順）
   行儀よく: netkeibaへのリクエスト間に sleep を入れる。
   ===================================================================== */

date_default_timezone_set('Asia/Tokyo');
@set_time_limit(280);

$DIR  = __DIR__ . '/data';
$SNAP = $DIR . '/odds_snaps.json';   // 収集中のオッズ時系列（mode混在でOK・一時データ）
$STATE= $DIR . '/odds_cron_state.json';
if (!is_dir($DIR)) @mkdir($DIR, 0755, true);
/* mode別ログファイル */
function log_file($mode) { return __DIR__ . '/data/odds_log_' . ($mode === 'nar' ? 'nar' : 'jra') . '.json'; }
function lock_file($mode) { return __DIR__ . '/data/odds_log_' . ($mode === 'nar' ? 'nar' : 'jra') . '.lock'; }

/* ---- 設定 ---- */
$WINDOW_BEFORE = 30;   // 発走何分前から収集開始
$WINDOW_AFTER  = 8;    // 発走何分後まで（オッズ確定の猶予）
$RESULT_AFTER  = 4;    // 発走何分後から結果照合を試す
$REQ_SLEEP     = 0.7;  // netkeiba 連続アクセスの間隔(秒)
$MAX_RACES     = 24;   // 1回の起動で扱う最大レース数
$MAX_SNAPS     = 60;   // 1レースあたり保持スナップ数
$TH = ['drop'=>22,'rise'=>28,'vel'=>8];          // 検知しきい値（JRA寄り）
$TH_NAR = ['drop'=>30,'rise'=>40,'vel'=>12];     // 地方

/* ---- HTTP（curl優先、無ければfile_get_contents） ---- */
function http_get($url, $referer = '') {
  $ua = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36';
  if (function_exists('curl_init')) {
    $ch = curl_init($url);
    curl_setopt_array($ch, [
      CURLOPT_RETURNTRANSFER => true, CURLOPT_TIMEOUT => 12,
      CURLOPT_USERAGENT => $ua, CURLOPT_FOLLOWLOCATION => true,
      CURLOPT_HTTPHEADER => $referer ? ["Referer: $referer"] : [],
    ]);
    $r = curl_exec($ch); $code = curl_getinfo($ch, CURLINFO_HTTP_CODE); curl_close($ch);
    return ($code >= 200 && $code < 400) ? $r : null;
  }
  $hdr = "User-Agent: $ua\r\n" . ($referer ? "Referer: $referer\r\n" : '');
  $ctx = stream_context_create(['http' => ['header' => $hdr, 'timeout' => 12]]);
  $r = @file_get_contents($url, false, $ctx);
  return $r !== false ? $r : null;
}
function eucjp_to_utf8($s) {
  if (function_exists('mb_convert_encoding')) return mb_convert_encoding($s, 'UTF-8', 'EUC-JP,UTF-8');
  if (function_exists('iconv')) { $r = @iconv('EUC-JP', 'UTF-8//IGNORE', $s); if ($r !== false) return $r; }
  return $s; // 最低限ASCII(race_id/時刻)は読める
}
function http_get_eucjp($url, $referer = '') { $r = http_get($url, $referer); return $r === null ? null : eucjp_to_utf8($r); }

function jload($f, $def) { if (!file_exists($f)) return $def; $j = json_decode(file_get_contents($f), true); return $j === null ? $def : $j; }
function jsave($f, $data) { file_put_contents($f, json_encode($data, JSON_UNESCAPED_UNICODE), LOCK_EX); }

$JRA = ['01'=>'札幌','02'=>'函館','03'=>'福島','04'=>'新潟','05'=>'東京','06'=>'中山','07'=>'中京','08'=>'京都','09'=>'阪神','10'=>'小倉'];
$NAR = ['30'=>'門別','35'=>'盛岡','36'=>'水沢','42'=>'浦和','43'=>'船橋','44'=>'大井','45'=>'川崎','46'=>'金沢','47'=>'笠松','48'=>'名古屋','50'=>'園田','51'=>'姫路','54'=>'高知','55'=>'佐賀','65'=>'帯広'];
function track_of($rid, $mode) { global $JRA, $NAR; $c = substr($rid, 4, 2); $m = $mode === 'nar' ? $NAR : $JRA; return isset($m[$c]) ? $m[$c] : ($mode === 'nar' ? "NAR:$c" : "場$c"); }

/* ---- レース一覧（発走時刻つき） ---- */
function fetch_race_list($date, $mode) {
  $base = $mode === 'nar' ? 'https://nar.netkeiba.com' : 'https://race.netkeiba.com';
  $html = http_get_eucjp("$base/top/race_list_sub.html?kaisai_date=$date");
  if (!$html) return [];
  $out = []; $seen = [];
  if (preg_match_all('/shutuba\.html\?race_id=(\d{12})/', $html, $m, PREG_OFFSET_CAPTURE)) {
    foreach ($m[1] as $mm) {
      $rid = $mm[0]; if (isset($seen[$rid])) continue; $seen[$rid] = 1;
      $win = substr($html, $mm[1], 900);
      $post = preg_match('/(\d{1,2}:\d{2})/', $win, $t) ? $t[1] : null;
      $out[] = ['race_id'=>$rid, 'mode'=>$mode, 'track'=>track_of($rid,$mode), 'no'=>intval(substr($rid,10,2)), 'post'=>$post];
    }
  }
  return $out;
}
function post_min($p) { if (!$p || !preg_match('/(\d{1,2}):(\d{2})/', $p, $m)) return null; return intval($m[1])*60 + intval($m[2]); }

/* ---- オッズ取得（単勝） ---- */
function fetch_win_odds($rid, $mode) {
  $base = $mode === 'nar' ? 'https://nar.netkeiba.com' : 'https://race.netkeiba.com';
  $api  = $mode === 'nar' ? 'api/api_get_nar_odds.html' : 'api/api_get_jra_odds.html';
  // JRAは action=init が無いとオッズが空で返る（NARは不要）
  $q = $mode === 'nar' ? "race_id=$rid&type=1" : "race_id=$rid&type=1&action=init";
  $raw = http_get("$base/$api?$q", "$base/odds/index.html?race_id=$rid");
  if (!$raw) return null;
  $j = json_decode($raw, true); if (!$j) return null;
  $win = [];
  if (!empty($j['ary_odds'])) {                       // NAR形 {ary_odds:{馬番:{Odds,Ninki}}}
    foreach ($j['ary_odds'] as $k => $v) { $o = floatval($v['Odds']); if ($o > 0) $win[strval(intval($k))] = $o; }
  } else {
    // JRA形: data.odds["1"]（action=init時）。旧形 odds.data["1"] もフォールバック。
    $od = null;
    if (!empty($j['data']['odds']['1'])) $od = $j['data']['odds']['1'];
    elseif (!empty($j['odds']['data']['1'])) $od = $j['odds']['data']['1'];
    if ($od) foreach ($od as $k => $v) { $o = floatval(is_array($v) ? $v[0] : $v); if ($o > 0) $win[strval(intval($k))] = $o; }
  }
  return $win ?: null;
}

/* ---- 結果（着順・勝ち馬の枠/人気/騎手/タイム） ---- */
function fetch_result($rid, $mode) {
  $base = $mode === 'nar' ? 'https://nar.netkeiba.com' : 'https://race.netkeiba.com';
  $html = http_get_eucjp("$base/race/result.html?race_id=$rid");
  if (!$html) return null;
  if (!preg_match_all('/<tr[\s\S]*?<\/tr>/', $html, $rows)) return null;
  $arr = [];
  foreach ($rows[0] as $r) {
    if (!preg_match('/class="Rank"[^>]*>\s*(\d{1,2})\s*</', $r, $rk)) continue;
    $nums = []; if (preg_match_all('/class="Num Waku\d*"[^>]*>\s*(?:<div[^>]*>)?\s*(\d{1,2})/', $r, $nm)) $nums = $nm[1];
    $waku = isset($nums[0]) ? intval($nums[0]) : null;
    $num  = isset($nums[1]) ? strval(intval($nums[1])) : null;
    $name = preg_match('/\/horse\/\d+[^"]*"[^>]*>([^<]{1,30})</', $r, $n) ? trim($n[1]) : '';
    $jk   = preg_match('/\/jockey\/(?:result\/recent\/)?\d+[^"]*"[^>]*>\s*([^<]{1,16}?)\s*</', $r, $j) ? trim($j[1]) : '';
    $pop  = preg_match('/Odds_Ninki[^>]*>\s*(?:<span[^>]*>)?\s*(\d{1,2})/', $r, $p) ? intval($p[1]) : null;
    $time = preg_match('/(\d:\d{2}\.\d)/', $r, $t) ? $t[1] : null;
    if (!$num) continue;
    $arr[] = ['rank'=>intval($rk[1]), 'waku'=>$waku, 'num'=>$num, 'name'=>$name, 'jockey'=>$jk, 'pop'=>$pop, 'time'=>$time];
  }
  usort($arr, fn($a,$b)=>$a['rank']-$b['rank']);
  return $arr ?: null;
}

/* ---- 異常検知（アプリの簡易版・単勝の始点→現在の変動） ---- */
function detect($series, $th) {
  // $series: [ ['win'=>{num:odds}], ... ] 時系列
  $first = $series[0]['win']; $last = end($series)['win'];
  $prev  = count($series) >= 2 ? $series[count($series)-2]['win'] : $first;
  $picks = [];
  foreach ($last as $num => $od) {
    if (!isset($first[$num]) || $first[$num] <= 0) continue;
    $total = ($od - $first[$num]) / $first[$num] * 100;
    $recent = isset($prev[$num]) && $prev[$num] > 0 ? ($od - $prev[$num]) / $prev[$num] * 100 : 0;
    $tags = [];
    if ($total <= -$th['drop']) $tags[] = '🔻急落';
    $band = 1.02 * exp(-pow(log($od/3.5),2)/2.6) + 0.05; $band = min(1,$band);
    if ($total >= $th['rise'] && $band >= 0.35) $tags[] = '🔺急騰';
    if (abs($recent) >= $th['vel'] && $band >= 0.3) $tags[] = '⚡直前急変';
    if (!$tags) continue;
    $dir = $total < 0 ? 1.0 : 0.45;
    $score = round(min(60,abs($total))/60*60 * $band * $dir);
    $picks[] = ['num'=>strval($num), 'score'=>$score, 'tags'=>$tags,
      'totalPct'=>round($total,1), 'recentPct'=>round($recent,1), 'odds'=>round($od,1)];
  }
  usort($picks, fn($a,$b)=>$b['score']-$a['score']);
  return array_slice($picks, 0, 5);
}

/* ---- 学習ログ upsert（odds-log.php と同形式・ロック付き） ---- */
function log_upsert($LOG, $LOCK, $rec, $MAX = 5000) {
  $fp = fopen($LOCK, 'c'); if ($fp) flock($fp, LOCK_EX);
  $all = jload($LOG, []);
  $done = false;
  foreach ($all as $i => $r) {
    if (isset($r['id']) && $r['id'] === $rec['id']) {
      if (empty($rec['result']) && !empty($r['result'])) $rec['result'] = $r['result'];
      $all[$i] = $rec; $done = true; break;
    }
  }
  if (!$done) $all[] = $rec;
  if (count($all) > $MAX) $all = array_slice($all, -$MAX);
  jsave($LOG, $all);
  if ($fp) { flock($fp, LOCK_UN); fclose($fp); }
}

/* ============================ MAIN ============================ */
$now = intval(date('G')) * 60 + intval(date('i'));
$today = date('Ymd');

// 開催一覧（JRA→NAR、各取得後に小休止）
$races = [];
foreach (['jra','nar'] as $mode) { $races = array_merge($races, fetch_race_list($today, $mode)); usleep(intval($REQ_SLEEP*1e6)); }

// 収集ウィンドウ内のレースに絞る
$targets = [];
foreach ($races as $r) {
  $pm = post_min($r['post']); if ($pm === null) continue;
  if ($pm - $WINDOW_BEFORE <= $now && $now <= $pm + $WINDOW_AFTER) $targets[] = $r + ['postMin'=>$pm];
}
usort($targets, fn($a,$b)=>$a['postMin']-$b['postMin']);
$targets = array_slice($targets, 0, $MAX_RACES);

$snaps = jload($SNAP, []);   // {rid: {mode,track,no,postMin, series:[{ts,win}]}}
$collected = 0; $reconciled = 0;

foreach ($targets as $r) {
  $rid = $r['race_id']; $mode = $r['mode'];
  $th = $mode === 'nar' ? $TH_NAR : $TH;

  if ($now <= $r['postMin']) {
    // 発走前: オッズ収集
    $win = fetch_win_odds($rid, $mode); usleep(intval($REQ_SLEEP*1e6));
    if ($win) {
      if (!isset($snaps[$rid])) $snaps[$rid] = ['mode'=>$mode,'track'=>$r['track'],'no'=>$r['no'],'postMin'=>$r['postMin'],'series'=>[]];
      $snaps[$rid]['series'][] = ['ts'=>time(), 'win'=>$win];
      if (count($snaps[$rid]['series']) > $MAX_SNAPS) $snaps[$rid]['series'] = array_slice($snaps[$rid]['series'], -$MAX_SNAPS);
      $collected++;
      // 検知してログへ
      if (count($snaps[$rid]['series']) >= 2) {
        $picks = detect($snaps[$rid]['series'], $th);
        if ($picks) {
          log_upsert(log_file($mode), lock_file($mode), [
            'id'=>$rid, 'mode'=>$mode, 'track'=>$r['track'], 'no'=>strval($r['no']),
            'going'=>null, 'surface'=>null, 'dist'=>null, 'ts'=>time()*1000,
            'picks'=>$picks, 'result'=>null
          ]);
        }
      }
    }
  }
  if ($now >= $r['postMin'] + $RESULT_AFTER) {
    // 発走後: 結果照合（未照合のみ）
    $all = jload(log_file($mode), []); $rec = null; foreach ($all as $x) if ($x['id'] === $rid) { $rec = $x; break; }
    if ($rec && empty($rec['result'])) {
      $res = fetch_result($rid, $mode); usleep(intval($REQ_SLEEP*1e6));
      if ($res) {
        $w = null; foreach ($res as $x) if ($x['rank'] === 1) { $w = $x; break; }
        $place3 = []; foreach ($res as $x) if ($x['rank'] <= 3) $place3[] = $x['num'];
        $rec['result'] = ['win'=>$w?$w['num']:null, 'place3'=>$place3,
          'winWaku'=>$w?$w['waku']:null, 'winPop'=>$w?$w['pop']:null,
          'winJockey'=>$w?$w['jockey']:null, 'winTime'=>$w?$w['time']:null, 'fetched'=>time()*1000];
        log_upsert(log_file($mode), lock_file($mode), $rec);
        $reconciled++;
        unset($snaps[$rid]);   // 収集終了→スナップ破棄
      }
    }
  }
}

jsave($SNAP, $snaps);
jsave($STATE, ['lastRun'=>date('c'), 'now'=>$now, 'targets'=>count($targets), 'collected'=>$collected, 'reconciled'=>$reconciled]);

header('Content-Type: application/json; charset=utf-8');
echo json_encode(['ok'=>true, 'time'=>date('H:i'), 'targets'=>count($targets), 'collected'=>$collected, 'reconciled'=>$reconciled], JSON_UNESCAPED_UNICODE);
