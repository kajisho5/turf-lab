<?php
/* seventh-well.com/odds/oddslog.php
   オッズのスナップショットを時系列で蓄積する。
   目的: 「発走前オッズ」と「締切直前オッズ」の差分＝市場の動きを検出するため。
   公開情報（脚質・血統・騎手など）は既にオッズに織り込まれているが、
   「オッズが今まさに動いている」という事実だけは、リアルタイムでしか観測できない。

   POST ?action=save  body: {rid, mode, date, ts, odds:{num:{odds,pop}}}
     → odds_data/{date}/{rid}.json に追記（同一ridの時系列配列）
   GET  ?action=get&rid=xxx      → そのレースの全スナップショット
   GET  ?action=dates            → 保存済み日付一覧
   GET  ?action=list&date=xxxxxx → その日の保存済みrid一覧
*/
header('Access-Control-Allow-Origin: *');
header('Content-Type: application/json; charset=utf-8');
header('Access-Control-Allow-Methods: GET, POST, OPTIONS');
header('Access-Control-Allow-Headers: Content-Type');
// ★nginxのレスポンスキャッシュ対策★ オッズの時系列は数分単位で追記される生データ。
//   キャッシュされると「オッズが今まさに動いている」を見るための本来の目的が壊れる。
header('Cache-Control: no-store, no-cache, must-revalidate');
if ($_SERVER['REQUEST_METHOD'] === 'OPTIONS') { exit; }

$BASE = __DIR__ . '/odds_data';
if (!is_dir($BASE)) { @mkdir($BASE, 0755, true); }

$action = isset($_GET['action']) ? $_GET['action'] : '';

function jout($x){ echo json_encode($x, JSON_UNESCAPED_UNICODE); exit; }

if ($action === 'save') {
  $raw = file_get_contents('php://input');
  $d = json_decode($raw, true);
  if (!$d || empty($d['rid']) || empty($d['odds'])) { http_response_code(400); jout(['error'=>'bad payload']); }

  $rid  = preg_replace('/[^0-9]/', '', $d['rid']);
  $date = preg_replace('/[^0-9]/', '', isset($d['date']) ? $d['date'] : '');
  if ($rid === '' || strlen($date) !== 8) { http_response_code(400); jout(['error'=>'bad rid/date']); }

  $dir = $BASE . '/' . $date;
  if (!is_dir($dir)) { @mkdir($dir, 0755, true); }
  $file = $dir . '/' . $rid . '.json';

  // 既存のスナップショット配列に追記
  $arr = [];
  if (file_exists($file)) {
    $j = json_decode(file_get_contents($file), true);
    if (is_array($j)) { $arr = $j; }
  }
  /* ★2026-07-30: post(発走時刻)と mtp(発走までの残り分数)も保存する★
     この2つが無いと「7分前のオッズ vs 2分前のオッズ」に振り分けられない。
     実際、5ヶ月分の記録が貯まっていたのに ts(絶対時刻)しか無いため
     時系列検証に使えなかった（間隔も2時間差と5分差が混在していた）。
     ここは白リスト方式なので、項目を足さないと黙って捨てられる。 */
  $snap = [
    'ts'   => isset($d['ts']) ? (int)$d['ts'] : (time() * 1000),
    'mode' => isset($d['mode']) ? $d['mode'] : '',
    'post' => isset($d['post']) ? preg_replace('/[^0-9:]/', '', (string)$d['post']) : null,
    'mtp'  => (isset($d['mtp']) && is_numeric($d['mtp'])) ? (int)$d['mtp'] : null,
    'odds' => $d['odds'],
  ];
  // 同一分内の重複は上書き（無駄な肥大化を防ぐ）
  $minute = floor($snap['ts'] / 60000);
  $replaced = false;
  foreach ($arr as $i => $old) {
    if (isset($old['ts']) && floor($old['ts'] / 60000) === $minute) { $arr[$i] = $snap; $replaced = true; break; }
  }
  if (!$replaced) { $arr[] = $snap; }

  // 原子的書き込み
  $tmp = $file . '.tmp';
  file_put_contents($tmp, json_encode($arr, JSON_UNESCAPED_UNICODE), LOCK_EX);
  @rename($tmp, $file);
  jout(['ok'=>true, 'rid'=>$rid, 'snapshots'=>count($arr)]);
}

if ($action === 'get') {
  $rid  = preg_replace('/[^0-9]/', '', isset($_GET['rid']) ? $_GET['rid'] : '');
  $date = preg_replace('/[^0-9]/', '', isset($_GET['date']) ? $_GET['date'] : '');
  if ($rid === '') { http_response_code(400); jout(['error'=>'no rid']); }
  // dateが無ければ全日付から探す
  $cands = [];
  if (strlen($date) === 8) { $cands[] = $BASE . '/' . $date . '/' . $rid . '.json'; }
  else {
    foreach (glob($BASE . '/*', GLOB_ONLYDIR) as $d) { $cands[] = $d . '/' . $rid . '.json'; }
  }
  foreach ($cands as $f) {
    if (file_exists($f)) { echo file_get_contents($f); exit; }
  }
  jout([]);
}

if ($action === 'dates') {
  $out = [];
  foreach (glob($BASE . '/*', GLOB_ONLYDIR) as $d) {
    $out[] = ['date'=>basename($d), 'races'=>count(glob($d . '/*.json'))];
  }
  usort($out, function($a,$b){ return strcmp($b['date'], $a['date']); });
  jout(['dates'=>$out]);
}

if ($action === 'list') {
  $date = preg_replace('/[^0-9]/', '', isset($_GET['date']) ? $_GET['date'] : '');
  if (strlen($date) !== 8) { http_response_code(400); jout(['error'=>'bad date']); }
  $out = [];
  foreach (glob($BASE . '/' . $date . '/*.json') as $f) {
    $j = json_decode(file_get_contents($f), true);
    $out[] = ['rid'=>basename($f, '.json'), 'snapshots'=>is_array($j) ? count($j) : 0];
  }
  jout(['date'=>$date, 'races'=>$out]);
}

http_response_code(400);
jout(['error'=>'unknown action']);
