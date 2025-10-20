# Issues TODO

> 無法直接建立 GitHub Issues，以下提供草稿與對應指令範本。

---

## Roadmap: v0.1 強化單流程

- 聚焦內容：
  - Playwright 逾時 / HTTPS 錯誤時給出明確錯誤碼與重試建議（目前 `scrape_lolalytics.py` 在 `Page.goto` 失敗時直接崩潰）。
  - 製作 `winning.csv` / `sets.csv` 欄位對照表與 README 對應，避免欄位變動時使用者摸索。
  - 在 Windows / macOS / Linux 進行 smoke test，至少 Varus ARAM 流程連跑 5 次成功率 ≥ 90%。
- 完成定義：有上列對應改善，並更新 README。

```bash
# gh issue create --title "Roadmap: v0.1 強化單流程" --body-file issue-roadmap-v0.1.md --label roadmap
```

---

## Roadmap: v0.2 批次多英雄 + 節流

- 聚焦內容：
  - `src/scrape_lolalytics_batch.py` 改為讀取英雄清單檔並加入節流（目前僅簡單迴圈，易觸發限流）。
  - 針對失敗場景（CF 驗證、網路中斷）設計重試與 resume。
  - 確認批次輸出檔名一致且不覆蓋成功結果。
- 完成定義：一次處理 5 名英雄完成且未出現 Cloudflare 阻擋記錄。

```bash
# gh issue create --title "Roadmap: v0.2 批次多英雄 + 節流" --body-file issue-roadmap-v0.2.md --label roadmap
```

---

## Good first issue: 精簡一鍵安裝腳本

- 說明：目前 README 需手動執行 `pip install`、`playwright install chromium` 與 apt 相依套件。新增 cross-platform（Windows PowerShell + Unix shell）腳本，自動完成套件安裝、Playwright browser 下載與相依檢查。
- 完成定義：新同事 3 分鐘內可依腳本完成安裝並跑 Quickstart。

```bash
# gh issue create --title "Good first issue: 精簡一鍵安裝腳本" --body-file issue-good-first-setup.md --label "good first issue"
```

---

## Good first issue: 主要流程錯誤訊息

- 說明：`scrape_lolalytics.py` 目前僅在輸出為空時印出 `[warn]` 與 `[error]`，遇到 Cloudflare 或 selector 失敗不易診斷。請在 `_goto_build_page`、`_parse_winning_items`、`_parse_sets_5` 等關鍵步驟加入 logging，並在失敗時回傳具體退出碼與提示。
- 完成定義：Quickstart 失敗時能指出是哪個步驟（例如 CF 驗證、找不到 Winning block），且命令結束碼非 0。

```bash
# gh issue create --title "Good first issue: 主要流程錯誤訊息" --body-file issue-good-first-logging.md --label "good first issue"
```

---

## Known limitations: Cloudflare 與站點改版

- 現況：
  - 需要安裝系統相依套件與 `ignore_https_errors=True` 才能繞過 SSL 問題。
  - Cloudflare 會要求互動驗證，`cf_shield_fix.py` 需人工啟動。
  - Lolalytics DOM 變動後 selector 易失效，`data/raw/*` dump 需定期檢查。
- 緩解建議：降低請求頻率、遇到驗證時改用 bootstrap 流程、維護 selector 清單。

```bash
# gh issue create --title "Known limitations: Cloudflare 與站點改版" --body-file issue-known-limitations.md --label "known issue"
```

