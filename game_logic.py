# game_logic.py
"""
Core game logic for GeoPolitical Domination (local mode).
Thread-safe Game class with locking around state mutations.
"""

import random
import time
import threading
import logging

from constants import CLAIM_COST, TROOP_COST, PEACE_PAYOUT_PER_COUNTRY, continent_value
from models import Player

logger = logging.getLogger(__name__)


class Game:
    """
    Manages the game state for local and spectate modes.
    All state mutations go through methods protected by a lock.
    """

    def __init__(self, players, countries):
        self.players = players
        self.countries = countries
        self.turn_idx = random.randrange(len(players)) if players else 0
        self.turn_number = 1
        self.logs = []
        self.bot_thread = None
        self._lock = threading.Lock()
        self.started = False
        self.host_name = players[0].name if players else None
        self.player_limit = 0  # 0 = no limit
        self.game_id = ""
        self.password = ""
        self.winner = None
        self.host_disbanded = False  # True when host leaves, ending the game

    def log(self, msg):
        """Append a timestamped log message."""
        ts = time.strftime("%H:%M:%S")
        line = f"[{ts}] {msg}"
        with self._lock:
            self.logs.append(line)
        logger.info(msg)

    def get_current_player(self):
        """Return the player whose turn it is."""
        with self._lock:
            if not self.players:
                return None
            return self.players[self.turn_idx]

    def active_players(self):
        """Return list of non-eliminated, non-spectator players."""
        return [p for p in self.players if not p.eliminated and not p.is_spectator]

    def check_elimination(self):
        """Check if any player who previously had territory now has none.
        Returns list of newly eliminated player names."""
        eliminated = []
        for p in self.players:
            if p.eliminated or p.is_spectator or p.is_bot:
                continue
            if p.had_territory and p.country_count() == 0:
                p.eliminated = True
                eliminated.append(p.name)
                self.log(f"{p.name} has been eliminated!")
        # Also check bots
        for p in self.players:
            if p.eliminated or p.is_spectator or not p.is_bot:
                continue
            if p.had_territory and p.country_count() == 0:
                p.eliminated = True
                self.log(f"{p.name} has been eliminated!")
        # Check for winner
        active = self.active_players()
        if len(active) == 1 and self.started:
            self.winner = active[0].name
            self.log(f"{self.winner} wins the game!")
        return eliminated

    def remove_player(self, player_name):
        """Remove a player from the game entirely (leave)."""
        is_host = False
        with self._lock:
            player = None
            idx = None
            for i, p in enumerate(self.players):
                if p.name == player_name:
                    player = p
                    idx = i
                    break
            if player is None:
                return
            # Release all their territory
            for cid, c in self.countries.items():
                if c.get("owner") == player_name:
                    c["owner"] = None
                    c["troops"] = 0
            # Check if this is the host leaving
            is_host = (player_name == self.host_name)
            # Remove from player list
            self.players.pop(idx)
            # Adjust turn_idx
            if self.players:
                if idx < self.turn_idx:
                    self.turn_idx -= 1
                elif idx == self.turn_idx:
                    self.turn_idx = self.turn_idx % len(self.players)
                self.turn_idx = min(self.turn_idx, len(self.players) - 1)
            if is_host:
                self.host_disbanded = True
        # Log outside the lock to avoid deadlock
        if is_host:
            self.log(f"Host {player_name} has left. Game disbanded.")
        else:
            self.log(f"{player_name} has left the game.")

    def make_spectator(self, player_name):
        """Convert a player to spectator mode."""
        for p in self.players:
            if p.name == player_name:
                p.is_spectator = True
                self.log(f"{player_name} is now spectating.")
                break

    def kick_player(self, host_name, target_name):
        """Host kicks a player from the game (lobby only)."""
        if self.host_name != host_name:
            return False
        if target_name == host_name:
            return False
        found = any(p.name == target_name for p in self.players)
        if found:
            self.remove_player(target_name)
            self.log(f"{target_name} was kicked by the host.")
            return True
        return False

    def can_join(self):
        """Check if a new player can join (respects player limit and game started)."""
        active = [p for p in self.players if not p.eliminated]
        if self.player_limit > 0 and len(active) >= self.player_limit:
            return False, "Game is full."
        return True, ""

    def add_player(self, player):
        """Add a player to the game. Late joiners become spectators if started."""
        can, reason = self.can_join()
        if not can:
            return False, reason
        with self._lock:
            # Check for duplicate names
            for p in self.players:
                if p.name == player.name:
                    return False, "Name already taken."
            if self.started:
                player.is_spectator = True
            self.players.append(player)
        # Log outside the lock to avoid deadlock (log() acquires _lock)
        self.log(f"{player.name} joined the game" +
                 (" as spectator." if player.is_spectator else "."))
        return True, ""

    def snapshot(self):
        """Return a thread-safe snapshot of the game state."""
        with self._lock:
            players = [p.to_snapshot_dict() for p in self.players]
            countries = {}
            for cid, c in self.countries.items():
                countries[cid] = {
                    "owner": c.get("owner"),
                    "troops": int(c.get("troops", 0)),
                    "continent": c.get("continent", ""),
                }
            return {
                "players": players,
                "countries": countries,
                "turn_idx": self.turn_idx,
                "turn_number": self.turn_number,
                "logs": list(self.logs),
                "started": self.started,
                "host": self.host_name,
                "player_limit": self.player_limit,
                "game_id": self.game_id,
                "winner": self.winner,
                "host_disbanded": self.host_disbanded,
            }


