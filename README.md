# LoL Build Assistant

英雄聯盟 ARAM 出裝助手。程式會透過 Riot 本機 Live Client Data API 辨識目前對局的十位英雄、敵我隊伍與自己的英雄，再依 LoLalytics ARAM 統計、敵方陣容及個人偏好產生推薦。

目前推薦規則：

- 預設使用 `aram`、`gold_plus` 與最近 7 天資料；樣本不足時依序擴大到 14、30 天。
- 五件非鞋成裝必須是 LoLalytics `Actually Built Sets: 5` 真實出現過的完整套裝。
- 鞋子獨立列出，只呈現勝率、選取率與場次。
- 綜合相對勝率、選取率、樣本量、敵方傷害類型與英雄路線，提供最多三種方向。
- 套用 [user_preferences.json](data/ref/user_preferences.json) 中的喜好、防禦傾向、厭惡裝備與女神之淚提醒。
- 使用 Riot Data Dragon 的繁體中文物品名稱與圖示。

## 安裝

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m playwright install chromium
python scripts/build_items_map.py --lang zh_TW
```

`items_map.csv` 已包含在專案內；只有遊戲版本更新或物品名稱需要同步時，才需要重新執行最後一行。

## Web 介面

```powershell
python -m src.main serve
```

開啟 [http://127.0.0.1:8765](http://127.0.0.1:8765)。

- `載入選取 Snapshot`：用下拉選單中已保存的對局重新計算，不需要遊戲仍在進行。
- `抓取目前 Live 對局`：即時讀取 `https://127.0.0.1:2999/liveclientdata/*`、保存 Snapshot，並產生推薦；必須已進入 loading 畫面或遊戲內。
- 推薦路線可手動置頂；選擇只保存在目前瀏覽器。

執行結果會寫入：

- `data/processed/live_recommendation.json`
- `data/processed/live_recommendation.md`
- `data/raw/live_*` 對局 Snapshot
- `data/cache/` 可重建的 LoLalytics 統計快取

## CLI

直接抓取目前對局並推薦：

```powershell
python -m src.main recommend-live
```

使用既有 Snapshot：

```powershell
python -m src.main recommend-live --snapshot data/raw/live_YYYYMMDD_HHMMSS
```

只保存目前對局：

```powershell
python -m src.main snapshot-live
```

所有子命令與選項：

```powershell
python -m src.main --help
python -m src.main recommend-live --help
```

## 維護清理

預覽可清理項目，不會刪除任何檔案：

```powershell
python -m src.main cleanup
```

套用預設策略：

```powershell
python -m src.main cleanup --apply
```

預設保留最新 5 份 Snapshot、正式推薦輸出與有效 JSON 統計快取；清除舊 Snapshot、可重建 HTML、空白或舊格式快取、測試畫面、暫存輸出及 Python 快取。可自行調整保留數量：

```powershell
python -m src.main cleanup --keep-snapshots 10 --apply
```

清理指令不會碰觸 `.venv`、`.git`、物品表、個人偏好或正式程式碼。

## 測試

```powershell
python -B -m pytest -q -p no:cacheprovider
node --check web/app.js
```

## Riot 合規邊界

本專案只讀取 Riot 官方本機 Live Client Data API 在當前遊戲中可見的資料，以及 LoLalytics 聚合統計與 Riot Data Dragon 靜態資料。它不分析敵方玩家的個人帳號或歷史戰績、不讀取遊戲記憶體、不注入程序、不繞過 Vanguard，也不自動操作遊戲。

Live Client Data API 在未進入對局時無法連線是正常情況；既有 Snapshot 仍可離線重新載入，缺少的 LoLalytics 快取則需要網路。
