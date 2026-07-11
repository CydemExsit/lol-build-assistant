# LoL Build Assistant

英雄聯盟 ARAM 出裝助手。進入 loading 畫面或遊戲內後，程式會透過 Riot 本機 Live Client Data API 讀取本場 10 個英雄、敵我隊伍與自己的英雄，再用 LoLalytics ARAM 統計推薦出裝。

目前推薦規則的最低限制：

- 模式固定預設為 `aram`
- LoLalytics tier 預設為 `gold_plus`，避免 `all` 混入太多低品質資料
- 先用 `patch=7`，若 `Champions Analysed` 低於門檻會 fallback 到 `14`、`30`
- 推薦的五件非鞋成裝必須完整出現在 LoLalytics `Actually Built Sets: 5`
- `Actually Built Sets` 優先直接讀取 LoLalytics `build-itemset` JSON；只有端點失敗時才使用網頁掃描備援
- 主推薦候選的套裝選取率至少為 `0.03%`，門檻會隨英雄總樣本量縮放；小樣本仍會經過勝率收縮與場次權重，避免偶然高勝率霸榜
- 鞋子獨立列出，不算在五件成裝內
- 多路線英雄會盡量列出不同方向，例如 Varus 的穿甲 Poke 與命中特效 AD；若 7 日視窗只有單一路線，才會用 14/30 日視窗補缺少的路線
- 物品顯示優先使用 Riot Data Dragon 的繁體中文名稱

個人出裝偏好位於 `data/ref/user_preferences.json`。可直接調整指定物品的正負分、極端傷害陣容門檻、純坦裝加分，以及射手純 AP 路線扣分；含女神之淚升級裝的路線會顯示開場提醒。

## Setup

```powershell
pip install -r requirements.txt
playwright install chromium
python scripts/build_items_map.py --lang zh_TW --out data/ref/items_map.csv
```

## Web UI

啟動本地介面：

```powershell
python -m src.main serve
```

打開：

```text
http://127.0.0.1:8765
```

介面可以：

- 顯示目前推薦結果
- 任一五件套都可按「置頂」移到三種路線最上方，再按「取消置頂」即可恢復演算法排序
- 「載入選取 Snapshot」：從既有 `data/raw/live_*` 舊資料重新產生推薦，不需要遊戲還開著
- 「抓取目前 Live 對局」：在你已進入 loading 畫面或遊戲內時，重新讀取 `https://127.0.0.1:2999/liveclientdata/*`

## CLI

在遊戲 loading 畫面或遊戲內直接抓 live data 並產生推薦：

```powershell
python -m src.main recommend-live
```

使用既有 snapshot：

```powershell
python -m src.main recommend-live --snapshot data/raw/live_20260710_015228
```

輸出：

- `data/processed/live_recommendation.json`
- `data/processed/live_recommendation.md`

如果沒有進入 loading 畫面或遊戲內，`https://127.0.0.1:2999/liveclientdata/*` 通常會連不上；只在 client、lobby、選角時不一定能取得資料。

## Riot Compliance Boundary

只使用：

- Riot 本機 Live Client Data API 的遊戲內可見資料
- LoLalytics aggregate build statistics
- Riot Data Dragon 公開物品資料

不使用：

- 隱藏玩家識別
- 敵方玩家個人帳號、牌位、勝率或歷史戰績分析
- 遊戲自動操作、記憶體讀取、Vanguard 繞過

## Legacy CSV Pipeline

舊 PoC 的 CSV 指令仍保留，但目前不建議作為主要流程：

```powershell
python src/scrape_lolalytics.py --hero varus --mode aram --tier d2_plus --patch 7 --lang zh_tw --winning_out data/processed/varus_aram_winning.csv --sets_out data/processed/varus_aram_sets.csv
python -m src.main --winning data/processed/varus_aram_winning.csv --sets data/processed/varus_aram_sets.csv --out outputs/varus_aram_7d.json --explain
```

現在請優先使用：

```powershell
python -m src.main serve
```

或：

```powershell
python -m src.main recommend-live
```

## Tests

```powershell
pytest -q
python -m compileall src tests
```
