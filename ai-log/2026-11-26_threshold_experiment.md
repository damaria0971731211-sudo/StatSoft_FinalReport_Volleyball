# 2026-11-26 報名門檻（第 5 題）與分隊實驗設計（第 6 題）工作線

| 欄位 | 內容 |
|---|---|
| 工具／模型 | Claude Code 雲端工作階段（Anthropic Claude Opus 5.5），未呼叫付費 API |
| 起因 | Iris：「跟統計的關聯好像就顯現不出來…希望你可以給我一些想法」→ 協調者提出「6 個問題 6 種統計方法」，本工作線負責第 5、6 題 |
| 輸入 | `python-team-split/`（既有分隊原型與 1000 晚模擬）、`r-rating-model/output/ratings_volley_sim.csv`、`volley-sim/truth/players_truth.csv` |
| 產出 | `volleysplit/threshold.py`、`volleysplit/design.py`、`analysis/q5_q6.py`、`tests/test_threshold_design.py`、`figures/q5_*.png q6_*.png`、`results/threshold.json design.json`、`docs/Q5_Q6_結果說明.md` |

## 流程階段

| 階段 | 內容 | 人工決策點（Iris 填） |
|---|---|---|
| Define | Q5：把誤放／誤擋定義成型一／型二錯誤（H0＝未達標）。Q6：真實野場一晚只能用一種方法 → 以「晚」為單位的兩獨立樣本實驗 | 誤放當型一是否合理：＿＿ |
| Plan | Q5 用常態共軛貝氏更新（自報當先驗）；每局資訊量從 R 模型標準誤校準（1/se² ≈ 1.43 + 0.044×局數）。Q6 用現有 sim_runs.csv 算效果大小，公式＋模擬檢定力，加 A/A 測試 | ＿＿ |
| Code | 兩個模組＋分析腳本 | ＿＿ |
| Test | 18 項新測試（手算混淆表、AUC 極端值、ROC 面積＝AUC、後驗校準、教科書樣本數 63、H0 下檢定力＝α、ANCOVA 增益、ICC），全套 60 項通過 | ＿＿ |
| Review（AI 自己發現的問題） | ① 小樣本時共變量共線，OLS 反矩陣出錯 → 改用偽逆並以秩算自由度。② 第一次 A/A 只跑評分最佳化，ICC 0.01、膨脹不明顯；改成兩種方法都跑，發現隨機分隊 ICC 0.05、假陽性 7~8%，如實報告兩者。③ 一項 ANCOVA 測試門檻設太嚴，檢查後是測試參數問題（效果太小），不是程式錯誤，調大效果 | ＿＿ |
| Reflect | 限制見 `docs/Q5_Q6_結果說明.md` 最後一節 | ＿＿ |

## 需人工查核

- 「誤放成本 = 2 倍誤擋」只是示範，你覺得實際比例多少？
- 三段式門檻 0.2／0.8、試打名額「每隊最多一個」是建議，不是統計結論。
- 每組 512 晚的結論依賴模擬的比賽隨機性；你在野場的經驗是否覺得 15/20 分局真的這麼隨機？
