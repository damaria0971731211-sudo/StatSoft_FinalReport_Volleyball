"""報名與程度分級。

只用標準函式庫，方便之後在瀏覽器（Pyodide）裡直接執行。
"""
from __future__ import annotations

import csv
from dataclasses import dataclass, field
from typing import Iterable

# 自報程度 1~5 的名稱
LEVEL_NAMES = {1: "新手", 2: "初階", 3: "中階", 4: "中高階", 5: "校隊級"}
SESSIONS = ("晚餐場", "消夜場")
POSITIONS = ("舉球", "攻擊", "自由", "不限")


@dataclass
class Player:
    """一位報名者。

    code        公開用代號（不放真名）
    self_level  自報程度 1~5
    rating      實力評分（R 模型或模擬給的估計值，平均 0、標準差約 1）；沒有就用自報程度換算
    n_games     rating 背後有幾場紀錄，用來決定評分可信度
    true_skill  只有模擬時才有，用來產生比賽結果，分隊方法看不到
    """

    code: str
    self_level: int
    session: str = "晚餐場"
    position: str = "不限"
    rating: float | None = None
    n_games: int = 0
    true_skill: float | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if not 1 <= int(self.self_level) <= 5:
            raise ValueError(f"{self.code}: 自報程度需在 1~5，收到 {self.self_level}")
        self.self_level = int(self.self_level)
        if self.session not in SESSIONS:
            raise ValueError(f"{self.code}: 場次需為 {SESSIONS}，收到 {self.session}")
        if self.position not in POSITIONS:
            raise ValueError(f"{self.code}: 位置需為 {POSITIONS}，收到 {self.position}")

    @property
    def level_name(self) -> str:
        return LEVEL_NAMES[self.self_level]


def level_to_z(level: int) -> float:
    """自報程度 1~5 換成平均 0、約略標準差 1 的尺度（3 → 0）。"""
    return (level - 3) / 1.2


def blended_rating(p: Player, prior_games: float = 8.0) -> float:
    """收縮估計：場數少時靠自報程度，場數多時靠模型評分。

    權重 w = n / (n + prior_games)；prior_games 可理解為「自報程度值幾場比賽的資訊」。
    """
    prior = level_to_z(p.self_level)
    if p.rating is None or p.n_games <= 0:
        return prior
    w = p.n_games / (p.n_games + prior_games)
    return w * p.rating + (1 - w) * prior


def assign_tiers(players: list[Player], n_tiers: int = 3) -> dict[str, str]:
    """依綜合評分的分位數分成 A（最強）、B、C… 級。同分時依代號排序，結果可重現。"""
    if n_tiers < 1:
        raise ValueError("n_tiers 至少 1")
    ranked = sorted(players, key=lambda p: (-blended_rating(p), p.code))
    labels = [chr(ord("A") + i) for i in range(n_tiers)]
    n = len(ranked)
    return {p.code: labels[min(i * n_tiers // max(n, 1), n_tiers - 1)] for i, p in enumerate(ranked)}


class Registry:
    """單一場次的報名表：先到先上，額滿進候補，有人取消就遞補。"""

    def __init__(self, session: str, capacity: int = 36):
        if session not in SESSIONS:
            raise ValueError(f"場次需為 {SESSIONS}")
        if capacity < 8:
            raise ValueError("名額至少 8 人（至少兩隊、每隊 4 人）")
        self.session = session
        self.capacity = capacity
        self.confirmed: list[Player] = []
        self.waitlist: list[Player] = []

    def _codes(self) -> set[str]:
        return {p.code for p in self.confirmed + self.waitlist}

    def sign_up(self, p: Player) -> str:
        if p.session != self.session:
            raise ValueError(f"{p.code} 報的是 {p.session}，不是 {self.session}")
        if p.code in self._codes():
            raise ValueError(f"{p.code} 已經報名過了")
        if len(self.confirmed) < self.capacity:
            self.confirmed.append(p)
            return "正取"
        self.waitlist.append(p)
        return f"候補第 {len(self.waitlist)} 位"

    def cancel(self, code: str) -> Player | None:
        """取消報名；若是正取，回傳遞補上來的人。"""
        for lst in (self.confirmed, self.waitlist):
            for i, p in enumerate(lst):
                if p.code == code:
                    del lst[i]
                    if lst is self.confirmed and self.waitlist:
                        promoted = self.waitlist.pop(0)
                        self.confirmed.append(promoted)
                        return promoted
                    return None
        raise KeyError(f"找不到 {code}")


def load_players_csv(path: str) -> list[Player]:
    """讀報名 CSV。欄位：code,self_level,session,position[,rating,n_games]"""
    out: list[Player] = []
    with open(path, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            rating = row.get("rating") or None
            out.append(
                Player(
                    code=row["code"].strip(),
                    self_level=int(row["self_level"]),
                    session=(row.get("session") or "晚餐場").strip(),
                    position=(row.get("position") or "不限").strip(),
                    rating=float(rating) if rating else None,
                    n_games=int(row.get("n_games") or 0),
                )
            )
    return out


def attach_ratings(players: Iterable[Player], ratings_csv: str) -> None:
    """接 R 模型輸出：CSV 欄位 code,rating,n_games。找不到的人維持原狀。"""
    table = {}
    with open(ratings_csv, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            table[row["code"].strip()] = (float(row["rating"]), int(row.get("n_games") or 0))
    for p in players:
        if p.code in table:
            p.rating, p.n_games = table[p.code]
