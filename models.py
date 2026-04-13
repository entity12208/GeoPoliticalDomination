# models.py
"""
Data models for GeoPolitical Domination.
Uses dataclasses for type safety and clarity.
"""

from dataclasses import dataclass, field
from typing import Optional, Set, Tuple
import random
import logging

from constants import PALETTE, STARTING_MONEY

logger = logging.getLogger(__name__)


@dataclass
class Player:
    """Represents a player (human or bot) in the game."""

    name: str
    is_bot: bool = False
    color: Tuple[int, int, int] = (120, 120, 120)
    money: int = STARTING_MONEY
    vulnerable: bool = False
    was_attacked: bool = False
    owned: Set[int] = field(default_factory=set)
    troop_buy_limit: int = 20
    last_gather_turn: int = 0
    is_host: bool = False
    is_spectator: bool = False
    eliminated: bool = False
    had_territory: bool = False  # tracks if player ever owned territory

    def __post_init__(self):
        if self.color == (120, 120, 120) and not self.is_bot:
            self.color = random.choice(PALETTE)

    def troop_count(self, countries):
        """Count total troops across all owned territories."""
        return sum(
            int(c.get("troops", 0))
            for c in countries.values()
            if c.get("owner") == self.name
        )

    def country_count(self):
        """Count owned territories."""
        return len(self.owned)

    def to_snapshot_dict(self):
        """Convert to a snapshot-compatible dict for bot AI and rendering."""
        return {
            "name": self.name,
            "money": self.money,
            "is_bot": self.is_bot,
            "color": self.color,
            "vulnerable": bool(self.vulnerable),
            "was_attacked": bool(self.was_attacked),
            "is_host": bool(self.is_host),
            "is_spectator": bool(self.is_spectator),
            "eliminated": bool(self.eliminated),
        }
