param(
  [string[]]$Heroes = @("varus","ezreal","lux","jhin"),
  [string]$Mode="aram", [string]$Tier="d2_plus", [string]$Patch="7", [string]$Lang="zh_tw"
)

$raw = "data/raw"; $out = "outputs"
New-Item -ItemType Directory -Force -Path $raw,$out | Out-Null

foreach ($h in $Heroes) {
  $win = "$raw/${h}_${Mode}_${Tier}_${Patch}d_winning.csv"
  $set = "$raw/${h}_${Mode}_${Tier}_${Patch}d_sets.csv"
  $json= "$out/${h}_${Mode}_${Patch}d.json"
  $md  = "$out/${h}_${Mode}_${Patch}d.md"

  python src/scrape_lolalytics.py --hero $h --mode $Mode --tier $Tier --patch $Patch --lang $Lang --winning_out $win --sets_out $set --no-headless
  if ($LASTEXITCODE -ne 0) { Write-Host "scraper failed for $h"; exit $LASTEXITCODE }
  python -m src.main --winning $win --sets $set --out $json --explain --topk 50 --cover 0.8
  python src/render_build.py --in_json $json --sets_csv $set --out_md $md
}
Write-Host "DONE."
