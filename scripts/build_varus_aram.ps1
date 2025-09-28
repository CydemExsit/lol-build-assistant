param(
  [string]$Tier="d2_plus",
  [string]$Patch="7",
  [string]$Lang="zh_tw"
)

$ErrorActionPreference = "Stop"
chcp 65001 > $null
$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()

$w = ".\data\raw\varus_aram_${Tier}_${Patch}d_winning.csv"
$s = ".\data\raw\varus_aram_${Tier}_${Patch}d_sets.csv"
$o = ".\outputs\varus_aram_${Patch}d.json"

python src/scrape_lolalytics.py --hero varus --mode aram --tier $Tier --patch $Patch --lang $Lang --winning_out $w --sets_out $s
python -m src.main --winning $w --sets $s --out $o --explain --topk 50 --cover 0.8
Write-Host "DONE -> $o"
