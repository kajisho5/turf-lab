<?php
/* results.php — SW TURF LAB レース結果キャッシュ（race_id単位）
 * lab.html が一度プロキシ取得した着順/配当をここに保存し、次回からサーバから読む。
 * 設置: seventh-well.com/odds/results.php （result_data/ は自動生成）
 */
header('Access-Control-Allow-Origin: *');
header('Access-Control-Allow-Methods: GET, POST, OPTIONS');
header('Access-Control-Allow-Headers: Content-Type');
header('Content-Type: application/json; charset=utf-8');
// ★nginxのレスポンスキャッシュ対策★ 発走前（結果なし）の応答がキャッシュされると、
//   レース確定後にPOSTで結果を保存しても、GETは古い「結果なし」を返し続ける
//   （tweet.htmlのcache:"no-store"コメントと同じ症状が、サーバー側でも起きうる）。
header('Cache-Control: no-store, no-cache, must-revalidate');
if (($_SERVER['REQUEST_METHOD'] ?? '') === 'OPTIONS') { http_response_code(204); exit; }

$DIR = __DIR__ . '/result_data';
if (!is_dir($DIR)) @mkdir($DIR, 0775, true);

$action = $_GET['action'] ?? 'get';

function rp($dir, $rid) {
  $safe = preg_replace('/[^A-Za-z0-9_\-]/', '_', (string)$rid);
  return $dir . '/' . $safe . '.json';
}
function reply($a) { echo json_encode($a, JSON_UNESCAPED_UNICODE); exit; }

/* 保存（複数）: body = {items:[{race_id,ranks,pays}]} */
if ($action === 'savebatch' || $action === 'save') {
  $j = json_decode(file_get_contents('php://input'), true);
  $items = ($action === 'save') ? [$j] : (($j['items'] ?? []));
  $n = 0;
  foreach ($items as $it) {
    if (empty($it['race_id'])) continue;
    $it['at'] = date('c');
    if (@file_put_contents(rp($DIR, $it['race_id']), json_encode($it, JSON_UNESCAPED_UNICODE)) !== false) $n++;
  }
  /* 120日より古いキャッシュを間引き */
  foreach (glob($DIR . '/*.json') as $f) {
    if (filemtime($f) < time() - 120 * 86400) @unlink($f);
  }
  reply(['ok' => true, 'saved' => $n]);
}

/* 取得: ?ids=rid1,rid2  または body {ids:[...]} */
if ($action === 'get') {
  $ids = [];
  if (!empty($_GET['ids'])) $ids = explode(',', $_GET['ids']);
  else {
    $j = json_decode(file_get_contents('php://input'), true);
    if (is_array($j['ids'] ?? null)) $ids = $j['ids'];
  }
  $out = [];
  foreach ($ids as $rid) {
    $rid = trim((string)$rid);
    if ($rid === '') continue;
    $f = rp($DIR, $rid);
    if (is_file($f)) {
      $v = json_decode(@file_get_contents($f), true);
      if ($v) $out[$rid] = $v;
    }
  }
  reply(['results' => $out]);
}

http_response_code(400);
reply(['ok' => false, 'error' => 'unknown action']);
