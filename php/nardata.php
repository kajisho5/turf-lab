<?php
/* nardata.php — 地方競馬(NAR)公式データ由来の馬別履歴サーバー
   出典: keiba.go.jp データダウンロード（公式・月次CSVを馬名別に整形して配置）
   目的: 当日予想で「実測先行力（近走の最終角位置÷頭数）」や近走補完に使う。

   データ配置: nardata/hist_XX.json （XX = md5(馬名) の先頭2桁, 256バケット）
     各ファイル: { "馬名": [ {d:日付, pf:最終角位置/頭数, rk:着順, fn:頭数, tk:場}... 日付昇順 ] }

   action:
     get    ?action=get&name=馬名                 -> 1頭の履歴
     batch  ?action=batch&names=馬名1,馬名2,...    -> {馬名:[...]} まとめて（当日出走馬をまとめ引き）
     info   ?action=info                          -> データ範囲・馬数
*/
header('Access-Control-Allow-Origin: *');
header('Access-Control-Allow-Methods: GET, POST, OPTIONS');
header('Access-Control-Allow-Headers: Content-Type');
header('Content-Type: application/json; charset=utf-8');
if ($_SERVER['REQUEST_METHOD'] === 'OPTIONS') { http_response_code(204); exit; }

$DIR = __DIR__ . '/nardata';
$action = isset($_GET['action']) ? $_GET['action'] : '';

/* バケットファイルを読んでデコード（簡易キャッシュ付き） */
$__cache = [];
function bucket_of($name) { return substr(md5($name), 0, 2); }
function load_bucket($DIR, $b, &$cache) {
  if (isset($cache[$b])) return $cache[$b];
  $p = $DIR . '/hist_' . $b . '.json';
  $d = is_file($p) ? json_decode(file_get_contents($p), true) : [];
  if (!is_array($d)) $d = [];
  $cache[$b] = $d;
  return $d;
}

/* ---- 公式デイリー結果（keiba.go.jp 当日ファイル・約2分毎更新）----
   action=daily   : 当日の全場の確定着順＋確定配当を返す
   action=collect : 上記を official_results/YYYYMMDD.json に永続化（cron用）

   rid = YYYYMMDD + 場コード + R番号2桁。daily は5分キャッシュ。

   ★2026-07-19 修正: 配当は同じZIPの payback.csv に入っている。
     v325 で「配当はOddsDataDownload(別ZIP)が必要」と書いたのは誤りで、
     RaceDataDownload の当日ZIPに racelist/horselist と並んで payback.csv が同梱される。
     追加リクエスト無しで答え合わせを完全公式化できる。 */

function nar_track_codes() {
  return ['門別'=>'30','盛岡'=>'35','水沢'=>'36','浦和'=>'42','船橋'=>'43','大井'=>'44','川崎'=>'45',
          '金沢'=>'46','笠松'=>'47','名古屋'=>'48','園田'=>'50','姫路'=>'51','高知'=>'54','佐賀'=>'55'];
}

