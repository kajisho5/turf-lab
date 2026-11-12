<?php
/* unzip_horse.php — horse_data_seed.zip を horse_data/ に一括展開する（1回だけ実行→削除）
   使い方:
     1) horse_data_seed.zip と このファイルを /odds/ に置く
     2) ブラウザで https://seventh-well.com/odds/unzip_horse.php を開く
     3) 「展開完了」が出たら、このファイルは削除してOK
*/
header('Content-Type: text/plain; charset=utf-8');
@set_time_limit(600);

$src = __DIR__ . '/horse_data_seed.zip';
$dst = __DIR__ . '/horse_data';

if (!class_exists('ZipArchive')) { echo "NG: このサーバーに ZipArchive が無い。cPanelのファイルマネージャや SSH の unzip で展開してください。"; exit; }
if (!is_file($src)) { echo "NG: horse_data_seed.zip が見つからない（このファイルと同じ場所に置いてください）"; exit; }
if (!is_dir($dst) && !@mkdir($dst, 0755, true)) { echo "NG: horse_data/ を作れない（書き込み権限を確認）"; exit; }

$zip = new ZipArchive;
if ($zip->open($src) !== TRUE) { echo "NG: zipを開けません（壊れている可能性）"; exit; }

$total = $zip->numFiles;
if (!$zip->extractTo($dst)) { $zip->close(); echo "NG: 展開に失敗（書き込み権限/容量を確認）"; exit; }
$zip->close();

$count = 0;
$dh = opendir($dst);
if ($dh) { while (($f = readdir($dh)) !== false) { if (substr($f, -5) === '.json') $count++; } closedir($dh); }

echo "展開完了: zip内 {$total} 件 / horse_data/ に {$count} 個の .json\n";
echo "→ 確認できたら unzip_horse.php と horse_data_seed.zip は削除してOKです。\n";
