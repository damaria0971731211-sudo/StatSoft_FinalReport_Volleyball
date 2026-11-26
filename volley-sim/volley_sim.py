"""
volley_sim.py — 政大體育館排球野場（晚餐場／消夜場）模擬資料產生器

用途：產生「虛擬球員 × 多個晚上 × 每局名單與比分」的合成資料，
讓 R 實力評分模型、Python 分隊原型、成果網站都讀同一份格式。

這是合成資料，不是真實紀錄。所有參數集中在 DEFAULT_CONFIG，
每個參數都標明「來源」或「假設」，執行時完整寫入 truth/config.json。

用法：
    python volley_sim.py                       # 用預設參數產生 data/ 與 truth/
    python volley_sim.py --seed 7 --weeks 4    # 換種子、縮短期間
    python volley_sim.py --method random       # 每晚都隨機分隊
    python volley_sim.py --out sim_run2        # 輸出到別的資料夾

在別的程式中重用模擬引擎（例如比較分隊方法）：
    import volley_sim as vs
    cfg = vs.default_config()
    rng = vs.np.random.default_rng(1)
    pool = vs.make_players(cfg, rng)
    chem = vs.make_chemistry(pool, cfg, rng)
    teams = vs.form_teams(ids, n_teams=5, method="snake_true", pool=pool, rng=rng)
    res = vs.simulate_game(teams[0], teams[1], pool, chem, cfg, rng)
"""
from __future__ import annotations

import argparse
import copy
import datetime as dt
import json
import math
import os
from itertools import combinations

import numpy as np
import pandas as pd

VERSION = "1.0.0"

# --------------------------------------------------------------------------
# 參數。source = "datavolley" 表示由公開比賽紀錄算出（見 README 的「參數來源」），
#       source = "assumption" 表示合理假設，可在報告中做敏感度分析。
# --------------------------------------------------------------------------
DEFAULT_CONFIG = {
    "seed": 20261126,
    # ---- 期間與場次 ----
    "start_date": "2026-09-14",          # 假設：學期第 2 週的週一
    "weeks": 6,                          # 假設
    "weekdays": [0, 1, 2, 3],            # 週一到週四（0=週一）；假設
    "sessions": {                        # 假設：時段長度與可用場地
        "dinner": {"start": "18:00", "minutes": 90, "courts": 1},   # Iris 確認：18:00–19:30
        "late":   {"start": "22:00", "minutes": 90, "courts": 1},   # Iris 確認：22:00–23:30
    },
    # ---- 球員母體 ----
    "n_pool": 80,                        # 假設：常來野場的人數
    "skill_sd": 1.0,                     # 真實實力 θ ~ N(0, 1)，尺度自訂
    "attend_beta": [2.0, 6.0],           # 假設：每人每場出席機率 ~ Beta(2,6)，平均 0.25
    "session_pref_late": 0.5,            # 假設：偏好消夜場的比例
    "pref_strength": 0.75,               # 假設：在偏好時段出現的權重
    "turnout_min": 16, "turnout_max": 36,  # 依 Iris 描述：一晚 4~6 隊、每隊 4~6 人
    "team_size_target": 6,
    # ---- 自報程度（1~5 級） ----
    "self_report_noise_sd": 0.6,         # 假設：自評誤差
    "self_report_bias": 0.3,             # 假設：普遍略為高估自己
    "level_cuts": [-1.2, -0.4, 0.4, 1.2],  # θ 的切點 → 1~5 級
    # ---- 位置 ----
    "positions": {"主攻": 0.30, "副攻": 0.15, "舉球": 0.15, "接應": 0.10, "自由": 0.08, "不限": 0.22},
    "attack_weight": {"主攻": 1.0, "接應": 0.9, "副攻": 0.7, "不限": 0.6, "舉球": 0.15, "自由": 0.0},
    # ---- 搭檔默契 ----
    "chem_prob": 0.10,                   # 假設：10% 的兩兩組合有非零默契
    "chem_sd": 0.4,                      # 假設：非零默契 ~ N(0, 0.4)，單位與 θ 相同
    # ---- 一球（rally）的模擬，基準機率取自 datavolley 範例比賽 ----
    "p_ace": 0.141,                      # datavolley：發球直接得分率
    "p_serve_error": 0.141,              # datavolley：發球失誤率
    "p_kill": 0.290,                     # datavolley：攻擊得分率
    "p_attack_error": 0.071,             # datavolley：攻擊失誤率
    "p_blocked": 0.043,                  # datavolley：攻擊被攔死率
    "beta_skill": 0.4,                   # 假設：實力差 1 單位時 logit 的位移（試過 0.4~0.6，0.4 讓攻擊得分率最接近 datavolley 基準）
    "missing_player_penalty": 0.15,      # 假設：每少 1 人（相對 6 人）團隊實力扣分
    "seconds_per_rally": 29,             # datavolley：相鄰兩分間隔中位數（秒）
    "seconds_between_games": 120,        # 假設：換隊、熱身
    # ---- 賽制 ----
    # Iris 確認：依隊伍數量打 15 或 20 分。哪個隊數打幾分是假設：隊多→打短一點讓大家輪得到
    "target_by_teams": {"2": 20, "3": 20, "4": 20, "5": 15, "6": 15},
    "target_points": 20,                 # 未對應到隊數時的預設
    "short_target_points": 15,           # 假設：剩餘時間不夠打完整局時改打 15 分
    "point_cap": 25,                     # 假設：deuce 打到 25 分強制結束
    "winner_stay_max": 2,                # 假設：贏球最多連續留場 2 局
    # ---- 分隊方法（歷史資料中每晚怎麼分隊） ----
    "history_methods": {"self_level": 0.6, "random": 0.4},  # 假設：多數靠自報程度，部分隨機
}


