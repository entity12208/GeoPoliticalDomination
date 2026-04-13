# bot_playstyles.py
"""
Adaptive bot AI for GeoPolitical Domination.

Instead of locking each bot into a single personality, the AI dynamically
analyzes the game state every turn and computes optimal weights:

  - Early game / few territories  -> expansionist (grab free land)
  - Vulnerable targets exist      -> opportunist (guaranteed wins)
  - Near continent completion     -> continent-focused (huge bonus)
  - Under threat / thin troops    -> defensive (gather, avoid PEACE)
  - Rich / many territories       -> economic (PEACE for income)
  - Flush with cash + troops      -> aggressive (attack to dominate)

Supports configurable difficulty via constants.get_difficulty_preset().

Improvements in this version:
  - Smarter troop distribution: prioritizes border countries facing strongest threats
  - Multi-turn planning: tracks "target continent" for sustained focus
  - Diplomatic awareness: avoids attacking strongest players when weak
  - Better stalemate breaking: targets weakest enemy borders
  - Risk assessment: considers post-attack vulnerability before attacking
  - Opportunistic timing: builds up for continent completion
"""

import random
import logging
from collections import defaultdict

from constants import (
    CLAIM_COST, TROOP_COST, continent_value,
    get_difficulty_preset, DEFAULT_BOT_DIFFICULTY,
)

logger = logging.getLogger(__name__)

# Module-level difficulty (can be changed at runtime)
_current_difficulty = DEFAULT_BOT_DIFFICULTY

# Module-level target continent tracking for multi-turn planning
_target_continents = {}


def set_difficulty(name):
    """Set the bot difficulty level ('easy', 'normal', 'hard')."""
    global _current_difficulty
    _current_difficulty = name
    logger.info("Bot difficulty set to: %s", name)


def get_difficulty():
    """Get the current bot difficulty name."""
    return _current_difficulty


def set_target_continent(bot_name, continent):
    """Set a bot's target continent for multi-turn planning."""
    global _target_continents
    _target_continents[bot_name] = continent
    if continent:
        logger.debug("Bot %s targeting continent: %s", bot_name, continent)


def get_target_continent(bot_name):
    """Get a bot's target continent, or None if not set."""
    return _target_continents.get(bot_name)


# ============================================================
# Helpers
# ============================================================

def find_player(gs, name):
    for p in gs.get("players", []):
        if p.get("name") == name:
            return p
    return None


def pins_of(gs, owner_name):
    return [p for p in gs.get("pins", []) if p.get("owner") == owner_name]


def pin_by_id(gs, pid):
    for p in gs.get("pins", []):
        if p.get("id") == pid:
            return p
    return None


def all_pins(gs):
    return gs.get("pins", [])


def attack_win_probability():
    """P(1d20 > max(2d20)) ~ 0.2467"""
    return 0.2467


def evaluate_continent_state(gs, me_name):
    cont_map = defaultdict(lambda: {"total": 0, "mine": 0, "enemy": 0, "free": 0})
    for p in all_pins(gs):
        cont = p.get("continent", "") or ""
        if not cont:
            continue
        cont_map[cont]["total"] += 1
        owner = p.get("owner")
        if owner == me_name:
            cont_map[cont]["mine"] += 1
        elif owner:
            cont_map[cont]["enemy"] += 1
        else:
            cont_map[cont]["free"] += 1
    return cont_map


def get_vulnerable_players(gs, me_name):
    return {p.get("name") for p in gs.get("players", [])
            if p.get("vulnerable") and p.get("name") != me_name}


def total_troops(gs, name):
    return sum(int(p.get("troops", 0) or 0) for p in pins_of(gs, name))


def neighbors_of(gs, pin, me_name):
    result = []
    for a in pin.get("adj", []):
        nb = pin_by_id(gs, a.get("to"))
        if nb:
            result.append((nb, int(a.get("cost", 0) or 0)))
    return result


# ============================================================
# New improvement helpers
# ============================================================

def get_strongest_player(gs, me_name):
    """Find the player with the most troops (excluding self)."""
    strongest = None
    strongest_troops = 0
    for p in gs.get("players", []):
        pname = p.get("name")
        if pname == me_name:
            continue
        troops = total_troops(gs, pname)
        if troops > strongest_troops:
            strongest_troops = troops
            strongest = pname
    return strongest, strongest_troops


