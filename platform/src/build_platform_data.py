"""把跨球館模擬資料與 R 平台模型輸出整理成示範頁用的 platform-data.js。

輸入（全部是模擬資料）：
  volley-sim/platform/data/*.csv          Python 跨球館模擬器（4 館、150 人、8 週）
  volley-sim/platform/truth/*.csv         模擬真值（只有模擬才有，頁面上預設隱藏）
  r-rating-model/output/*_platform_sim.*  analysis/07_platform_demo_export.R 的輸出
執行：python3 platform/src/build_platform_data.py（在 repo 根目錄）
"""
from __future__ import annotations

import csv
import json
import math
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve()
# 往上找含 volley-sim/ 的資料夾當專案根目錄（repo 根目錄 platform/src/ 或專案資料夾 website/platform/src/ 都能跑）
ROOT = next(p for p in HERE.parents if (p / "volley-sim").is_dir())
SIM = ROOT / "volley-sim" / "platform"
ROUT = ROOT / "r-rating-model" / "output"
OUT = HERE.parents[1] / "platform-data.js"

LEVEL_CUTS_TRUE = [-1.2, -0.4, 0.4, 1.2]  # volley-sim 自報 1~5 級的切點（真值尺度）
SESSION_ZH = {"dinner": "晚餐場", "late": "宵夜場", "night": "夜場"}
WEEKDAY_ZH = "一二三四五六日"


