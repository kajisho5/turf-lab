<?php
/* cleanup.php — サーバー容量の確認と掃除（tweet.htmlの🧹ボタンから）
   GET             : 各データディレクトリの使用量レポート（削除しない）
   GET ?run=1      : 掃除を実行して結果を返す
   掃除ルール（保守的）:
     odds_data   14日より古いもの削除（オッズログ＝一番肥大化しやすい）
     horse_data  120日より古いもの削除（馬キャリアキャッシュ、また取り直せる）
     jockey_data 120日より古いもの削除
     result_data 90日より古いもの削除（答え合わせ済みの結果キャッシュ）
     pred_data   30日より古いもの＋0バイトファイル削除
     lock_data   30日より古いもの削除
*/
header('Access-Control-Allow-Origin: *');
header('Content-Type: application/json; charset=utf-8');
/* ★2026-07-30 全部残す方針に変更★（ユーザー指示「データは全てサーバーに残して」
   「予想した結果とかをサーバーに残すように」）
   実測: サーバー空き 14.3TB / 現在の使用量は全ディレクトリ合計で 23MB。
   消す理由が容量には無い。一方、消すと困る理由は各々にある:

     odds_data   締切前のオッズ変化＝市場に無い情報の本命。
                 「7分前vs2分前」の検証は**貯めないと永久に着手できない**
                 （14日で消していたので、これまで検証が不可能だった）
     horse_data  netkeibaの馬キャリア。★netkeibaは実際にIPをブロックしてきた★
                 「また取れる」を前提にできない
     jockey_data 同上
     result_data 予想の答え合わせに必要。予想だけ残して結果を消すと検証できない
     pred_data   「どのモデルが何を選び実際どうだったか」の唯一の資料
     lock_data   その日どのレースを狙い目に固定したか（投稿内容の裏付け）

   仕組みは残す（容量が本当に苦しくなったら数字を下げれば効く）。
   0バイトの壊れたファイル掃除は下のロジックで継続。 */
$RULES = [
  'odds_data'   => 36500,
  'horse_data'  => 36500,
  'jockey_data' => 36500,
  'result_data' => 36500,
  'pred_data'   => 36500,
  'lock_data'   => 36500,
];
$run = isset($_GET['run']);
$out = ['run' => $run, 'dirs' => [], 'freedBytes' => 0, 'deleted' => 0];
/* ★2026-07-30: サブフォルダも見るようにした★
   これまで glob($dir.'/*') + is_file() だったので、
   **odds_data/{日付}/{rid}.json のような入れ子は集計も削除もされていなかった**。
   ・結果オーライだった面: 14日ルールでオッズ記録が消されずに2月分から残っていた
   ・嘘をついていた面: 使用量が「odds_data 0MB」と表示されていた（実際は中身がある）
   容量を見るためのページなので、実物を数えないと意味がない。 */
function walk_files($dir) {
  $out = [];
  foreach (glob($dir . '/*') as $p) {
    if (is_dir($p)) { $out = array_merge($out, walk_files($p)); }
    elseif (is_file($p)) { $out[] = $p; }
  }
  return $out;
}
foreach ($RULES as $d => $days) {
  $dir = __DIR__ . '/' . $d;
  if (!is_dir($dir)) { $out['dirs'][$d] = ['missing' => true]; continue; }
  $files = walk_files($dir);
  $bytes = 0; $old = 0; $oldBytes = 0; $zero = 0;
  $cut = time() - $days * 86400;
  foreach ($files as $f) {
    $sz = filesize($f); $bytes += $sz;
    $isOld = filemtime($f) < $cut;
    $isZero = ($sz === 0);
    if ($isOld || ($d === 'pred_data' && $isZero)) {
      $old++; $oldBytes += $sz; if ($isZero) $zero++;
      if ($run) { if (@unlink($f)) { $out['freedBytes'] += $sz; $out['deleted']++; } }
    }
  }
  $out['dirs'][$d] = ['files' => count($files), 'mb' => round($bytes/1048576, 1),
                      'deletable' => $old, 'deletableMb' => round($oldBytes/1048576, 1), 'zeroByte' => $zero];
}
$free = @disk_free_space(__DIR__);
if ($free !== false) $out['diskFreeMb'] = round($free/1048576, 1);
echo json_encode($out, JSON_UNESCAPED_UNICODE);
