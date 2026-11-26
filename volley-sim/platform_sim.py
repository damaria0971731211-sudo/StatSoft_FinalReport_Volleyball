"""
platform_sim.py — 跨球館排球實力平台的模擬資料產生器（v2）

情境：球員在平台建一份個人檔案（自報程度 1~5），到不同球館打野場／臨打，
每局比分都累積到同一個帳號，平台再用統計模型估出真正的程度。

這是合成資料，不是真實紀錄。逐球比賽引擎沿用 volley_sim.py（參數取自 datavolley 公開比賽），
本檔只加上「多球館、跨館球員、自報偏誤」這一層。原本的 volley_sim.py 仍可單獨使用。

自報程度的生成規則：
    reported_i = θ_i + α_{home(i)} + b0 + b_male·male_i + b_years·(years_i − 3) + ε_i,   ε_i ~ N(0, σ_report)
    self_level_i = 依 level_cuts 把 reported_i 切成 1~5 級
    α_v：球館「自評文化」偏差（同樣實力，在某些館習慣報高）
    b_male、b_years：系統性高估隨性別、球齡改變（假設值，供自報偏誤檢定驗證能否抓到）

用法：
    python platform_sim.py                          # 預設 4 館、150 人、8 週、跨館比例 10%
    python platform_sim.py --cross 0.3 --out platform_cross30
    python platform_sim.py --report-sd 1.0          # 敏感度分析：個人認知誤差加大
    python platform_sim.py --config my.json         # 覆寫任何參數
"""
from __future__ import annotations

import argparse
import copy
import datetime as dt
import json
import os

import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import volley_sim as vs  # noqa: E402

VERSION = "2.0.0"

PLATFORM_CONFIG = {
    "seed": 20261126,
    "start_date": "2026-09-14",
    "weeks": 8,                       # 提案：8 週
    "n_players": 150,                 # 提案：約 150 位
    "cross_venue_share": 0.10,        # 提案：跨館球員比例 0 / 0.1 / 0.3 做比較
    "cross_visit_prob": 0.35,         # 假設：跨館球員每次出賽有 35% 機率去非主場球館
    # ---- 球員屬性（假設） ----
    "p_male": 0.55,
    "years_lambda": 4.0,              # 球齡 ~ Poisson(4)，上限 20
    "skill_per_year": 0.12,           # 球齡每多 1 年，真實實力 +0.12（遞減到 10 年為止）
    "skill_noise_sd": 0.85,
    # ---- 自報程度（假設；敏感度分析主要調 report_sd 與 alpha） ----
    "report_b0": 0.30,                # 整體高估
    "report_b_male": 0.20,            # 男性額外高估
    "report_b_years": -0.06,          # 球齡每多 1 年，高估減少 0.06（新手高估最多）
    "report_b_skill": -0.20,          # 真實實力每高 1 單位，高估減少 0.20（實力弱的人高估較多）
    "report_sd": 0.60,                # 個人認知誤差
    "level_cuts": [-1.2, -0.4, 0.4, 1.2],
    # ---- 4 家球館。V01 為政大野場（Iris 確認的規則），V02~V04 為虛構球館 ----
    # mu：來客實力中心（球館水準）；alpha：自評文化偏差；share：以此為主場的球員比例
    # level_min / level_max：報名門檻（依自報程度）
    "venues": [
        {"venue_id": "V01", "name": "政大體育館野場", "region": "台北", "mu": 0.0, "alpha": 0.0, "share": 0.30,
         "weekdays": [0, 1, 2, 3],
         "sessions": {"dinner": {"start": "18:00", "minutes": 90, "courts": 1},
                      "late": {"start": "22:00", "minutes": 90, "courts": 1}},
         "target_by_teams": {"2": 20, "3": 20, "4": 20, "5": 15, "6": 15},
         "turnout": [16, 36], "level_min": None, "level_max": None,
         "history_methods": {"self_level": 0.6, "random": 0.4}},
        {"venue_id": "V02", "name": "虛構球館 B（市區付費臨打）", "region": "台北", "mu": 0.2, "alpha": 0.3, "share": 0.20,
         "weekdays": [1, 3, 5],
         "sessions": {"night": {"start": "19:00", "minutes": 150, "courts": 1}},
         "target_by_teams": {"2": 25, "3": 25, "4": 25, "5": 25, "6": 25},
         "turnout": [18, 30], "level_min": None, "level_max": None,
         "history_methods": {"self_level": 1.0}},
        {"venue_id": "V03", "name": "虛構球館 C（進階場）", "region": "新北", "mu": 0.8, "alpha": -0.2, "share": 0.25,
         "weekdays": [2, 5],
         "sessions": {"night": {"start": "19:30", "minutes": 150, "courts": 1}},
         "target_by_teams": {"2": 25, "3": 25, "4": 25, "5": 25, "6": 25},
         "turnout": [16, 24], "level_min": 4, "level_max": None,
         "history_methods": {"self_level": 1.0}},
        {"venue_id": "V04", "name": "虛構球館 D（新手友善）", "region": "新北", "mu": -0.7, "alpha": 0.5, "share": 0.25,
         "weekdays": [0, 4, 6],
         "sessions": {"night": {"start": "19:00", "minutes": 120, "courts": 1}},
         "target_by_teams": {"2": 15, "3": 15, "4": 15, "5": 15, "6": 15},
         "turnout": [16, 30], "level_min": None, "level_max": 3,
         "history_methods": {"random": 0.5, "self_level": 0.5}},
    ],
    "venue_fit_sd": 1.0,              # 假設：實力離球館水準越遠越少去（高斯權重的寬度）
}


