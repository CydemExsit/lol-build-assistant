# lol-build-assistant

以 Playwright 抓取 LoLalytics 單英雄資料，先完成「一條龍」最小可用流程（MVP）。

## MVP 範圍
- 目標：單一英雄 + 單一模式（示例：`lux / ARAM`）
- 產出：`data/processed/sets.csv`、`data/processed/winning.csv`
- 來源：LoLalytics（受 Cloudflare 保護，需先通過一次驗證）
- 已附 `demo/` 小樣本輸出供瀏覽

## 快速開始
```bash
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m playwright install --with-deps
cp env.example .env

# 1) 先通過 Cloudflare（只需一次）
python cf_shield_fix.py bootstrap --hero lux --lang zh_tw --mode aram --tier d2_plus --patch 7 --state data/cf_state.json
# 依指示在跳出的視窗內完成驗證，完成後按 Enter 儲存 cookie

# 2) 測試 cookie 有效
python cf_shield_fix.py test --hero lux --lang zh_tw --mode aram --tier d2_plus --patch 7 --state data/cf_state.json

# 3) 跑單一流程（產出 sets.csv / winning.csv）
python run_pipeline.py --hero lux --lang zh_tw --mode aram --tier d2_plus --patch 7 --state data/cf_state.json --out data/processed
