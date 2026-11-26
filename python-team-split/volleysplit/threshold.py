"""第 5 題：報名門檻要設多嚴？（分類錯誤、ROC、新人處理）

情境：某場次限「中高階以上」（真實實力 θ ≥ c，c 預設 0.4，對應 volley-sim 自報 4 級的切點）。
平台看不到 θ，只看到自報程度和比賽資料，要決定放行或擋下。

把它寫成假設檢定（每位報名者一次）：
    H0：此人未達門檻（θ < c）     H1：此人達到門檻（θ ≥ c）
    放行 = 拒絕 H0。
    型一錯誤 = 誤放（未達門檻卻放行，影響同場其他人）
    型二錯誤 = 誤擋（達標卻被擋，影響本人）
ROC 的橫軸 = 誤放率（FPR，型一錯誤率），縱軸 = 正確放行率（TPR，檢定力 = 1 − 誤擋率）。

測量模型（常態共軛，參數校準自 R 實力模型 r-rating-model 的輸出）：
    θ ~ N(0, 1)
    自報 = 1 + #{切點 < θ + 高估 0.3 + N(0, 0.6²)}           （與 volley-sim 相同）
    先驗：θ | 自報 = ℓ ~ N(μ_ℓ, τ_ℓ²)                          （平台可從累積資料學到）
    資料：x̄ | θ ~ N(θ, 1/(b·n))，n = 已打局數，b = 每局帶來的資訊量
    後驗：精度 = 1/τ_ℓ² + b·n，平均 = (μ_ℓ/τ_ℓ² + b·n·x̄)/精度
R 模型 80 人的標準誤（換成 θ 尺度，除以 beta_skill 0.4）符合 1/se² ≈ 1.43 + 0.044 × 局數，
所以 b 預設 0.044。

決策規則：
    自報規則：自報 ≥ 4 就放行（現況）。
    後驗機率規則：P(θ ≥ c | 資料) ≥ q 就放行；q 越高越嚴。
    三段式規則（處理新人）：P ≥ q_hi 放行、P ≤ q_lo 擋下、其餘「待定」→ 給試打名額或限制名額。
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.stats import norm

LEVEL_CUTS = (-1.2, -0.4, 0.4, 1.2)


@dataclass
class ThresholdConfig:
    cut: float = 0.4  # 門檻 c：真實實力 ≥ c 才算「中高階以上」
    self_bias: float = 0.3  # 自評平均高估（volley-sim）
    self_sd: float = 0.6  # 自評雜訊（volley-sim）
    info_per_set: float = 0.044  # b：每打一局增加的精度（校準自 R 模型）
    self_level_rule: int = 4  # 現況：自報 ≥ 4 就放行


def self_level(theta: np.ndarray, rng: np.random.Generator, cfg: ThresholdConfig) -> np.ndarray:
    reported = theta + cfg.self_bias + rng.normal(0, cfg.self_sd, len(theta))
    return 1 + np.searchsorted(LEVEL_CUTS, reported)


def level_prior(cfg: ThresholdConfig, n: int = 400_000, seed: int = 0) -> dict[int, tuple[float, float]]:
    """每個自報等級下真實實力的平均與標準差（平台用歷史資料就能估到，這裡用大樣本模擬算）。"""
    rng = np.random.default_rng(seed)
    th = rng.normal(0, 1, n)
    lv = self_level(th, rng, cfg)
    return {int(k): (float(th[lv == k].mean()), float(th[lv == k].std())) for k in range(1, 6)}


def simulate_applicants(
    n: int, sets: np.ndarray | int, rng: np.random.Generator, cfg: ThresholdConfig, prior=None
) -> dict[str, np.ndarray]:
    """模擬 n 位報名者：真實實力、自報、已打局數、後驗平均與標準差、達標機率。"""
    prior = prior or level_prior(cfg)
    theta = rng.normal(0, 1, n)
    lv = self_level(theta, rng, cfg)
    sets = np.broadcast_to(np.asarray(sets), (n,)).astype(float)
    mu0 = np.array([prior[int(k)][0] for k in lv])
    tau0 = np.array([prior[int(k)][1] for k in lv])
    info = cfg.info_per_set * sets
    xbar = theta + rng.normal(0, 1, n) / np.sqrt(np.maximum(info, 1e-12))
    prec = 1 / tau0**2 + info
    mean = (mu0 / tau0**2 + info * xbar) / prec
    sd = 1 / np.sqrt(prec)
    return {
        "theta": theta,
        "level": lv,
        "sets": sets,
        "post_mean": mean,
        "post_sd": sd,
        "p_qualified": posterior_prob(mean, sd, cfg.cut),
        "qualified": theta >= cfg.cut,
    }


def posterior_prob(mean, sd, cut: float):
    """P(θ ≥ c | 資料)。"""
    return norm.sf((cut - np.asarray(mean)) / np.asarray(sd))


def error_rates(admit: np.ndarray, qualified: np.ndarray) -> dict[str, float]:
    """誤放率（FPR，型一）、誤擋率（FNR，型二）、正確放行率（TPR）與混淆表。"""
    admit = np.asarray(admit, bool)
    qualified = np.asarray(qualified, bool)
    tp = int(np.sum(admit & qualified))
    fp = int(np.sum(admit & ~qualified))
    fn = int(np.sum(~admit & qualified))
    tn = int(np.sum(~admit & ~qualified))
    pos, neg = tp + fn, fp + tn
    return {
        "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        "tpr": tp / pos if pos else float("nan"),
        "fpr": fp / neg if neg else float("nan"),
        "fnr": fn / pos if pos else float("nan"),
        # 放行的人裡有多少其實未達標：場上球友最在意這個
        "false_admit_share": fp / (tp + fp) if tp + fp else float("nan"),
    }


def roc_curve(score: np.ndarray, qualified: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """回傳 (FPR, TPR, 門檻)；門檻由高到低，score ≥ 門檻就放行。"""
    score = np.asarray(score, float)
    y = np.asarray(qualified, bool)
    order = np.argsort(-score, kind="mergesort")
    s, y = score[order], y[order]
    distinct = np.r_[np.where(np.diff(s))[0], len(s) - 1]
    tp = np.cumsum(y)[distinct]
    fp = np.cumsum(~y)[distinct]
    tpr = np.r_[0, tp / max(y.sum(), 1)]
    fpr = np.r_[0, fp / max((~y).sum(), 1)]
    return fpr, tpr, np.r_[np.inf, s[distinct]]


def auc(score: np.ndarray, qualified: np.ndarray) -> float:
    """AUC = 隨機挑一位達標者與一位未達標者，達標者分數較高的機率（Mann–Whitney，同分算一半）。"""
    from scipy.stats import rankdata

    y = np.asarray(qualified, bool)
    r = rankdata(score)
    n1, n0 = y.sum(), (~y).sum()
    if n1 == 0 or n0 == 0:
        return float("nan")
    return float((r[y].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


def bootstrap_auc_ci(score, qualified, rng: np.random.Generator, b: int = 2000, alpha: float = 0.05):
    score, y = np.asarray(score), np.asarray(qualified, bool)
    n = len(y)
    vals = []
    for _ in range(b):
        i = rng.integers(0, n, n)
        if y[i].all() or (~y[i]).all():
            continue
        vals.append(auc(score[i], y[i]))
    return float(np.quantile(vals, alpha / 2)), float(np.quantile(vals, 1 - alpha / 2))


def choose_threshold(p: np.ndarray, qualified: np.ndarray, grid=None) -> dict[str, dict]:
    """三種選門檻的準則，回傳各自的 q 與錯誤率。

    youden     ：最大化 TPR − FPR（兩種錯誤一樣嚴重）
    fpr_5pct   ：誤放率 ≤ 5% 下檢定力最大（把誤放當型一錯誤，α = 0.05）
    cost_2to1  ：誤放成本是誤擋的 2 倍時，總成本最小（理論上 q* = 2/(1+2) = 2/3）
    """
    grid = np.linspace(0.01, 0.99, 99) if grid is None else grid
    rows = [(q, error_rates(p >= q, qualified)) for q in grid]
    pos = np.sum(qualified)
    neg = len(qualified) - pos
    youden = max(rows, key=lambda r: r[1]["tpr"] - r[1]["fpr"])
    ok = [r for r in rows if r[1]["fpr"] <= 0.05]
    fpr5 = max(ok, key=lambda r: r[1]["tpr"]) if ok else rows[-1]
    cost = min(rows, key=lambda r: 2 * r[1]["fpr"] * neg + r[1]["fnr"] * pos)
    pack = lambda r: {"q": round(float(r[0]), 2), **r[1]}
    return {"youden": pack(youden), "fpr_5pct": pack(fpr5), "cost_2to1": pack(cost)}


def three_way(p: np.ndarray, q_lo: float = 0.2, q_hi: float = 0.8) -> np.ndarray:
    """三段式決策：1 = 放行、0 = 待定（試打名額）、−1 = 擋下。"""
    if not 0 <= q_lo < q_hi <= 1:
        raise ValueError("需要 0 ≤ q_lo < q_hi ≤ 1")
    p = np.asarray(p)
    return np.where(p >= q_hi, 1, np.where(p <= q_lo, -1, 0))


def sets_to_decide(cfg: ThresholdConfig, share: float = 0.8, q_lo=0.2, q_hi=0.8, n=20_000, seed=1, max_sets=300):
    """要打幾局，才會有 share 比例的報名者能被三段式規則判定（不是待定）。"""
    prior = level_prior(cfg)
    for s in range(0, max_sets + 1, 2):
        d = simulate_applicants(n, s, np.random.default_rng(seed), cfg, prior)
        if np.mean(three_way(d["p_qualified"], q_lo, q_hi) != 0) >= share:
            return s
    return None
