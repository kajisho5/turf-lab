<?php
/* horse.php — 馬の全キャリア成績サーバーキャッシュ
   取得済みの馬データを horse_data/{hid}.json に保存し、次回以降の再取得を省く。
   蓄積データはバックテスト（当地実績が的中に効くか等）の素材にもなる。
   action:
     get      ?action=get&hid=XXXX                 -> 1頭の記録
     getbatch ?action=getbatch&hids=a,b,c          -> {records:{hid:{...}}}
     save     POST {records:[{hid,races:[...]}]}    -> まとめて保存（単体{hid,races}も可）
*/
header('Access-Control-Allow-Origin: *');
header('Access-Control-Allow-Methods: GET, POST, OPTIONS');
header('Access-Control-Allow-Headers: Content-Type');
header('Content-Type: application/json; charset=utf-8');
if ($_SERVER['REQUEST_METHOD'] === 'OPTIONS') { http_response_code(204); exit; }

$DIR = __DIR__ . '/horse_data';
if (!is_dir($DIR)) { @mkdir($DIR, 0755, true); }

function hid_ok($h) { return preg_match('/^[0-9]{6,14}$/', (string)$h); }
function hpath($DIR, $h) { return $DIR . '/' . $h . '.json'; }

$action = isset($_GET['action']) ? $_GET['action'] : '';

/* ---- get ---- */
if ($action === 'get') {
  $hid = isset($_GET['hid']) ? $_GET['hid'] : '';
  if (!hid_ok($hid)) { echo json_encode(['error' => 'bad hid']); exit; }
  $p = hpath($DIR, $hid);
  if (is_file($p)) { readfile($p); } else { echo json_encode(['hid' => $hid, 'miss' => true]); }
  exit;
}

/* ---- getbatch ---- */
if ($action === 'getbatch') {
  $hids = isset($_GET['hids']) ? explode(',', $_GET['hids']) : [];
  $out = [];
  foreach ($hids as $h) {
    $h = trim($h);
    if (!hid_ok($h)) continue;
    $p = hpath($DIR, $h);
    if (is_file($p)) {
      $j = json_decode(file_get_contents($p), true);
      if ($j) { $out[$h] = $j; }
    }
  }
  echo json_encode(['records' => $out], JSON_UNESCAPED_UNICODE);
  exit;
}

/* ---- save (single or batch) ---- */
if ($action === 'save') {
  $raw = file_get_contents('php://input');
  $data = json_decode($raw, true);
  if (!$data) { echo json_encode(['error' => 'bad json']); exit; }
  $items = [];
  if (isset($data['records']) && is_array($data['records'])) { $items = $data['records']; }
  elseif (isset($data['hid'])) { $items = [$data]; }
  $n = 0;
  foreach ($items as $it) {
    if (!isset($it['hid']) || !hid_ok($it['hid'])) continue;
    if (!isset($it['races']) || !is_array($it['races'])) continue;
    $rec = [
      'hid'     => (string)$it['hid'],
      'races'   => $it['races'],
      'updated' => time(),
    ];
    file_put_contents(hpath($DIR, $it['hid']), json_encode($rec, JSON_UNESCAPED_UNICODE));
    $n++;
  }
  echo json_encode(['saved' => $n]);
  exit;
}

echo json_encode(['error' => 'unknown action']);
