param(
  [string]$Heroes = "varus",
  [switch]$ShowBrowser
)

$heroes = $Heroes -split '[,\s]+' | Where-Object { $_ }
$raw = "data/raw"; $out = "outputs"
New-Item -ItemType Directory -Force -Path $raw,$out | Out-Null

foreach ($h in $heroes) {
  $win  = "$raw/${h}_aram_d2_plus_7d_winning.csv"
  $set  = "$raw/${h}_aram_d2_plus_7d_sets.csv"
  $json = "$out/${h}_aram_7d.json"
  $md   = "$out/${h}_aram_7d.md"

  # 先刪舊檔，確保是新寫出來的
  Remove-Item $win,$set -ErrorAction SilentlyContinue

  $argsList = @(
    "src/scrape_lolalytics.py",
    "--hero",  $h,
    "--mode",  "aram",
    "--tier",  "d2_plus",
    "--patch", "7",
    "--lang",  "zh_tw",
    "--winning_out", $win,
    "--sets_out",    $set
  )
  if ($ShowBrowser) { $argsList += "--no-headless" }

  Write-Host "[run] scrape $h..."
  & python @argsList
  if ($LASTEXITCODE -ne 0) { throw "scraper failed for $h" }

  # 讀行數驗證確實寫到檔案（含表頭，所以要 >1）
  $winRows = if (Test-Path $win) { (Import-Csv $win).Count } else { 0 }
  $setRows = if (Test-Path $set) { (Import-Csv $set).Count } else { 0 }
  Write-Host "[ok] rows -> winning=$winRows, sets=$setRows"

  if ($winRows -le 1 -or $setRows -le 1) { throw "empty csv for $h" }

  & python -m src.main --winning $win --sets $set --out $json --explain --topk 50 --cover 0.8
  if ($LASTEXITCODE -ne 0) { throw "algo failed for $h" }

  & python src/render_build.py --sets_csv $set --out_md $md --topk 50
  if ($LASTEXITCODE -ne 0) { throw "render failed for $h" }
}

Write-Host "DONE."
