#!/usr/bin/env python3
"""野場排球平衡分隊與檢查（balance-teams skill 的執行腳本）

只用 Python 標準函式庫。流程：
  1. 檢查名單（欄位、重複 ID、缺值、範圍、隊數與人數是否可行）
     有任何「錯誤」就停止，不產生分隊，只輸出 STOP 報告。
  2. 以實力（rating 優先，否則 level）蛇形選秀，先把舉球員分散到各隊。
  3. 兩兩交換球員做局部搜尋，降低「各隊平均實力的全距」。
  4. 與同樣隊伍人數的隨機分隊比較（基準方法），報告百分位。
  5. 小名單（<=12 人）可加 --verify-bruteforce 窮舉最佳解做獨立檢核。

用法：
  python balance_teams.py ROSTER.csv --teams 5 --out runs/normal --seed 115
"""
import argparse
import csv
import itertools
import json
import math
import random
import statistics
import sys
from pathlib import Path

POSITIONS = {"S", "OH", "MB", "OPP", "L", "ANY"}
LEVEL_MIN, LEVEL_MAX = 1, 5
RATING_MIN, RATING_MAX = 0.0, 10.0


# ---------------------------------------------------------------- 讀檔與檢查
def load_and_validate(path, n_teams, min_size, max_size):
    errors, warnings, players = [], [], []
    try:
        with open(path, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            cols = [c.strip() for c in (reader.fieldnames or [])]
            rows = list(reader)
    except FileNotFoundError:
        return [], [f"找不到名單檔：{path}"], [], 0

    for need in ("player_id", "level", "position"):
        if need not in cols:
            errors.append(f"缺少必要欄位 {need}（目前欄位：{', '.join(cols) or '無'}）")
    if errors:
        return [], errors, warnings, len(rows)
    has_rating = "rating" in cols

    seen = {}
    for i, raw in enumerate(rows, start=2):  # 第 1 列是標題
        r = {k.strip(): (v or "").strip() for k, v in raw.items() if k}
        pid = r.get("player_id", "")
        if not pid:
            errors.append(f"第 {i} 列：player_id 空白")
            continue
        if pid in seen:
            errors.append(f"第 {i} 列：player_id {pid} 與第 {seen[pid]} 列重複")
            continue
        seen[pid] = i

        level = None
        lv = r.get("level", "")
        if lv == "":
            if not (has_rating and r.get("rating")):
                errors.append(f"第 {i} 列（{pid}）：level 空白且沒有 rating")
        else:
            try:
                level = int(lv)
                if not LEVEL_MIN <= level <= LEVEL_MAX:
                    errors.append(f"第 {i} 列（{pid}）：level={lv} 超出 {LEVEL_MIN}–{LEVEL_MAX}")
            except ValueError:
                errors.append(f"第 {i} 列（{pid}）：level={lv!r} 不是整數")

        rating = None
        if has_rating and r.get("rating"):
            try:
                rating = float(r["rating"])
                if math.isnan(rating) or not RATING_MIN <= rating <= RATING_MAX:
                    errors.append(f"第 {i} 列（{pid}）：rating={r['rating']} 超出 {RATING_MIN}–{RATING_MAX}")
            except ValueError:
                errors.append(f"第 {i} 列（{pid}）：rating={r['rating']!r} 不是數字")

        pos = (r.get("position") or "ANY").upper()
        if pos not in POSITIONS:
            warnings.append(f"第 {i} 列（{pid}）：position={pos} 不認得，當作 ANY")
            pos = "ANY"

        strength = rating if rating is not None else (level * 2.0 if level is not None else None)
        players.append({"player_id": pid, "level": level, "rating": rating,
                        "position": pos, "strength": strength})

    n = len(rows)
    if n_teams < 2:
        errors.append(f"隊數 {n_teams} 必須至少 2")
    elif n < n_teams * min_size:
        errors.append(f"報名 {n} 人不夠分成 {n_teams} 隊（每隊至少 {min_size} 人，需 {n_teams * min_size} 人）"
                      f"；可改成 {max(n // min_size, 0)} 隊")
    elif n > n_teams * max_size:
        errors.append(f"報名 {n} 人超過 {n_teams} 隊上限（每隊最多 {max_size} 人，共 {n_teams * max_size} 人）"
                      f"；可改成 {math.ceil(n / max_size)} 隊或設定候補")

    if has_rating:
        mixed = sum(p["rating"] is None for p in players)
        if 0 < mixed < len(players):
            warnings.append(f"有 {mixed} 人沒有 rating，改用 level×2 換算，兩種尺度混用請留意")
    n_setters = sum(p["position"] == "S" for p in players)
    if not errors and n_setters < n_teams:
        warnings.append(f"舉球員只有 {n_setters} 位，少於隊數 {n_teams}，有隊伍會沒有舉球員")
    return players, errors, warnings, n


# ---------------------------------------------------------------- 分隊
def team_sizes(n, k):
    base, extra = divmod(n, k)
    return [base + (1 if t < extra else 0) for t in range(k)]


def objective(teams):
    means = [statistics.fmean(p["strength"] for p in t) for t in teams]
    no_setter = sum(1 for t in teams if not any(p["position"] == "S" for p in t))
    return (max(means) - min(means)) + 0.5 * no_setter, means


def snake_draft(players, k, rng):
    sizes = team_sizes(len(players), k)
    teams = [[] for _ in range(k)]
    setters = sorted([p for p in players if p["position"] == "S"],
                     key=lambda p: (-p["strength"], rng.random()))
    others = sorted([p for p in players if p["position"] != "S"],
                    key=lambda p: (-p["strength"], rng.random()))
    order = list(range(k)) + list(range(k - 1, -1, -1))
    i = 0
    for p in setters + others:
        while True:
            t = order[i % len(order)]
            i += 1
            if len(teams[t]) < sizes[t]:
                teams[t].append(p)
                break
    return teams


def improve_by_swaps(teams, max_rounds=200):
    best, _ = objective(teams)
    for _ in range(max_rounds):
        improved = False
        for a, b in itertools.combinations(range(len(teams)), 2):
            for i in range(len(teams[a])):
                for j in range(len(teams[b])):
                    teams[a][i], teams[b][j] = teams[b][j], teams[a][i]
                    val, _ = objective(teams)
                    if val < best - 1e-12:
                        best, improved = val, True
                    else:
                        teams[a][i], teams[b][j] = teams[b][j], teams[a][i]
        if not improved:
            break
    return teams


def random_split(players, k, rng):
    shuffled = players[:]
    rng.shuffle(shuffled)
    sizes, teams, start = team_sizes(len(players), k), [], 0
    for s in sizes:
        teams.append(shuffled[start:start + s])
        start += s
    return teams


def bruteforce_best(players, k):
    """窮舉所有同樣人數配置，回傳最小 objective（只給小名單做獨立檢核）。"""
    sizes = team_sizes(len(players), k)
    best = math.inf

    def rec(remaining, idx, teams):
        nonlocal best
        if idx == k:
            best = min(best, objective(teams)[0])
            return
        first, rest = remaining[0], remaining[1:]
        for combo in itertools.combinations(rest, sizes[idx] - 1):
            chosen = [first, *combo]
            left = [p for p in rest if p not in combo]
            rec(left, idx + 1, teams + [chosen])

    rec(players, 0, [])
    return best


# ---------------------------------------------------------------- 主程式
def main():
    ap = argparse.ArgumentParser(description="野場排球平衡分隊與檢查")
    ap.add_argument("roster")
    ap.add_argument("--teams", type=int, required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--seed", type=int, default=115)
    ap.add_argument("--min-size", type=int, default=4)
    ap.add_argument("--max-size", type=int, default=6)
    ap.add_argument("--baseline-reps", type=int, default=2000)
    ap.add_argument("--verify-bruteforce", action="store_true")
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    players, errors, warnings, n_rows = load_and_validate(args.roster, args.teams, args.min_size, args.max_size)
    report = {"roster": str(args.roster), "teams_requested": args.teams, "seed": args.seed,
              "n_rows": n_rows, "n_players": len(players), "errors": errors, "warnings": warnings}

    if errors:
        report["status"] = "STOP"
        (out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        write_md(out, report)
        print("STOP：名單有錯誤，未產生分隊。")
        for e in errors:
            print("  錯誤：", e)
        sys.exit(1)

    rng = random.Random(args.seed)
    teams = improve_by_swaps(snake_draft(players, args.teams, rng))
    obj, means = objective(teams)
    gap = max(means) - min(means)

    base_gaps = []
    for _ in range(args.baseline_reps):
        _, m = objective(random_split(players, args.teams, rng))
        base_gaps.append(max(m) - min(m))
    base_gaps.sort()
    pct = sum(g <= gap + 1e-12 for g in base_gaps) / len(base_gaps)

    report.update({
        "status": "OK",
        "teams": [{"team": t + 1, "size": len(tm), "mean_strength": round(means[t], 3),
                   "sum_strength": round(sum(p["strength"] for p in tm), 3),
                   "setters": sum(p["position"] == "S" for p in tm),
                   "players": [p["player_id"] for p in tm]} for t, tm in enumerate(teams)],
        "mean_gap": round(gap, 3),
        "objective": round(obj, 3),
        "teams_without_setter": sum(1 for tm in teams if not any(p["position"] == "S" for p in tm)),
        "baseline_random": {"reps": args.baseline_reps,
                            "mean_gap_mean": round(statistics.fmean(base_gaps), 3),
                            "mean_gap_p05": round(base_gaps[int(0.05 * len(base_gaps))], 3),
                            "mean_gap_median": round(statistics.median(base_gaps), 3),
                            "share_random_at_least_as_good": round(pct, 4)},
    })
    if args.verify_bruteforce:
        if len(players) > 12:
            report["bruteforce"] = "略過：超過 12 人，窮舉太慢"
        else:
            bf = bruteforce_best(players, args.teams)
            report["bruteforce"] = {"best_objective": round(bf, 6), "ours": round(obj, 6),
                                    "match": abs(bf - obj) < 1e-9}

    with open(out / "teams.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["team", "player_id", "position", "level", "rating", "strength"])
        for t, tm in enumerate(teams, start=1):
            for p in sorted(tm, key=lambda p: -p["strength"]):
                w.writerow([t, p["player_id"], p["position"], p["level"] if p["level"] is not None else "",
                            p["rating"] if p["rating"] is not None else "", p["strength"]])
    (out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    write_md(out, report)
    print(f"OK：{args.teams} 隊，平均實力全距 {gap:.3f}；隨機分隊全距中位數 "
          f"{report['baseline_random']['mean_gap_median']}")


def write_md(out, r):
    L = [f"# 分隊報告：{r['status']}", "",
         f"- 名單：`{r['roster']}`，資料 {r['n_rows']} 列，通過 ID 檢查 {r['n_players']} 人，要求 {r['teams_requested']} 隊，seed={r['seed']}"]
    if r["errors"]:
        L += ["", "## 錯誤（已停止，未產生分隊）", *[f"- {e}" for e in r["errors"]]]
    if r["warnings"]:
        L += ["", "## 警告", *[f"- {w}" for w in r["warnings"]]]
    if r["status"] == "OK":
        L += ["", "## 各隊", "", "| 隊 | 人數 | 平均實力 | 舉球員 | 球員 |", "|---|---|---|---|---|"]
        for t in r["teams"]:
            L.append(f"| {t['team']} | {t['size']} | {t['mean_strength']} | {t['setters']} | {', '.join(t['players'])} |")
        b = r["baseline_random"]
        L += ["", "## 檢查",
              f"- 各隊平均實力全距：{r['mean_gap']}",
              f"- 沒有舉球員的隊數：{r['teams_without_setter']}",
              f"- 基準（{b['reps']} 次隨機分隊）全距：平均 {b['mean_gap_mean']}，中位數 {b['mean_gap_median']}，"
              f"第 5 百分位 {b['mean_gap_p05']}",
              f"- 隨機分隊至少一樣平衡的比例：{b['share_random_at_least_as_good']}"]
        if "bruteforce" in r:
            L.append(f"- 窮舉檢核：{r['bruteforce']}")
        L += ["", "> 這份報告只檢查「分隊是否平衡」，不代表實力評分本身正確，也不是統計結論。"]
    (out / "report.md").write_text("\n".join(L) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
