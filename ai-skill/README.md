# AI 協作證據包（StatSoft 期末專題：野場排球分隊）

對應課程指引的三項 AI 要求：

| 要求 | 檔案 | 狀態 |
|---|---|---|
| ≥1 個 AI skill（SKILL.md）、跑 ≥2 次含邊界案例 | `skills/balance-teams/SKILL.md`、`docs/skill-run-log.md` | 已跑 5 次（正常 2、邊界 2、手算檢核 1），等 Iris 審查判定 |
| AI agent workflow（Define→Plan→Review→Code→Test→Reflect） | `docs/agent-workflow-template.md` | 範本＋本技能的例子，Review 與 Reflect 待 Iris 填 |
| AI 使用揭露／協作時間軸 | `../ai-log/00_總時間軸.md`（跨工作線總表）與 `../ai-log/` 各工作線紀錄 | 從 2026-11-26 開始，持續更新 |
| Vibe coding 迭代紀錄 | `docs/vibe-coding-log-template.md` | 範本，等做網站或 Python 原型時填 |

快速重跑（只需 Python 3）：

```bash
cd skills/balance-teams
python scripts/balance_teams.py examples/normal_roster.csv --teams 5 --out runs/run1_normal --seed 115
python scripts/balance_teams.py examples/edge_dirty_roster.csv --teams 2 --out runs/run2_edge_dirty
python scripts/balance_teams.py examples/small_8_players.csv --teams 2 --out runs/run3_small_bruteforce --verify-bruteforce
python scripts/balance_teams.py examples/normal_roster.csv --teams 7 --out runs/run4_edge_too_few_players
```

放進 GitHub repo 時，建議把 `skills/balance-teams/` 複製到 `.claude/skills/balance-teams/`，`docs/` 下的檔案放到組別的 `docs/`。所有名單都是模擬資料。
