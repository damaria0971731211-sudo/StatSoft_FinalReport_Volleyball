# 野場排球實力評分與分隊（StatSoft 期末專題）

115-1 程式設計與統計軟體（國立政治大學統計學系）期末專題 · 作者：Iris（一人一組）· 組別：Gxx（待公布）

**成果網站**：<https://damaria0971731211-sudo.github.io/StatSoft_FinalReport_Volleyball/>

## 這個專題在做什麼

政大體育館的排球野場（晚餐場、消夜場）常常臨時湊隊，強弱懸殊、比賽一面倒。本專題用「每局名單＋比分」估計每位球員的實力，再比較三種分隊方法（隨機、依自報程度蛇形、依實力評分最佳化）哪一種讓比賽更勢均力敵；並延伸到多家球館共用評分的平台情境。

> **所有野場與球館資料都是模擬的，沒有真實人物。** 公開資料只用來設定模擬參數與驗證模型。

主要結果（模擬 1,000 晚）：分差 3 分以內的接近比賽，隨機分隊 33.6%、自報程度蛇形 38.1%、評分最佳化 41.1%。詳見網站「分隊結果」分頁。

## 資料夾

| 資料夾 | 語言 | 內容 |
|---|---|---|
| `index.htm`、`assets/` | HTML/JS | 成果網站（GitHub Pages 直接讀根目錄） |
| `volley-sim/` | Python | 模擬資料產生器：單館野場 `volley_sim.py`、4 館平台 `platform_sim.py` |
| `r-rating-model/` | R | 逐球 Bradley–Terry 實力評分模型、三層驗證、平台版報告 |
| `python-team-split/` | Python | 報名、分隊、模擬比較、報名門檻與實驗設計（第 5、6 題）、瀏覽器分隊工具 `web/split.html` |
| `ai-skill/` | Python | AI skill `balance-teams` 與 5 次執行紀錄 |
| `ai-log/` | — | AI 協作時間軸與各工作線紀錄 |

每個資料夾都有自己的 README，寫明輸入、輸出與欄位。

## 環境

- **Python 3.13**，套件見 `requirements.txt`（已鎖版本）
- **R 4.3.3**，套件 `Matrix`、`ggplot2`、`rmarkdown`、`knitr`；版本見 `r-rating-model/renv.lock` 與 `r-rating-model/sessionInfo.txt`

```bash
python -m venv .venv && source .venv/bin/activate   # Windows：.venv\Scripts\activate
pip install -r requirements.txt
```

## 重跑順序

所有隨機過程都有固定種子，同一環境下輸出相同。

| 步驟 | 指令（在 repo 根目錄執行） | 輸出 | 時間 |
|---|---|---|---|
| 1 單館模擬資料 | `cd volley-sim && python volley_sim.py && cd ..` | `volley-sim/data/`、`truth/` | 數秒 |
| 2 平台模擬資料 | `cd volley-sim && python platform_sim.py && cd ..` | `volley-sim/platform/` | 約 12 秒 |
| 3 R 實力評分 | `cd r-rating-model && VOLLEY_SIM_DIR=../volley-sim Rscript analysis/03_volley_sim.R && cd ..` | `r-rating-model/output/ratings_volley_sim.csv` | 約 10 秒 |
| 4 分隊方法比較 | `cd python-team-split && python -m volleysplit simulate --reps 1000 && cd ..` | `python-team-split/results/summary.json`（實測與 repo 內相同） | 約 20 秒 |
| 5 測試 | `cd python-team-split && python -m pytest -q && cd ..` | 60 項通過 | 約 7 秒 |

其他分析（德甲樣本外驗證、模擬研究、平台版、第 5、6 題）的指令見各資料夾 README。

**預期輸出與容差**：步驟 1、2 的 CSV 應與 `SHA256SUMS.txt` 的雜湊完全相同（2026-11-26 已在乾淨環境驗證）。模擬比較的比例類指標，不同平台的浮點差異應小於 0.001。

## 資料來源與授權

| 資料 | 來源 | 授權 | 用途 |
|---|---|---|---|
| D1 DataVolley 範例比賽 | R 套件 [datavolley](https://github.com/openvolley/datavolley) | MIT | 校準模擬器的攻擊、發球基準 |
| D2 德甲排球每局比分 2013/14–2018/19 | R 套件 [volleystat](https://github.com/bozhinvi/volleystat) | CC0 | 實力模型樣本外驗證、借參數 |
| D3 模擬野場與 4 館平台資料 | 本專題 `volley-sim/` 產生 | 與本 repo 相同 | 回答研究問題（真值已知） |

網站使用 [Pyodide](https://pyodide.org/)（MPL-2.0）與 Noto Sans TC 字型（SIL OFL）。

## AI 使用

本專題使用 Claude（claude.ai 專案）協助規劃、寫程式與整理文件；每項建議的採納或拒絕理由記錄在 `ai-log/00_階段大綱.md`。AI skill 見 `ai-skill/skills/balance-teams/SKILL.md`。

## 已知問題

- 組別代號、教師網頁樣版尚未公布，網站暫用 Gxx。
- 主問題的確認性試驗（種子 20261218000 + k）尚未執行，網站目前列的是預試結果。
- 報告、簡報、影片尚未完成。
- 交件版本將打 tag `final-v1.0`（2026-12-18）。
