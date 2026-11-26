# 分隊報告：STOP

- 名單：`examples/edge_dirty_roster.csv`，資料 9 列，通過 ID 檢查 8 人，要求 2 隊，seed=115

## 錯誤（已停止，未產生分隊）
- 第 5 列：player_id P02 與第 3 列重複
- 第 6 列（P05）：level 空白且沒有 rating
- 第 7 列（P06）：level=7 超出 1–5
- 第 8 列（P07）：level='三' 不是整數

## 警告
- 第 9 列（P08）：position=SETTER 不認得，當作 ANY
