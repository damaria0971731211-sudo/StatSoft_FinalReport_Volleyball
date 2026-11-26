# 2026-11-26 書面報告初稿工作線

| 欄位 | 內容 |
|---|---|
| 工具／模型 | Claude Code 雲端工作階段（Anthropic Claude Opus 5.5），未呼叫付費 API |
| 任務 | 依指引第 11 節起草 8–12 頁書面報告（摘要、動機與問題、資料、方法、流程、結果、測試與 AI 驗證、限制、分工、參考資料） |
| 輸入 | 指引 PDF v1.1；提案（Claude Doc）；r-rating-model、python-team-split、volley-sim、ai-skill、ai-log、review/ 的現有結果；提案工作線通知的鎖定門檻與確認性種子（20261218000+k） |
| 產出 | `report/Gxx_Report.docx`、`report/Gxx_Report.pdf`（含封面 11 頁，正文約 9 頁）、`report/src/build_report.py`（可重跑產生 docx）、`report/figures/`（圖 1 流程圖為新畫，其餘複製自各工作線） |

## AI 做的判斷（請 Iris 審查）

- 主問題與門檻照提案，現有數字一律標「探索性」。分隊均衡度 −0.22（CI −0.30～−0.14）依事先規則判為「方向一致但未達門檻」。
- D3 平台資料上階層模型沒有比較好，照實寫在 5.2 節（缺口檢查要求）。
- 型一／型二的定義採 Q5 程式（H0＝未達標，誤放＝型一），和提案第 3 節表格相反，已在報告附錄列為待 Iris 決定。
- 「自報與真實實力相關 0.67」在 volley-sim README 沒寫是 Pearson 還是 Spearman，標為待確認。
- 沒有代寫任何個人判斷與反思，全部以【待 Iris 填】標示。

| 人工決策點 | Iris 填 |
|---|---|
| 是否接受報告架構與結果寫法 | ＿＿ |
| 型一／型二定義 | 已統一為誤放＝型一（11/26） |
