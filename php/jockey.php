<?php
/* jockey.php — 騎手の競馬場別成績サーバーキャッシュ（keyは netkeiba 騎手ID）
   keeeeeeba由来の競馬場別成績(競馬場→{n,winR,p3R})を jockey_data/{jkid}.json に保存。
   馬(horse.php)と同じID方式で統一。将来の拡張データ置き場も兼ねる。
   action:
     getbatch ?action=getbatch&ids=a,b,c        -> {records:{jkid:{...}}}
     get      ?action=get&id=XXXX               -> 1件
     save     POST {records:[{jkid,name,tracks}]} -> まとめ保存（単体{jkid,...}も可）
*/
header('Access-Control-Allow-Origin: *');
header('Access-Control-Allow-Methods: GET, POST, OPTIONS');
header('Access-Control-Allow-Headers: Content-Type');
header('Content-Type: application/json; charset=utf-8');
if ($_SERVER['REQUEST_METHOD'] === 'OPTIONS') { http_response_code(204); exit; }

$DIR = __DIR__ . '/jockey_data';
if (!is_dir($DIR)) { @mkdir($DIR, 0755, true); }

function jk_ok($h) { return preg_match('/^[a-z0-9]{3,10}$/i', (string)$h); }
function jpath($DIR, $h) { return $DIR . '/' . $h . '.json'; }

$action = isset($_GET['action']) ? $_GET['action'] : '';

if ($action === 'get') {
  $id = isset($_GET['id']) ? $_GET['id'] : '';
  if (!jk_ok($id)) { echo json_encode(['error' => 'bad id']); exit; }
  $p = jpath($DIR, $id);
  if (is_file($p)) { readfile($p); } else { echo json_encode(['jkid' => $id, 'miss' => true]); }
  exit;
}

if ($action === 'getbatch') {
  $ids = isset($_GET['ids']) ? explode(',', $_GET['ids']) : [];
  $out = [];
  foreach ($ids as $h) {
    $h = trim($h);
    if (!jk_ok($h)) continue;
    $p = jpath($DIR, $h);
    if (is_file($p)) { $j = json_decode(file_get_contents($p), true); if ($j) $out[$h] = $j; }
  }
  echo json_encode(['records' => $out], JSON_UNESCAPED_UNICODE);
  exit;
}

if ($action === 'save') {
  $raw = file_get_contents('php://input');
  $data = json_decode($raw, true);
  if (!$data) { echo json_encode(['error' => 'bad json']); exit; }
  $items = [];
  if (isset($data['records']) && is_array($data['records'])) { $items = $data['records']; }
  elseif (isset($data['jkid'])) { $items = [$data]; }
  $n = 0;
  foreach ($items as $it) {
    if (!isset($it['jkid']) || !jk_ok($it['jkid'])) continue;
    if (!isset($it['tracks']) || !is_array($it['tracks'])) continue;
    $rec = [
      'jkid'    => (string)$it['jkid'],
      'name'    => isset($it['name']) ? $it['name'] : '',
      'tracks'  => $it['tracks'],
      'updated' => time(),
    ];
    file_put_contents(jpath($DIR, $it['jkid']), json_encode($rec, JSON_UNESCAPED_UNICODE));
    $n++;
  }
  echo json_encode(['saved' => $n]);
  exit;
}

echo json_encode(['error' => 'unknown action']);
