<?php
/* proxy.php のキャッシュを外部から充填する（netkeibaブロック時の緊急バイパス）
 *
 * ■ なぜ
 *   netkeiba がサーバーIPをブロックすると proxy.php は何も返せない。
 *   だが開発PCのIPからは取得できる。そこで開発PCが取得したHTMLを
 *   ここへPOSTし、proxy.php のキャッシュ（stale-fallback）として置く。
 *   proxy.php は既にキャッシュがあれば返す実装なので、この充填だけで
 *   サイトは無変更で動き出す。
 *
 * ■ 使い方（開発PCから）
 *   POST /proxy_seed.php?t=<TOKEN>
 *   body: JSON {"url": "https://nar.netkeiba.com/...", "body_b64": "<base64 HTML>",
 *               "ctype": "text/html; charset=UTF-8"}
 *
 * ■ 安全
 *   ・トークン必須（外部からの汚染防止）
 *   ・URLは proxy.php と同じホワイトリスト（netkeiba系のみ）
 *   ・書き込み先は cache/proxy/ 固定（sha1名なのでパストラバーサル不可）
 */
const SEED_TOKEN = 'sw-seed-9f2a1c7e';   // 簡易トークン（漏れたら変える）

header('Content-Type: application/json; charset=UTF-8');

if (($_GET['t'] ?? '') !== SEED_TOKEN) {
  http_response_code(403);
  echo json_encode(['ok' => false, 'error' => 'forbidden']);
  exit;
}

$raw = file_get_contents('php://input');
$req = json_decode($raw, true);
$url = (string)($req['url'] ?? '');
$b64 = (string)($req['body_b64'] ?? '');
$ctype = (string)($req['ctype'] ?? 'text/html; charset=UTF-8');

if ($url === '' || !preg_match('#^https://[a-z0-9.-]*\.(netkeiba|keeeeeeba)\.com/#i', $url)) {
  http_response_code(400);
  echo json_encode(['ok' => false, 'error' => 'bad url']);
  exit;
}
$body = base64_decode($b64, true);
if ($body === false || strlen($body) < 200) {
  http_response_code(400);
  echo json_encode(['ok' => false, 'error' => 'bad body']);
  exit;
}

$dir = __DIR__ . '/cache/proxy';
if (!is_dir($dir)) { @mkdir($dir, 0775, true); }
$f = $dir . '/' . sha1($url) . '.cache';
$ok = @file_put_contents($f, json_encode(['code' => 200, 'ctype' => $ctype], JSON_UNESCAPED_UNICODE) . "\n" . $body, LOCK_EX);

echo json_encode(['ok' => $ok !== false, 'file' => basename($f), 'bytes' => strlen($body)]);