def get_border_threats(gs, me_name):
    """
    Map each of my border countries to the maximum enemy troop count adjacent to it.
    Returns: {pin_id: max_adjacent_enemy_troops}
    """
    threats = {}
    for pin in pins_of(gs, me_name):
        max_threat = 0
        for nb, _ in neighbors_of(gs, pin, me_name):
            if nb.get("owner") and nb.get("owner") != me_name:
                enemy_troops = int(nb.get("troops", 0) or 0)
                max_threat = max(max_threat, enemy_troops)
        if max_threat > 0:
            threats[pin["id"]] = max_threat
    return threats


def find_weakest_border(gs, me_name):
    """
    Find the border country with the weakest enemy opposition.
    Returns: (pin_id, min_max_threat) or (None, float('inf'))
    Useful for stalemate breaking.
    """
    threats = get_border_threats(gs, me_name)
    if not threats:
        return None, float('inf')
    min_id = min(threats.keys(), key=lambda pid: threats[pid])
    return min_id, threats[min_id]


def compute_post_attack_safety(gs, src_pin, send_amount, me_name):
    """
    After attacking with send_amount troops, will the source country be
    left critically vulnerable (0-1 troops next to strong enemy)?
    Returns True if safe, False if risky.
    """
    src_troops = int(src_pin.get("troops", 0) or 0)
    remaining = src_troops - send_amount

    # If we'd have 0-1 troops left and adjacent to a strong enemy, risky
    if remaining <= 1:
        for nb, _ in neighbors_of(gs, src_pin, me_name):
            if nb.get("owner") and nb.get("owner") != me_name:
                enemy_troops = int(nb.get("troops", 0) or 0)
                if enemy_troops >= 3:
                    logger.debug("Post-attack safety risk: %d troops after attack, %d enemy adjacent",
                                remaining, enemy_troops)
                    return False
    return True


def get_nearest_continent_to_complete(gs, me_name):
    """
    Find the continent closest to completion that I own at least 1 territory in.
    Returns: (continent_name, remaining_to_claim) or (None, float('inf'))
    """
    cont_state = evaluate_continent_state(gs, me_name)
    best_cont = None
    min_remaining = float('inf')

    for cont, ci in cont_state.items():
        # Only consider continents where I have at least 1 territory
        if ci["mine"] > 0:
            remaining = ci["total"] - ci["mine"]
            if remaining > 0 and remaining < min_remaining:
                min_remaining = remaining
                best_cont = cont

    return best_cont, min_remaining if best_cont else float('inf')


# ============================================================
# Situational analysis -> dynamic weights
# ============================================================