def platform_config() -> dict:
    return copy.deepcopy(PLATFORM_CONFIG)


def make_platform_players(pc: dict, rng: np.random.Generator) -> pd.DataFrame:
    n = pc["n_players"]
    ids = [f"U{i:04d}" for i in range(1, n + 1)]
    male = rng.random(n) < pc["p_male"]
    years = np.minimum(rng.poisson(pc["years_lambda"], n), 20)
    theta = pc["skill_per_year"] * (np.minimum(years, 10) - 4) + rng.normal(0, pc["skill_noise_sd"], n)
    theta = theta - theta.mean()
    venues = pc["venues"]
    vids = [v["venue_id"] for v in venues]
    share = np.array([v["share"] for v in venues], float)
    eps = rng.normal(0, pc["report_sd"], n)
    bias0 = (pc["report_b0"] + pc["report_b_male"] * male + pc["report_b_years"] * (years - 3)
             + pc["report_b_skill"] * theta)
    alphas = np.array([v["alpha"] for v in venues])
    # 若以 v 為主場，自報程度會是多少（α_v 是主場的自評文化）
    lvl_by_v = 1 + np.searchsorted(pc["level_cuts"], (theta + bias0 + eps)[:, None] + alphas[None, :])
    elig = np.ones_like(lvl_by_v, dtype=bool)
    for k, v in enumerate(venues):
        if v["level_min"] is not None:
            elig[:, k] &= lvl_by_v[:, k] >= v["level_min"]
        if v["level_max"] is not None:
            elig[:, k] &= lvl_by_v[:, k] <= v["level_max"]
    # 主場：依球館占比與實力是否接近該館水準，只在自己符合報名門檻的球館中選
    fit = np.exp(-((theta[:, None] - np.array([v["mu"] for v in venues])[None, :]) ** 2) / (2 * pc["venue_fit_sd"] ** 2))
    w = share[None, :] * fit * elig
    home_idx = np.array([rng.choice(len(vids), p=row / row.sum()) for row in w])
    bias = bias0 + alphas[home_idx]
    self_level = lvl_by_v[np.arange(n), home_idx]
    cross = rng.random(n) < pc["cross_venue_share"]
    base = vs.default_config()
    pos_names = list(base["positions"])
    pos_p = np.array(list(base["positions"].values()))
    pos = rng.choice(pos_names, size=n, p=pos_p / pos_p.sum())
    return pd.DataFrame({
        "player_id": ids, "gender": np.where(male, "M", "F"), "years_playing": years,
        "self_level": self_level.astype(int), "main_position": pos,
        "venue_home": [vids[k] for k in home_idx], "cross_venue": cross.astype(int),
        "true_skill": theta.round(4), "report_bias": bias.round(4),
        "attend_prob": rng.beta(2.0, 5.0, n).round(4),
    }).set_index("player_id", drop=False)