/* 当日ZIPを取得して {rid: {ranks, top3, pay}} を組み立てる */
function nar_fetch_daily() {
  $TC = nar_track_codes();
  $zipUrl = 'https://www.keiba.go.jp/KeibaWeb/DataDownload/RaceDataDownload?type=daily';
  $zipData = @file_get_contents($zipUrl, false, stream_context_create(
    ['http' => ['timeout' => 25, 'header' => "User-Agent: Mozilla/5.0\r\n"]]));
  if ($zipData === false || strlen($zipData) < 1000) return ['error' => 'fetch failed'];

  $tmp = tempnam(sys_get_temp_dir(), 'narz');
  file_put_contents($tmp, $zipData);
  $za = new ZipArchive();
  $out = [];
  if ($za->open($tmp) !== true) { @unlink($tmp); return ['error' => 'zip open failed']; }

  for ($i = 0; $i < $za->numFiles; $i++) {
    $nm = $za->getNameIndex($i);
    $isHorse = strpos($nm, 'horselist') !== false;
    $isPay   = strpos($nm, 'payback')   !== false;
    if (!$isHorse && !$isPay) continue;

    foreach (preg_split('/\r?\n/', $za->getFromIndex($i)) as $ln) {
      if ($ln === '') continue;
      $c = str_getcsv($ln);
      if (!isset($c[0]) || $c[0] === '競馬場' || !isset($TC[$c[0]])) continue;
      /* アプリのrid形式に合わせる: YYYY + TC(2) + MMDD(4) + RR(2)
         例 202654071912 = 2026年・高知(54)・07/19・12R。
         v325 の実装は YYYYMMDD+TC+RR を作っており、pred_data と突き合わせられなかった。
         action=daily を使っている箇所がまだ無いうちに揃えておく。 */
      $ymd = str_replace('/', '', $c[1]);
      if (strlen($ymd) !== 8) continue;
      $rid = substr($ymd, 0, 4) . $TC[$c[0]] . substr($ymd, 4, 4) . str_pad($c[2], 2, '0', STR_PAD_LEFT);
      if (!isset($out[$rid])) $out[$rid] = ['ranks' => [], 'top3' => [], 'pay' => null];

      if ($isHorse && count($c) >= 36) {
        if ($c[31] !== '' && ctype_digit($c[31])) {
          $out[$rid]['ranks'][$c[5]] = (int)$c[31];
          if ((int)$c[31] <= 3) $out[$rid]['top3'][] = $c[5];
        }
      } elseif ($isPay && count($c) >= 54) {
        /* 列定義は docs/DATA_SOURCES.md 参照。払戻は100円あたり */
        $p = ['tan' => [], 'fuku' => [], 'wide' => [], 'umaren' => null,
              'umatan' => null, 'sanpuku' => null, 'santan' => null];
        if ($c[4] !== '' && ctype_digit($c[5])) $p['tan'][$c[4]] = (int)$c[5];
        foreach ([[7,8],[10,11],[13,14]] as $ix) {
          if ($c[$ix[0]] !== '' && ctype_digit($c[$ix[1]])) $p['fuku'][$c[$ix[0]]] = (int)$c[$ix[1]];
        }
        foreach ([[32,33,34],[36,37,38],[40,41,42]] as $ix) {
          if ($c[$ix[0]] !== '' && ctype_digit($c[$ix[2]]))
            $p['wide'][$c[$ix[0]] . '-' . $c[$ix[1]]] = (int)$c[$ix[2]];
        }
        if ($c[24] !== '' && ctype_digit($c[26])) $p['umaren'] = ['c' => [$c[24], $c[25]], 'y' => (int)$c[26]];
        if ($c[28] !== '' && ctype_digit($c[30])) $p['umatan'] = ['c' => [$c[28], $c[29]], 'y' => (int)$c[30]];
        if ($c[44] !== '' && ctype_digit($c[47])) $p['sanpuku'] = ['c' => [$c[44], $c[45], $c[46]], 'y' => (int)$c[47]];
        if ($c[49] !== '' && ctype_digit($c[52])) $p['santan']  = ['c' => [$c[49], $c[50], $c[51]], 'y' => (int)$c[52]];
        $out[$rid]['pay'] = $p;
        $out[$rid]['raceName'] = isset($c[3]) ? $c[3] : '';
      }
    }
  }
  $za->close();
  @unlink($tmp);

  /* 着順が1件も無いレースは未確定＝発走前。decided フラグを付けておく */
  foreach ($out as $rid => $r) {
    $out[$rid]['decided'] = (count($r['ranks']) > 0 && $r['pay'] !== null);
  }
  return ['generated' => date('c'), 'races' => $out];
}

if ($action === 'daily') {
  $cacheF = sys_get_temp_dir() . '/nar_daily_cache.json';
  if (is_file($cacheF) && time() - filemtime($cacheF) < 300) { readfile($cacheF); exit; }
  $res = nar_fetch_daily();
  $json = json_encode($res, JSON_UNESCAPED_UNICODE);
  if (!isset($res['error'])) @file_put_contents($cacheF, $json);
  echo $json; exit;
}