def default_config() -> dict:
    return copy.deepcopy(DEFAULT_CONFIG)


def _logit(p: float) -> float:
    return math.log(p / (1 - p))


def _sigmoid(x: float) -> float:
    return 1 / (1 + math.exp(-x))


# --------------------------------------------------------------------------
# 球員與默契
# --------------------------------------------------------------------------
def make_players(cfg: dict, rng: np.random.Generator) -> pd.DataFrame:
    n = cfg["n_pool"]
    ids = [f"P{i:03d}" for i in range(1, n + 1)]
    theta = rng.normal(0, cfg["skill_sd"], n)
    reported = theta + cfg["self_report_bias"] + rng.normal(0, cfg["self_report_noise_sd"], n)
    self_level = 1 + np.searchsorted(cfg["level_cuts"], reported)
    pos_names = list(cfg["positions"])
    pos_p = np.array(list(cfg["positions"].values()))
    pos = rng.choice(pos_names, size=n, p=pos_p / pos_p.sum())
    attend = rng.beta(*cfg["attend_beta"], n)
    pref_late = rng.random(n) < cfg["session_pref_late"]
    return pd.DataFrame({
        "player_id": ids,
        "true_skill": theta.round(4),
        "self_level": self_level.astype(int),
        "main_position": pos,
        "attend_prob": attend.round(4),
        "prefers": np.where(pref_late, "late", "dinner"),
    }).set_index("player_id", drop=False)


def make_chemistry(pool: pd.DataFrame, cfg: dict, rng: np.random.Generator) -> dict:
    chem = {}
    for a, b in combinations(pool.index, 2):
        if rng.random() < cfg["chem_prob"]:
            chem[(a, b)] = round(float(rng.normal(0, cfg["chem_sd"])), 4)
    return chem


def team_chemistry(ids, chem: dict) -> float:
    """隊內所有兩兩默契的平均（不是總和，避免人多的隊伍被放大）。"""
    pairs = list(combinations(sorted(ids), 2))
    if not pairs:
        return 0.0
    return sum(chem.get(p, 0.0) for p in pairs) / len(pairs)


def team_strength(ids, pool: pd.DataFrame, chem: dict, cfg: dict) -> float:
    base = pool.loc[list(ids), "true_skill"].mean()
    missing = max(0, cfg["team_size_target"] - len(ids))
    return float(base + team_chemistry(ids, chem) * len(ids) / 2 - cfg["missing_player_penalty"] * missing)
    # 默契乘上 n/2：平均默契 × 每人平均搭檔數的一半，讓默契效果與單人實力同量級


# --------------------------------------------------------------------------
# 分隊
# --------------------------------------------------------------------------
def n_teams_for(turnout: int, cfg: dict) -> int:
    k = int(round(turnout / cfg["team_size_target"]))
    k = max(4, min(6, k))
    while turnout / k > 6 and k < 6:
        k += 1
    while turnout / k < 4 and k > 2:
        k -= 1
    return k


