# heuristic_bot.py
"""
Enhanced heuristic bot for GPD (client snapshot interface) with multiple playstyles.

This module now imports from bot_playstyles.py for more sophisticated AI.
Falls back to basic heuristics if bot_playstyles is unavailable.

Interface:
decide(game_state, player_name) -> ("PEACE"/"GATHER"/"EXPAND", params)
  where params for EXPAND is (src_id, tgt_id, send_amount)
"""

import random
import math
from collections import defaultdict

# Try to import enhanced bot playstyles
try:
    import bot_playstyles
    HAS_ENHANCED_BOTS = True
except ImportError:
    HAS_ENHANCED_BOTS = False
    print("Warning: bot_playstyles not available, using basic heuristics")

CLAIM_COST = 200
TROOP_COST = 50
TARGET_MONEY = 1000
MONEY_TOLERANCE = 200
MONEY_LOWER = TARGET_MONEY - MONEY_TOLERANCE   # 800
MONEY_UPPER = TARGET_MONEY + MONEY_TOLERANCE   # 1200

CONT_VALUES = {"Europe":1000,"Asia":1000,"North America":800,"South America":350,"Central America":200,"Africa":400}
DEFAULT_CONT_VALUE = 150
def continent_value(name):
    return CONT_VALUES.get(name, DEFAULT_CONT_VALUE)

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

def estimated_attack_success_prob(att_troops, def_troops):
    try:
        att = float(att_troops)
        d = float(def_troops)
    except Exception:
        return 0.25
    if att <= 0:
        return 0.0
    if d <= 0:
        return 0.92
    ratio = att / (d + 0.01)
    val = 1.0 / (1.0 + math.exp(-1.05*(ratio - 1.0)))
    return max(0.03, min(0.97, 0.25 + 0.75*val))

def evaluate_continent_completion(gs, me_name):
    cont_map = defaultdict(lambda: {"total":0, "owned":0})
    for p in gs.get("pins", []):
        cont = p.get("continent", "") or ""
        cont_map[cont]["total"] += 1
        if p.get("owner") == me_name:
            cont_map[cont]["owned"] += 1
    return cont_map

def value_of_capture(gs, me_name, tgt):
    base = 40.0
    cont = tgt.get("continent", "") or ""
    cont_val = continent_value(cont) / 40.0
    cont_map = evaluate_continent_completion(gs, me_name)
    cont_info = cont_map.get(cont, {"total":0,"owned":0})
    completion_bonus = 0.0
    if cont_info["total"] > 0:
        if cont_info["owned"] + 1 >= cont_info["total"]:
            completion_bonus = continent_value(cont) / 25.0
        else:
            completion_bonus = (cont_info["owned"] / max(1.0, cont_info["total"])) * (continent_value(cont)/80.0)
    adjacent_my_count = 0
    for a in tgt.get("adj", []):
        nb = pin_by_id(gs, a.get("to"))
        if nb and nb.get("owner") == me_name:
            adjacent_my_count += 1
    adjacency_bonus = min(20, adjacent_my_count * 6)
    return base + cont_val + completion_bonus + adjacency_bonus

