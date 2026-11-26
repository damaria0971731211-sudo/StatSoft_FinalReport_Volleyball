"""第 6 題：分隊方式真的讓比賽比較好玩嗎？（實驗設計、效果大小、檢定力）

模擬裡同一晚可以把三種方法都試一次（配對、共同隨機數）；真實野場一晚只能用一種方法，
所以真實實驗要把「晚」隨機分派給方法，用兩獨立樣本比較。這個模組回答：
    1. 效果有多大（配對差、Cohen's d、bootstrap 信賴區間）
    2. 真實實驗要幾晚才看得出來（公式與模擬兩種檢定力分析，含共變量調整）
    3. 為什麼分析單位必須是「晚」而不是「局」（A/A 測試：同一方法分兩組，看假陽性率）
"""
from __future__ import annotations

import math
import random

import numpy as np
from scipy import stats

SESSIONS_PER_WEEK = 8  # 週一到週四 × 晚餐場、消夜場（與 volley-sim 一致）


# ---------- 1. 效果大小 ----------

def effect_size(a: np.ndarray, b: np.ndarray, paired: bool, rng: np.random.Generator, n_boot: int = 4000) -> dict:
    """a − b 的平均差、95% bootstrap CI，以及 Cohen's d。

    paired=True：d_z = 平均差 / 差的標準差（同一晚兩種方法）。
    paired=False：d = 平均差 / 合併標準差（不同晚）——這才是真實實驗看到的效果大小。
    """
    a, b = np.asarray(a, float), np.asarray(b, float)
    if paired:
        d = a - b
        boots = [d[rng.integers(0, len(d), len(d))].mean() for _ in range(n_boot)]
        es = d.mean() / d.std(ddof=1)
        sd = d.std(ddof=1)
    else:
        boots = [a[rng.integers(0, len(a), len(a))].mean() - b[rng.integers(0, len(b), len(b))].mean() for _ in range(n_boot)]
        sd = math.sqrt((a.var(ddof=1) + b.var(ddof=1)) / 2)
        es = (a.mean() - b.mean()) / sd
    lo, hi = np.quantile(boots, [0.025, 0.975])
    return {"mean_diff": float(a.mean() - b.mean()), "ci95": [float(lo), float(hi)], "cohen_d": float(es), "sd": float(sd)}


# ---------- 2. 檢定力 ----------

def n_per_arm_formula(delta: float, sd: float, alpha: float = 0.05, power: float = 0.8, paired: bool = False) -> int:
    """常態近似的樣本數公式。

    兩獨立組：n = 2 (z_{1−α/2} + z_{power})² σ² / δ²（每組）
    配對：    n = (z_{1−α/2} + z_{power})² σ_d² / δ²
    """
    if delta == 0:
        raise ValueError("效果為 0 時樣本數無限大")
    z = stats.norm.ppf(1 - alpha / 2) + stats.norm.ppf(power)
    k = 1 if paired else 2
    return math.ceil(k * (z * sd / delta) ** 2)


def power_formula(n: int, delta: float, sd: float, alpha: float = 0.05) -> float:
    """兩獨立組、每組 n 晚的近似檢定力（雙尾）。"""
    se = sd * math.sqrt(2 / n)
    z = stats.norm.ppf(1 - alpha / 2)
    return float(stats.norm.sf(z - abs(delta) / se) + stats.norm.cdf(-z - abs(delta) / se))


def _ols_t(y: np.ndarray, x: np.ndarray) -> float:
    """OLS 迴歸，回傳第 2 欄（處理組虛擬變數）係數的雙尾 p 值。x 已含截距。"""
    beta, *_ = np.linalg.lstsq(x, y, rcond=None)
    resid = y - x @ beta
    dof = len(y) - np.linalg.matrix_rank(x)  # 小樣本時共變量可能共線（例如全部都是 6 隊），用偽逆
    s2 = resid @ resid / dof
    cov = s2 * np.linalg.pinv(x.T @ x)
    t = beta[1] / math.sqrt(cov[1, 1])
    return float(2 * stats.t.sf(abs(t), dof))