def check_and_pay_continent_bonus(game, player, continent_name):
    """Award a continent bonus if the player owns all countries in that continent."""
    if not continent_name:
        return
    cont_countries = [
        c
        for c in game.countries.values()
        if (c.get("continent", "") or "") == continent_name
    ]
    if not cont_countries:
        return
    if all(c.get("owner") == player.name for c in cont_countries):
        bonus = continent_value(continent_name)
        player.money += bonus
        game.log(
            f"{player.name} captured a continent ({continent_name}) and received ${bonus}."
        )


def claim_country(player, country, troops, game):
    """
    Claim an unclaimed country for the player.
    Returns True on success, False if the player can't afford it.
    """
    if player.money < CLAIM_COST:
        game.log(
            f"{player.name} cannot afford to claim that country (need ${CLAIM_COST})."
        )
        return False

    player.money -= CLAIM_COST
    prev = country.get("owner")
    if prev:
        prevpl = next((p for p in game.players if p.name == prev), None)
        if prevpl and country["id"] in prevpl.owned:
            prevpl.owned.remove(country["id"])

    country["owner"] = player.name
    country["troops"] = troops
    player.owned.add(country["id"])
    player.had_territory = True
    game.log(
        f"{player.name} claimed a country in {country.get('continent', 'unknown')} "
        f"with {troops} troops (paid ${CLAIM_COST})."
    )

    try:
        check_and_pay_continent_bonus(game, player, country.get("continent", ""))
    except (KeyError, TypeError, ValueError) as e:
        logger.warning("Error checking continent bonus: %s", e)

    return True


