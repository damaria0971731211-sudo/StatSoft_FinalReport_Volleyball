"""第 5 題（報名門檻）與第 6 題（實驗設計）的測試。"""
import math

import numpy as np
import pytest

from volleysplit import design as D
from volleysplit import threshold as T


# ---------- 第 5 題 ----------

def test_error_rates_hand_computed():
    admit = np.array([1, 1, 0, 0, 1, 0], bool)
    qual = np.array([1, 0, 1, 0, 1, 0], bool)
    e = T.error_rates(admit, qual)
    assert (e["tp"], e["fp"], e["fn"], e["tn"]) == (2, 1, 1, 2)
    assert e["tpr"] == pytest.approx(2 / 3) and e["fpr"] == pytest.approx(1 / 3)
    assert e["false_admit_share"] == pytest.approx(1 / 3)


def test_auc_extremes_and_ties():
    y = np.array([0, 0, 1, 1], bool)
    assert T.auc(np.array([0.1, 0.2, 0.8, 0.9]), y) == 1.0
    assert T.auc(np.array([0.9, 0.8, 0.2, 0.1]), y) == 0.0
    assert T.auc(np.array([0.5, 0.5, 0.5, 0.5]), y) == 0.5  # 全部同分 = 亂猜
    assert math.isnan(T.auc(np.array([0.1, 0.2]), np.array([1, 1], bool)))  # 沒有負例


def test_roc_matches_auc_trapezoid():
    rng = np.random.default_rng(0)
    y = rng.random(500) < 0.4
    s = y + rng.normal(0, 1, 500)
    fpr, tpr, _ = T.roc_curve(s, y)
    assert fpr[0] == 0 and tpr[0] == 0 and fpr[-1] == 1 and tpr[-1] == 1
    assert np.all(np.diff(fpr) >= 0) and np.all(np.diff(tpr) >= 0)
    assert np.trapezoid(tpr, fpr) == pytest.approx(T.auc(s, y), abs=1e-9)


def test_posterior_prob_symmetry():
    assert T.posterior_prob(0.4, 1.0, 0.4) == pytest.approx(0.5)
    assert T.posterior_prob(10, 0.1, 0.4) == pytest.approx(1.0)
    assert T.posterior_prob(-10, 0.1, 0.4) == pytest.approx(0.0)


def test_level_prior_is_increasing_and_shrinks_overestimate():
    cfg = T.ThresholdConfig()
    pr = T.level_prior(cfg, n=100_000)
    means = [pr[k][0] for k in range(1, 6)]
    assert means == sorted(means)
    # 自報有高估：自報 4 級的人，平均真實實力低於 4 級的切點 0.4
    assert pr[4][0] < cfg.cut


def test_more_sets_shrinks_uncertainty_and_raises_auc():
    cfg = T.ThresholdConfig()
    pr = T.level_prior(cfg, n=100_000)
    d0 = T.simulate_applicants(8000, 0, np.random.default_rng(1), cfg, pr)
    d1 = T.simulate_applicants(8000, 150, np.random.default_rng(1), cfg, pr)
    assert np.median(d1["post_sd"]) < np.median(d0["post_sd"])
    assert T.auc(d1["p_qualified"], d1["qualified"]) > T.auc(d0["p_qualified"], d0["qualified"]) + 0.03


def test_posterior_rule_beats_self_report_on_false_admits():
    """同樣的正確放行率附近，後驗規則的誤放率應低於只看自報 ≥4。"""
    cfg = T.ThresholdConfig()
    d = T.simulate_applicants(20000, 40, np.random.default_rng(2), cfg)
    self_rule = T.error_rates(d["level"] >= 4, d["qualified"])
    fpr, tpr, _ = T.roc_curve(d["p_qualified"], d["qualified"])
    fpr_at_same_tpr = fpr[np.searchsorted(tpr, self_rule["tpr"])]
    assert fpr_at_same_tpr < self_rule["fpr"]


def test_choose_threshold_constraints():
    cfg = T.ThresholdConfig()
    d = T.simulate_applicants(20000, 30, np.random.default_rng(3), cfg)
    c = T.choose_threshold(d["p_qualified"], d["qualified"])
    assert c["fpr_5pct"]["fpr"] <= 0.05
    # 誤放成本 2 倍 → 理論最佳 q* = 2/3（後驗機率已校準時）
    assert abs(c["cost_2to1"]["q"] - 2 / 3) < 0.08
    assert c["youden"]["tpr"] - c["youden"]["fpr"] >= c["fpr_5pct"]["tpr"] - c["fpr_5pct"]["fpr"]


