import os
import random
from collections import Counter

import pytest

from volleysplit.registration import Player, Registry, assign_tiers, attach_ratings, blended_rating, level_to_z, load_players_csv
from volleysplit.simulate import SimConfig, make_pool, night_metrics, play_night, play_set, run_simulation, sign_flip_pvalue, summarize
from volleysplit.teaming import METHODS, _objective, balanced_split, choose_n_teams, random_split, snake_split, team_sizes

DATA = os.path.join(os.path.dirname(__file__), "..", "data")


def pool(n, seed=0):
    return make_pool(n, random.Random(seed), SimConfig())


# ---------- 報名 ----------

def test_player_validation():
    with pytest.raises(ValueError):
        Player("X", 6)
    with pytest.raises(ValueError):
        Player("X", 3, session="午餐場")
    with pytest.raises(ValueError):
        Player("X", 3, position="中間手")


def test_registry_waitlist_and_promotion():
    reg = Registry("晚餐場", capacity=8)
    results = [reg.sign_up(Player(f"P{i}", 3)) for i in range(10)]
    assert results[:8] == ["正取"] * 8
    assert results[8:] == ["候補第 1 位", "候補第 2 位"]
    promoted = reg.cancel("P0")
    assert promoted.code == "P8" and len(reg.confirmed) == 8 and len(reg.waitlist) == 1
    assert reg.cancel("P9") is None  # 取消候補不會遞補
    with pytest.raises(KeyError):
        reg.cancel("nobody")


def test_registry_rejects_duplicates_and_wrong_session():
    reg = Registry("消夜場", capacity=8)
    reg.sign_up(Player("A", 3, session="消夜場"))
    with pytest.raises(ValueError):
        reg.sign_up(Player("A", 4, session="消夜場"))
    with pytest.raises(ValueError):
        reg.sign_up(Player("B", 3, session="晚餐場"))


def test_blended_rating_shrinkage():
    p = Player("A", 5, rating=-1.0, n_games=0)
    assert blended_rating(p) == level_to_z(5)  # 沒場數：完全用自報
    p.n_games = 1000
    assert abs(blended_rating(p) - (-1.0)) < 0.03  # 場數很多：幾乎等於模型評分
    p.n_games = 8
    assert blended_rating(p) == pytest.approx(0.5 * -1.0 + 0.5 * level_to_z(5))


def test_tiers_are_balanced_and_ordered():
    ps = pool(30)
    tiers = assign_tiers(ps, 3)
    assert Counter(tiers.values()) == {"A": 10, "B": 10, "C": 10}
    best = max(ps, key=blended_rating)
    worst = min(ps, key=blended_rating)
    assert tiers[best.code] == "A" and tiers[worst.code] == "C"


def test_csv_loading_and_ratings():
    ps = load_players_csv(os.path.join(DATA, "sample_signups.csv"))
    assert len(ps) == 40 and all(p.rating is None for p in ps)
    attach_ratings(ps, os.path.join(DATA, "sample_ratings.csv"))
    assert sum(p.rating is not None for p in ps) == 24


# ---------- 分隊 ----------

@pytest.mark.parametrize("n,expected", [(8, 2), (12, 2), (13, 3), (20, 4), (28, 5), (36, 6), (40, 6)])
def test_choose_n_teams(n, expected):
    k = choose_n_teams(n)
    assert k == expected
    if n <= 36:
        assert 4 <= min(team_sizes(n, k)) and max(team_sizes(n, k)) <= 6


def test_too_few_players():
    with pytest.raises(ValueError):
        choose_n_teams(7)


@pytest.mark.parametrize("name", list(METHODS))
@pytest.mark.parametrize("n", [8, 17, 23, 30, 36])
def test_every_method_is_a_partition(name, n):
    ps = pool(n, seed=n)
    k = choose_n_teams(n)
    teams = METHODS[name](ps, k, random.Random(1))
    assert len(teams) == k
    codes = [p.code for t in teams for p in t]
    assert sorted(codes) == sorted(p.code for p in ps)  # 每人恰好一隊
    sizes = [len(t) for t in teams]
    assert max(sizes) - min(sizes) <= 1


def test_methods_reproducible_with_seed():
    ps = pool(26)
    for fn in METHODS.values():
        a = [[p.code for p in t] for t in fn(ps, 5, random.Random(3))]
        b = [[p.code for p in t] for t in fn(ps, 5, random.Random(3))]
        assert a == b


def test_snake_balances_self_levels():
    ps = [Player(f"P{i}", lvl) for i, lvl in enumerate([5, 5, 4, 4, 3, 3, 2, 2, 1, 1, 1, 1])]
    teams = snake_split(ps, 2, random.Random(0))
    sums = [sum(p.self_level for p in t) for t in teams]
    assert abs(sums[0] - sums[1]) <= 1


