"""第 5、6 題的完整分析：產生 results/threshold.json、results/design.json 與 figures/*.png。

用法（在 python-team-split/ 底下）：
    python analysis/q5_q6.py            # 約 1~2 分鐘，seed 固定，可重現
需要 numpy、scipy、pandas、matplotlib。
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import font_manager  # noqa: E402

from volleysplit import design as D  # noqa: E402
from volleysplit import threshold as T  # noqa: E402

PROJECT = os.path.dirname(ROOT)
R_RATINGS = os.path.join(PROJECT, "r-rating-model", "output", "ratings_volley_sim.csv")
TRUTH = os.path.join(PROJECT, "volley-sim", "truth", "players_truth.csv")
FIG = os.path.join(ROOT, "figures")
RES = os.path.join(ROOT, "results")
BETA_SKILL = 0.4  # volley-sim 的 beta_skill：R 模型 θ（每球 logit）÷ 0.4 = 實力尺度

# 圖表樣式：類別色固定順序（dataviz 預設調色盤），文字用中性色
C = ["#257de0", "#f47230", "#00b894", "#f2a600"]
INK, INK2, GRID = "#191919", "#666666", "#e6e6e6"
for f in ("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",):
    if os.path.exists(f):
        font_manager.fontManager.addfont(f)
        plt.rcParams["font.family"] = font_manager.FontProperties(fname=f).get_name()
plt.rcParams.update({
    "axes.edgecolor": INK2, "axes.labelcolor": INK, "xtick.color": INK2, "ytick.color": INK2,
    "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True, "grid.color": GRID,
    "grid.linewidth": 0.8, "lines.linewidth": 2, "font.size": 11, "axes.titlesize": 13,
    "axes.titleweight": "bold", "legend.frameon": False, "figure.dpi": 100, "axes.unicode_minus": False,
})


def save(fig, name):
    os.makedirs(FIG, exist_ok=True)
    fig.savefig(os.path.join(FIG, name), dpi=200, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def r4(x):
    return round(float(x), 4)


# ======================= 第 5 題 =======================

def q5() -> dict:
    cfg = T.ThresholdConfig()
    prior = T.level_prior(cfg)
    rng = np.random.default_rng(20261126)
    out = {"config": vars(cfg), "level_prior": {k: [r4(m), r4(s)] for k, (m, s) in prior.items()}}

    # (a) 不同經驗的人：ROC 與 AUC
    groups = [0, 10, 40, 150]
    roc = {}
    fig, ax = plt.subplots(figsize=(6.4, 5.6))
    ax.plot([0, 1], [0, 1], color=GRID, lw=1.2, ls="--")
    for col, s in zip(C, groups):
        d = T.simulate_applicants(20000, s, rng, cfg, prior)
        fpr, tpr, _ = T.roc_curve(d["p_qualified"], d["qualified"])
        a = T.auc(d["p_qualified"], d["qualified"])
        lo, hi = T.bootstrap_auc_ci(d["p_qualified"][:4000], d["qualified"][:4000], rng, b=300)
        roc[s] = {"auc": r4(a), "auc_ci95_n4000": [r4(lo), r4(hi)]}
        ax.plot(fpr, tpr, color=col, label=f"已打 {s} 局（AUC {a:.2f}）")
    # 現況：只看自報（同一批 0 局的人）
    d0 = T.simulate_applicants(20000, 0, rng, cfg, prior)
    pts = {}
    for lv in (4, 5):
        e = T.error_rates(d0["level"] >= lv, d0["qualified"])
        pts[f"self_ge_{lv}"] = {k: r4(v) for k, v in e.items()}
        ax.plot(e["fpr"], e["tpr"], "o", ms=9, color=INK, mec="white", mew=2, zorder=5)
        ax.annotate(f"只看自報 ≥{lv}", (e["fpr"], e["tpr"]), xytext=(10, -14), textcoords="offset points", color=INK)
    ax.set_xlabel("誤放率（未達標卻放行；型一錯誤率）")
    ax.set_ylabel("正確放行率（達標者被放行；檢定力）")
    ax.set_title("報名門檻的 ROC：打越多局，曲線越靠左上")
    ax.legend(loc="lower right")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1.01)
    save(fig, "q5_roc.png")
    out["roc_by_sets"] = roc
    out["self_report_rule"] = pts

    # (b) 混合族群（局數分布取自 R 模型那 80 人），三種準則選門檻
    rset = pd.read_csv(R_RATINGS)["sets"].to_numpy()
    sets = rng.choice(rset, 40000)
    dm = T.simulate_applicants(40000, sets, rng, cfg, prior)
    choice = T.choose_threshold(dm["p_qualified"], dm["qualified"])
    out["mixed_population"] = {
        "sets_source": "r-rating-model/output/ratings_volley_sim.csv 的 sets 欄（80 人經驗分布）",
        "qualified_share": r4(dm["qualified"].mean()),
        "auc": r4(T.auc(dm["p_qualified"], dm["qualified"])),
        "self_ge_4": {k: r4(v) for k, v in T.error_rates(dm["level"] >= 4, dm["qualified"]).items()},
        "choices": {k: {kk: (r4(vv) if isinstance(vv, float) else vv) for kk, vv in v.items()} for k, v in choice.items()},
    }
    qs = np.linspace(0.02, 0.98, 49)
    er = [T.error_rates(dm["p_qualified"] >= q, dm["qualified"]) for q in qs]
    fig, ax = plt.subplots(figsize=(7.2, 4.6))
    ax.plot(qs, [e["fpr"] for e in er], color=C[0], label="誤放率（型一）")
    ax.plot(qs, [e["fnr"] for e in er], color=C[1], label="誤擋率（型二）")
    names = {"youden": "Youden", "fpr_5pct": "誤放 ≤5%", "cost_2to1": "誤放成本 2 倍"}
    for i, (k, v) in enumerate(choice.items()):
        ax.axvline(v["q"], color=INK2, lw=1, ls=":")
        ax.text(v["q"], 0.97 - 0.08 * i, f" {names[k]}：q={v['q']:.2f}", color=INK, va="top", fontsize=10)
    ax.set_xlabel("放行門檻 q：P(達標 | 資料) ≥ q 才放行")
    ax.set_ylabel("錯誤率")
    ax.set_ylim(0, 1)
    ax.set_title("門檻越嚴，誤放越少、誤擋越多（兩種錯誤此消彼長）")
    ax.legend(loc="center right")
    save(fig, "q5_tradeoff.png")

    # (c) 新人：三段式規則（≥0.8 放行、≤0.2 擋下、其餘待定）
    grid = list(range(0, 201, 5))
    rows = []
    for s in grid:
        d = T.simulate_applicants(20000, s, np.random.default_rng(s + 7), cfg, prior)
        tw = T.three_way(d["p_qualified"])
        adm = tw == 1
        rows.append({
            "sets": s,
            "admit": r4(np.mean(tw == 1)), "undecided": r4(np.mean(tw == 0)), "reject": r4(np.mean(tw == -1)),
            "false_admit_share": r4(np.mean(~d["qualified"][adm])) if adm.any() else None,
            "post_sd_median": r4(np.median(d["post_sd"])),
        })
    out["three_way"] = {"q_lo": 0.2, "q_hi": 0.8, "by_sets": rows,
                        "sets_for_80pct_decided": T.sets_to_decide(cfg)}
    fig, ax = plt.subplots(figsize=(7.2, 4.6))
    for col, key, lab in zip(C, ["admit", "undecided", "reject"], ["確定放行", "待定（給試打名額）", "確定擋下"]):
        y = [r[key] for r in rows]
        ax.plot(grid, y, color=col, label=lab)
        ax.text(grid[-1] + 3, y[-1], lab, color=INK, va="center", fontsize=10)
    ax.set_xlim(0, 235)
    ax.set_xlabel("已打局數")
    ax.set_ylabel("報名者比例")
    ax.set_title("新人區間寬，先放進「待定」；打得越多，越能下判斷")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.15), ncol=3)
    save(fig, "q5_newcomer.png")

    # (d) 用真的 R 模型輸出（80 人）驗證：門檻規則在實際估計管線上表現如何
    r = pd.read_csv(R_RATINGS).merge(pd.read_csv(TRUTH), left_on="player", right_on="player_id")
    z, se = r["theta"] / BETA_SKILL, r["se"] / BETA_SKILL
    p = T.posterior_prob(z, se, cfg.cut)
    y = (r["true_skill"] >= cfg.cut).to_numpy()
    q = choice["youden"]["q"]
    lo, hi = T.bootstrap_auc_ci(p, y, np.random.default_rng(5), b=2000)
    out["r_model_check"] = {
        "n": int(len(r)), "qualified": int(y.sum()),
        "auc_posterior": r4(T.auc(p, y)), "auc_ci95": [r4(lo), r4(hi)],
        "auc_self_level": r4(T.auc(r["level"], y)),
        "rule_posterior_youden_q": q,
        "posterior_rule": T.error_rates(p >= q, y),
        "self_ge_4": T.error_rates(r["level"].to_numpy() >= 4, y),
        "note": "R 的 θ 為每球 logit，÷0.4 換成實力尺度；θ 已經過收縮、平均置中，只作方向性檢查。",
    }
    return out


# ======================= 第 6 題 =======================

def q6() -> dict:
    runs = pd.read_csv(os.path.join(RES, "sim_runs.csv"))
    rng = np.random.default_rng(20261126)
    base = "評分最佳化"
    out = {"source": "results/sim_runs.csv（1000 晚 × 3 方法，seed 2026，共同隨機數）",
           "sessions_per_week": D.SESSIONS_PER_WEEK, "effects": {}, "power": {}}
    # 共變量：當晚隊數（決定打 15 或 20 分）與人數；分派前就知道，可以合法調整
    def covs(df):
        return np.column_stack([(df["n_teams"] == 5), (df["n_teams"] == 6), df["n_players"]]).astype(float)

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.4), sharey=True)
    for ax, other in zip(axes, ["隨機", "自報程度蛇形"]):
        res = {}
        for metric in ("mean_margin", "close_rate"):
            w = runs.pivot(index="rep", columns="method", values=metric)
            res[metric] = {
                "paired": D.effect_size(w[base], w[other], True, rng),
                "independent": D.effect_size(w[base], w[other], False, rng),
            }
        key = f"{base} − {other}"
        out["effects"][key] = res
        ind = res["mean_margin"]["independent"]
        delta, sd = ind["mean_diff"], ind["sd"]
        a = runs[runs.method == base].sort_values("rep")
        b = runs[runs.method == other].sort_values("rep")
        grid = [8, 16, 24, 32, 48, 64, 96, 128, 192, 256, 384, 512, 640, 768, 1024]
        curve = []
        for n in grid:
            row = D.simulate_power(a["mean_margin"].to_numpy(), b["mean_margin"].to_numpy(), n, rng, reps=1000,
                                   cov_a=covs(a), cov_b=covs(b))
            row["power_formula"] = D.power_formula(n, delta, sd)
            curve.append({k: (r4(v) if isinstance(v, float) else v) for k, v in row.items()})
        out["power"][key] = {
            "delta": r4(delta), "sd_between_nights": r4(sd),
            "n_formula_independent": D.n_per_arm_formula(delta, sd),
            "n_formula_paired": D.n_per_arm_formula(res["mean_margin"]["paired"]["mean_diff"], res["mean_margin"]["paired"]["sd"], paired=True),
            "n_sim_t": D.nights_needed(curve, "power_t"),
            "n_sim_ancova": D.nights_needed(curve, "power_ancova"),
            "curve": curve,
        }
        for col, k, lab in [(C[0], "power_t", "模擬：Welch t"), (C[1], "power_ancova", "模擬：調整隊數與人數"),
                            (C[2], "power_formula", "公式（常態近似）")]:
            ax.plot(grid, [r[k] for r in curve], color=col, marker="o", ms=4, label=lab,
                    ls="--" if k == "power_formula" else "-")
        ax.axhline(0.8, color=INK2, lw=1, ls=":")
        ax.set_xscale("log", base=2)
        ticks = [8, 32, 128, 1024]
        ax.set_xticks(ticks)
        ax.set_xticklabels([f"{n}\n({n * 2 / D.SESSIONS_PER_WEEK:.0f} 週)" for n in ticks], fontsize=9)
        ax.set_title(f"評分最佳化 vs {other}（平均分差差 {delta:.2f} 分）")
        ax.set_xlabel("每種方法的晚數（括號：兩組合計需幾週）")
    axes[0].set_ylabel("檢定力（α = 0.05）")
    axes[0].text(8.5, 0.82, "80%", color=INK2, fontsize=9)
    axes[1].legend(loc="lower right")
    fig.suptitle("真實實驗要幾晚才看得出差異？", fontweight="bold", fontsize=14, y=1.02)
    save(fig, "q6_power.png")

    # 效果大小圖：配對 vs 獨立的平均差與 95% CI
    fig, ax = plt.subplots(figsize=(7.2, 3.4))
    labels, ys = [], 0
    for key, res in out["effects"].items():
        for j, (mode, lab) in enumerate([("paired", "同一晚配對（模擬才做得到）"), ("independent", "不同晚（真實實驗）")]):
            e = res["mean_margin"][mode]
            ax.errorbar(e["mean_diff"], ys, xerr=[[e["mean_diff"] - e["ci95"][0]], [e["ci95"][1] - e["mean_diff"]]],
                        fmt="o", color=C[j], ms=8, capsize=4, lw=2, label=lab if ys < 2 else None)
            ax.text(e["ci95"][1] + 0.03, ys, f"d = {e['cohen_d']:.2f}", va="center", color=INK, fontsize=10)
            labels.append(key.replace("評分最佳化 − ", "vs "))
            ys += 1
    ax.axvline(0, color=INK2, lw=1)
    ax.set_yticks(range(ys))
    ax.set_yticklabels(labels)
    ax.invert_yaxis()
    ax.set_xlabel("評分最佳化減對照的平均分差（分；負值 = 比賽更接近）")
    ax.set_title("效果大小與 95% 信賴區間")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.25), ncol=2, fontsize=9)
    save(fig, "q6_effect.png")

    # A/A 測試：分析單位錯了會怎樣（兩種方法各做一次：隨機分隊時同一晚的隊伍強弱固定，局與局更像）
    out["aa_test"] = {}
    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    xs = [10, 20, 40, 80, 160]
    top = 0.1
    for j, (m, seed) in enumerate([("隨機", 11), (base, 12)]):
        nights = D.game_level_nights(1200, m, seed=seed)
        aa = [D.aa_test(nights, n, rng, reps=1500) for n in xs]
        out["aa_test"][m] = {"icc_games_within_night": r4(D.icc_oneway(nights)),
                             "mean_games_per_night": r4(np.mean([len(x) for x in nights])),
                             "rows": [{k: (r4(v) if not isinstance(v, int) else v) for k, v in r.items()} for r in aa]}
        g = [r["false_pos_game_level"] for r in aa]
        top = max(top, max(g) + 0.03)
        ax.plot(xs, g, color=C[1 + 2 * j], marker="o", label=f"以局為單位：{m}（ICC {out['aa_test'][m]['icc_games_within_night']:.2f}）")
        ax.plot(xs, [r["false_pos_night_level"] for r in aa], color=C[1 + 2 * j], marker="o", ls="--", alpha=0.8,
                label=f"以晚為單位：{m}")
    ax.axhline(0.05, color=INK2, lw=1, ls=":")
    ax.text(xs[0], 0.053, "名目 α = 5%", color=INK2, fontsize=9)
    ax.set_xscale("log", base=2)
    ax.set_xticks(xs)
    ax.set_xticklabels(xs)
    ax.set_ylim(0, top)
    ax.set_xlabel("每組晚數")
    ax.set_ylabel("假陽性率（兩組其實一樣）")
    ax.set_title("A/A 測試：把同一晚的局當獨立樣本，會假裝有差異")
    ax.legend(loc="upper left", fontsize=9)
    save(fig, "q6_aa_test.png")
    return out


def main():
    os.makedirs(RES, exist_ok=True)
    a = q5()
    with open(os.path.join(RES, "threshold.json"), "w", encoding="utf-8") as f:
        json.dump(a, f, ensure_ascii=False, indent=2, default=float)
    print("第 5 題完成：results/threshold.json")
    b = q6()
    with open(os.path.join(RES, "design.json"), "w", encoding="utf-8") as f:
        json.dump(b, f, ensure_ascii=False, indent=2, default=float)
    print("第 6 題完成：results/design.json")


if __name__ == "__main__":
    main()
