"""三種分隊方法：隨機、自報程度蛇形、依評分最佳化平衡。

所有方法回傳 list[list[Player]]，每隊人數差最多 1 人。
"""
from __future__ import annotations

import math
import random
from typing import Callable

from .registration import Player, blended_rating, level_to_z

FULL_TEAM = 6
SIZE_PENALTY = 0.15  # 每少 1 人，隊伍強度扣多少（以實力標準差為單位）


def choose_n_teams(n_players: int, min_size: int = 4, max_size: int = 6, max_teams: int = 6) -> int:
    """依人數決定隊數：盡量每隊滿 max_size 人，且每隊不少於 min_size 人。"""
    if n_players < 2 * min_size:
        raise ValueError(f"至少要 {2 * min_size} 人才能分兩隊，現在 {n_players} 人")
    n = max(2, math.ceil(n_players / max_size))
    n = min(n, max_teams, n_players // min_size)
    return n


def team_sizes(n_players: int, n_teams: int) -> list[int]:
    base, extra = divmod(n_players, n_teams)
    return [base + 1 if i < extra else base for i in range(n_teams)]


def team_strength(values: list[float]) -> float:
    """隊伍強度 = 平均實力 − 人數不足的懲罰。"""
    return sum(values) / len(values) - SIZE_PENALTY * max(0, FULL_TEAM - len(values))


def _deal(order: list[Player], sizes: list[int]) -> list[list[Player]]:
    """蛇形發牌：1→n、n→1、1→n…；某隊額滿就跳過。"""
    teams: list[list[Player]] = [[] for _ in sizes]
    n = len(sizes)
    idx = 0
    forward = True
    for p in order:
        while True:
            t = idx if forward else n - 1 - idx
            idx += 1
            if idx == n:
                idx, forward = 0, not forward
            if len(teams[t]) < sizes[t]:
                teams[t].append(p)
                break
    return teams


def random_split(players: list[Player], n_teams: int, rng: random.Random) -> list[list[Player]]:
    """方法一：完全隨機。"""
    order = players[:]
    rng.shuffle(order)
    sizes = team_sizes(len(order), n_teams)
    teams, start = [], 0
    for s in sizes:
        teams.append(order[start : start + s])
        start += s
    return teams


def snake_split(players: list[Player], n_teams: int, rng: random.Random) -> list[list[Player]]:
    """方法二：依自報程度由高到低蛇形分配，同程度者隨機排序。"""
    order = players[:]
    rng.shuffle(order)
    order.sort(key=lambda p: -p.self_level)  # sort 是穩定的，同程度保留隨機順序
    return _deal(order, team_sizes(len(order), n_teams))


def _score(strengths: list[float], setter_counts: list[int], want: int, setter_weight: float) -> float:
    spread = max(strengths) - min(strengths)
    mean = sum(strengths) / len(strengths)
    var = sum((x - mean) ** 2 for x in strengths) / len(strengths)
    covered = sum(c > 0 for c in setter_counts)
    return spread + 0.1 * var + setter_weight * (want - covered)


def _objective(teams: list[list[Player]], key: Callable[[Player], float], setter_weight: float) -> float:
    """平衡分隊的目標函數（越小越平衡）。"""
    s = [team_strength([key(p) for p in t]) for t in teams]
    c = [sum(p.position == "舉球" for p in t) for t in teams]
    # 舉球員：有人報「舉球」時，盡量每隊至少一位
    return _score(s, c, min(sum(c), len(teams)), setter_weight)


def balanced_split(
    players: list[Player],
    n_teams: int,
    rng: random.Random,
    key: Callable[[Player], float] = blended_rating,
    setter_weight: float = 0.3,
    max_rounds: int = 200,
) -> list[list[Player]]:
    """方法三：以綜合評分做蛇形起點，再用兩兩交換的局部搜尋縮小隊伍強度差。

    目標函數 = 最強隊與最弱隊的強度差 + 0.1×強度變異數 + 舉球員缺額懲罰。
    """
    order = players[:]
    rng.shuffle(order)
    order.sort(key=lambda p: -key(p))
    teams = _deal(order, team_sizes(len(order), n_teams))
    val = {id(p): key(p) for p in players}
    setter = {id(p): int(p.position == "舉球") for p in players}
    sums = [sum(val[id(p)] for p in t) for t in teams]
    sizes = [len(t) for t in teams]
    pen = [SIZE_PENALTY * max(0, FULL_TEAM - s) for s in sizes]
    cnt = [sum(setter[id(p)] for p in t) for t in teams]
    want = min(sum(cnt), n_teams)

    def strengths(sm: list[float]) -> list[float]:
        return [sm[k] / sizes[k] - pen[k] for k in range(n_teams)]

    best = _score(strengths(sums), cnt, want, setter_weight)
    # 最陡下降：每輪找出最好的一次交換，直到沒有交換能改善
    for _ in range(max_rounds):
        best_swap = None
        for a in range(n_teams):
            for b in range(a + 1, n_teams):
                sa, sb, ca, cb = sums[a], sums[b], cnt[a], cnt[b]
                for i, pa in enumerate(teams[a]):
                    va, xa = val[id(pa)], setter[id(pa)]
                    for j, pb in enumerate(teams[b]):
                        vb, xb = val[id(pb)], setter[id(pb)]
                        sums[a], sums[b] = sa - va + vb, sb - vb + va
                        cnt[a], cnt[b] = ca - xa + xb, cb - xb + xa
                        v = _score(strengths(sums), cnt, want, setter_weight)
                        if v < best - 1e-12:
                            best, best_swap = v, (a, i, b, j)
                sums[a], sums[b], cnt[a], cnt[b] = sa, sb, ca, cb
        if best_swap is None:
            break
        a, i, b, j = best_swap
        pa, pb = teams[a][i], teams[b][j]
        teams[a][i], teams[b][j] = pb, pa
        sums[a] += val[id(pb)] - val[id(pa)]
        sums[b] += val[id(pa)] - val[id(pb)]
        cnt[a] += setter[id(pb)] - setter[id(pa)]
        cnt[b] += setter[id(pa)] - setter[id(pb)]
    return teams


METHODS = {
    "隨機": random_split,
    "自報程度蛇形": snake_split,
    "評分最佳化": balanced_split,
}

METHOD_KEYS = {"random": "隨機", "snake": "自報程度蛇形", "balanced": "評分最佳化"}


def describe(teams: list[list[Player]]) -> list[dict]:
    """把分隊結果整理成可輸出 JSON 的樣子（只用代號與公開資訊）。"""
    out = []
    for k, t in enumerate(teams, 1):
        out.append(
            {
                "team": f"第{k}隊",
                "members": [p.code for p in t],
                "size": len(t),
                "setters": sum(p.position == "舉球" for p in t),
                "mean_self_level": round(sum(p.self_level for p in t) / len(t), 2),
                "strength_est": round(team_strength([blended_rating(p) for p in t]), 3),
                "strength_self": round(team_strength([level_to_z(p.self_level) for p in t]), 3),
            }
        )
    return out
