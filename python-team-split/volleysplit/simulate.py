"""模擬：產生報名名單、模擬一晚的野場（贏球留場）、比較三種分隊方法。

模型假設（報告裡要寫清楚）：
- 真實實力 true_skill ~ N(0, 1)。
- 自報程度 = 真實實力加上雜訊與高估偏誤後，四捨五入成 1~5。
- 模型評分 rating = 真實實力 + N(0, sd)，sd = rating_sd / sqrt(1 + n_games / 4)，
  代表場數越多、R 模型估得越準。之後可換成 R 模型的實際輸出。
- 每一分（rally）A 隊得分機率 = logistic(k × (A 隊強度 − B 隊強度))，打到目標分且領先 2 分。
- 野場規則（與 volley-sim 一致，Iris 確認的時段）：每時段 90 分鐘、一面場地；4 隊以下打 20 分、
  5~6 隊打 15 分；剩餘時間不夠就改打 15 分，連 15 分都不夠就收場。
  贏的留場、輸的排隊尾；贏球最多連續留場 max_streak 局。每球（含死球）約 29 秒。
"""
from __future__ import annotations

import math
import random
from collections import deque
from dataclasses import dataclass

from .registration import Player
from .teaming import METHODS, choose_n_teams, team_strength

POSITION_WEIGHTS = (("舉球", 0.18), ("攻擊", 0.42), ("自由", 0.12), ("不限", 0.28))


@dataclass
class SimConfig:
    self_report_sd: float = 0.7  # 自報程度的雜訊（越大越不準）
    self_report_bias: float = 0.2  # 平均高估多少（以實力標準差計）
    rating_sd: float = 0.8  # 模型評分在 0 場時的誤差
    max_games_history: int = 30  # 每人過去場數 ~ U{0..max}
    rally_k: float = 0.5  # 每球得分機率對強度差的敏感度
    minutes: int = 90  # 晚餐場 18:00–19:30、消夜場 22:00–23:30
    seconds_per_rally: int = 29  # datavolley 公開比賽：相鄰兩分間隔中位數
    target_by_teams: tuple = ((4, 20), (6, 15))  # 隊數 ≤4 打 20 分，5~6 隊打 15 分
    short_target: int = 15
    courts: int = 1
    max_streak: int = 2
    min_players: int = 20
    max_players: int = 36


def make_pool(n: int, rng: random.Random, cfg: SimConfig, session: str = "晚餐場") -> list[Player]:
    """產生 n 位模擬報名者（代號 P01、P02…）。"""
    pos_names = [p for p, _ in POSITION_WEIGHTS]
    pos_w = [w for _, w in POSITION_WEIGHTS]
    pool = []
    for i in range(n):
        true = rng.gauss(0, 1)
        perceived = true + cfg.self_report_bias + rng.gauss(0, cfg.self_report_sd)
        level = min(5, max(1, round(3 + 1.2 * perceived)))
        g = rng.randint(0, cfg.max_games_history)
        sd = cfg.rating_sd / math.sqrt(1 + g / 4)
        pool.append(
            Player(
                code=f"P{i + 1:02d}",
                self_level=level,
                session=session,
                position=rng.choices(pos_names, pos_w)[0],
                rating=true + rng.gauss(0, sd),
                n_games=g,
                true_skill=true,
            )
        )
    return pool


def true_strength(team: list[Player]) -> float:
    return team_strength([p.true_skill for p in team])


def play_set(s_a: float, s_b: float, rng: random.Random, k: float = 0.5, target: int = 20) -> tuple[int, int]:
    """逐球模擬一局，回傳 (A 得分, B 得分)。"""
    p = 1 / (1 + math.exp(-k * (s_a - s_b)))
    a = b = 0
    while not ((a >= target or b >= target) and abs(a - b) >= 2):
        if rng.random() < p:
            a += 1
        else:
            b += 1
    return a, b


def night_target(n_teams: int, cfg: SimConfig) -> int:
    for max_teams, target in cfg.target_by_teams:
        if n_teams <= max_teams:
            return target
    return cfg.target_by_teams[-1][1]


