<?php
/* predictions.php — SW TURF LAB 予想サーバ保存
 * tweet.html が予想を回すと action=save でPOST、lab.html が action=list で取得。
 * kaiko.php と同じ作法（JSONファイル保存・CORS開放・records配列で返す）。
 * 設置: seventh-well.com/odds/predictions.php （pred_data/ は自動生成）
 */
header('Access-Control-Allow-Origin: *');
header('Access-Control-Allow-Methods: GET, POST, OPTIONS');
header('Access-Control-Allow-Headers: Content-Type');
header('Content-Type: application/json; charset=utf-8');
// ★nginxのレスポンスキャッシュ対策★ 予想・ロックは1日の中で書き変わる生データ。
//   キャッシュされると古い予想/ロックが返り続ける（errlog_view.phpで実際に踏んだ罠と同種）。
header('Cache-Control: no-store, no-cache, must-revalidate');
if (($_SERVER['REQUEST_METHOD'] ?? '') === 'OPTIONS') { http_response_code(204); exit; }

$DIR = __DIR__ . '/pred_data';
if (!is_dir($DIR)) @mkdir($DIR, 0775, true);

$action = $_GET['action'] ?? 'list';

function rec_path($dir, $key) {
  $safe = preg_replace('/[^A-Za-z0-9_\-]/', '_', $key);
  return $dir . '/' . $safe . '.json';
}
function reply($arr) { echo json_encode($arr, JSON_UNESCAPED_UNICODE); exit; }

/* ---- 狙い目ロック（B: 最初の予想を固定）---- */
$LOCKDIR = __DIR__ . '/lock_data';
if (!is_dir($LOCKDIR)) { @mkdir($LOCKDIR, 0755, true); }
if ($action === 'savelock') {
  $raw = file_get_contents('php://input');
  $rec = json_decode($raw, true);
  if (!$rec || empty($rec['date']) || !isset($rec['tc'])) { http_response_code(400); reply(['ok' => false]); }
  $mode = $rec['mode'] ?? 'nar';
  $rec['savedAt'] = date('c');
  file_put_contents(rec_path($LOCKDIR, $rec['date'] . '_' . $mode . '_' . $rec['tc']), json_encode($rec, JSON_UNESCAPED_UNICODE));
  reply(['ok' => true]);
}
if ($action === 'listlocks') {
  $date = $_GET['date'] ?? '';
  $mode = $_GET['mode'] ?? '';
  $out = [];
  foreach (glob($LOCKDIR . '/*.json') as $f) {
    $j = json_decode(@file_get_contents($f), true);
    if (!$j) continue;
    if ($date && (($j['date'] ?? '') !== $date)) continue;
    if ($mode && (($j['mode'] ?? '') !== $mode)) continue;
    $out[] = $j;
  }
  reply(['locks' => $out]);
}

/* ---- 1件取得（localStorageが空の時のフォールバック用）---- */
if ($action === 'deletelock') {
  $date = $_GET['date'] ?? ''; $mode = $_GET['mode'] ?? 'nar'; $tc = $_GET['tc'] ?? '';
  if ($date !== '' && $tc !== '') { $p = rec_path($LOCKDIR, $date . '_' . $mode . '_' . $tc); if (is_file($p)) @unlink($p); }
  reply(['ok' => true]);
}
if ($action === 'get') {
  $date = $_GET['date'] ?? '';
  $mode = $_GET['mode'] ?? 'nar';
  $tc   = $_GET['tc'] ?? '';
  if ($date === '' || $tc === '') { reply(['miss' => true]); }
  $p = rec_path($DIR, $date . '_' . $mode . '_' . $tc);
  if (is_file($p)) { readfile($p); exit; }
  reply(['miss' => true]);
}

/* ---- 削除（テストデータ掃除・メンテ用）---- */
if ($action === 'delete') {
  $date = $_GET['date'] ?? ''; $mode = $_GET['mode'] ?? 'nar'; $tc = $_GET['tc'] ?? '';
  if ($date === '' || $tc === '') { reply(['ok' => false, 'error' => 'date/tc required']); }
  $p = rec_path($DIR, $date . '_' . $mode . '_' . $tc);
  $ok = is_file($p) ? @unlink($p) : false;
  reply(['ok' => (bool)$ok]);
}

