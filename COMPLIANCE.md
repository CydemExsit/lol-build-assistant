# Riot 合規資料界線

本專案採用 `static_pregame_v1` 模式。每場只在 loading 畫面或 Live Client Data API 可用後產生一次靜態方案，產出隨即凍結，局內不重新排序、不新增提示，也不依即時狀態改動內容。

## 可使用資料

- 本場畫面可見的英雄、敵我隊伍與自己的英雄。
- LoLalytics ARAM 聚合統計，不查詢或分析任何玩家個人資料。
- Riot Data Dragon 的靜態英雄與裝備資料。
- 已完成之過往方案的本機手動回饋。

## 禁止進入推薦的資料

- Riot ID、召喚師名稱、PUUID 或對手個人戰績。
- 目前金錢、持有裝備、比分、事件、冷卻時間或即時位置。
- 任何讀取記憶體、程序注入、自動操作遊戲或繞過 Vanguard 的行為。
- 任何局內重新評分、即時指揮或替玩家做出單一決策的提示。

背景偵測可能暫時讀取 `gameTime` 來區分新舊對局，但它不會寫入 Snapshot、推薦或歷史資料，也不參與任何路線評分。

## 實作保護

- Snapshot 只保留靜態白名單欄位，玩家識別與局內動態欄位會在寫入磁碟前移除。
- 所有 CLI、API 與背景偵測入口都必須經過同一個 `RecommendationService`。
- 輸出必須具有 `session.scope=static_pregame_v1`、`frozen=true` 與 `updates_during_match=false`。
- 合規驗證器會拒絕含有私人或局內動態欄位的推薦 JSON。
- UI 同時提供多條靜態路線，使用者自行選擇；不宣稱單一唯一解。

依據：[League of Legends policy](https://developer.riotgames.com/docs/lol) 與 [Riot Games API Terms and Policies](https://developer.riotgames.com/policies/general)。若要向其他玩家公開或散布產品，仍須依 Riot 當時政策完成產品註冊與審核；本專案本身不代表 Riot 核准。

LoL Build Assistant isn't endorsed by Riot Games and doesn't reflect the views or opinions of Riot Games or anyone officially involved in producing or managing Riot Games properties. Riot Games, and all associated properties are trademarks or registered trademarks of Riot Games, Inc.
