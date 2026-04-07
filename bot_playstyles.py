# bot_playstyles.py
"""
Adaptive bot AI for GeoPolitical Domination.

Instead of locking each bot into a single personality, the AI dynamically
analyzes the game state every turn and computes optimal weights:

  - Early game / few territories  → expansionist (grab free land)
  - Vulnerable targets exist      → opportunist (guaranteed wins)
  - Near continent completion     → continent-focused (huge bonus)
  - Under threat / thin troops    → defensive (gather, avoid PEACE)
  - Rich / many territories       → economic (PEACE for income)
  - Flush with cash + troops      → aggressive (attack to dominate)

Uses a single score_expansion_candidates() + _base_decide() framework
with weights computed fresh each turn from situational analysis.
"""

import random
import math
from collections import defaultdict

CLAIM_COST = 200
TROOP_COST = 50

CONT_VALUES = {
    "Europe": 1000, "Asia": 1000, "North America": 800,
    "South America": 350, "Central America": 200, "Africa": 400,
}
DEFAULT_CONT_VALUE = 150


def continent_value(name):
    return CONT_VALUES.get(name, DEFAULT_CONT_VALUE)


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
    """P(1d20 > max(2d20)) ≈ 0.2467"""
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
# Situational analysis → dynamic weights
# ============================================================