def test_three_way_rule():
    p = np.array([0.05, 0.2, 0.5, 0.8, 0.95])
    assert T.three_way(p).tolist() == [-1, -1, 0, 1, 1]
    with pytest.raises(ValueError):
        T.three_way(p, 0.8, 0.2)


def test_posterior_is_calibrated():
    """後驗機率 0.6~0.8 的人，實際達標比例應落在這個區間附近（模型正確時）。"""
    cfg = T.ThresholdConfig()
    d = T.simulate_applicants(60000, 20, np.random.default_rng(4), cfg)
    m = (d["p_qualified"] >= 0.6) & (d["p_qualified"] < 0.8)
    assert 0.6 <= d["qualified"][m].mean() <= 0.8


# ---------- 第 6 題 ----------

def test_sample_size_formula_textbook():
    # 教科書例：δ/σ = 0.5、α=0.05、檢定力 0.8 → 每組 63 人（常態近似；t 檢定約 64）
    assert D.n_per_arm_formula(0.5, 1.0) == 63
    assert D.n_per_arm_formula(0.5, 1.0, paired=True) == 32
    assert D.power_formula(63, 0.5, 1.0) == pytest.approx(0.8, abs=0.01)
    with pytest.raises(ValueError):
        D.n_per_arm_formula(0, 1)


def test_simulated_power_matches_formula():
    rng = np.random.default_rng(5)
    a = rng.normal(0.5, 1, 20000)
    b = rng.normal(0.0, 1, 20000)
    r = D.simulate_power(a, b, 63, rng, reps=1500)
    assert r["power_t"] == pytest.approx(0.8, abs=0.04)


def test_simulated_power_under_null_is_alpha():
    rng = np.random.default_rng(6)
    a = rng.normal(0, 1, 20000)
    r = D.simulate_power(a, a, 30, rng, reps=2000)
    assert r["power_t"] == pytest.approx(0.05, abs=0.015)


def test_ancova_gains_power_when_covariate_explains_variance():
    rng = np.random.default_rng(7)
    xa, xb = rng.integers(4, 7, 20000), rng.integers(4, 7, 20000)
    a = 0.5 + 2.0 * xa + rng.normal(0, 1, 20000)
    b = 0.0 + 2.0 * xb + rng.normal(0, 1, 20000)
    r = D.simulate_power(a, b, 60, rng, reps=600, cov_a=xa[:, None].astype(float), cov_b=xb[:, None].astype(float))
    assert r["power_ancova"] > r["power_t"] + 0.2


def test_effect_size_paired_vs_independent():
    rng = np.random.default_rng(8)
    base = rng.normal(0, 1, 3000)
    a, b = base - 0.2 + rng.normal(0, 0.3, 3000), base + rng.normal(0, 0.3, 3000)
    p = D.effect_size(a, b, True, rng, n_boot=500)
    i = D.effect_size(a, b, False, rng, n_boot=500)
    assert p["ci95"][0] < -0.2 < p["ci95"][1]
    assert abs(p["cohen_d"]) > abs(i["cohen_d"])  # 配對把晚與晚之間的差異扣掉，效果看起來大很多


def test_icc_and_aa_test():
    rng = np.random.default_rng(9)
    # 每組有共同效果 → ICC 明顯大於 0；以局為單位的 t 檢定假陽性會膨脹
    groups = [list(rng.normal(rng.normal(0, 1), 1, 6)) for _ in range(400)]
    assert D.icc_oneway(groups) == pytest.approx(0.5, abs=0.1)
    r = D.aa_test(groups, 20, rng, reps=800)
    assert r["false_pos_game_level"] > 0.15
    assert r["false_pos_night_level"] == pytest.approx(0.05, abs=0.03)


def test_game_level_nights_reproducible():
    a = D.game_level_nights(3, "隨機", seed=1)
    b = D.game_level_nights(3, "隨機", seed=1)
    assert a == b and all(len(x) >= 3 for x in a)


def test_nights_needed():
    curve = [{"n_per_arm": 10, "p": 0.3}, {"n_per_arm": 20, "p": 0.81}]
    assert D.nights_needed(curve, "p") == 20
    assert D.nights_needed(curve, "p", 0.9) is None
