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

同一個種子產生的 CSV 完全相同（已驗證）。預設資料集：48 個時段、229 局、79 位球員出場，執行約 2 秒。

## 模擬怎麼運作

1. **球員**：80 人，真實實力 θ ~ N(0, 1)；自報程度 1~5 級 = θ 加上高估 0.3 和誤差，再切成 5 級；主要位置依比例抽。每人有出席機率和偏好時段。
2. **默契**：10% 的兩兩組合有非零默契 ~ N(0, 0.4)。同隊時默契加進團隊實力。
3. **每個時段**：抽出 16~36 人出席，分成 4~6 隊。分隊方法每晚抽一種：自報程度蛇形選秀（60%）或隨機（40%），記錄在 `team_method`。
4. **時段與賽制（Iris 確認）**：晚餐場 18:00–19:30、消夜場 22:00–23:30，依隊伍數量打 15 或 20 分（假設 4 隊以下打 20 分、5~6 隊打 15 分），需領先 2 分、25 分封頂。一面場地，贏球留場、輸球排到隊尾，贏球最多連留 2 局（假設）；剩餘時間不夠打完整局時改打 15 分。
5. **每一局逐球模擬**：發球（直接得分／失誤／進入來回），接著雙方輪流攻擊，每次攻擊結果為得分、失誤、被攔或繼續。機率以公開比賽的基準值為中心，再依實力調整：發球被直接得分看發球者對上「接發球的人」（依位置抽，自由球員最常接）；攻擊看攻擊者、舉球者（舉球員最常舉）對上「防守這球的人」，加上雙方團隊平均實力。所以自由球員、舉球員的實力也會影響比分（v1.1 修正，原本只透過團隊平均，影響太小）。少一人（相對 6 人）團隊實力扣 0.15。

## 參數來源

| 參數 | 值 | 來源 |
|---|---|---|
| 發球直接得分率、發球失誤率 | 0.141、0.141 | DataVolley 公開範例比賽 |
| 攻擊得分率、失誤率、被攔率 | 0.290、0.071、0.043 | 同上 |
| 每球（含死球時間）秒數 | 29 秒 | 同上，相鄰兩分間隔中位數 |
| 接發球方得分率（檢查用） | 0.520 | 同上 |
| 時段 18:00–19:30、22:00–23:30；打 15 或 20 分 | | Iris 確認的實際野場規則 |
| 實力效果、默契大小、出席率、自評偏誤、幾隊打幾分、留場規則 | 見 `volley_sim.py` 的 `DEFAULT_CONFIG` | **假設**，報告中可做敏感度分析 |

公開比賽是 openvolley/datavolley R 套件附的範例檔（2015 斯洛維尼亞青年女子組決賽，127 球），用 `calibrate_from_datavolley.py` 重算。**限制**：只有一場、是有組織的青年比賽，野場程度差異更大，所以實力效果等參數都是假設。模擬後實際的攻擊得分率 0.30、發球得分率 0.17，與基準接近。

## 輸出檔案（資料字典）

`data/` 是分析時看得到的資料，`truth/` 是只有模擬才知道的真值，**不可當模型輸入**，只能用來驗證。

| 檔案 | 一列代表 | 欄位 |
|---|---|---|
| `data/players.csv` | 一位球員 | `player_id`（P001…）、`self_level`（1~5）、`main_position`（主攻／副攻／舉球／接應／自由／不限） |
| `data/teams.csv` | 某時段的一隊 | `session_id`、`date`、`session`（dinner／late）、`team`（A~F）、`team_method`（random／self_level）、`n_players`、`players`（空白分隔的代號） |
| `data/games.csv` | 一局 | `game_id`、`session_id`、`date`、`weekday`、`session`、`court`、`game_no`、`team_a`、`team_b`、`n_a`、`n_b`、`score_a`、`score_b`、`winner`、`margin`（分差）、`target_points`（20 或 15）、`start_time`、`end_time`、`rallies`、`team_method` |
| `data/game_players.csv` | 一局中的一位球員（長格式，模型直接用） | `game_id`、`session_id`、`date`、`session`、`player_id`、`team`、`side`（A／B）、`won`（0／1）、`points_for`、`points_against`、`margin` |
| `data/attack_stats.csv` | 一局中的一位球員 | `game_id`、`player_id`、`team`、`attempts`、`kills`、`errors`、`blocked`、`serves`、`aces`、`serve_errors`、`receives`（接發球次數）、`aced`（被發球直接得分）、`digs`（防守接起） |
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

- 平均分差 6.3 分，分差 ≤3 的比例 0.30；隨機分隊 7.0 分（0.24），自報程度分隊 5.9 分（0.33）。
- 球員勝率和真實實力相關約 0.43，所以光看勝率會低估實力差，需要模型。
- 兩人同隊的次數中位數只有 3 局，搭檔默契估計會很不穩，建議用收縮估計（隨機效果）。

