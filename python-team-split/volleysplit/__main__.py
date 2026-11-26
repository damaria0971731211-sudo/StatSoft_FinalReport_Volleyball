"""命令列入口。

  python -m volleysplit split  data/sample_signups.csv --session 晚餐場 [--ratings ratings.csv]
  python -m volleysplit demo   --players 28 --seed 1
  python -m volleysplit simulate --reps 500 --out results
  python -m volleysplit scenarios --reps 300 --out results
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import random
from dataclasses import asdict

from .registration import Registry, assign_tiers, attach_ratings, load_players_csv
from .simulate import METRICS, SimConfig, make_pool, night_metrics, play_night, run_simulation, summarize
from .teaming import METHOD_KEYS, METHODS, choose_n_teams, describe


def _print_teams(name: str, teams) -> None:
    print(f"\n== {name} ==")
    for t in describe(teams):
        print(
            f"{t['team']}（{t['size']}人，舉球{t['setters']}，自報平均{t['mean_self_level']}，"
            f"估計強度{t['strength_est']:+.2f}）：{'、'.join(t['members'])}"
        )


def cmd_split(args) -> None:
    players = [p for p in load_players_csv(args.csv) if p.session == args.session]
    if args.ratings:
        attach_ratings(players, args.ratings)
    reg = Registry(args.session, capacity=args.capacity)
    for p in players:
        reg.sign_up(p)
    print(f"{args.session}：正取 {len(reg.confirmed)} 人，候補 {len(reg.waitlist)} 人")
    tiers = assign_tiers(reg.confirmed, 3)
    print("分級：" + "，".join(f"{c}={t}" for c, t in tiers.items()))
    n_teams = args.teams or choose_n_teams(len(reg.confirmed))
    rng = random.Random(args.seed)
    methods = METHODS if args.method == "all" else {METHOD_KEYS[args.method]: METHODS[METHOD_KEYS[args.method]]}
    for name, fn in methods.items():
        _print_teams(name, fn(reg.confirmed, n_teams, random.Random(rng.random())))


def cmd_demo(args) -> None:
    """產生一晚的示範：名單、三種分隊、比賽結果，存成 JSON 給網站用。"""
    cfg = SimConfig()
    rng = random.Random(args.seed)
    pool = make_pool(args.players, rng, cfg)
    n_teams = choose_n_teams(args.players)
    tiers = assign_tiers(pool, 3)
    out = {
        "seed": args.seed,
        "players": [
            {
                "code": p.code,
                "self_level": p.self_level,
                "level_name": p.level_name,
                "position": p.position,
                "rating": round(p.rating, 3),
                "n_games": p.n_games,
                "tier": tiers[p.code],
                "true_skill": round(p.true_skill, 3),
            }
            for p in pool
        ],
        "methods": {},
    }
    for name, fn in METHODS.items():
        teams = fn(pool, n_teams, random.Random(args.seed + 1))
        night = play_night(teams, random.Random(args.seed + 2), cfg)
        _print_teams(name, teams)
        m = night_metrics(teams, night)
        print("  " + "，".join(f"{k}={v:.2f}" for k, v in m.items()))
        out["methods"][name] = {"teams": describe(teams), "games": night["games"], "metrics": m}
    if args.out:
        os.makedirs(args.out, exist_ok=True)
        path = os.path.join(args.out, "demo_night.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=1)
        print(f"\n已輸出 {path}")


def _write_runs(rows, path) -> None:
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def cmd_simulate(args) -> None:
    cfg = SimConfig(courts=args.courts)
    rows = run_simulation(args.reps, args.seed, cfg)
    summary = summarize(rows)
    summary["config"] = asdict(cfg)
    summary["seed"] = args.seed
    os.makedirs(args.out, exist_ok=True)
    _write_runs(rows, os.path.join(args.out, "sim_runs.csv"))
    with open(os.path.join(args.out, "summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=1)
    labels = summary["metric_labels"]
    print(f"模擬 {summary['n_nights']} 晚（seed={args.seed}）")
    for m, d in summary["per_method"].items():
        print(f"\n[{m}]")
        for k in METRICS:
            lo, hi = d[k]["ci95"]
            print(f"  {labels[k]}：{d[k]['mean']:.3f}（95% CI {lo:.3f}～{hi:.3f}）")
    for name, d in summary["comparisons"].items():
        print(f"\n[{name}] 配對差")
        for k in METRICS:
            lo, hi = d[k]["ci95"]
            print(f"  {labels[k]}：{d[k]['mean_diff']:+.3f}（95% CI {lo:+.3f}～{hi:+.3f}，p={d[k]['p_value']:.4f}）")
    print(f"\n已輸出 {args.out}/sim_runs.csv、{args.out}/summary.json")


def cmd_scenarios(args) -> None:
    """敏感度分析：自報程度多不準、模型評分多不準時，三種方法的平均分差如何變化。"""
    grid = []
    for srs in (0.3, 0.7, 1.2):
        for rsd in (0.3, 0.8, 1.5):
            cfg = SimConfig(self_report_sd=srs, rating_sd=rsd)
            rows = run_simulation(args.reps, args.seed, cfg)
            entry = {"self_report_sd": srs, "rating_sd": rsd}
            for m in METHODS:
                xs = [r for r in rows if r["method"] == m]
                entry[m] = {k: sum(r[k] for r in xs) / len(xs) for k in ("mean_margin", "close_rate", "games_sd")}
            grid.append(entry)
            print(
                f"自報雜訊 {srs}、評分誤差 {rsd}："
                + "，".join(f"{m} 平均分差 {entry[m]['mean_margin']:.2f}" for m in METHODS)
            )
    os.makedirs(args.out, exist_ok=True)
    with open(os.path.join(args.out, "scenarios.json"), "w", encoding="utf-8") as f:
        json.dump({"reps_per_cell": args.reps, "seed": args.seed, "grid": grid}, f, ensure_ascii=False, indent=1)
    print(f"已輸出 {args.out}/scenarios.json")


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(prog="volleysplit", description="政大野場排球報名分隊原型")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("split", help="讀報名 CSV 並分隊")
    s.add_argument("csv")
    s.add_argument("--session", default="晚餐場")
    s.add_argument("--ratings", help="R 模型輸出的評分 CSV（code,rating,n_games）")
    s.add_argument("--capacity", type=int, default=36)
    s.add_argument("--teams", type=int)
    s.add_argument("--method", choices=["all", *METHOD_KEYS], default="all")
    s.add_argument("--seed", type=int, default=1)
    s.set_defaults(func=cmd_split)

    d = sub.add_parser("demo", help="模擬一晚並輸出示範 JSON")
    d.add_argument("--players", type=int, default=28)
    d.add_argument("--seed", type=int, default=1)
    d.add_argument("--out", default="results")
    d.set_defaults(func=cmd_demo)

    m = sub.add_parser("simulate", help="蒙地卡羅比較三種分隊方法")
    m.add_argument("--reps", type=int, default=500)
    m.add_argument("--seed", type=int, default=2026)
    m.add_argument("--courts", type=int, default=1)
    m.add_argument("--out", default="results")
    m.set_defaults(func=cmd_simulate)

    c = sub.add_parser("scenarios", help="自報/評分準確度的敏感度分析")
    c.add_argument("--reps", type=int, default=200)
    c.add_argument("--seed", type=int, default=2026)
    c.add_argument("--out", default="results")
    c.set_defaults(func=cmd_scenarios)

    args = ap.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
