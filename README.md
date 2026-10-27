# LoL Build Assistant

[![CI](https://github.com/CydemExsit/lol-build-assistant/actions/workflows/ci.yml/badge.svg)](https://github.com/CydemExsit/lol-build-assistant/actions/workflows/ci.yml)

英雄聯盟 ARAM 賽前出裝助手。背景服務會在 Riot 本機 Live Client Data API 出現新對局時辨識十位英雄、敵我隊伍與自己的英雄，並依 LoLalytics 聚合數據產生一次性的靜態方案；已開啟的瀏覽器介面會自動更新。

## 目前行為

- 固定 ARAM，預設 `gold_plus` 與最近 7 天；Champions Analysed 不足時才擴大資料窗。
- 新對局優先使用 6 小時內有效的 LoLalytics 快取，各份資料獨立判斷效期；只補抓缺少或過期的資料。可用 `--cache-max-age-hours` 調整，`--refresh-lolalytics` 強制更新。
- 鞋子、熱門裝備與高勝率裝備共用一次瀏覽器頁面載入；本場方案產生後仍維持凍結。
- 五件非鞋成裝必須完整出現在 LoLalytics `Actually Built Sets: 5`。
- 候選套裝以選取率百分比過濾，不用固定組數截斷完整資料。
- 鞋子獨立列出，照搬勝率、選取率與場次。
- 同時提供最多三條靜態路線、成裝順序、樣本可信度與陣容觀察。
- 敵方傷害輪廓以每名英雄的物理／魔法／真實傷害分布與輸出權重估算，極端陣容會額外評估大型防裝。
- 每條路線依第一件成裝提供自己的起手銜接；能對應時採用 LoLalytics 起手，否則使用 Data Dragon 合成樹。
- 起手銜接一律排除生命藥水、回復藥水與其他藥劑。
- 使用 Riot Data Dragon 的繁體中文裝備名稱，並自動同步靜態資料版本。
- 路線回饋只存在本機，下一場才會成為小幅個人偏好調整。
- 每場方案產生後立即凍結，局內不重新分析或改動。

## 一次性安裝

需要 Python 3.11 以上版本。自動對局偵測與登入啟動以 Windows 為主要使用環境。

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m playwright install chromium
python -m src.main sync-data --force
python -m src.main autostart install
```

完成後，Windows 登入時會在背景啟動。平時將 [http://127.0.0.1:8765](http://127.0.0.1:8765) 保持開啟即可；十人名單完整後只處理一次，方案完成時目前頁面會自動更新，不會另開視窗。

移除 Windows 登入啟動：

```powershell
python -m src.main autostart remove
```

## 瀏覽器介面

- `本場方案`：陣容、鞋子，以及各自附帶起手銜接的三條五件成裝路線。
- `歷史`：本機方案紀錄、套路回饋及手動勝敗標記。
- `資料狀態`：Data Dragon 版本、LoLalytics 快取、本機學習與合規資料界線。
- 路線右上角箭頭可在本場置頂；`適合我` / `不適合` 會影響後續對局，不會改動當前凍結方案。
- `手動資料` 保留舊 Snapshot 重算與目前對局重新抓取，供維護與除錯使用。

## 手動啟動

Windows 開始功能表若已安裝「LoL 出裝助手」捷徑，點選即可啟動背景服務並開啟網頁；服務已執行時直接沿用。可在捷徑上按右鍵，選擇「釘選到開始畫面」。

捷徑使用 `.venv\Scripts\pythonw.exe` 執行 `scripts\launch_assistant.py`。啟動失敗會顯示提示，日誌保存在 `data/runtime/assistant-stderr.log`。

啟動器會確認背景對局偵測已開啟；快速重複點擊也只會啟動一份服務。若已有僅提供網頁的 `serve` 服務，會提示先關閉該服務，避免誤以為自動偵測已就緒。

背景偵測與 UI：

```powershell
python -m src.main watch
```

預設不會開啟新瀏覽器視窗；只有明確需要時才可加上 `--auto-open`。

只開 UI、不偵測新對局：

```powershell
python -m src.main serve
```

使用既有 Snapshot 產生凍結方案：

```powershell
python -m src.main recommend-live --snapshot data/raw/live_YYYYMMDD_HHMMSS
```

## 資料與維護

- `data/raw/live_*`：已去識別化的靜態對局 Snapshot。
- `data/cache/`：可重建的 LoLalytics 統計快取。
- `data/processed/`：目前凍結方案 JSON 與 Markdown。
- `data/history/assistant.db`：本機歷史、回饋與手動勝敗。
- `data/ref/`：Data Dragon 裝備、英雄與個人偏好。
- `data/ref/champion_damage_profiles.json`：混傷、真實傷害及低輸出前排的靜態校正值。

預覽或套用儲存空間清理：

```powershell
python -m src.main cleanup
python -m src.main cleanup --apply
```

預設保留最新 5 份 Snapshot；不會刪除本機歷史、個人偏好、Data Dragon 參考表、虛擬環境或程式碼。

## 驗證

```powershell
python -B -m pytest -q
node --check web/app.js
python -B -m src.main audit
```

`audit` 會檢查凍結標記、私人/動態欄位、五件唯一非鞋成裝、Actually Built Sets 樣本與鞋子類型。

GitHub Actions 會在 Windows／Linux 與 Python 3.11／3.13 執行離線測試及 JavaScript 語法檢查。快取與頁面共用的效能測量範圍見 [效能紀錄](docs/performance.md)。

## Riot 合規

完整資料界線見 [COMPLIANCE.md](COMPLIANCE.md)。本專案只產生多個賽前靜態選項，不依局內資訊替玩家指揮決策。Riot 的政策可能更新；若要公開散布，仍須依當時規則完成產品註冊與審核。

LoL Build Assistant isn't endorsed by Riot Games and doesn't reflect the views or opinions of Riot Games or anyone officially involved in producing or managing Riot Games properties. Riot Games, and all associated properties are trademarks or registered trademarks of Riot Games, Inc.