def attack_country(attacker, source_country, target_country, send_troops, game):
    """
    Execute an attack from source to target country.
    Returns True if the attack succeeds, False otherwise.
    """
    src_available = int(source_country.get("troops", 0) or 0)
    if send_troops <= 0 or send_troops >= src_available:
        game.log(
            f"{attacker.name} attempted to send {send_troops} troops but only "
            f"{src_available} available (must leave at least 1)."
        )
        return False

    source_country["troops"] = max(0, src_available - send_troops)
    defender_name = target_country.get("owner")
    defender = (
        next((p for p in game.players if p.name == defender_name), None)
        if defender_name
        else None
    )

    # Auto-win against vulnerable defenders
    if defender and defender.vulnerable:
        if attacker.money < CLAIM_COST:
            game.log(
                f"{attacker.name} cannot afford the claim cost (${CLAIM_COST}); attack aborted."
            )
            source_country["troops"] += send_troops
            return False
        attacker.money -= CLAIM_COST
        if defender and target_country["id"] in defender.owned:
            defender.owned.remove(target_country["id"])
        target_country["owner"] = attacker.name
        target_country["troops"] = send_troops
        attacker.owned.add(target_country["id"])
        attacker.had_territory = True
        game.log(
            f"{attacker.name} swept vulnerable territory in "
            f"{target_country.get('continent', 'unknown')} and took it with "
            f"{send_troops} troops (paid ${CLAIM_COST})."
        )
        defender.was_attacked = True
        try:
            check_and_pay_continent_bonus(
                game, attacker, target_country.get("continent", "")
            )
        except (KeyError, TypeError, ValueError) as e:
            logger.warning("Error checking continent bonus: %s", e)
        # Check for eliminations after territory change
        game.check_elimination()
        return True

    # Combat roll: attacker 1d20 vs defender max(2d20)
    atk_roll = random.randint(1, 20)
    d1 = random.randint(1, 20)
    d2 = random.randint(1, 20)
    def_best = max(d1, d2)
    game.log(
        f"{attacker.name} (atk {atk_roll}) attacks territory in "
        f"{target_country.get('continent', 'unknown')} owned by "
        f"{defender_name or 'nobody'} (def [{d1},{d2}] -> {def_best})"
    )

    if atk_roll > def_best:
        if attacker.money < CLAIM_COST:
            game.log(
                f"{attacker.name} won the fight but couldn't pay the claim "
                f"(${CLAIM_COST}); troops returned to source."
            )
            source_country["troops"] += send_troops
            return False
        attacker.money -= CLAIM_COST
        if defender and target_country["id"] in defender.owned:
            defender.owned.remove(target_country["id"])
        target_country["owner"] = attacker.name
        target_country["troops"] = send_troops
        attacker.owned.add(target_country["id"])
        attacker.had_territory = True
        game.log(
            f"{attacker.name} won and captured territory in "
            f"{target_country.get('continent', 'unknown')} with {send_troops} troops "
            f"(paid ${CLAIM_COST})."
        )
        if defender:
            defender.was_attacked = True
        try:
            check_and_pay_continent_bonus(
                game, attacker, target_country.get("continent", "")
            )
        except (KeyError, TypeError, ValueError) as e:
            logger.warning("Error checking continent bonus: %s", e)
        # Check for eliminations after territory change
        game.check_elimination()
        return True
    else:
        game.log(
            f"{attacker.name} attacked but lost; {send_troops} attacking troops "
            f"were destroyed."
        )
        if defender:
            defender.was_attacked = True
        return False


def resolve_peace_if_needed(game, player):
    """
    Resolve a player's vulnerability from a previous PEACE.
    Called at the START of their turn, before they act.
    """
    if player.vulnerable:
        if not player.was_attacked:
            payout = PEACE_PAYOUT_PER_COUNTRY * max(0, player.country_count())
            player.money += payout
            game.log(
                f"{player.name} was peaceful and earned ${payout} "
                f"(${PEACE_PAYOUT_PER_COUNTRY} x {player.country_count()} countries)."
            )
        else:
            game.log(
                f"{player.name} was attacked while vulnerable — no PEACE payout."
            )
        player.vulnerable = False
        player.was_attacked = False


def end_turn_housekeeping(game, player):
    """Advance to next player and resolve their vulnerability if any.
    Skips eliminated and spectating players."""
    with game._lock:
        game.turn_number += 1
        if not game.players:
            return
        # Find next active player (skip eliminated/spectators)
        attempts = 0
        while attempts < len(game.players):
            game.turn_idx = (game.turn_idx + 1) % len(game.players)
            next_p = game.players[game.turn_idx]
            if not next_p.eliminated and not next_p.is_spectator:
                break
            attempts += 1
    # Resolve next player's PEACE vulnerability from their previous turn
    next_p = game.players[game.turn_idx]
    if not next_p.eliminated and not next_p.is_spectator:
        resolve_peace_if_needed(game, next_p)