def play_night(teams: list[list[Player]], rng: random.Random, cfg: SimConfig, game=None, strengths=None) -> dict:
    """贏球留場制模擬一個時段（依時間打到收場）。回傳每局紀錄與每隊上場局數。

    game(a, b, target) -> (A 得分, B 得分) 可替換成別的單局模擬器（例如 volley-sim 的逐球攻防模型）；
    strengths 是每隊真實強度（用來算強度差指標），預設用 true_skill 平均。
    """
    n = len(teams)
    strengths = strengths or [true_strength(t) for t in teams]
    if game is None:
        def game(a: int, b: int, target: int) -> tuple[int, int]:
            return play_set(strengths[a], strengths[b], rng, cfg.rally_k, target)
    full = night_target(n, cfg)
    budget = cfg.minutes * 60
    need = lambda t: t * 1.8 * cfg.seconds_per_rally  # 一局大約要打 1.8 × 目標分 球
    courts = max(1, min(cfg.courts, n // 2))
    queue = deque(range(n))
    rng.shuffle(queue)  # 上場順序抽籤
    on_court = [[queue.popleft(), queue.popleft()] for _ in range(courts)]
    streak = [0] * courts
    holder = [None] * courts  # 哪一隊在連勝
    clock = [0.0] * courts
    played = [0] * n
    games = []
    while True:
        open_courts = [c for c in range(courts) if budget - clock[c] >= need(cfg.short_target)]
        if not open_courts:
            break
        c = min(open_courts, key=lambda k: clock[k])  # 先空出來的場地先開下一局
        target = full if budget - clock[c] >= need(full) else cfg.short_target
        a, b = on_court[c]
        sa, sb = game(a, b, target)
        played[a] += 1
        played[b] += 1
        winner, loser = (a, b) if sa > sb else (b, a)
        games.append({"court": c + 1, "start_min": round(clock[c] / 60, 1), "target": target,
                      "A": a, "B": b, "score_A": sa, "score_B": sb})
        clock[c] += (sa + sb) * cfg.seconds_per_rally
        streak[c] = streak[c] + 1 if holder[c] == winner else 1
        holder[c] = winner
        queue.append(loser)
        if streak[c] >= cfg.max_streak:
            queue.append(winner)
            streak[c], holder[c] = 0, None
            on_court[c] = [queue.popleft(), queue.popleft()]
        else:
            on_court[c] = [winner, queue.popleft()]
    return {"games": games, "played": played, "strengths": strengths}


def night_metrics(teams: list[list[Player]], night: dict) -> dict:
    margins = [abs(g["score_A"] - g["score_B"]) for g in night["games"]]
    # 以「人」為單位的上場局數
    per_player = [night["played"][k] for k, t in enumerate(teams) for _ in t]
    mean_pp = sum(per_player) / len(per_player)
    sd_pp = math.sqrt(sum((x - mean_pp) ** 2 for x in per_player) / len(per_player))
    s = night["strengths"]
    return {
        "mean_margin": sum(margins) / len(margins),
        "close_rate": sum(m <= 3 for m in margins) / len(margins),
        "blowout_rate": sum(m >= 10 for m in margins) / len(margins),
        "strength_spread": max(s) - min(s),
        "games_sd": sd_pp,  # 每人上場局數的標準差：越小越公平
        "games_gap": max(per_player) - min(per_player),
    }


METRICS = ("mean_margin", "close_rate", "blowout_rate", "strength_spread", "games_sd", "games_gap")
METRIC_LABELS = {
    "mean_margin": "平均分差",
    "close_rate": "接近比賽比例（分差≤3）",
    "blowout_rate": "懸殊比賽比例（分差≥10）",
    "strength_spread": "最強隊與最弱隊真實強度差",
    "games_sd": "每人上場局數標準差",
    "games_gap": "上場最多與最少者局數差",
}


def run_simulation(reps: int = 500, seed: int = 2026, cfg: SimConfig | None = None) -> list[dict]:
    """蒙地卡羅：每一晚用同一份名單、同一個比賽亂數種子，分別套三種分隊方法（共同隨機數）。"""
    cfg = cfg or SimConfig()
    master = random.Random(seed)
    rows = []
    for r in range(reps):
        night_seed = master.randrange(2**31)
        pool_rng = random.Random(night_seed)
        n = pool_rng.randint(cfg.min_players, cfg.max_players)
        pool = make_pool(n, pool_rng, cfg)
        n_teams = choose_n_teams(n)
        for name, fn in METHODS.items():
            teams = fn(pool, n_teams, random.Random(night_seed + 1))
            night = play_night(teams, random.Random(night_seed + 2), cfg)
            row = {"rep": r + 1, "method": name, "n_players": n, "n_teams": n_teams}
            row.update(night_metrics(teams, night))
            rows.append(row)
    return rows


# ---------- 統計摘要：平均數、bootstrap 信賴區間、配對差異檢定 ----------

def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs)


def bootstrap_ci(xs: list[float], rng: random.Random, b: int = 2000, alpha: float = 0.05) -> tuple[float, float]:
    n = len(xs)
    stats = sorted(_mean([xs[rng.randrange(n)] for _ in range(n)]) for _ in range(b))
    return stats[int(b * alpha / 2)], stats[int(b * (1 - alpha / 2)) - 1]


def sign_flip_pvalue(diffs: list[float], rng: random.Random, b: int = 5000) -> float:
    """配對差的隨機符號置換檢定（雙尾），H0：兩方法的期望差為 0。"""
    obs = abs(_mean(diffs))
    hits = 0
    for _ in range(b):
        if abs(_mean([d if rng.random() < 0.5 else -d for d in diffs])) >= obs - 1e-12:
            hits += 1
    return (hits + 1) / (b + 1)


def summarize(rows: list[dict], seed: int = 7, b: int = 2000) -> dict:
    rng = random.Random(seed)
    methods = list(dict.fromkeys(r["method"] for r in rows))
    by = {m: {k: [] for k in METRICS} for m in methods}
    for r in rows:
        for k in METRICS:
            by[r["method"]][k].append(r[k])
    per_method = {}
    for m in methods:
        per_method[m] = {}
        for k in METRICS:
            xs = by[m][k]
            lo, hi = bootstrap_ci(xs, rng, b)
            per_method[m][k] = {"mean": _mean(xs), "ci95": [lo, hi]}
    # 以「評分最佳化」為基準，和其他方法做配對比較
    base = "評分最佳化"
    comparisons = {}
    for m in methods:
        if m == base:
            continue
        comparisons[f"{base} − {m}"] = {}
        for k in METRICS:
            d = [x - y for x, y in zip(by[base][k], by[m][k])]
            lo, hi = bootstrap_ci(d, rng, b)
            comparisons[f"{base} − {m}"][k] = {
                "mean_diff": _mean(d),
                "ci95": [lo, hi],
                "p_value": sign_flip_pvalue(d, rng, b),
            }
    return {
        "n_nights": len(rows) // len(methods),
        "metric_labels": METRIC_LABELS,
        "per_method": per_method,
        "comparisons": comparisons,
    }
