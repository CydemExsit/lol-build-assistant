# LoL Build Assistant

> LoLalytics → normalized CSVs (single-champion MVP)

- **MVP 範圍：** 單一英雄（Varus）搭配 ARAM 模式，實際產出 `data/processed/varus_aram_winning.csv` 與 `data/processed/varus_aram_sets.csv`。
- **Quickstart：**
  ```bash
  python src/scrape_lolalytics.py --hero varus --mode aram --tier d2_plus --patch 7 --lang zh_tw --winning_out data/processed/varus_aram_winning.csv --sets_out data/processed/varus_aram_sets.csv
  ```
- **Demo：** [`demo/winning.sample.csv`](demo/winning.sample.csv) · [`demo/sets.sample.csv`](demo/sets.sample.csv)
- **限制：** 目前缺乏重試與節流機制，若 LoLalytics 站點回應為空或速度過慢請稍後重跑。
- **Roadmap / Issues：** 請依 [`ISSUES_TODO.md`](ISSUES_TODO.md) 建立對應 GitHub Issues（v0.1、v0.2、Good first issue ×2、Known limitations）。

## 需求與環境

1. Python 3.11+。
2. 安裝套件：
   ```bash
   pip install -r requirements.txt
   pip install playwright
   playwright install chromium
   ```
3. 若缺少 Playwright 執行環境，參考命令輸出安裝對應系統套件（本機範例：`apt-get install libatk1.0-0t64 ...`）。

可選：複製 `env.example` 為 `.env` 後修改，命令列參數會自動讀取 `LOL_*` 變數。

## 執行說明

1. 準備 `.env` 或以指令直接帶入英雄與輸出路徑。
2. 執行 Quickstart 中的命令，完成後 `data/processed/` 會新增 `varus_aram_winning.csv` 與 `varus_aram_sets.csv`。
3. 若命令執行過程中出現逾時或空結果，請確認網路可達後再重跑，或降低連續請求次數。

## 產出格式

- `*_winning.csv`：`img,name,win_rate,pick_rate,sample_size`，勝率/選用率已正規化為 0~1。
- `*_sets.csv`：`items,items_img,set_win_rate,set_pick_rate,set_sample_size`，`items` 為 `|` 分隔的繁中裝備名。
- 範例截圖請參考 `demo/` 目錄。

## 限制與下一步

- 站點 DOM 變動或回傳空資料時需人工調查，詳見 `ISSUES_TODO.md` 的 Known limitations 草稿。
- 強化錯誤訊息、批次節流與安裝腳本等規劃詳見 `ISSUES_TODO.md` 內的 Roadmap/Good first issue 草稿。
