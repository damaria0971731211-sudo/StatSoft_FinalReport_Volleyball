# 野場排球球員實力評分模型（R）

StatSoft 期末專題的 **R 實質任務**：從「每局兩隊名單＋比分」估計每位球員的實力，附 95% 不確定區間；自報程度當先驗；搭檔默契用收縮估計。完整說明、公式與結果見 `report.html`（由 `report.Rmd` 產生）。

> 野場資料全部是模擬的，沒有真實人物。

## 檔案

| 路徑 | 內容 |
|---|---|
| `R/rating_model.R` | 模型本體：`fit_rating_model()`、`predict_set()`、`set_win_prob()` |
| `R/simulate.R` | 已知真值的模擬資料產生器（驗證用） |
| `R/read_volley_sim.R` | 讀取 Python 模擬器 `volley-sim/` 的輸出並轉成模型格式 |
| `analysis/01_bundesliga.R` | 公開資料：德甲排球 6,330 局比分的樣本外預測驗證 |
| `analysis/02_simulation_study.R` | 模擬研究：估回真值、涵蓋率、需要幾晚資料、敏感度 |
| `analysis/03_volley_sim.R` | 套用到 Python 模擬資料，輸出 `output/ratings_volley_sim.csv` |
| `report.Rmd` / `report.html` | 單館版繁中報告（含圖） |
| `R/platform_model.R` | 跨球館版：球館隨機效果的階層模型 `fit_platform_model()`、每局線上更新 `online_update()` / `online_run()` |
| `R/simulate_platform.R`、`R/read_platform_sim.R` | 多球館模擬、讀取 Python 跨球館模擬資料 |
| `analysis/04_platform_venues.R` | 橋接球員比例 vs 跨館比較能力；線上 vs 批次 |
| `analysis/05_cold_start.R` | 冷啟動：新人區間收斂、自報錯誤修正速度 |
| `analysis/06_platform_python.R` | 套用 Python 跨球館資料；自報偏誤 Bland-Altman 與誤差迴歸 |
| `platform_report.Rmd` / `platform_report.html` | 平台版繁中報告 |
| `figures/` | 報告用圖（PNG） |
| `data/public/` | 公開資料（CC0，見下方） |
| `results/` | 各分析的結果（.rds） |
| `output/` | 給 Python 分隊原型用的實力估計 CSV |

## 最短用法

```r
source("R/rating_model.R")
games <- read.csv("my_games.csv")          # date, session, game_id, team_a, team_b, score_a, score_b
players <- read.csv("my_players.csv")      # player, level（自報 1–5，可省略）
fit <- fit_rating_model(games, players)    # 自動估 sigma, tau
fit                                        # 摘要
head(fit$ratings)                          # 每人 theta 與 95% 區間
predict_set(fit, c("P01","P02","P03","P04","P05"), c("P06","P07","P08","P09","P10"))
```

`team_a` / `team_b` 是以 `;` 分隔的球員代號。

## 重現

```bash
Rscript analysis/01_bundesliga.R
R_REPS=200 Rscript analysis/02_simulation_study.R  # 4 核心約 25 分鐘
VOLLEY_SIM_DIR=/mnt/project-files/volley-sim Rscript analysis/03_volley_sim.R
Rscript -e 'rmarkdown::render("report.Rmd")'
# 平台版
R_REPS=100 Rscript analysis/04_platform_venues.R   # 約 7 分鐘
N_NEW=400 Rscript analysis/05_cold_start.R          # 約 20 秒
# 06 需要 Python 跨館資料：python platform_sim.py --cross 0 / 0.3 --out ...，路徑用 PLAT_CROSS0 / PLAT_CROSS10 / PLAT_CROSS30 指定
Rscript analysis/06_platform_python.R
Rscript -e 'rmarkdown::render("platform_report.Rmd")'
```

需要 R ≥ 4.1 與套件 `Matrix`、`ggplot2`、`rmarkdown`、`knitr`；圖中文字型為 WenQuanYi Zen Hei（其他系統可在 `report.Rmd` 開頭改 `FONT`）。`sessionInfo.txt` 記錄了開發時的版本。

## 資料來源與授權

- **德甲排球每局比分 2013/14–2018/19**：R 套件 [volleystat](https://github.com/bozhinvi/volleystat)（commit c385865），授權 CC0；原始資料來自 volleyball-bundesliga.de。檔案：`data/public/sets.rda`、`matches.rda`，整理後為 `bundesliga_sets.csv`。
- **DataVolley 範例比賽**：R 套件 [datavolley](https://github.com/openvolley/datavolley)，MIT 授權；由 Python 模擬器用來設定技術統計基準。
