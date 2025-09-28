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

  # ✅ 關視窗
  python src/scrape_lolalytics.py --headless 1 --hero $h --mode $Mode --tier $Tier --patch $Patch --lang $Lang --winning_out $win --sets_out $set

  python -m src.main --winning $win --sets $set --out $json --explain --topk 50 --cover 0.8

  # ✅ 用資料本身挑升級靴（先看 sets，加權 pick；缺時回退 winning）
  python src/fix_boots.py --json $json --sets_csv $set --winning_csv $win

  python src/render_build.py --in_json $json --sets_csv $set --out_md $md
}
Write-Host "DONE."