def rd(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def r3(x: float) -> float:
    return round(float(x), 3)


def main() -> None:
    scale = json.loads((ROUT / "platform_sim_scale.json").read_text())
    k = scale["k"]
    cuts = [r3(k * c) for c in LEVEL_CUTS_TRUE]  # 模型尺度上的等級切點

    venues_raw = rd(SIM / "data" / "venues.csv")
    alpha = {v["venue"]: v for v in rd(ROUT / "venues_platform_sim.csv")}
    venues = []
    for v in venues_raw:
        sess = json.loads(v["sessions"])
        days = json.loads(v["weekdays"])
        venues.append({
            "id": v["venue_id"], "name": v["name"], "region": v["region"],
            "days": "、".join("週" + WEEKDAY_ZH[d] for d in days),
            "sessions": [{"key": s, "name": SESSION_ZH.get(s, s), "start": c["start"], "minutes": c["minutes"]}
                         for s, c in sess.items()],
            "target": sorted(set(json.loads(v["target_by_teams"]).values())),
            "target_by": {int(a): b for a, b in json.loads(v["target_by_teams"]).items()},
            "level_min": int(float(v["level_min"])) if v["level_min"] else None,
            "level_max": int(float(v["level_max"])) if v["level_max"] else None,
            "alpha": r3(alpha[v["venue_id"]]["alpha"]), "alpha_se": r3(alpha[v["venue_id"]]["se"]),
        })

    players_raw = {p["player_id"]: p for p in rd(SIM / "data" / "players.csv")}
    truth = {p["player_id"]: p for p in rd(SIM / "truth" / "players_truth.csv")}
    ratings = {r["player"]: r for r in rd(ROUT / "ratings_platform_sim.csv")}

    games = {g["game_id"]: g for g in rd(SIM / "data" / "games.csv")}
    gp = rd(SIM / "data" / "game_players.csv")
    att = rd(SIM / "data" / "attack_stats.csv")
    attendance = rd(SIM / "data" / "attendance.csv")

    # 每人每館紀錄
    per = defaultdict(lambda: defaultdict(lambda: {"sets": 0, "wins": 0, "pf": 0, "pa": 0, "nights": set(),
                                                    "first": "9999", "last": "0000"}))
    hist = defaultdict(list)
    for r in gp:
        d = per[r["player_id"]][r["venue_id"]]
        d["sets"] += 1; d["wins"] += int(r["won"]); d["pf"] += int(r["points_for"]); d["pa"] += int(r["points_against"])
        d["nights"].add(r["session_id"]); d["first"] = min(d["first"], r["date"]); d["last"] = max(d["last"], r["date"])
        hist[r["player_id"]].append(r)
    atk = defaultdict(lambda: [0, 0, 0, 0, 0])
    for r in att:
        a = atk[r["player_id"]]
        a[0] += int(r["attempts"]); a[1] += int(r["kills"]); a[2] += int(r["errors"]); a[3] += int(r["aces"]); a[4] += int(r["digs"])

    # 線上更新軌跡：平移到與批次估計相同的中心（批次估計全體平均 = 0）
    trace = defaultdict(list)
    for r in rd(ROUT / "online_trace_platform_sim.csv"):
        trace[r["player"]].append((int(r["sets"]), float(r["mu"]), float(r["sd"])))
    finals = [v[-1][1] for v in trace.values() if v]
    shift = sum(finals) / len(finals)

    players = []
    for pid, p in sorted(players_raw.items()):
        rt = ratings[pid]
        tr = trace.get(pid, [])
        if len(tr) > 40:  # 抽樣到最多約 40 點，保留第一點與最後一點
            step = len(tr) / 39
            tr = [tr[min(len(tr) - 1, round(i * step))] for i in range(40)]
        lv = int(p["self_level"])
        prior_mu = float(alpha[p["venue_home"]]["alpha"]) + scale["beta"] * (lv - 3)  # 先驗平均：主場平均 + 自報
        recent = sorted(hist[pid], key=lambda r: (r["date"], r["game_id"]))[-6:][::-1]
        a = atk[pid]
        players.append({
            "id": pid, "gender": "男" if p["gender"] == "M" else "女", "years": int(p["years_playing"]),
            "pos": p["main_position"], "self": lv, "home": p["venue_home"],
            "theta": r3(rt["theta"]), "se": r3(rt["se"]), "sets": int(rt["sets"]), "nv": int(rt["n_venues"]),
            "prior": r3(prior_mu),
            "venues": [{"v": v, "sets": d["sets"], "wins": d["wins"], "pf": d["pf"], "pa": d["pa"],
                        "nights": len(d["nights"]), "first": d["first"], "last": d["last"]}
                       for v, d in sorted(per[pid].items(), key=lambda kv: -kv[1]["sets"])],
            "recent": [{"d": r["date"], "v": r["venue_id"], "s": SESSION_ZH.get(r["session"], r["session"]),
                        "pf": int(r["points_for"]), "pa": int(r["points_against"]), "w": int(r["won"])} for r in recent],
            "atk": {"att": a[0], "kill": a[1], "err": a[2], "ace": a[3], "dig": a[4]},
            "trace": [[n, r3(mu - shift), r3(sd)] for n, mu, sd in tr],
            "truth": r3(k * float(truth[pid]["true_theta"])),
        })

    # 分隊示範：每館最後一晚的出席名單
    nights = defaultdict(list)
    for r in attendance:
        nights[(r["venue_id"], r["session_id"], r["date"], r["session"])].append(r["player_id"])
    last_night = {}
    for (v, sid, d, s), ids in nights.items():
        if v not in last_night or (d, s) > (last_night[v]["date"], last_night[v]["session_key"]):
            last_night[v] = {"venue": v, "session_id": sid, "date": d, "session_key": s,
                             "session": SESSION_ZH.get(s, s), "players": sorted(ids)}

    xs = [p["sets"] for p in players]; ys = [1 / p["se"] ** 2 for p in players]
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sum((x - mx) ** 2 for x in xs)
    prec = (my - b * mx, b)

    # 驗證數字（給頁面上的「模型可信嗎」小卡）
    data = {
        "meta": {
            "source": "volley-sim/platform（seed 20261126，4 館、150 人、8 週，跨館比例 10%）＋ R fit_platform_model()",
            "n_games": scale["n_games"], "n_players": scale["n_players"],
            "spearman_model": r3(scale["spearman_model_truth"]), "spearman_self": r3(scale["spearman_self_truth"]),
            "coverage": r3(scale["coverage"]), "online_batch_cor": r3(scale["online_batch_cor"]),
            "sigma": r3(scale["sigma"]), "sigma_v": r3(scale["sigma_v"]), "beta": r3(scale["beta"]),
            "delta": r3(scale["delta"]), "k": r3(k), "cuts": cuts,
            "rule": {"pass": 0.8, "block": 0.2, "q_alpha5": 0.63},
            "shift": r3(shift),
            # 每多打一局增加的精確度（1/se² 對局數的迴歸斜率），用來估「還要打幾局」
            "prec0": r3(prec[0]), "prec_per_set": round(prec[1], 5),
        },
        "venues": venues, "players": players, "nights": list(last_night.values()),
    }
    OUT.write_text("// 自動產生：platform/src/build_platform_data.py。全部是模擬資料。\nwindow.PLATFORM_DATA=" +
                   json.dumps(data, ensure_ascii=False, separators=(",", ":")) + ";\n", encoding="utf-8")
    print(f"寫出 {OUT}（{OUT.stat().st_size/1024:.0f} KB），球員 {len(players)}、球館 {len(venues)}")


if __name__ == "__main__":
    main()