## 個資

全部是虛構代號，沒有任何真實人物。若之後加入真實紀錄，需另行告知與同意，代號對照表不放進公開 repo。

---

# 跨球館平台版（platform_sim.py，v2）

專題已擴大成「跨球館實力評分與報名平台」。`platform_sim.py` 沿用上面的逐球比賽引擎，多加一層：**4 家球館、150 位有個人檔案的球員、8 週**。`volley_sim.py` 和上面的單館資料都沒動。

```bash
python platform_sim.py                     # 預設：跨館比例 10%，輸出到 platform/
python platform_sim.py --cross 0   --out platform_cross0
python platform_sim.py --cross 0.3 --out platform_cross30
python platform_sim.py --report-sd 1.0 --out platform_sd10   # 自報誤差敏感度分析
```

## 4 家球館（V01 是政大野場，其餘虛構）

| 館 | 時段與賽制 | 報名門檻 | 水準 μ | 自評文化 α |
|---|---|---|---|---|
| V01 政大體育館野場 | 週一~四 18:00–19:30、22:00–23:30；4 隊以下打 20 分、5~6 隊打 15 分 | 無 | 0.0 | 0.0 |
| V02 虛構球館 B（市區付費臨打） | 週二、四、六 19:00 起 150 分鐘；打 25 分 | 無 | +0.2 | +0.3 |
| V03 虛構球館 C（進階場） | 週三、六 19:30 起 150 分鐘；打 25 分 | 自報 ≥4 級 | +0.8 | −0.2 |
| V04 虛構球館 D（新手友善） | 週一、五、日 19:00 起 120 分鐘；打 15 分 | 自報 ≤3 級 | −0.7 | +0.5 |

μ、α 都是假設值，只寫在 `truth/venues_truth.csv`。

## 球員與自報程度

- 真實實力 θ 隨球齡增加（每年 +0.12，10 年後不再增加）再加個別差異，平均為 0。
- 主場：依球館占比、實力是否接近該館水準，且只會選自己符合報名門檻的球館。
- 跨館球員（預設 10%）每次有 35% 機率去其他球館；非跨館球員只在主場打。
- **自報程度**：`reported = θ + α_主場 + 0.30 + 0.20·男性 − 0.06·(球齡 − 3) − 0.20·θ + ε`，ε ~ N(0, 0.6)，再切成 1~5 級。係數真值寫在 `truth/config.json` 的 `self_report_bias`。
  也就是整體高估、男性高估多一點、新手和實力弱的人高估多、在某些球館的人習慣報高。這些係數都是假設，用來檢驗統計方法能不能把它們找回來。

## 輸出（platform/）

| 檔案 | 內容 |
|---|---|
| `data/players.csv` | `player_id`（U0001…）、`gender`、`years_playing`、`self_level`、`main_position`、`venue_home` |
| `data/venues.csv` | 各館公開規則：時段、目標分數、出席人數範圍、報名門檻 |
| `data/matches.csv` | 一局一列：`game_id`、`date`、`venue_id`、`session`、`team_a`、`team_b`、`score_a`、`score_b`、`target_points`、`players_a`、`players_b`（空白分隔） |
| `data/games.csv`、`game_players.csv`、`attack_stats.csv`、`teams.csv`、`attendance.csv` | 和單館版欄位相同，最前面多一欄 `venue_id`；`game_id`、`session_id` 前面加館代號 |
| `truth/players_truth.csv` | `player_id`、`true_theta`、`report_bias`（該球員自報偏誤的真值）、`cross_venue`、`attend_prob` |
| `truth/venues_truth.csv` | `venue_id`、`mu`、`alpha`、`share` |
| `truth/pair_chemistry.csv`、`truth/config.json` | 默契真值、全部參數 |

## 預設資料（種子 20261126，跨館 10%）

- 150 人全部有出賽，128 個時段、772 局；每人出賽局數中位數 52。
- 在 2 館以上出賽的只有 17 人。各館之間的實力要靠這些人「串起來」，跨館比例 0% 時，不同館的評分無法直接比較，這正是 0/10/30% 比較要看的。
- 自報程度和真實實力相關 0.67；球員勝率和真實實力相關只有 0.45。
- **給自報偏誤檢定**：150 人時，性別（+0.20）和球齡（−0.06）的效果用簡單迴歸大多抓不到（標準誤和效果差不多大）。用 20,000 人檢查時，係數能完整找回來，所以程式沒錯，是樣本太小、檢定力不足，可用 `--players` 做檢定力分析。另外報名門檻會讓「主場」和自報程度互相影響（進階場的人一定報 ≥4 級），不能直接把主場虛擬變數當成 α。