def form_teams(ids, n_teams: int, method: str, pool: pd.DataFrame, rng: np.random.Generator,
               ratings: dict | None = None) -> list[list[str]]:
    """method: random | self_level | snake_true | rating（用外部 ratings 字典，例如模型估計值）"""
    ids = list(ids)
    if method == "random":
        order = list(rng.permutation(ids))
    else:
        if method == "self_level":
            key = pool.loc[ids, "self_level"].astype(float).to_dict()
        elif method == "snake_true":
            key = pool.loc[ids, "true_skill"].to_dict()
        elif method == "rating":
            if ratings is None:
                raise ValueError("method='rating' 需要提供 ratings")
            key = {i: ratings.get(i, 0.0) for i in ids}
        else:
            raise ValueError(f"未知的分隊方法：{method}")
        jitter = rng.random(len(ids)) * 1e-3   # 同分時隨機打破平手
        order = sorted(ids, key=lambda i: -(key[i] + jitter[ids.index(i)]))
    teams = [[] for _ in range(n_teams)]
    for r, pid in enumerate(order):               # 蛇形選秀：1,2,…,k,k,…,2,1
        rnd, pos = divmod(r, n_teams)
        teams[pos if rnd % 2 == 0 else n_teams - 1 - pos].append(pid)
    return teams


# --------------------------------------------------------------------------
# 單局模擬（逐球）
# --------------------------------------------------------------------------
def _new_stats(ids):
    return {i: dict(attempts=0, kills=0, errors=0, blocked=0, serves=0, aces=0, serve_errors=0) for i in ids}


def _pick_attacker(ids, pool, cfg, rng):
    w = np.array([cfg["attack_weight"][pool.at[i, "main_position"]] for i in ids], dtype=float)
    if w.sum() == 0:
        w = np.ones(len(ids))
    return ids[rng.choice(len(ids), p=w / w.sum())]


def simulate_rally(serving, receiving, server, S, pool, cfg, rng, stats):
    """回傳得分的一方（'A' 或 'B'）。serving/receiving 為 (side, ids)。"""
    b = cfg["beta_skill"]
    s_side, s_ids = serving
    r_side, r_ids = receiving
    th = pool["true_skill"]
    stats[server]["serves"] += 1
    diff = th[server] - S[r_side]
    p_ace = _sigmoid(_logit(cfg["p_ace"]) + b * diff)
    p_err = _sigmoid(_logit(cfg["p_serve_error"]) - b * th[server])
    u = rng.random()
    if u < p_ace:
        stats[server]["aces"] += 1
        return s_side
    if u < p_ace + p_err:
        stats[server]["serve_errors"] += 1
        return r_side
    att_side, att_ids, def_side = r_side, r_ids, s_side   # 接發方先攻
    for _ in range(40):
        hitter = _pick_attacker(att_ids, pool, cfg, rng)
        d = 0.5 * (th[hitter] + S[att_side]) - S[def_side]
        pk = _sigmoid(_logit(cfg["p_kill"]) + b * d)
        pe = _sigmoid(_logit(cfg["p_attack_error"]) - b * d)
        pb = _sigmoid(_logit(cfg["p_blocked"]) - b * d)
        st = stats[hitter]
        st["attempts"] += 1
        u = rng.random()
        if u < pk:
            st["kills"] += 1
            return att_side
        if u < pk + pe:
            st["errors"] += 1
            return def_side
        if u < pk + pe + pb:
            st["blocked"] += 1
            return def_side
        att_ids, (att_side, def_side) = (s_ids if att_side == r_side else r_ids), (def_side, att_side)
    return att_side


def simulate_game(team_a, team_b, pool, chem, cfg, rng, target=None):
    """模擬一局。回傳 dict：score_a, score_b, rallies, stats（每位球員的攻擊／發球統計）。"""
    target = target or cfg["target_points"]
    cap = max(cfg["point_cap"], target + 2)
    S = {"A": team_strength(team_a, pool, chem, cfg), "B": team_strength(team_b, pool, chem, cfg)}
    ids = {"A": list(team_a), "B": list(team_b)}
    stats = _new_stats(ids["A"] + ids["B"])
    score = {"A": 0, "B": 0}
    rot = {"A": 0, "B": 0}
    serve_side = "A" if rng.random() < 0.5 else "B"
    rallies = 0
    while True:
        other = "B" if serve_side == "A" else "A"
        server = ids[serve_side][rot[serve_side] % len(ids[serve_side])]
        w = simulate_rally((serve_side, ids[serve_side]), (other, ids[other]), server, S, pool, cfg, rng, stats)
        rallies += 1
        score[w] += 1
        if w != serve_side:          # 換發球、輪轉
            rot[w] += 1
            serve_side = w
        hi, lo = max(score.values()), min(score.values())
        if (hi >= target and hi - lo >= 2) or hi >= cap:
            break
    return {"score_a": score["A"], "score_b": score["B"], "rallies": rallies, "stats": stats,
            "strength_a": S["A"], "strength_b": S["B"]}