def compute_situation_weights(gs, me_name, my_pins, my_money):
    """
    Analyze the game state and return a weight dict tuned to the current situation.
    This replaces static playstyles with adaptive decision-making.
    """
    territory_count = len(my_pins)
    my_troop_total = total_troops(gs, me_name)
    total_pins = len(all_pins(gs))
    vulnerable = get_vulnerable_players(gs, me_name)
    cont_state = evaluate_continent_state(gs, me_name)

    # Max troops on any border country (key metric for attack readiness)
    max_border_troops = 0
    for pin in my_pins:
        t = int(pin.get("troops", 0) or 0)
        for a in pin.get("adj", []):
            nb = pin_by_id(gs, a.get("to"))
            if nb and nb.get("owner") and nb.get("owner") != me_name:
                max_border_troops = max(max_border_troops, t)
                break

    # --- Count free adjacent territory ---
    free_adjacent = 0
    for pin in my_pins:
        for nb, cost in neighbors_of(gs, pin, me_name):
            if not nb.get("owner"):
                free_adjacent += 1

    # --- Count vulnerable adjacent targets ---
    vuln_adjacent = 0
    for pin in my_pins:
        for nb, cost in neighbors_of(gs, pin, me_name):
            if nb.get("owner") in vulnerable:
                vuln_adjacent += 1

    # --- Measure threat level ---
    adjacent_enemy_troops = 0
    for pin in my_pins:
        for nb, cost in neighbors_of(gs, pin, me_name):
            if nb.get("owner") and nb.get("owner") != me_name and nb.get("owner") not in vulnerable:
                adjacent_enemy_troops += int(nb.get("troops", 0) or 0)
    threat_ratio = adjacent_enemy_troops / max(1, my_troop_total)

    # --- Check continent completion proximity ---
    near_continent = False
    for cont, ci in cont_state.items():
        if ci["total"] > 1 and ci["mine"] > 0:
            remaining = ci["total"] - ci["mine"]
            if remaining <= 2:
                near_continent = True
                break

    # --- Stalemate detection ---
    # If no free territory and no vulnerable targets, the game is stalled.
    # Bots must become aggressive or the game never ends.
    all_owned = all(p.get("owner") for p in all_pins(gs))
    stalemate = all_owned and vuln_adjacent == 0 and free_adjacent == 0

    # --- Compute weights ---
    # Start with balanced defaults
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

    # Check if we have any countries with enough troops to actually attack from
    can_attack = any(int(p.get("troops", 0) or 0) >= 3 for p in my_pins
                     if any(pin_by_id(gs, a.get("to")) and
                            pin_by_id(gs, a.get("to")).get("owner") != me_name
                            for a in p.get("adj", [])))

    # STALEMATE BREAKER: when all territory is claimed and nobody is vulnerable,
    # bots MUST attack or the game devolves into infinite PEACE.
    if stalemate:
        w["peace_preference"] = 0.01  # virtually never PEACE in stalemate
        w["crossing_penalty"] = 0.3
        w["continent_weight"] = 2.5
        if can_attack:
            w["attack_willingness"] = 2.5
            w["gather_preference"] = 0.3
        else:
            w["attack_willingness"] = 0.1
            w["gather_preference"] = 5.0  # VERY high — gather until we can attack
            w["gather_threshold"] = 8

    # Early game: grab free land aggressively
    if territory_count <= 2 or (free_adjacent > 0 and territory_count < total_pins * 0.15):
        w["free_claim_bonus"] = 250
        w["peace_preference"] = 0.3
        w["crossing_penalty"] = 0.6
        w["gather_preference"] = 0.5

    # Vulnerable targets exist: go for guaranteed wins
    if vuln_adjacent > 0:
        w["vuln_bonus"] = 400
        w["attack_willingness"] = max(w["attack_willingness"], 0.8)
        w["peace_preference"] *= 0.5  # don't PEACE when there are free kills

    # Near continent completion: prioritize it heavily
    if near_continent:
        w["continent_weight"] = 2.5
        w["attack_willingness"] = max(w["attack_willingness"], 0.7)
        w["crossing_penalty"] = min(w["crossing_penalty"], 0.5)

    # Under threat: gather and avoid PEACE
    if threat_ratio > 1.5:
        w["peace_preference"] *= 0.3
        w["gather_preference"] = 2.0
        w["gather_threshold"] = 6
        w["attack_willingness"] = min(w["attack_willingness"], 0.3)
    elif threat_ratio > 0.8:
        w["peace_preference"] *= 0.6
        w["gather_preference"] = 1.4
        w["gather_threshold"] = 4

    # Rich with many territories and no immediate opportunities: PEACE for income
    # (but NOT during stalemate — stalemate overrides this)
    if not stalemate and territory_count >= 5 and free_adjacent == 0 and vuln_adjacent == 0:
        w["peace_preference"] = max(w["peace_preference"], 1.5)
        if my_money > 1000:
            w["peace_preference"] = max(w["peace_preference"], 1.8)

    # Flush with cash + troops: be more willing to attack
    if my_money > 800 and max_border_troops > 4:
        w["attack_willingness"] = max(w["attack_willingness"], 0.8)
        w["crossing_penalty"] = min(w["crossing_penalty"], 0.7)

    # Low troops on borders: prefer gathering over risky attacks
    if not stalemate and max_border_troops < 2 and territory_count > 0:
        w["gather_preference"] = max(w["gather_preference"], 1.5)
        w["attack_willingness"] = min(w["attack_willingness"], 0.3)

    return w


# ============================================================
# PEACE value estimation
# ============================================================

