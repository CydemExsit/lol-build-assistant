# LoL Build Assistant (PoC)

用手動輸入的 CSV（Winning Items / Actually Built Sets）產出 ARAM 出裝順序（中文裝備名）。

## 專案資料夾整理

執行流程會在 `data/raw/`, `data/processed/` 與 `outputs/` 產出大量中間資料與結果檔案，這些內容現在已加入 `.gitignore`，預設不再納入版本控制：

- `data/raw/`：爬蟲或手動整理後的原始 CSV / HTML / 圖像等資料。請自行於本機建立並填入最新資料。
- `data/processed/`：經 `scripts/normalize_outputs*.py` 清整後的中間資料。
- `outputs/`：`src/pipeline.py` 或其他腳本輸出的最終 JSON/Markdown 結果。
- `data/debug/`：除錯時產生的報告或截圖。
- `data/cf_state.json`：Scraper 與 Cloudflare 互動時的暫存狀態。

如需保留本地測試用的範例，可使用 `data/samples/` 目錄中的 sample CSV；或自行建立未被忽略的子資料夾。

若要重新產生上述資料夾內容，請參考 `scripts/` 內的工具或自訂流程。 