def choose_send_amount_for_unowned(src):
    s = int(src.get("troops", 0) or 0)
    if s <= 1:
        return 0
    if s <= 3:
        return 1
    if s <= 6:
        return max(1, s//3)
    return max(1, min(6, s//2))

def choose_send_amount_for_attack(src, tgt):
    s = int(src.get("troops", 0) or 0)
    d = int(tgt.get("troops", 0) or 0)
    if s <= 1:
        return 0
    possible = s - 1
    desired = d + 1
    send = max(1, min(possible, desired))
    if possible >= d*3 and d > 0:
        send = min(possible, d + max(2, d//2))
    send = min(send, max(1, int(s*0.7)))
    return send

def find_prioritized_expansion(gs, me_name, my_pins, my_money):
    sources = sorted([p for p in my_pins if int(p.get("troops", 0) or 0) > 3], key=lambda x: -int(x.get("troops",0) or 0))
    for src in sources:
        src_troops = int(src.get("troops",0) or 0)
        candidates = []
        for a in src.get("adj", []):
            tgt = pin_by_id(gs, a.get("to"))
            if not tgt:
                continue
            # Never expand into own country
            if tgt.get("owner") == me_name:
                continue
            cost = int(a.get("cost", 0) or 0)
            is_unowned = 1 if not tgt.get("owner") else 0
            def_troops = int(tgt.get("troops", 0) or 0)
            candidates.append({
                "key": (-is_unowned, cost, def_troops, int(tgt.get("id", 0))),
                "tgt": tgt,
                "adj": a
            })
        if not candidates:
            continue
        candidates.sort(key=lambda c: c["key"])
        best = candidates[0]
        crossing_cost = int(best["adj"].get("cost", 0) or 0)
        best_tgt = best["tgt"]
        send = 2
        if src_troops <= send:
            continue
        needed = crossing_cost + CLAIM_COST
        if my_money >= needed:
            return (src["id"], best_tgt["id"], send)
        if my_money >= MONEY_UPPER and my_money >= needed:
            return (src["id"], best_tgt["id"], send)
    return None

def find_any_expansion(gs, me_name, my_pins, my_money):
    # Scan all sources for any legal expansion (never into own country)
    for src in my_pins:
        src_troops = int(src.get("troops",0) or 0)
        if src_troops <= 1:
            continue
        for a in src.get("adj", []):
            tgt = pin_by_id(gs, a.get("to"))
            if not tgt:
                continue
            if tgt.get("owner") == me_name:
                continue  # never attack own country
            crossing = int(a.get("cost",0) or 0)
            needed = crossing + CLAIM_COST
            if my_money < needed:
                continue
            if not tgt.get("owner"):
                send = choose_send_amount_for_unowned(src)
                if send > 0 and send < src_troops:
                    return (src["id"], tgt["id"], send)
            else:
                send = choose_send_amount_for_attack(src, tgt)
                if send > 0 and send < src_troops:
                    return (src["id"], tgt["id"], send)
    return None

def decide(game_state, player_name):
    """
    Main decision function. Uses enhanced playstyles if available,
    otherwise falls back to basic heuristics.
    """
    try:
        # Use enhanced bot playstyles if available
        if HAS_ENHANCED_BOTS:
            return bot_playstyles.decide(game_state, player_name)
        
        # Fallback to basic heuristics
        gs = game_state or {}
        me = find_player(gs, player_name)
        if not me:
            return ("PEACE", None)

        my_money = int(me.get("money", 0) or 0)
        my_pins = pins_of(gs, player_name)
        all_pins = gs.get("pins", []) or []
        my_troops_total = sum(int(p.get("troops",0) or 0) for p in my_pins)

        threatened = False
        for src in my_pins:
            st = int(src.get("troops",0) or 0)
            for a in src.get("adj", []):
                nb = pin_by_id(gs, a.get("to"))
                if nb and nb.get("owner") and nb.get("owner") != player_name:
                    if int(nb.get("troops",0) or 0) >= st + 2:
                        threatened = True
                        break
            if threatened:
                break

        # If no countries, gather if possible, else peace
        if not my_pins:
            if my_money >= TROOP_COST:
                return ("GATHER", None)
            return ("PEACE", None)

        # 1) Prioritized expansion: never into own country
        pri = find_prioritized_expansion(gs, player_name, my_pins, my_money)
        if pri:
            return ("EXPAND", pri)

        # 2) Scan for any expansion (never into own country)
        any_exp = find_any_expansion(gs, player_name, my_pins, my_money)
        if any_exp:
            return ("EXPAND", any_exp)

        # 3) If no expansion possible, gather if money allows
        if my_money >= TROOP_COST:
            return ("GATHER", None)

        # 4) Otherwise, peace
        return ("PEACE", None)
    except Exception as e:
        print("heuristic_bot exception in decide:", e)
        return ("PEACE", None)

# Test harness
if __name__ == "__main__":
    sample = {
        "players":[{"name":"bot1","money":900,"is_bot":True},{"name":"player","money":500,"is_bot":False}],
        "pins":[
            {"id":1,"name":"A","owner":"bot1","troops":6,"adj":[{"to":2,"cost":0},{"to":3,"cost":40}], "continent":"Europe"},
            {"id":2,"name":"B","owner":None,"troops":0,"adj":[{"to":1,"cost":0}], "continent":"Europe"},
            {"id":3,"name":"C","owner":"bot1","troops":2,"adj":[{"to":1,"cost":40}], "continent":"Europe"}  # own country; never attack
        ]
    }
    print(decide(sample,"bot1"))