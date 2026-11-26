# 排球野場模擬資料（volley-sim）

> **這是合成資料，不是真實野場紀錄。** 依課程指引第 05 節，合成資料須標示生成規則與用途；本頁就是那份說明。

## 用途

研究問題：用比賽結果估出的球員實力分隊，是否比隨機分隊或依自報程度分隊更勢均力敵？
真實的野場名單與比分拿不到，所以用模擬產生「已知答案」的資料：每位虛擬球員有真實實力、自報程度、搭檔默契。模型估得準不準、分隊方法好不好，都可以拿 `truth/` 的真值來檢驗。

## 怎麼跑

```bash
pip install numpy pandas
python volley_sim.py                    # 預設：種子 20261126，6 週、週一到週四、晚餐場＋消夜場
python volley_sim.py --seed 7 --out run_seed7
python volley_sim.py --method random    # 所有時段都隨機分隊
python volley_sim.py --config my.json   # 用 JSON 覆寫任何參數，例如 {"beta_skill": 0.5}
```

同一個種子產生的 CSV 完全相同（已驗證）。預設資料集：48 個時段、246 局、77 位球員出場，執行約 2 秒。

## 模擬怎麼運作

1. **球員**：80 人，真實實力 θ ~ N(0, 1)；自報程度 1~5 級 = θ 加上高估 0.3 和誤差，再切成 5 級；主要位置依比例抽。每人有出席機率和偏好時段。
2. **默契**：10% 的兩兩組合有非零默契 ~ N(0, 0.4)。同隊時默契加進團隊實力。
3. **每個時段**：抽出 16~36 人出席，分成 4~6 隊。分隊方法每晚抽一種：自報程度蛇形選秀（60%）或隨機（40%），記錄在 `team_method`。
4. **輪替**：一面場地，贏球留場、輸球排到隊尾，贏球最多連留 2 局。時間不夠打 25 分就改打 15 分。
5. **每一局逐球模擬**：發球（直接得分／失誤／進入來回），接著雙方輪流攻擊，每次攻擊結果為得分、失誤、被攔或繼續。機率以公開比賽的基準值為中心，再依攻擊者實力和雙方團隊實力差調整。少一人（相對 6 人）團隊實力扣 0.15。

## 參數來源

| 參數 | 值 | 來源 |
|---|---|---|
| 發球直接得分率、發球失誤率 | 0.141、0.141 | DataVolley 公開範例比賽 |
| 攻擊得分率、失誤率、被攔率 | 0.290、0.071、0.043 | 同上 |
| 每球（含死球時間）秒數 | 29 秒 | 同上，相鄰兩分間隔中位數 |
| 接發球方得分率（檢查用） | 0.520 | 同上 |
| 實力效果、默契大小、出席率、自評偏誤、時段長度、賽制 | 見 `volley_sim.py` 的 `DEFAULT_CONFIG` | **假設**，報告中可做敏感度分析 |

公開比賽是 openvolley/datavolley R 套件附的範例檔（2015 斯洛維尼亞青年女子組決賽，127 球），用 `calibrate_from_datavolley.py` 重算。**限制**：只有一場、是有組織的青年比賽，野場程度差異更大，所以實力效果等參數都是假設。模擬後實際的攻擊得分率 0.30、發球得分率 0.17，與基準接近。

## 輸出檔案（資料字典）

`data/` 是分析時看得到的資料，`truth/` 是只有模擬才知道的真值，**不可當模型輸入**，只能用來驗證。

| 檔案 | 一列代表 | 欄位 |
|---|---|---|
| `data/players.csv` | 一位球員 | `player_id`（P001…）、`self_level`（1~5）、`main_position`（主攻／副攻／舉球／接應／自由／不限） |
| `data/teams.csv` | 某時段的一隊 | `session_id`、`date`、`session`（dinner／late）、`team`（A~F）、`team_method`（random／self_level）、`n_players`、`players`（空白分隔的代號） |
| `data/games.csv` | 一局 | `game_id`、`session_id`、`date`、`weekday`、`session`、`court`、`game_no`、`team_a`、`team_b`、`n_a`、`n_b`、`score_a`、`score_b`、`winner`、`margin`（分差）、`target_points`（25 或 15）、`start_time`、`end_time`、`rallies`、`team_method` |
| `data/game_players.csv` | 一局中的一位球員（長格式，模型直接用） | `game_id`、`session_id`、`date`、`session`、`player_id`、`team`、`side`（A／B）、`won`（0／1）、`points_for`、`points_against`、`margin` |
| `data/attack_stats.csv` | 一局中的一位球員 | `game_id`、`player_id`、`team`、`attempts`、`kills`、`errors`、`blocked`、`serves`、`aces`、`serve_errors` |
| `data/attendance.csv` | 某時段出席的一位球員 | `session_id`、`date`、`session`、`player_id`、`team`（等待時間可由此和 `games.csv` 算出） |
| `truth/players_truth.csv` | 一位球員 | `player_id`、`true_skill`、`attend_prob`、`prefers` |
| `truth/pair_chemistry.csv` | 一組有默契的搭檔 | `player_1`、`player_2`、`chemistry`（沒列出的組合默契為 0） |
| `truth/config.json` | 這次執行 | 全部參數、種子、版本 |

連接鍵：`game_id` 連 `games`、`game_players`、`attack_stats`；`session_id` + `team` 連 `teams`；`player_id` 連球員檔。沒有缺失值。

## 給其他程式重用

分隊原型可以直接匯入模擬引擎，用同一套規則比較分隊方法：

```python
import numpy as np, volley_sim as vs
cfg = vs.default_config(); rng = np.random.default_rng(1)
pool = vs.make_players(cfg, rng); chem = vs.make_chemistry(pool, cfg, rng)
teams = vs.form_teams(ids, 5, "rating", pool, rng, ratings=est)  # random / self_level / snake_true / rating
res = vs.simulate_game(teams[0], teams[1], pool, chem, cfg, rng)   # 回傳 score_a, score_b, stats …
```

## 預設資料的初步樣子（種子 20261126）

- 25 分局平均分差 7.4 分，分差 ≤3 的比例 0.25。
- 球員勝率和真實實力相關約 0.44，所以光看勝率會低估實力差，需要模型。
- 兩人同隊的次數中位數只有 3 局，搭檔默契估計會很不穩，建議用收縮估計（隨機效果）。

## 個資

全部是虛構代號，沒有任何真實人物。若之後加入真實紀錄，需另行告知與同意，代號對照表不放進公開 repo。
