param(
  [string]$Heroes = "varus",
  [switch]$ShowBrowser
)

$heroList = $Heroes -split '[,\s]+' | Where-Object { $_ -ne '' }
$raw = "data/raw"; $out = "outputs"
New-Item -ItemType Directory -Force -Path $raw,$out | Out-Null
$headlessArg = if ($ShowBrowser.IsPresent) { "--no-headless" } else { "" }

foreach ($h in $heroList) {
  $win = "$raw/${h}_aram_d2_plus_7d_winning.csv"
  $set = "$raw/${h}_aram_d2_plus_7d_sets.csv"
  $md  = "$out/${h}_aram_7d.md"

  python src/scrape_lolalytics.py --hero $h --mode aram --tier d2_plus --patch 7 --lang zh_tw --winning_out $win --sets_out $set $headlessArg
  if ($LASTEXITCODE -ne 0) { throw "scraper failed for $h" }

  python src/render_build.py --sets_csv $set --out_md $md --topk 8
}
Write-Host "DONE."
