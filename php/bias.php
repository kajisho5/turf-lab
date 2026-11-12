<?php
/* 日次バイアス（脚質・枠・馬場）保存API  SW TURF LAB */
header('Content-Type: application/json; charset=utf-8');
header('Access-Control-Allow-Origin: *');
header('Access-Control-Allow-Methods: GET, POST, OPTIONS');
header('Access-Control-Allow-Headers: Content-Type');
if ($_SERVER['REQUEST_METHOD'] === 'OPTIONS') { http_response_code(204); exit; }

$DIR = __DIR__ . '/bias_data';
if (!is_dir($DIR)) { @mkdir($DIR, 0755, true); }

$action = $_GET['action'] ?? 'list';

function rec_path($dir, $key) {
  $safe = preg_replace('/[^A-Za-z0-9_\-]/', '_', $key);
  return $dir . '/' . $safe . '.json';
}
function reply($arr) { echo json_encode($arr, JSON_UNESCAPED_UNICODE); exit; }

/* ---- 保存: 1日分（date + mode + races[]） ---- */
if ($action === 'save') {
  $raw = file_get_contents('php://input');
  $rec = json_decode($raw, true);
  if (!$rec || empty($rec['date'])) { http_response_code(400); reply(['ok' => false, 'error' => 'invalid payload']); }
  $mode = $rec['mode'] ?? 'nar';
  $rec['savedAt'] = date('c');
  $key = $rec['date'] . '_' . $mode;
  file_put_contents(rec_path($DIR, $key), json_encode($rec, JSON_UNESCAPED_UNICODE));
  reply(['ok' => true, 'key' => $key, 'races' => count($rec['races'] ?? [])]);
}

/* ---- 1日分取得 ---- */
if ($action === 'get') {
  $date = $_GET['date'] ?? '';
  $mode = $_GET['mode'] ?? 'nar';
  if ($date === '') { reply(['miss' => true]); }
  $p = rec_path($DIR, $date . '_' . $mode);
  if (is_file($p)) { readfile($p); exit; }
  reply(['miss' => true]);
}

/* ---- 一覧（期間集計用。date/mode/track で絞れる） ---- */
if ($action === 'list') {
  $date = $_GET['date'] ?? null;
  $mode = $_GET['mode'] ?? null;
  $from = $_GET['from'] ?? null;   // YYYYMMDD
  $to   = $_GET['to'] ?? null;
  $recs = [];
  foreach (glob($DIR . '/*.json') as $f) {
    $j = json_decode(@file_get_contents($f), true);
    if (!$j) continue;
    $d = $j['date'] ?? '';
    if ($date && $d !== $date) continue;
    if ($mode && (($j['mode'] ?? '') !== $mode)) continue;
    if ($from && $d < $from) continue;
    if ($to && $d > $to) continue;
    $recs[] = $j;
  }
  usort($recs, function ($a, $b) { return strcmp($b['date'] ?? '', $a['date'] ?? ''); });
  reply(['records' => $recs]);
}

/* ---- 保存済み日付一覧 ---- */
if ($action === 'dates') {
  $items = [];
  foreach (glob($DIR . '/*.json') as $f) {
    $j = json_decode(@file_get_contents($f), true);
    if ($j && !empty($j['date'])) {
      $items[] = ['date' => $j['date'], 'mode' => $j['mode'] ?? 'nar', 'races' => count($j['races'] ?? [])];
    }
  }
  usort($items, function ($a, $b) { return strcmp($b['date'], $a['date']); });
  reply(['items' => $items]);
}

http_response_code(400);
reply(['ok' => false, 'error' => 'unknown action']);