def compute_situation_weights(gs, me_name, my_pins, my_money):
    """
    Analyze the game state and return a weight dict tuned to the current situation.
    This replaces static playstyles with adaptive decision-making.
    Weights are further modified by the current difficulty preset.

    Improvements:
    - Diplomatic awareness: avoid attacking strongest player when weak
    - Better stalemate strategy: target weakest borders
    - Opportunistic continent completion: build up for final push
    """
    preset = get_difficulty_preset(_current_difficulty)

    territory_count = len(my_pins)
    my_troop_total = total_troops(gs, me_name)
    total_pins_count = len(all_pins(gs))
    vulnerable = get_vulnerable_players(gs, me_name)
    cont_state = evaluate_continent_state(gs, me_name)

    # Max troops on any border country
    max_border_troops = 0
    for pin in my_pins:
        t = int(pin.get("troops", 0) or 0)
        for a in pin.get("adj", []):
            nb = pin_by_id(gs, a.get("to"))
            if nb and nb.get("owner") and nb.get("owner") != me_name:
                max_border_troops = max(max_border_troops, t)
                break

    # Count free adjacent territory
    free_adjacent = 0
    for pin in my_pins:
        for nb, cost in neighbors_of(gs, pin, me_name):
            if not nb.get("owner"):
                free_adjacent += 1

    # Count vulnerable adjacent targets
    vuln_adjacent = 0
    for pin in my_pins:
        for nb, cost in neighbors_of(gs, pin, me_name):
            if nb.get("owner") in vulnerable:
                vuln_adjacent += 1

    # Measure threat level
    adjacent_enemy_troops = 0
    for pin in my_pins:
        for nb, cost in neighbors_of(gs, pin, me_name):
            if nb.get("owner") and nb.get("owner") != me_name and nb.get("owner") not in vulnerable:
                adjacent_enemy_troops += int(nb.get("troops", 0) or 0)
    threat_ratio = adjacent_enemy_troops / max(1, my_troop_total)

    # Check continent completion proximity
    near_continent = False
    target_cont, cont_remaining = get_nearest_continent_to_complete(gs, me_name)
    if target_cont and cont_remaining <= 2:
        near_continent = True
        set_target_continent(me_name, target_cont)
        logger.debug("%s targeting continent %s (needs %d more)", me_name, target_cont, cont_remaining)

    # Special handling for continent about to complete
    building_for_continent = False
    if target_cont and cont_remaining <= 3 and cont_remaining > 0:
        # If close to completing, be willing to gather more to finish it
        building_for_continent = True

    # Stalemate detection
    all_owned = all(p.get("owner") for p in all_pins(gs))
    stalemate = all_owned and vuln_adjacent == 0 and free_adjacent == 0

    # Diplomatic awareness: check strength relative to strongest player
    strongest_player, strongest_troops = get_strongest_player(gs, me_name)
    im_weak = my_troop_total < strongest_troops * 0.5
    strongest_is_neighbor = False
    if strongest_player:
        for pin in my_pins:
            for nb, _ in neighbors_of(gs, pin, me_name):
                if nb.get("owner") == strongest_player:
                    strongest_is_neighbor = True
                    break
            if strongest_is_neighbor:
                break

    # Compute base weights
    w = {
        "attack_willingness": 0.5,
        "continent_weight": 1.0,
        "vuln_bonus": 200,
        "free_claim_bonus": 150,
        "crossing_penalty": 1.0,
        "peace_preference": 1.0,
        "gather_preference": 1.0,
        "gather_threshold": 3,
    }

    can_attack = any(
        int(p.get("troops", 0) or 0) >= 3
        for p in my_pins
        if any(
            pin_by_id(gs, a.get("to"))
            and pin_by_id(gs, a.get("to")).get("owner") != me_name
            for a in p.get("adj", [])
        )
    )

    # STALEMATE BREAKER (improved: target weakest borders)
    if stalemate:
        w["peace_preference"] = 0.01
        w["crossing_penalty"] = 0.3
        w["continent_weight"] = 2.5
        if can_attack:
            w["attack_willingness"] = preset.get("stalemate_aggression", 2.5)
            w["gather_preference"] = 0.3
            # Mark weakest border for targeting in expansion scoring
            weakest_border_id, _ = find_weakest_border(gs, me_name)
            w["_stalemate_target"] = weakest_border_id
        else:
            w["attack_willingness"] = 0.1
            w["gather_preference"] = 5.0
            w["gather_threshold"] = 8

    # Early game
    if territory_count <= 2 or (free_adjacent > 0 and territory_count < total_pins_count * 0.15):
        w["free_claim_bonus"] = 250
        w["peace_preference"] = 0.3
        w["crossing_penalty"] = 0.6
        w["gather_preference"] = 0.5

    # Vulnerable targets
    if vuln_adjacent > 0:
        w["vuln_bonus"] = 400
        w["attack_willingness"] = max(w["attack_willingness"], 0.8)
        w["peace_preference"] *= 0.5

    # Near continent completion (improved: more aggressive for final push)
    if near_continent:
        w["continent_weight"] = 2.5
        w["attack_willingness"] = max(w["attack_willingness"], 0.7)
        w["crossing_penalty"] = min(w["crossing_penalty"], 0.5)
    elif building_for_continent:
        # Not quite done, but close enough to be willing to gather more
        w["gather_preference"] = max(w["gather_preference"], 1.8)
        w["continent_weight"] = 1.8

    # Diplomatic awareness: avoid attacking strongest player when weak
    if im_weak and strongest_is_neighbor:
        w["attack_willingness"] = min(w["attack_willingness"], 0.2)
        w["gather_preference"] = max(w["gather_preference"], 2.0)
        logger.debug("%s is weak and adjacent to strongest player, playing defensively", me_name)
        # Prefer vulnerable or weak targets instead
        w["vuln_bonus"] = min(w["vuln_bonus"], 150)
    elif im_weak:
        # Weak but not adjacent to strongest: be cautious overall
        w["attack_willingness"] = min(w["attack_willingness"], 0.35)

    # Under threat
    if threat_ratio > 1.5:
        w["peace_preference"] *= 0.3
        w["gather_preference"] = 2.0
        w["gather_threshold"] = 6
        w["attack_willingness"] = min(w["attack_willingness"], 0.3)
    elif threat_ratio > 0.8:
        w["peace_preference"] *= 0.6
        w["gather_preference"] = 1.4
        w["gather_threshold"] = 4

    # Rich with many territories, no immediate opportunities (not in stalemate)
    if not stalemate and territory_count >= 5 and free_adjacent == 0 and vuln_adjacent == 0:
        w["peace_preference"] = max(w["peace_preference"], 1.5)
        if my_money > 1000:
            w["peace_preference"] = max(w["peace_preference"], 1.8)

    # Flush with cash + troops
    if my_money > 800 and max_border_troops > 4:
        w["attack_willingness"] = max(w["attack_willingness"], 0.8)
        w["crossing_penalty"] = min(w["crossing_penalty"], 0.7)

    # Low troops on borders
    if not stalemate and max_border_troops < 2 and territory_count > 0:
        w["gather_preference"] = max(w["gather_preference"], 1.5)
        w["attack_willingness"] = min(w["attack_willingness"], 0.3)

    # Apply difficulty multipliers
    w["attack_willingness"] *= preset.get("attack_willingness_mult", 1.0)
    w["peace_preference"] *= preset.get("peace_preference_mult", 1.0)
    w["gather_preference"] *= preset.get("gather_preference_mult", 1.0)
    w["continent_weight"] *= preset.get("continent_weight_mult", 1.0)

    return w


