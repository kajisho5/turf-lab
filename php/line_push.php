<?php
/* line_push.php — LINE配信の出口（tweet.htmlのLINE配信モードからPOSTされる）
 *
 * ★設計★
 *   トークンは line_config.php（gitに入れない・サーバーにだけ置く）から読む。
 *   トークン未設定でも動く: メッセージを line_outbox/ に保存して ok:false, reason
 *   を返す（＝ドライラン。実際に何が送られるかを先に確認できる）。
 *
 * ★二重送信ガード★
 *   同じ race_id への送信は1回だけ（line_sent/ にマーカー）。
 *   ブラウザ側のタイマーが二重に発火しても2通は送らない。
 *
 * POST body: { race_id, text }
 * line_config.php の中身:
 *   <?php $LINE_CHANNEL_TOKEN = 'チャネルアクセストークン';
 */
header('Access-Control-Allow-Origin: *');
header('Access-Control-Allow-Methods: POST, OPTIONS');
header('Access-Control-Allow-Headers: Content-Type');
header('Content-Type: application/json; charset=utf-8');
if (($_SERVER['REQUEST_METHOD'] ?? '') === 'OPTIONS') { http_response_code(204); exit; }

$OUTBOX = __DIR__ . '/line_outbox';
$SENT   = __DIR__ . '/line_sent';
foreach ([$OUTBOX, $SENT] as $d) { if (!is_dir($d)) @mkdir($d, 0775, true); }

function reply($a) { echo json_encode($a, JSON_UNESCAPED_UNICODE); exit; }

$j = json_decode(file_get_contents('php://input'), true);
$rid  = preg_replace('/[^0-9]/', '', (string)($j['race_id'] ?? ''));
$text = (string)($j['text'] ?? '');
if ($rid === '' || $text === '') { http_response_code(400); reply(['ok' => false, 'error' => 'bad payload']); }
if (mb_strlen($text) > 1800) $text = mb_substr($text, 0, 1800);   // LINE上限5000だが安全側

/* ★ドライラン★ dry=1 なら送信せず outbox 保存のみ（.dry.txt）。
   送信済みマークも付けない＝後で本物を送れる。無人運転の通し試験用。 */
if (!empty($j['dry'])) {
  @file_put_contents($OUTBOX . '/' . $rid . '.dry.txt', $text);
  reply(['ok' => true, 'dry' => true]);
}

/* 二重送信ガード */
$mark = $SENT . '/' . $rid . '.sent';
if (file_exists($mark)) { reply(['ok' => true, 'dup' => true]); }

/* 何を送った(送ろうとした)かは必ず残す（配信履歴＝検証の資料） */
@file_put_contents($OUTBOX . '/' . $rid . '.txt', $text);

$token = null;
if (file_exists(__DIR__ . '/line_config.php')) {
  include __DIR__ . '/line_config.php';
  $token = $LINE_CHANNEL_TOKEN ?? null;
}
if (!$token) {
  reply(['ok' => false, 'reason' => 'no_token',
         'note' => 'line_config.php 未設置。メッセージは line_outbox/ に保存した（ドライラン）']);
}

/* LINE Messaging API broadcast（友だち全員へ） */
$ch = curl_init('https://api.line.me/v2/bot/message/broadcast');
curl_setopt_array($ch, [
  CURLOPT_POST => true,
  CURLOPT_HTTPHEADER => ['Content-Type: application/json',
                         'Authorization: Bearer ' . $token],
  CURLOPT_POSTFIELDS => json_encode(['messages' => [['type' => 'text', 'text' => $text]]],
                                    JSON_UNESCAPED_UNICODE),
  CURLOPT_RETURNTRANSFER => true, CURLOPT_TIMEOUT => 15,
]);
$res = curl_exec($ch);
$code = curl_getinfo($ch, CURLINFO_HTTP_CODE);
curl_close($ch);

if ($code >= 200 && $code < 300) {
  @file_put_contents($mark, date('c'));
  reply(['ok' => true]);
}
reply(['ok' => false, 'error' => 'line api ' . $code, 'body' => substr((string)$res, 0, 300)]);