def _eligible(pool, v):
    ok = pd.Series(True, index=pool.index)
    if v["level_min"] is not None:
        ok &= pool["self_level"] >= v["level_min"]
    if v["level_max"] is not None:
        ok &= pool["self_level"] <= v["level_max"]
    return ok


def sample_session_players(pool, v, pc, rng, busy):
    """抽出某館某時段的出席者。主場球員依出席率；跨館球員有機會來客場。"""
    elig = _eligible(pool, v) & ~pool.index.isin(busy)
    home = pool["venue_home"] == v["venue_id"]
    away = (pool["cross_venue"] == 1) & ~home
    fit = np.exp(-((pool["true_skill"] - v["mu"]) ** 2) / (2 * pc["venue_fit_sd"] ** 2))
    w = pool["attend_prob"] * (home * 1.0 + away * pc["cross_visit_prob"] * fit) * elig
    w = w.to_numpy(float)
    lo, hi = v["turnout"]
    n_avail = int((w > 0).sum())
    target = int(rng.integers(lo, hi + 1))
    k = min(target, n_avail)
    if k < 8:
        return []
    chosen = rng.choice(pool.index.to_numpy(), size=k, replace=False, p=w / w.sum())
    return list(chosen)


def run(pc: dict) -> dict:
    rng = np.random.default_rng(pc["seed"])
    pool = make_platform_players(pc, rng)
    base = vs.default_config()
    chem = vs.make_chemistry(pool, base, rng)
    start = dt.date.fromisoformat(pc["start_date"])
    out = {k: [] for k in ("games", "game_players", "attack_stats", "teams", "attendance")}
    for d in range(pc["weeks"] * 7):
        day = start + dt.timedelta(days=d)
        busy: set = set()   # 同一天只去一個時段
        for v in pc["venues"]:
            if day.weekday() not in v["weekdays"]:
                continue
            vcfg = copy.deepcopy(base)
            vcfg.update(sessions=v["sessions"], target_by_teams=v["target_by_teams"],
                        turnout_min=v["turnout"][0], turnout_max=v["turnout"][1])
            hm = v["history_methods"]
            for session in v["sessions"]:
                present = sample_session_players(pool, v, pc, rng, busy)
                if not present:
                    continue
                busy.update(present)
                m = str(rng.choice(list(hm), p=np.array(list(hm.values())) / sum(hm.values())))
                parts = vs.simulate_session(day.isoformat(), session, present, pool, chem, vcfg, rng, m)
                for name, rows in zip(("games", "game_players", "attack_stats", "teams", "attendance"), parts):
                    for r in rows:
                        r = dict(r)
                        if "session_id" in r:
                            r["session_id"] = f"{v['venue_id']}_{r['session_id']}"
                        if "game_id" in r:
                            r["game_id"] = f"{v['venue_id']}_{r['game_id']}"
                        r = {"venue_id": v["venue_id"], **r}
                        out[name].append(r)
    res = {k: pd.DataFrame(rows) for k, rows in out.items()}
    res["pool"], res["chem"] = pool, chem
    return res


