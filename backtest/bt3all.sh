#!/bin/bash
echo "=== レースレベルON（現行モデル）==="
for f in /tmp/btreal/races_*.jsonl; do node bt3.js "$f"; done
echo "=== レースレベルOFF（KILL）==="
for f in /tmp/btreal/races_*.jsonl; do KILL=レースレベル node bt3.js "$f"; done