def peace_value(gs, me_name):
    my_countries = len(pins_of(gs, me_name))
    if my_countries == 0:
        return 0
    base_payout = 100 * my_countries
    my_pins = pins_of(gs, me_name)
    adjacent_enemy_threat = 0
    for pin in my_pins:
        for nb, cost in neighbors_of(gs, pin, me_name):
            if nb.get("owner") and nb.get("owner") != me_name:
                adjacent_enemy_threat += int(nb.get("troops", 0) or 0)
    my_total = total_troops(gs, me_name)
    if my_total > 0 and adjacent_enemy_threat > my_total * 2:
        return base_payout * 0.15  # very high risk
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
    candidates = []
    cont_state = evaluate_continent_state(gs, me_name)
    p_win = attack_win_probability()

    for src in my_pins:
        src_troops = int(src.get("troops", 0) or 0)
        if src_troops < 3:
            continue  # need at least 3 to send 2 and keep 1

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

            # --- Optimal send amount ---
            max_send = src_troops - 1
            if is_free:
                send = min(max_send, max(1, src_troops // 4))
            elif is_vulnerable:
                send = min(max_send, max(2, src_troops // 3))
            else:
                desired = max(3, tgt_troops + 2)  # want to garrison well if we win
                send = min(max_send, desired)
                if send < 2:
                    continue

            # --- Score ---
            score = 0.0

            if is_free:
                score += 200 + weights.get("free_claim_bonus", 150)
            elif is_vulnerable:
                score += 300 + weights.get("vuln_bonus", 200)
            else:
                troop_value = send * TROOP_COST
                ev_win = 100 * 3 + 50
                ev_attack = p_win * ev_win - (1 - p_win) * (troop_value + total_cost * 0.5)
                willingness = weights.get("attack_willingness", 0.5)
                score += ev_attack * willingness
                # In stalemate (willingness > 1.0), add a flat positive base to overcome EV deficit
                if willingness > 1.0:
                    score += 120 * (willingness - 1.0)

            # Continent completion bonus (before negative filter)
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
                    progress = ci["mine"] / ci["total"]
                    score += continent_value(tgt_cont) * progress * 0.3 * weights.get("continent_weight", 1.0)

            # Skip truly bad actions
            if not is_free and not is_vulnerable and score < 0:
                continue

            score -= crossing_cost * weights.get("crossing_penalty", 1.0)

            if not is_free and not is_vulnerable:
                score -= tgt_troops * 10

            candidates.append((score, src["id"], nb["id"], send))

    candidates.sort(key=lambda x: -x[0])
    return candidates


# ============================================================
# Core decision logic
# ============================================================

def _base_decide(gs, me_name, my_pins, my_money, weights):
    vulnerable = get_vulnerable_players(gs, me_name)

    candidates = score_expansion_candidates(gs, me_name, my_pins, my_money, vulnerable, weights)
    best_expand = candidates[0] if candidates else None
    best_expand_score = best_expand[0] if best_expand else -9999

    pv = peace_value(gs, me_name) * weights.get("peace_preference", 1.0)

    my_troop_total = total_troops(gs, me_name)
    territory_count = len(my_pins)
    # Compute max troops on any single border country (that's what matters for attacking)
    max_border_troops = 0
    for pin in my_pins:
        t = int(pin.get("troops", 0) or 0)
        for a in pin.get("adj", []):
            nb = pin_by_id(gs, a.get("to"))
            if nb and nb.get("owner") and nb.get("owner") != me_name:
                max_border_troops = max(max_border_troops, t)
                break

    gather_value = 0
    threshold = weights.get("gather_threshold", 3)
    if my_money >= TROOP_COST * 3 and territory_count > 0:
        if max_border_troops < threshold:
            gather_value = 150 * weights.get("gather_preference", 1.0)
        elif max_border_troops < 6:
            gather_value = 80 * weights.get("gather_preference", 1.0)
        else:
            gather_value = 30

    # Always take strong expansion opportunities first
    if best_expand and best_expand_score > 150:
        return ("EXPAND", (best_expand[1], best_expand[2], best_expand[3]))

    if pv > best_expand_score and pv > gather_value:
        return ("PEACE", None)

    if best_expand and best_expand_score > gather_value and best_expand_score > 0:
        return ("EXPAND", (best_expand[1], best_expand[2], best_expand[3]))

    if gather_value > 0 and my_money >= TROOP_COST * 2:
        return ("GATHER", None)

    # Stalemate fallback: attack even at poor odds rather than PEACE forever
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
    optimal action — no fixed playstyle, just pure situational play.
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
    except Exception as e:
        print(f"bot_playstyles exception: {e}")
        return ("PEACE", None)


# Legacy compatibility — these are no longer used but kept so
# heuristic_bot.py doesn't break if it references them.
def assign_playstyle(bot_name):
    return "adaptive"

def get_playstyle(bot_name):
    return "adaptive"