def write_outputs(res: dict, pc: dict, outdir: str):
    data_dir, truth_dir = os.path.join(outdir, "data"), os.path.join(outdir, "truth")
    os.makedirs(data_dir, exist_ok=True)
    os.makedirs(truth_dir, exist_ok=True)
    pool = res["pool"]
    # data/：平台看得到的資料
    pool[["player_id", "gender", "years_playing", "self_level", "main_position", "venue_home"]].to_csv(
        os.path.join(data_dir, "players.csv"), index=False)
    pd.DataFrame([{k: (json.dumps(v[k], ensure_ascii=False) if isinstance(v[k], (dict, list)) else v[k])
                   for k in ("venue_id", "name", "region", "weekdays", "sessions", "target_by_teams",
                             "turnout", "level_min", "level_max")} for v in pc["venues"]]).to_csv(
        os.path.join(data_dir, "venues.csv"), index=False)
    for name in ("teams", "games", "game_players", "attack_stats", "attendance"):
        res[name].to_csv(os.path.join(data_dir, f"{name}.csv"), index=False)
    # matches.csv：一局一列、雙方名單直接展開（提案要求的精簡格式）
    teams = res["teams"].set_index(["session_id", "team"])["players"]
    g = res["games"]
    m = g[["game_id", "date", "venue_id", "session", "team_a", "team_b", "score_a", "score_b", "target_points"]].copy()
    m["players_a"] = [teams[(s, t)] for s, t in zip(g.session_id, g.team_a)]
    m["players_b"] = [teams[(s, t)] for s, t in zip(g.session_id, g.team_b)]
    m.to_csv(os.path.join(data_dir, "matches.csv"), index=False)
    # truth/：只有模擬才知道，只能拿來驗證
    pool[["player_id", "true_skill", "report_bias", "cross_venue", "attend_prob"]].rename(
        columns={"true_skill": "true_theta"}).to_csv(os.path.join(truth_dir, "players_truth.csv"), index=False)
    pd.DataFrame([dict(venue_id=v["venue_id"], mu=v["mu"], alpha=v["alpha"], share=v["share"])
                  for v in pc["venues"]]).to_csv(os.path.join(truth_dir, "venues_truth.csv"), index=False)
    pd.DataFrame([dict(player_1=a, player_2=b, chemistry=c) for (a, b), c in res["chem"].items()]).to_csv(
        os.path.join(truth_dir, "pair_chemistry.csv"), index=False)
    meta = dict(version=VERSION, generated_at=dt.datetime.now().isoformat(timespec="seconds"),
                platform_config=pc, engine_config=vs.default_config(),
                self_report_bias=dict(
                    formula="reported = θ + b0 + b_male·male + b_years·(years_playing − 3) + b_skill·θ + alpha[venue_home] + N(0, sd)；"
                            "self_level = 1 + 落在 level_cuts 的位置",
                    b0=pc["report_b0"], b_male=pc["report_b_male"], b_years=pc["report_b_years"],
                    years_center=3, b_skill=pc["report_b_skill"], sd=pc["report_sd"],
                    alpha={v["venue_id"]: v["alpha"] for v in pc["venues"]}, level_cuts=pc["level_cuts"]),
                note="合成資料（simulated data），非真實紀錄。")
    with open(os.path.join(truth_dir, "config.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)


def summarize(res: dict) -> str:
    g, gp, pool = res["games"], res["game_players"], res["pool"]
    played = gp.groupby("player_id")["venue_id"].nunique()
    lines = [
        f"球員 {len(pool)} 人（出場 {gp.player_id.nunique()}），時段 {g.session_id.nunique()}，局數 {len(g)}",
        "各館局數 " + str(g.venue_id.value_counts().sort_index().to_dict()),
        "各館平均分差 " + str(g.groupby("venue_id").margin.mean().round(2).to_dict()),
        f"在 2 館以上出賽的球員 {int((played >= 2).sum())} 人",
        f"自報程度與真實實力相關 {np.corrcoef(pool.self_level, pool.true_skill)[0, 1]:.2f}",
    ]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description="跨球館排球平台模擬資料產生器")
    ap.add_argument("--seed", type=int)
    ap.add_argument("--weeks", type=int)
    ap.add_argument("--players", type=int)
    ap.add_argument("--cross", type=float, help="跨館球員比例，例如 0、0.1、0.3")
    ap.add_argument("--report-sd", type=float, help="自報的個人認知誤差標準差")
    ap.add_argument("--config", help="JSON 檔，覆寫部分參數")
    ap.add_argument("--out", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "platform"))
    a = ap.parse_args()
    pc = platform_config()
    if a.config:
        with open(a.config, encoding="utf-8") as f:
            pc.update(json.load(f))
    for key, val in (("seed", a.seed), ("weeks", a.weeks), ("n_players", a.players),
                     ("cross_venue_share", a.cross), ("report_sd", a.report_sd)):
        if val is not None:
            pc[key] = val
    res = run(pc)
    write_outputs(res, pc, a.out)
    print(summarize(res))
    print(f"已輸出到 {os.path.abspath(a.out)}")


if __name__ == "__main__":
    main()