def test_balanced_not_worse_than_its_snake_start():
    for seed in range(10):
        ps = pool(30, seed)
        k = choose_n_teams(30)
        start = snake_split([*ps], k, random.Random(seed))
        # snake_split 用自報程度；拿 balanced 的目標函數比較
        bal = balanced_split(ps, k, random.Random(seed))
        assert _objective(bal, blended_rating, 0.3) <= _objective(start, blended_rating, 0.3) + 1e-9


def test_balanced_spreads_setters():
    # 舉球員都在同一個程度時，平衡與舉球分散不衝突，應該每隊一位
    ps = [Player(f"S{i}", 4, position="舉球") for i in range(4)]
    ps += [Player(f"H{i}", 5 if i < 4 else 2) for i in range(12)]
    teams = balanced_split(ps, 4, random.Random(0))
    assert all(any(p.position == "舉球" for p in t) for t in teams)


def test_balanced_all_equal_players():
    ps = [Player(f"P{i}", 3) for i in range(16)]
    teams = balanced_split(ps, 4, random.Random(0))
    assert sorted(len(t) for t in teams) == [4, 4, 4, 4]


# ---------- 模擬 ----------

def test_play_set_rules():
    rng = random.Random(0)
    for _ in range(200):
        a, b = play_set(0.0, 0.0, rng, target=25)
        assert max(a, b) >= 25 and abs(a - b) >= 2
        if max(a, b) > 25:
            assert abs(a - b) == 2  # 延長賽只會贏 2 分


def test_stronger_team_wins_more():
    rng = random.Random(1)
    wins = sum(a > b for a, b in (play_set(1.0, 0.0, rng) for _ in range(400)))
    assert wins > 300


def test_play_night_two_teams_always_play():
    ps = pool(8)
    teams = balanced_split(ps, 2, random.Random(0))
    night = play_night(teams, random.Random(0), SimConfig())
    k = len(night["games"])
    assert 3 <= k <= 8 and night["played"] == [k, k]
    m = night_metrics(teams, night)
    assert m["games_sd"] == 0 and m["games_gap"] == 0


def test_play_night_targets_and_time_budget():
    cfg = SimConfig()
    for n_teams, full in ((4, 20), (6, 15)):
        ps = pool(n_teams * 6)
        teams = balanced_split(ps, n_teams, random.Random(0))
        night = play_night(teams, random.Random(1), cfg)
        assert night["games"][0]["target"] == full
        assert all(g["target"] in (full, 15) for g in night["games"])
        last = night["games"][-1]
        end = last["start_min"] * 60 + (last["score_A"] + last["score_B"]) * cfg.seconds_per_rally
        assert end <= cfg.minutes * 60 + 15 * 60  # 最後一局可能稍微超時，但不會離譜


def test_winner_stays_at_most_max_streak():
    ps = pool(24)
    teams = random_split(ps, 4, random.Random(0))
    night = play_night(teams, random.Random(0), SimConfig())
    run, prev = 0, None
    for g in night["games"]:
        w = g["A"] if g["score_A"] > g["score_B"] else g["B"]
        run = run + 1 if (w == prev and w in (g["A"], g["B"])) else 1
        prev = w
        assert run <= SimConfig().max_streak


def test_play_night_two_courts():
    ps = pool(30)
    teams = balanced_split(ps, 5, random.Random(0))
    night = play_night(teams, random.Random(0), SimConfig(courts=2))
    assert {g["court"] for g in night["games"]} == {1, 2}
    assert sum(night["played"]) == 2 * len(night["games"])


def test_sign_flip_pvalue():
    rng = random.Random(0)
    assert sign_flip_pvalue([1.0] * 30, rng, 2000) < 0.01
    assert sign_flip_pvalue([1.0, -1.0] * 15, rng, 2000) > 0.5


def test_simulation_end_to_end_direction():
    """小型模擬：評分最佳化的隊伍強度差應明顯小於隨機分隊。"""
    rows = run_simulation(reps=40, seed=5)
    s = summarize(rows, b=300)
    pm = s["per_method"]
    assert s["n_nights"] == 40
    assert pm["評分最佳化"]["strength_spread"]["mean"] < pm["隨機"]["strength_spread"]["mean"]
    assert pm["評分最佳化"]["mean_margin"]["mean"] < pm["隨機"]["mean_margin"]["mean"]
    assert s["comparisons"]["評分最佳化 − 隨機"]["strength_spread"]["ci95"][1] < 0