/* ---- 保存（tweet.html から）---- */
if ($action === 'save') {
  $raw = file_get_contents('php://input');
  $rec = json_decode($raw, true);
  if (!$rec || empty($rec['date']) || !isset($rec['tc'])) {
    http_response_code(400);
    reply(['ok' => false, 'error' => 'invalid payload']);
  }
  $mode = $rec['mode'] ?? 'nar';
  $key  = $rec['date'] . '_' . $mode . '_' . $rec['tc'];
  /* ★noclobber: 既に記録があれば上書きしない★（2026-07-31追加）
     無人運転・オッズ自動更新からの再採点保存は noclobber=true で来る。
     朝の手動ツイート版を発走直前の再採点が上書きする事故を防ぐ。
     手動の全場予想ボタンは noclobber を送らない＝従来通り上書き可。 */
  if (!empty($rec['noclobber']) && file_exists(rec_path($DIR, $key))) {
    reply(['ok' => true, 'kept' => true, 'key' => $key]);
  }
  $rec['savedAt'] = date('c');
  $json = json_encode($rec, JSON_UNESCAPED_UNICODE);
  $ok = @file_put_contents(rec_path($DIR, $key), $json);
  /* 容量満杯だと0バイト書いて0が返る（!==falseだと嘘のokになる）。全量書けた時だけok */
  if ($ok === false || $ok < strlen($json)) { reply(['ok' => false, 'error' => 'disk full or write failed', 'wrote' => ($ok===false?-1:$ok)]); }
  /* ★2026-07-30: 予想は消さない★（ユーザー指示「予想した結果をサーバーに残すように」）
     以前は30日より古い予想を毎回削除していた。だが予想の記録は
     「どのモデルが何を選んで、実際どうだったか」を後から検証する唯一の資料で、
     消すと二度と作れない（当時のオッズ・当時の索引・当時のモデルが揃わない）。
     容量: 1ファイル約80KB × 1日十数場 ≒ 年200MB程度。サーバー空きは14.3TB（実測）。
     0バイトの壊れたファイルだけは掃除する（cleanup.php側で実施）。 */
  reply(['ok' => $ok !== false, 'key' => $key]);
}

/* ---- 一覧（lab.html から）---- */
if ($action === 'list') {
  $date = $_GET['date'] ?? null;        // 任意: 特定日のみ
  $mode = $_GET['mode'] ?? null;        // 任意: jra / nar
  $recs = [];
  foreach (glob($DIR . '/*.json') as $f) {
    $j = json_decode(@file_get_contents($f), true);
    if (!$j) continue;
    if ($date && (($j['date'] ?? '') !== $date)) continue;
    if ($mode && (($j['mode'] ?? '') !== $mode)) continue;
    $recs[] = $j;
  }
  /* 日付降順 → ts降順 */
  usort($recs, function ($a, $b) {
    $c = strcmp((string)($b['date'] ?? ''), (string)($a['date'] ?? ''));
    if ($c !== 0) return $c;
    return ($b['ts'] ?? 0) <=> ($a['ts'] ?? 0);
  });
  reply(['records' => $recs]);
}

/* ---- 保存日一覧（ピッカー用・軽量）---- */
if ($action === 'dates') {
  $seen = [];
  foreach (glob($DIR . '/*.json') as $f) {
    $j = json_decode(@file_get_contents($f), true);
    if ($j && !empty($j['date'])) {
      $m = $j['mode'] ?? 'jra'; $d = $j['date']; $ts = $j['ts'] ?? 0;
      $key = $m . '|' . $d;
      if (!isset($seen[$key]) || $ts > $seen[$key]['ts']) $seen[$key] = ['mode' => $m, 'date' => $d, 'ts' => $ts];
    }
  }
  $items = array_values($seen);
  usort($items, function ($a, $b) { return $b['ts'] - $a['ts']; });
  $dates = [];
  foreach ($items as $it) { $dates[$it['date']] = true; }
  reply(['items' => $items, 'dates' => array_keys($dates)]);
}

http_response_code(400);
reply(['ok' => false, 'error' => 'unknown action']);
