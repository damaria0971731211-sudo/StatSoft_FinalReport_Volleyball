# volleysplit：政大野場排球報名分隊原型（Python）

> 所有名單與比賽都是**模擬資料**，沒有任何真實人物；代號 P01、P02… 是虛構的。

## 研究問題

用實力評分分隊，是否比**隨機分隊**或**自報程度蛇形分隊**更勢均力敵？等待（上場局數）是否也更公平？

## 功能

| 模組 | 做什麼 |
|---|---|
| `registration.py` | 報名（晚餐場／消夜場）、名額與候補遞補、自報程度 1~5、位置；**收縮估計**把自報程度和 R 模型評分合成一個分數；依分位數分 A/B/C 級 |
| `teaming.py` | 三種分隊方法：`隨機`、`自報程度蛇形`、`評分最佳化`（蛇形起點＋兩兩交換局部搜尋，目標是縮小最強與最弱隊的強度差，並盡量讓每隊有舉球員） |
| `simulate.py` | 模擬報名者、逐球模擬一局（需領先 2 分）、贏球留場制依時間模擬一個時段；蒙地卡羅比較三種方法，附 bootstrap 95% 信賴區間與配對符號置換檢定 |
| `crosscheck.py` | 把三種方法丟進另一套模擬引擎 `volley-sim`（逐球攻防＋搭檔默契）再比一次，確認結論不是本套件簡化模型造成的 |
| `web/split.html` | 用 Pyodide 在瀏覽器裡直接跑分隊，可放上 GitHub Pages |

核心程式只用 Python 標準函式庫（方便 Pyodide），`crosscheck.py` 需要 numpy、pandas，測試需要 pytest。

## 怎麼跑

```bash
pip install -r requirements.txt
python -m pytest -q                                   # 42 項測試
python -m volleysplit split data/sample_signups.csv --ratings data/sample_ratings.csv
python -m volleysplit demo --players 28 --seed 1      # 一晚示範 → results/demo_night.json
python -m volleysplit simulate --reps 1000            # 主要結果 → results/summary.json、sim_runs.csv
python -m volleysplit scenarios --reps 200            # 敏感度分析 → results/scenarios.json
python -m volleysplit.crosscheck --sim ../volley-sim/volley_sim.py --reps 500
```

同一個 seed 結果完全相同。三種方法在同一晚用**同一份名單、同一串比賽亂數**（共同隨機數），所以差異可以做配對比較。

## 接 R 模型

R 模型輸出 `code,rating,n_games` 的 CSV，用 `--ratings` 讀進來。綜合分數

  綜合分數 = w × 模型評分 + (1 − w) × 自報程度換算值，w = n_games / (n_games + 8)

場數少的人主要看自報程度，場數多的人主要看模型。8 可理解為「自報程度值 8 場比賽的資訊」，報告裡可以做敏感度分析。

## 模擬假設

- 真實實力 ~ N(0,1)；自報程度 = 實力 + 高估 0.2 + N(0, 0.7²)，四捨五入成 1~5 級。
- 模型評分 = 實力 + N(0, sd²)，sd = 0.8 / √(1 + 場數/4)，代表場數越多估得越準（之後換成 R 模型輸出）。
- 每球 A 隊得分機率 = logistic(0.5 × 強度差)；隊伍強度 = 平均實力 − 0.15 × (6 − 人數)。
- 一晚 20~36 人、4~6 隊、每隊 4~6 人。
- 野場規則與 volley-sim 一致：晚餐場 18:00–19:30、消夜場 22:00–23:30（各 90 分鐘）、一面場地；4 隊以下打 20 分、5~6 隊打 15 分，時間不夠改打 15 分；贏球留場、最多連續留 2 局；每球約 29 秒。

## 主要結果（1000 晚，seed 2026）

| 指標 | 隨機 | 自報程度蛇形 | 評分最佳化 |
|---|---|---|---|
| 平均分差 | 5.53 | 5.05 | **4.83** |
| 接近比賽比例（分差≤3） | 33.6% | 38.1% | **41.1%** |
| 懸殊比賽比例（分差≥10） | 12.7% | 8.6% | **7.2%** |
| 最強與最弱隊真實強度差 | 1.00 | 0.65 | **0.37** |
| 每人上場局數標準差 | 0.67 | 0.66 | **0.65** |

配對差（評分最佳化 − 自報程度蛇形）：平均分差 −0.22 分（95% CI −0.30～−0.14，p < 0.001）；接近比賽多 2.9 個百分點（95% CI 1.5～4.4）。
評分最佳化 − 隨機：平均分差 −0.70 分（95% CI −0.79～−0.60）；接近比賽多 7.5 個百分點。

**交叉驗證（volley-sim 引擎，500 晚，含搭檔默契）**方向一致：平均分差 隨機 5.62、蛇形 5.02、評分最佳化 4.78；評分最佳化 − 蛇形 = −0.24（95% CI −0.37～−0.10）。

**敏感度分析**（`results/scenarios.json`）：自報越不準，蛇形就越接近隨機（自報雜訊 1.2 時平均分差 5.21 vs 隨機 5.42）；評分最佳化在 9 種情境都最好，但評分誤差變大時優勢縮小。

**解讀上的限制**：平衡分隊把最強與最弱隊的強度差縮小一半以上，但野場打 15 或 20 分、比賽隨機性大，平均分差只少約 0.2～0.7 分；上場公平性的改善很小。這些都依賴模擬假設，參數來源見 volley-sim 的 README。

## 檔案

```
volleysplit/   套件原始碼
tests/         pytest 測試
data/          範例報名表（40 人）與範例評分（24 人）
results/       模擬輸出（JSON/CSV，網站直接讀）
web/split.html 瀏覽器試用頁
```

## 放上 GitHub Pages

把 `volleysplit/`、`data/`、`web/` 放在網站根目錄下同一層，開 `web/split.html` 即可（頁面會讀 `../volleysplit/*.py` 和 `../data/sample_signups.csv`）。Pyodide 從 jsDelivr 載入，第一次約需數秒。結果圖表可以直接讀 `results/summary.json`、`results/scenarios.json`。