# ============================================================
# PEACE value estimation
# ============================================================

def peace_value(gs, me_name):
    my_countries = len(pins_of(gs, me_name))
    if my_countries == 0:
        return 0
    base_payout = 100 * my_countries
    my_pins_list = pins_of(gs, me_name)
    adjacent_enemy_threat = 0
    for pin in my_pins_list:
        for nb, cost in neighbors_of(gs, pin, me_name):
            if nb.get("owner") and nb.get("owner") != me_name:
                adjacent_enemy_threat += int(nb.get("troops", 0) or 0)
    my_total = total_troops(gs, me_name)
    if my_total > 0 and adjacent_enemy_threat > my_total * 2:
        return base_payout * 0.15
    elif adjacent_enemy_threat > my_total:
        return base_payout * 0.4
    elif adjacent_enemy_threat > my_total * 0.5:
        return base_payout * 0.7
    else:
        return base_payout * 0.9


# ============================================================
# Expansion candidate scoring
# ============================================================

def score_expansion_candidates(gs, me_name, my_pins, my_money, vulnerable, weights):
    """
    Score expansion candidates with improvements:
    - Risk assessment: penalize attacks that leave source vulnerable
    - Smarter troop distribution: prioritize threatening borders
    - Stalemate targeting: favor weakest borders when in stalemate
    - Opportunistic continent completion: boost targets for near-complete continents
    """
    candidates = []
    cont_state = evaluate_continent_state(gs, me_name)
    p_win = attack_win_probability()

    for src in my_pins:
        src_troops = int(src.get("troops", 0) or 0)
        if src_troops < 3:
            continue

        for nb, crossing_cost in neighbors_of(gs, src, me_name):
            if nb.get("owner") == me_name:
                continue

            total_cost = crossing_cost + CLAIM_COST
            if my_money < total_cost:
                continue

            tgt_owner = nb.get("owner")
            tgt_troops = int(nb.get("troops", 0) or 0)
            tgt_cont = nb.get("continent", "") or ""
            is_free = not tgt_owner
            is_vulnerable = tgt_owner in vulnerable
            max_send = src_troops - 1

            # Smart send amount based on troop advantage
            if is_free:
                send = min(max_send, max(1, src_troops // 4))
            elif is_vulnerable:
                send = min(max_send, max(2, src_troops // 2))
            else:
                advantage = src_troops / max(1, tgt_troops + 1)
                if advantage >= 5:
                    send = min(max_send, max(3, int(src_troops * 0.7)))
                elif advantage >= 3:
                    send = min(max_send, max(3, int(src_troops * 0.5)))
                elif advantage >= 2:
                    send = min(max_send, max(3, tgt_troops + 2))
                else:
                    send = min(max_send, max(2, tgt_troops + 1))
                if send < 2:
                    continue

            # RISK ASSESSMENT: check if we'd be left vulnerable
            if not is_free and not is_vulnerable:
                if not compute_post_attack_safety(gs, src, send, me_name):
                    # Skip this attack if it leaves us critically vulnerable
                    logger.debug("Skipping risky attack from pin %d", src["id"])
                    continue

            # Score: base value
            score = 0.0
            willingness = weights.get("attack_willingness", 0.5)

            if is_free:
                score += 200 + weights.get("free_claim_bonus", 150)
            elif is_vulnerable:
                score += 300 + weights.get("vuln_bonus", 200)
                score += max(0, 100 - tgt_troops * 20)
            else:
                advantage_ratio = src_troops / max(1, tgt_troops)
                troop_value = send * TROOP_COST
                ev_win = 100 * 3 + 50
                ev_attack = p_win * ev_win - (1 - p_win) * (troop_value + total_cost * 0.5)
                score += ev_attack * willingness

                if tgt_troops <= 1:
                    score += 200 * willingness
                elif tgt_troops <= 3:
                    score += 120 * willingness
                elif tgt_troops <= 5:
                    score += 50 * willingness

                if advantage_ratio >= 5:
                    score += 150 * willingness
                elif advantage_ratio >= 3:
                    score += 80 * willingness
                elif advantage_ratio >= 2:
                    score += 30 * willingness

                if willingness > 1.0:
                    score += 120 * (willingness - 1.0)

            # Continent completion bonus (improved for opportunistic timing)
            if tgt_cont and cont_state[tgt_cont]["total"] > 0:
                ci = cont_state[tgt_cont]
                remaining = ci["total"] - ci["mine"]
                if remaining <= 1:
                    bonus = continent_value(tgt_cont) * weights.get("continent_weight", 1.0)
                    if is_free or is_vulnerable:
                        score += bonus
                    else:
                        score += bonus * 0.5
                    score = max(score, bonus * 0.4)
                elif remaining <= 3 and ci["mine"] > 0:
                    # Boost score for targets on target continent
                    target_cont = get_target_continent(me_name)
                    if tgt_cont == target_cont:
                        progress = ci["mine"] / ci["total"]
                        score += continent_value(tgt_cont) * progress * 0.5 * weights.get("continent_weight", 1.0)
                    else:
                        progress = ci["mine"] / ci["total"]
                        score += continent_value(tgt_cont) * progress * 0.3 * weights.get("continent_weight", 1.0)

            # SMARTER TROOP DISTRIBUTION: prioritize borders facing strongest threats
            if not is_free and not is_vulnerable:
                threats = get_border_threats(gs, me_name)
                threat_at_src = threats.get(src["id"], 0)
                if threat_at_src > tgt_troops:
                    # Attacking from a threatened border: boost score
                    score += threat_at_src * 2

            # Penalties
            if not is_free and not is_vulnerable and score < 0:
                continue

            score -= crossing_cost * weights.get("crossing_penalty", 1.0)

            # STALEMATE TARGETING: if we have a marked stalemate target, boost it
            stalemate_target = weights.get("_stalemate_target")
            if stalemate_target and src["id"] == stalemate_target:
                score += 100
                logger.debug("Stalemate: prioritizing weakest border pin %d", stalemate_target)

            # Prefer targets surrounded by allies
            friendly_neighbors = 0
            enemy_neighbors = 0
            for nb2, _ in neighbors_of(gs, nb, me_name):
                if nb2.get("owner") == me_name:
                    friendly_neighbors += 1
                elif nb2.get("owner") and nb2.get("owner") != me_name:
                    enemy_neighbors += 1
            score += friendly_neighbors * 15
            score -= enemy_neighbors * 5

            candidates.append((score, src["id"], nb["id"], send))

    candidates.sort(key=lambda x: -x[0])
    return candidates


# ============================================================
# Core decision logic
# ============================================================

def _base_decide(gs, me_name, my_pins, my_money, weights):
    """
    Core decision logic with improvements:
    - Smarter troop distribution when gathering
    - Opportunistic continent completion building
    """
    vulnerable = get_vulnerable_players(gs, me_name)

    candidates = score_expansion_candidates(gs, me_name, my_pins, my_money, vulnerable, weights)
    best_expand = candidates[0] if candidates else None
    best_expand_score = best_expand[0] if best_expand else -9999

    pv = peace_value(gs, me_name) * weights.get("peace_preference", 1.0)

    my_troop_total = total_troops(gs, me_name)
    territory_count = len(my_pins)

    # SMARTER TROOP DISTRIBUTION: prioritize threatened borders
    threats = get_border_threats(gs, me_name)
    max_border_troops = 0
    most_threatened_id = None
    max_threat = 0

    for pin in my_pins:
        t = int(pin.get("troops", 0) or 0)
        is_border = False
        for a in pin.get("adj", []):
            nb = pin_by_id(gs, a.get("to"))
            if nb and nb.get("owner") and nb.get("owner") != me_name:
                is_border = True
                max_border_troops = max(max_border_troops, t)
                break
        if is_border and pin["id"] in threats:
            if threats[pin["id"]] > max_threat:
                max_threat = threats[pin["id"]]
                most_threatened_id = pin["id"]

    gather_value = 0
    threshold = weights.get("gather_threshold", 3)
    if my_money >= TROOP_COST * 3 and territory_count > 0:
        if max_border_troops < threshold:
            gather_value = 150 * weights.get("gather_preference", 1.0)
        elif max_border_troops < 6:
            gather_value = 80 * weights.get("gather_preference", 1.0)
        else:
            gather_value = 30

    # Check if we're building for continent completion
    target_cont = get_target_continent(me_name)
    cont_state = evaluate_continent_state(gs, me_name)
    building_for_continent = False
    if target_cont and target_cont in cont_state:
        ci = cont_state[target_cont]
        remaining = ci["total"] - ci["mine"]
        if 0 < remaining <= 3:
            # Building for final push: boost gather value
            building_for_continent = True
            gather_value = max(gather_value, 120 * weights.get("gather_preference", 1.0))

    # Always take strong expansion opportunities first
    if best_expand and best_expand_score > 150:
        return ("EXPAND", (best_expand[1], best_expand[2], best_expand[3]))

    if pv > best_expand_score and pv > gather_value:
        return ("PEACE", None)

    if best_expand and best_expand_score > gather_value and best_expand_score > 0:
        return ("EXPAND", (best_expand[1], best_expand[2], best_expand[3]))

    if gather_value > 0 and my_money >= TROOP_COST * 2:
        return ("GATHER", None)

    # Stalemate fallback
    if best_expand and weights.get("peace_preference", 1.0) < 0.3 and best_expand_score > -200:
        return ("EXPAND", (best_expand[1], best_expand[2], best_expand[3]))

    if pv > 0:
        return ("PEACE", None)

    return ("NOTHING", None)


# ============================================================
# Main entry point
# ============================================================

def decide(game_state, player_name):
    """
    Adaptive AI entry point. Analyzes the game state and picks the
    optimal action -- no fixed playstyle, just pure situational play.
    """
    try:
        gs = game_state or {}
        me = find_player(gs, player_name)
        if not me:
            return ("PEACE", None)

        my_money = int(me.get("money", 0) or 0)
        my_pins = pins_of(gs, player_name)

        if not my_pins:
            if my_money >= TROOP_COST:
                return ("GATHER", None)
            return ("NOTHING", None)

        weights = compute_situation_weights(gs, player_name, my_pins, my_money)
        return _base_decide(gs, player_name, my_pins, my_money, weights)
    except (KeyError, TypeError, ValueError, IndexError) as e:
        logger.error("bot_playstyles decision error for %s: %s", player_name, e)
        return ("PEACE", None)
    except Exception as e:
        logger.error("Unexpected bot_playstyles error for %s: %s", player_name, e, exc_info=True)
        return ("PEACE", None)


# Legacy compatibility
def assign_playstyle(bot_name):
    return "adaptive"


def get_playstyle(bot_name):
    return "adaptive"