# --------------------------------------------------------------------------
# 一個時段（晚餐場或消夜場）：贏球留場、輸球排隊
# --------------------------------------------------------------------------
def simulate_session(date, session, present, pool, chem, cfg, rng, method):
    scfg = cfg["sessions"][session]
    k = n_teams_for(len(present), cfg)
    night_target = int(cfg["target_by_teams"].get(str(k), cfg["target_points"]))
    team_lists = form_teams(present, k, method, pool, rng)
    names = [chr(ord("A") + i) for i in range(k)]
    teams = dict(zip(names, team_lists))
    sid = f"{date}_{session}"
    t0 = dt.datetime.fromisoformat(f"{date}T{scfg['start']}")
    t_end = t0 + dt.timedelta(minutes=scfg["minutes"])
    sec = cfg["seconds_per_rally"]

    games, gp_rows, atk_rows = [], [], []
    for court in range(1, scfg["courts"] + 1):
        queue = list(rng.permutation(names)) if scfg["courts"] == 1 else names[court - 1::scfg["courts"]]
        queue = list(queue)
        if len(queue) < 2:
            continue
        on = [queue.pop(0), queue.pop(0)]
        streak = {n: 0 for n in names}
        t = t0
        while True:
            remaining = (t_end - t).total_seconds()
            full_need = (night_target * 1.8) * sec
            short_need = (cfg["short_target_points"] * 1.8) * sec
            if remaining >= full_need:
                target = night_target
            elif remaining >= short_need:
                target = cfg["short_target_points"]
            else:
                break
            a, b_ = on
            res = simulate_game(teams[a], teams[b_], pool, chem, cfg, rng, target)
            g_no = len([g for g in games if g["court"] == court]) + 1
            gid = f"{sid}_C{court}G{g_no:02d}"
            start = t
            t = t + dt.timedelta(seconds=res["rallies"] * sec)
            win, lose = (a, b_) if res["score_a"] > res["score_b"] else (b_, a)
            games.append(dict(
                game_id=gid, session_id=sid, date=date, weekday=start.strftime("%a"), session=session,
                court=court, game_no=g_no, team_a=a, team_b=b_, n_a=len(teams[a]), n_b=len(teams[b_]),
                score_a=res["score_a"], score_b=res["score_b"], winner=win,
                margin=abs(res["score_a"] - res["score_b"]), target_points=target,
                start_time=start.strftime("%H:%M"), end_time=t.strftime("%H:%M"),
                rallies=res["rallies"], team_method=method,
            ))
            for side, tm, pf, pa in (("A", a, res["score_a"], res["score_b"]), ("B", b_, res["score_b"], res["score_a"])):
                for pid in teams[tm]:
                    gp_rows.append(dict(game_id=gid, session_id=sid, date=date, session=session, player_id=pid,
                                        team=tm, side=side, won=int(tm == win), points_for=pf,
                                        points_against=pa, margin=pf - pa))
                    atk_rows.append(dict(game_id=gid, player_id=pid, team=tm, **res["stats"][pid]))
            # 輪替：輸的下場排到隊尾；贏的留場，但最多連續 winner_stay_max 局
            streak[win] += 1
            streak[lose] = 0
            queue.append(lose)
            if streak[win] >= cfg["winner_stay_max"] and len(queue) >= 2:
                streak[win] = 0
                queue.append(win)
                on = [queue.pop(0), queue.pop(0)]
            else:
                on = [win, queue.pop(0)]
            t = t + dt.timedelta(seconds=cfg["seconds_between_games"])

    team_rows = [dict(session_id=sid, date=date, session=session, team=n, team_method=method,
                      n_players=len(teams[n]), players=" ".join(teams[n])) for n in names]
    att_rows = [dict(session_id=sid, date=date, session=session, player_id=p,
                     team=next(n for n in names if p in teams[n])) for p in present]
    return games, gp_rows, atk_rows, team_rows, att_rows


# --------------------------------------------------------------------------
# 整個期間
# --------------------------------------------------------------------------
def sample_turnout(pool, session, cfg, rng):
    w = np.where(pool["prefers"] == session, cfg["pref_strength"], 1 - cfg["pref_strength"]) * 2
    p = np.clip(pool["attend_prob"].to_numpy() * w, 0, 0.95)
    for _ in range(200):
        present = pool.index[rng.random(len(pool)) < p].tolist()
        if cfg["turnout_min"] <= len(present) <= cfg["turnout_max"]:
            return present
    # 出席人數超出範圍時，抽樣補足或刪減到邊界
    present = list(rng.permutation(pool.index))[: int(np.clip(len(present), cfg["turnout_min"], cfg["turnout_max"]))]
    return present