/* cron から叩く収集エンドポイント。
   確定済みレースだけを official_results/YYYYMMDD.json に追記マージする（冪等）。
   5-10分間隔で十分。2分毎に叩くのは公式サーバーへの行儀が悪い。 */
if ($action === 'collect') {
  $RD = __DIR__ . '/official_results';
  if (!is_dir($RD)) @mkdir($RD, 0755, true);
  $res = nar_fetch_daily();
  if (isset($res['error'])) { http_response_code(502); echo json_encode($res); exit; }

  $byDate = [];
  foreach ($res['races'] as $rid => $r) {
    if (empty($r['decided'])) continue;
    /* rid = YYYY + TC(2) + MMDD(4) + RR(2) なので日付は 0-3 と 6-9 に分かれている */
    $ymd = substr($rid, 0, 4) . substr($rid, 6, 4);
    $byDate[$ymd][$rid] = $r;
  }

  $added = 0; $totalNow = 0; $dates = [];
  foreach ($byDate as $ymd => $races) {
    $f = $RD . '/' . $ymd . '.json';
    $cur = is_file($f) ? json_decode(file_get_contents($f), true) : [];
    if (!is_array($cur)) $cur = [];
    foreach ($races as $rid => $r) {
      if (!isset($cur[$rid])) $added++;
      $cur[$rid] = $r;                       // 確定後も上書き（訂正があり得るため）
    }
    $body = json_encode($cur, JSON_UNESCAPED_UNICODE);
    /* 書き込みバイト数を検証する。file_put_contents は容量不足時に
       0を返して成功に見えることがある（v306 の教訓） */
    $w = @file_put_contents($f, $body);
    if ($w === false || $w < strlen($body)) {
      http_response_code(507);
      echo json_encode(['error' => 'write failed (disk full?)', 'date' => $ymd]); exit;
    }
    $totalNow += count($cur); $dates[] = $ymd;
  }
  echo json_encode(['ok' => true, 'generated' => $res['generated'],
                    'dates' => $dates, 'newly_decided' => $added, 'stored' => $totalNow],
                   JSON_UNESCAPED_UNICODE);
  exit;
}

if ($action === 'get') {
  $name = isset($_GET['name']) ? $_GET['name'] : '';
  if ($name === '') { echo json_encode(['error' => 'no name']); exit; }
  $b = bucket_of($name);
  $d = load_bucket($DIR, $b, $__cache);
  echo json_encode(['name' => $name, 'hist' => isset($d[$name]) ? $d[$name] : []], JSON_UNESCAPED_UNICODE);
  exit;
}

if ($action === 'batch') {
  $names = isset($_GET['names']) ? explode(',', $_GET['names']) : [];
  // POSTでも受ける（名前が多い/長い場合）
  if (!$names && $_SERVER['REQUEST_METHOD'] === 'POST') {
    $body = json_decode(file_get_contents('php://input'), true);
    if (isset($body['names'])) $names = $body['names'];
  }
  $out = [];
  foreach ($names as $name) {
    $name = trim($name);
    if ($name === '') continue;
    $b = bucket_of($name);
    $d = load_bucket($DIR, $b, $__cache);
    $out[$name] = isset($d[$name]) ? $d[$name] : [];
  }
  echo json_encode(['records' => $out], JSON_UNESCAPED_UNICODE);
  exit;
}

if ($action === 'info') {
  $files = glob($DIR . '/hist_*.json');
  $horses = 0;
  foreach ($files as $f) { $d = json_decode(file_get_contents($f), true); if (is_array($d)) $horses += count($d); }
  echo json_encode(['buckets' => count($files), 'horses' => $horses, 'source' => 'keiba.go.jp official']);
  exit;
}

echo json_encode(['error' => 'unknown action', 'actions' => ['get', 'batch', 'info']]);
