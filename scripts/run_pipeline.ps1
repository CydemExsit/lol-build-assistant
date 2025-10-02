param(
  [string[]] $Heroes = @(),
  [string]   $InDir    = "data/raw",
  [string]   $OutDir   = "data/processed",
  [string]   $ItemsMap = "data/ref/items_map.csv",
  [switch]   $SkipScrape
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

Write-Host "[1/3] Build items_map" -ForegroundColor Cyan
& python "scripts/build_items_map.py" --out $ItemsMap

if (-not $SkipScrape -and $Heroes.Count -gt 0) {
  Write-Host "[2/3] Scrape (build_batch.ps1)" -ForegroundColor Cyan
  & "$PSScriptRoot/build_batch.ps1" -Heroes $Heroes
}
else {
  Write-Host ("[2/3] Skip scrape. Use existing files in " + $InDir) -ForegroundColor Yellow
}

Write-Host "[3/3] Normalize & audit" -ForegroundColor Cyan
& python "scripts/normalize_outputs_batch.py" --in-dir $InDir --items-map $ItemsMap --out-dir $OutDir

Write-Host ("Done. Output at " + $OutDir) -ForegroundColor Green
