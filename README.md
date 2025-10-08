# LoL Build Assistant

## MVP 範圍
- 目標：針對單一英雄（目前為 Varus）從 Lolalytics 擷取 ARAM 裝備資料，輸出推薦出裝 JSON。
- 輸入：Lolalytics 實際出裝/最高勝率裝備區塊。
- 輸出：`*_winning.csv`、`*_sets.csv` 以及含理由的 `*_build.json`。
- 依賴：Python 3.10+、Playwright（Chromium）、Lolalytics 頁面能正常存取。

## Quickstart（單英雄一鍵流程）
```bash
python scripts/quickstart.py --hero varus --mode aram --lang zh_tw --tier d2_plus --patch 7 --out data/processed
```
流程說明：
1. 建立虛擬環境並安裝依賴：`scripts/setup.sh` 或 `scripts/setup.ps1`。
2. 執行上述指令，會自動抓取資料、輸出 CSV、JSON 與 Markdown 卡片表。
3. 產物範例位於 `data/processed`：`varus_aram_d2_plus_7_winning.csv`、`varus_aram_d2_plus_7_sets.csv`、`varus_aram_d2_plus_7_build.json`、`varus_aram_d2_plus_7_build.md`。

## Cloudflare 說明
Lolalytics 可能以 Cloudflare 擋下自動化請求，建議流程：
1. `python cf_shield_fix.py bootstrap --hero varus --mode aram --tier d2_plus --patch 7 --lang zh_tw --state data/cf_state.json`
2. 按照螢幕指示手動通過驗證後存成 storage state。
3. 若仍遭阻擋，可用 `python cf_shield_fix.py test --hero varus --mode aram --tier d2_plus --patch 7 --lang zh_tw --state data/cf_state.json` 檢查。
4. 主流程可在 Playwright `new_context` 時帶入 `storage_state`。

## Demo 連結
- [`demo/winning.sample.csv`](demo/winning.sample.csv)
- [`demo/sets.sample.csv`](demo/sets.sample.csv)

## 已知限制
- 需人工處理 Cloudflare 與 Lolalytics 站改版風險。
- 僅驗證 Varus ARAM 流程，其他英雄需另行測試。
- 目前僅支援單執行緒；批次流程尚未整合。

## License
本專案採用 [MIT License](LICENSE)。

## Roadmap
Roadmap 與子議題整理於 [Issues](../../issues)。歡迎以 `roadmap`、`good first issue`、`limitations`、`help wanted` 等標籤瀏覽。