def run(cfg: dict, method: str | None = None) -> dict:
    rng = np.random.default_rng(cfg["seed"])
    pool = make_players(cfg, rng)
    chem = make_chemistry(pool, cfg, rng)
    start = dt.date.fromisoformat(cfg["start_date"])
    games, gp, atk, teams, att = [], [], [], [], []
    hm = cfg["history_methods"]
    for d in range(cfg["weeks"] * 7):
        day = start + dt.timedelta(days=d)
        if day.weekday() not in cfg["weekdays"]:
            continue
        for session in cfg["sessions"]:
            m = method or rng.choice(list(hm), p=np.array(list(hm.values())) / sum(hm.values()))
            present = sample_turnout(pool, session, cfg, rng)
            g, p, a, t, at = simulate_session(day.isoformat(), session, present, pool, chem, cfg, rng, str(m))
            games += g; gp += p; atk += a; teams += t; att += at
    return dict(pool=pool, chem=chem, games=pd.DataFrame(games), game_players=pd.DataFrame(gp),
                attack_stats=pd.DataFrame(atk), teams=pd.DataFrame(teams), attendance=pd.DataFrame(att))


def write_outputs(out: dict, cfg: dict, outdir: str, method: str | None):
    data_dir = os.path.join(outdir, "data")
    truth_dir = os.path.join(outdir, "truth")
    os.makedirs(data_dir, exist_ok=True)
    os.makedirs(truth_dir, exist_ok=True)
    pool = out["pool"]
    # data/：分析時「看得到」的資料（像真實世界會記錄到的）
    pool[["player_id", "self_level", "main_position"]].to_csv(os.path.join(data_dir, "players.csv"), index=False)
    for name in ("teams", "games", "game_players", "attack_stats", "attendance"):
        out[name].to_csv(os.path.join(data_dir, f"{name}.csv"), index=False)
    # truth/：只有模擬才知道的真值，用來驗證模型，不可當作模型輸入
    pool[["player_id", "true_skill", "attend_prob", "prefers"]].to_csv(
        os.path.join(truth_dir, "players_truth.csv"), index=False)
    pd.DataFrame([dict(player_1=a, player_2=b, chemistry=v) for (a, b), v in out["chem"].items()]).to_csv(
        os.path.join(truth_dir, "pair_chemistry.csv"), index=False)
    meta = dict(version=VERSION, generated_at=dt.datetime.now().isoformat(timespec="seconds"),
                method_override=method, config=cfg,
                note="合成資料（simulated data），非真實野場紀錄。")
    with open(os.path.join(truth_dir, "config.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)


def summarize(out: dict) -> str:
    g = out["games"]
    a = out["attack_stats"].sum(numeric_only=True)
    lines = [
        f"時段數 {g['session_id'].nunique()}，局數 {len(g)}，球員出現 {out['game_players']['player_id'].nunique()} 人",
        f"每時段局數 平均 {g.groupby('session_id').size().mean():.1f}",
        f"局數依目標分數 {g.target_points.value_counts().to_dict()}",
        f"平均分差 {g['margin'].mean():.2f}，分差≤3 比例 {(g['margin'] <= 3).mean():.2f}",
        f"攻擊得分率 {a['kills'] / a['attempts']:.3f}，失誤 {a['errors'] / a['attempts']:.3f}，"
        f"被攔 {a['blocked'] / a['attempts']:.3f}",
        f"發球得分率 {a['aces'] / a['serves']:.3f}，發球失誤 {a['serve_errors'] / a['serves']:.3f}",
    ]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description="排球野場模擬資料產生器")
    ap.add_argument("--seed", type=int)
    ap.add_argument("--weeks", type=int)
    ap.add_argument("--players", type=int, help="球員母體人數")
    ap.add_argument("--method", choices=["random", "self_level", "snake_true"],
                    help="所有時段都用同一種分隊方法（預設依 history_methods 混合）")
    ap.add_argument("--out", default=os.path.dirname(os.path.abspath(__file__)))
    ap.add_argument("--config", help="JSON 檔，覆寫部分參數")
    args = ap.parse_args()
    cfg = default_config()
    if args.config:
        with open(args.config, encoding="utf-8") as f:
            cfg.update(json.load(f))
    if args.seed is not None:
        cfg["seed"] = args.seed
    if args.weeks is not None:
        cfg["weeks"] = args.weeks
    if args.players is not None:
        cfg["n_pool"] = args.players
    out = run(cfg, args.method)
    write_outputs(out, cfg, args.out, args.method)
    print(summarize(out))
    print(f"已輸出到 {os.path.abspath(args.out)}")


if __name__ == "__main__":
    main()