def simulate_power(
    y_a: np.ndarray,
    y_b: np.ndarray,
    n_per_arm: int,
    rng: np.random.Generator,
    reps: int = 2000,
    alpha: float = 0.05,
    cov_a: np.ndarray | None = None,
    cov_b: np.ndarray | None = None,
) -> dict:
    """模擬檢定力：從方法 A、B 的「晚」各抽 n 晚（不同晚，模擬真實隨機分派），做檢定，重複 reps 次。

    沒給共變量：Welch t 檢定。
    有共變量（例如當晚隊數、人數）：OLS y ~ 方法 + 共變量（ANCOVA），看方法係數。
    """
    y_a, y_b = np.asarray(y_a, float), np.asarray(y_b, float)
    hits_t = hits_adj = 0
    for _ in range(reps):
        ia = rng.integers(0, len(y_a), n_per_arm)
        ib = rng.integers(0, len(y_b), n_per_arm)
        p = stats.ttest_ind(y_a[ia], y_b[ib], equal_var=False).pvalue
        hits_t += p < alpha
        if cov_a is not None:
            y = np.r_[y_a[ia], y_b[ib]]
            treat = np.r_[np.ones(n_per_arm), np.zeros(n_per_arm)]
            c = np.vstack([np.asarray(cov_a)[ia], np.asarray(cov_b)[ib]])
            x = np.column_stack([np.ones(2 * n_per_arm), treat, c])
            hits_adj += _ols_t(y, x) < alpha
    out = {"n_per_arm": n_per_arm, "power_t": hits_t / reps}
    if cov_a is not None:
        out["power_ancova"] = hits_adj / reps
    return out


def nights_needed(curve: list[dict], key: str, target: float = 0.8) -> int | None:
    """從檢定力曲線找出第一個達到 target 的每組晚數。"""
    for row in curve:
        if row[key] >= target:
            return row["n_per_arm"]
    return None


# ---------- 3. 分析單位：A/A 測試 ----------

def game_level_nights(n_nights: int, method: str, seed: int) -> list[list[float]]:
    """用 volleysplit 的野場模擬，產生 n 晚、每晚每局的分差（同一種分隊方法）。"""
    from .simulate import SimConfig, make_pool, play_night
    from .teaming import METHODS, choose_n_teams

    cfg = SimConfig()
    master = random.Random(seed)
    out = []
    fn = METHODS[method]
    for _ in range(n_nights):
        s = master.randrange(2**31)
        r = random.Random(s)
        n = r.randint(cfg.min_players, cfg.max_players)
        pool = make_pool(n, r, cfg)
        teams = fn(pool, choose_n_teams(n), random.Random(s + 1))
        night = play_night(teams, random.Random(s + 2), cfg)
        out.append([abs(g["score_A"] - g["score_B"]) for g in night["games"]])
    return out


def aa_test(nights: list[list[float]], n_per_arm: int, rng: np.random.Generator, reps: int = 2000, alpha: float = 0.05) -> dict:
    """A/A 測試：所有晚都用同一種方法，隨機貼上 A、B 標籤，兩種分析的假陽性率。

    以局為單位（錯）：把每局分差當獨立樣本做 t 檢定。
    以晚為單位（對）：每晚先平均，再做 t 檢定。
    H0 為真，正確的檢定假陽性率應接近 α。
    """
    hits_game = hits_night = 0
    k = len(nights)
    means = np.array([np.mean(x) for x in nights])
    for _ in range(reps):
        idx = rng.choice(k, 2 * n_per_arm, replace=False)
        a, b = idx[:n_per_arm], idx[n_per_arm:]
        ga = np.concatenate([nights[i] for i in a])
        gb = np.concatenate([nights[i] for i in b])
        hits_game += stats.ttest_ind(ga, gb).pvalue < alpha
        hits_night += stats.ttest_ind(means[a], means[b]).pvalue < alpha
    return {"n_per_arm": n_per_arm, "false_pos_game_level": hits_game / reps, "false_pos_night_level": hits_night / reps}


def icc_oneway(groups: list[list[float]]) -> float:
    """單因子 ANOVA 估組內相關係數 ICC(1)：同一晚的局有多像。"""
    k = len(groups)
    ns = np.array([len(g) for g in groups], float)
    N = ns.sum()
    grand = np.concatenate(groups).mean()
    msb = sum(len(g) * (np.mean(g) - grand) ** 2 for g in groups) / (k - 1)
    msw = sum(((np.asarray(g) - np.mean(g)) ** 2).sum() for g in groups) / (N - k)
    n0 = (N - (ns**2).sum() / N) / (k - 1)
    return float((msb - msw) / (msb + (n0 - 1) * msw))
