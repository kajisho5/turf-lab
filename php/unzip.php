<?php
/* unzip.php — seed zip を対応フォルダに一括展開（1回だけ実行→削除）
   /odds/ に置いた seed zip を、それぞれの data フォルダに展開する:
     horse_data_seed.zip   -> horse_data/
     jockey_data_seed.zip  -> jockey_data/
   ブラウザで https://seventh-well.com/odds/unzip.php を開けば全部展開される。
*/
header('Content-Type: text/plain; charset=utf-8');
@set_time_limit(600);

$map = [
  'horse_data_seed.zip'  => 'horse_data',
  'jockey_data_seed.zip' => 'jockey_data',
];

if (!class_exists('ZipArchive')) { echo "NG: ZipArchive が無い。cPanel/SSH の unzip で展開してください。\n"; exit; }

foreach ($map as $zipName => $dirName) {
  $src = __DIR__ . '/' . $zipName;
  $dst = __DIR__ . '/' . $dirName;
  if (!is_file($src)) { echo "skip: {$zipName} が無い\n"; continue; }
  if (!is_dir($dst) && !@mkdir($dst, 0755, true)) { echo "NG: {$dirName}/ を作れない（権限）\n"; continue; }
  $zip = new ZipArchive;
  if ($zip->open($src) !== TRUE) { echo "NG: {$zipName} を開けない\n"; continue; }
  $total = $zip->numFiles;
  $ok = $zip->extractTo($dst);
  $zip->close();
  if (!$ok) { echo "NG: {$zipName} 展開失敗（権限/容量）\n"; continue; }
  $cnt = 0; $dh = opendir($dst);
  if ($dh) { while (($f = readdir($dh)) !== false) { if (substr($f, -5) === '.json') $cnt++; } closedir($dh); }
  echo "OK: {$zipName} → {$dirName}/ に {$cnt} 個の .json（zip内{$total}件）\n";
}
echo "\n完了したら unzip.php と *_seed.zip は削除してOKです。\n";
