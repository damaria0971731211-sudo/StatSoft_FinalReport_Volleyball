"""交叉驗證：把三種分隊方法丟進另一套模擬引擎（volley-sim）再比一次。

volley-sim 有逐球攻防、搭檔默契、5 種位置，比本套件內建的簡化模型更接近真實。
分隊方法看不到默契，所以這也檢驗「沒考慮默契時，平衡分隊還有沒有用」。

  python -m volleysplit.crosscheck --sim /path/to/volley_sim.py --reps 300 --out results
需要 numpy、pandas（volley-sim 的依賴）。
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import math
import os
import random

from .registration import Player
from .simulate import METRICS, SimConfig, night_metrics, play_night, summarize
from .teaming import METHODS, choose_n_teams

POS_MAP = {"舉球": "舉球", "自由": "自由", "不限": "不限"}  # 主攻／副攻／接應 → 攻擊


def load_engine(path: str):
    spec = importlib.util.spec_from_file_location("volley_sim", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def run_crosscheck(vs, reps: int = 300, seed: int = 2026, rating_sd: float = 0.8) -> list[dict]:
    import numpy as np

    vcfg = vs.default_config()
    cfg = SimConfig()  # 輪替規則沿用本套件設定，只把「單局怎麼打」換成 volley-sim
    master = random.Random(seed)
    rows = []
    for r in range(reps):
        night_seed = master.randrange(2**31)
        nrng = np.random.default_rng(night_seed)
        pool = vs.make_players(vcfg, nrng)
        chem = vs.make_chemistry(pool, vcfg, nrng)
        prng = random.Random(night_seed)
        n = prng.randint(cfg.min_players, cfg.max_players)
        ids = prng.sample(list(pool.index), n)
        players = []
        for pid in ids:
            row = pool.loc[pid]
            g = prng.randint(0, cfg.max_games_history)
            true = float(row["true_skill"])
            players.append(
                Player(
                    code=pid,
                    self_level=int(row["self_level"]),
                    position=POS_MAP.get(row["main_position"], "攻擊"),
                    rating=true + prng.gauss(0, rating_sd / math.sqrt(1 + g / 4)),
                    n_games=g,
                    true_skill=true,
                )
            )
        k = choose_n_teams(n)
        for name, fn in METHODS.items():
            teams = fn(players, k, random.Random(night_seed + 1))
            team_ids = [[p.code for p in t] for t in teams]
            grng = np.random.default_rng(night_seed + 2)  # 三種方法用同一串比賽亂數

            def game(a: int, b: int, target: int) -> tuple[int, int]:
                res = vs.simulate_game(team_ids[a], team_ids[b], pool, chem, vcfg, grng, target)
                return res["score_a"], res["score_b"]

            strengths = [vs.team_strength(t, pool, chem, vcfg) for t in team_ids]
            night = play_night(teams, random.Random(night_seed + 3), cfg, game=game, strengths=strengths)
            row = {"rep": r + 1, "method": name, "n_players": n, "n_teams": k}
            row.update(night_metrics(teams, night))
            rows.append(row)
    return rows


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description="用 volley-sim 交叉驗證三種分隊方法")
    ap.add_argument("--sim", default=os.path.join("..", "volley-sim", "volley_sim.py"))
    ap.add_argument("--reps", type=int, default=300)
    ap.add_argument("--seed", type=int, default=2026)
    ap.add_argument("--out", default="results")
    args = ap.parse_args(argv)
    vs = load_engine(args.sim)
    rows = run_crosscheck(vs, args.reps, args.seed)
    s = summarize(rows)
    s["engine"] = "volley-sim"
    os.makedirs(args.out, exist_ok=True)
    with open(os.path.join(args.out, "crosscheck_summary.json"), "w", encoding="utf-8") as f:
        json.dump(s, f, ensure_ascii=False, indent=1)
    for m, d in s["per_method"].items():
        print(m, "，".join(f"{s['metric_labels'][k]} {d[k]['mean']:.3f}" for k in METRICS))
    for name, d in s["comparisons"].items():
        k = "mean_margin"
        print(f"{name} 平均分差 {d[k]['mean_diff']:+.3f}（95% CI {d[k]['ci95'][0]:+.3f}～{d[k]['ci95'][1]:+.3f}）")
    print(f"已輸出 {args.out}/crosscheck_summary.json")


if __name__ == "__main__":
    main()
