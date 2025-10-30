# bot_playstyles.py
"""
Enhanced bot AI with multiple distinct playstyles.
Each bot randomly chooses a playstyle at game startup and sticks with it.
"""

import random
import math
from collections import defaultdict

CLAIM_COST = 200
TROOP_COST = 50

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

def evaluate_continent_completion(gs, me_name):
    cont_map = defaultdict(lambda: {"total":0, "owned":0})
    for p in gs.get("pins", []):
        cont = p.get("continent", "") or ""
        cont_map[cont]["total"] += 1
        if p.get("owner") == me_name:
            cont_map[cont]["owned"] += 1
    return cont_map

# ============ PLAYSTYLE: AGGRESSIVE ============
# Always prioritizes expansion, attacks frequently, takes risks
def aggressive_decide(gs, me_name, my_pins, my_money):
    """Aggressive bot: prioritizes expansion over everything"""
    # Always try to expand from strongest positions
    sources = sorted([p for p in my_pins if int(p.get("troops", 0) or 0) > 1], 
                    key=lambda x: -int(x.get("troops",0) or 0))
    
    for src in sources:
        src_troops = int(src.get("troops",0) or 0)
        for a in src.get("adj", []):
            tgt = pin_by_id(gs, a.get("to"))
            if not tgt or tgt.get("owner") == me_name:
                continue
            
            cost = int(a.get("cost", 0) or 0)
            needed = cost + CLAIM_COST
            if my_money >= needed:
                send = max(1, min(src_troops - 1, int(src_troops * 0.8)))  # Send 80% of troops
                if send > 0:
                    return ("EXPAND", (src["id"], tgt["id"], send))
    
    # If can't expand, gather aggressively
    if my_money >= TROOP_COST:
        return ("GATHER", None)
    
    return ("PEACE", None)

# ============ PLAYSTYLE: DEFENSIVE ============
# Focuses on building strong positions, only attacks when overwhelmingly strong
def defensive_decide(gs, me_name, my_pins, my_money):
    """Defensive bot: builds up troops, only attacks when very strong"""
    my_troops_total = sum(int(p.get("troops",0) or 0) for p in my_pins)
    
    # Check if threatened
    threatened = False
    for src in my_pins:
        st = int(src.get("troops",0) or 0)
        for a in src.get("adj", []):
            nb = pin_by_id(gs, a.get("to"))
            if nb and nb.get("owner") and nb.get("owner") != me_name:
                if int(nb.get("troops",0) or 0) >= st:
                    threatened = True
                    break
    
    # If threatened or weak, prioritize gathering
    if threatened or my_troops_total < len(my_pins) * 3:
        if my_money >= TROOP_COST * 2:  # Save money too
            return ("GATHER", None)
    
    # Only expand to unowned or very weak territories
    for src in my_pins:
        src_troops = int(src.get("troops",0) or 0)
        if src_troops <= 4:  # Need strong position
            continue
            
        for a in src.get("adj", []):
            tgt = pin_by_id(gs, a.get("to"))
            if not tgt or tgt.get("owner") == me_name:
                continue
            
            tgt_troops = int(tgt.get("troops", 0) or 0)
            # Only attack if unowned or we have 3x advantage
            if not tgt.get("owner") or (tgt_troops > 0 and src_troops > tgt_troops * 3):
                cost = int(a.get("cost", 0) or 0)
                needed = cost + CLAIM_COST
                if my_money >= needed + 400:  # Keep money reserve
                    send = min(2, src_troops - 2)  # Send conservatively
                    if send > 0:
                        return ("EXPAND", (src["id"], tgt["id"], send))
    
    # Default to peace for income
    return ("PEACE", None)

# ============ PLAYSTYLE: EXPANSIONIST ============
# Focuses on claiming unowned territories first, continent completion second
def expansionist_decide(gs, me_name, my_pins, my_money):
    """Expansionist bot: prioritizes unowned territories and continent completion"""
    cont_map = evaluate_continent_completion(gs, me_name)
    
    # Find best expansion targets (prioritize unowned, then continent completion)
    best_moves = []
    
    for src in my_pins:
        src_troops = int(src.get("troops",0) or 0)
        if src_troops <= 1:
            continue
            
        for a in src.get("adj", []):
            tgt = pin_by_id(gs, a.get("to"))
            if not tgt or tgt.get("owner") == me_name:
                continue
            
            cost = int(a.get("cost", 0) or 0)
            needed = cost + CLAIM_COST
            if my_money < needed:
                continue
            
            is_unowned = not tgt.get("owner")
            tgt_cont = tgt.get("continent", "")
            cont_info = cont_map.get(tgt_cont, {"total":0, "owned":0})
            
            # Score based on strategic value
            score = 0
            if is_unowned:
                score += 1000  # Highly prioritize unowned
            
            # Check if this completes a continent
            if cont_info["owned"] + 1 >= cont_info["total"] and cont_info["total"] > 0:
                score += 2000 + continent_value(tgt_cont)
            elif cont_info["owned"] > 0:
                score += 500  # Continue working on started continents
            
            tgt_troops = int(tgt.get("troops", 0) or 0)
            score -= tgt_troops * 10  # Prefer weaker targets
            score -= cost  # Prefer cheaper crossings
            
            send = max(1, min(src_troops - 1, 3))
            best_moves.append((score, src["id"], tgt["id"], send))
    
    if best_moves:
        best_moves.sort(key=lambda x: -x[0])
        _, src_id, tgt_id, send = best_moves[0]
        return ("EXPAND", (src_id, tgt_id, send))
    
    # Gather if can't expand
    if my_money >= TROOP_COST and my_money < 800:
        return ("GATHER", None)
    
    return ("PEACE", None)

# ============ PLAYSTYLE: ECONOMIC ============
# Focuses on money management, prefers PEACE, builds wealth before attacking
def economic_decide(gs, me_name, my_pins, my_money):
    """Economic bot: focuses on building wealth through PEACE"""
    TARGET_MONEY = 1500
    
    # If we have good money, consider expansion
    if my_money >= TARGET_MONEY:
        # Look for cheap, valuable expansions
        for src in my_pins:
            src_troops = int(src.get("troops",0) or 0)
            if src_troops <= 2:
                continue
                
            for a in src.get("adj", []):
                tgt = pin_by_id(gs, a.get("to"))
                if not tgt or tgt.get("owner") == me_name:
                    continue
                
                cost = int(a.get("cost", 0) or 0)
                # Only cheap expansions
                if cost > 100:
                    continue
                    
                needed = cost + CLAIM_COST
                if my_money >= needed + 800:  # Keep reserve
                    is_unowned = not tgt.get("owner")
                    if is_unowned:
                        send = max(1, min(src_troops - 2, 2))
                        if send > 0:
                            return ("EXPAND", (src["id"], tgt["id"], send))
    
    # Gather only if cheap and we need troops
    my_troops_total = sum(int(p.get("troops",0) or 0) for p in my_pins)
    if my_troops_total < len(my_pins) * 2 and my_money >= TROOP_COST * 3 and my_money < TARGET_MONEY:
        return ("GATHER", None)
    
    # Default to PEACE for income
    return ("PEACE", None)

# ============ PLAYSTYLE: OPPORTUNIST ============
# Waits for vulnerable players, attacks weak positions
def opportunist_decide(gs, me_name, my_pins, my_money):
    """Opportunist bot: targets vulnerable and weak positions"""
    # Find vulnerable players
    vulnerable_players = set()
    for p in gs.get("players", []):
        if p.get("vulnerable") and p.get("name") != me_name:
            vulnerable_players.add(p.get("name"))
    
    # Prioritize attacking vulnerable players
    if vulnerable_players:
        for src in my_pins:
            src_troops = int(src.get("troops",0) or 0)
            if src_troops <= 1:
                continue
                
            for a in src.get("adj", []):
                tgt = pin_by_id(gs, a.get("to"))
                if not tgt or tgt.get("owner") == me_name:
                    continue
                
                if tgt.get("owner") in vulnerable_players:
                    cost = int(a.get("cost", 0) or 0)
                    needed = cost + CLAIM_COST
                    if my_money >= needed:
                        send = max(1, src_troops - 1)  # Send all available
                        return ("EXPAND", (src["id"], tgt["id"], send))
    
    # Look for weak enemy positions (troops <= 2)
    for src in my_pins:
        src_troops = int(src.get("troops",0) or 0)
        if src_troops <= 2:
            continue
            
        for a in src.get("adj", []):
            tgt = pin_by_id(gs, a.get("to"))
            if not tgt or tgt.get("owner") == me_name:
                continue
            
            tgt_troops = int(tgt.get("troops", 0) or 0)
            if tgt.get("owner") and tgt_troops <= 2 and src_troops > tgt_troops + 2:
                cost = int(a.get("cost", 0) or 0)
                needed = cost + CLAIM_COST
                if my_money >= needed:
                    send = max(1, min(src_troops - 1, tgt_troops + 2))
                    return ("EXPAND", (src["id"], tgt["id"], send))
    
    # Otherwise gather or peace
    if my_money >= TROOP_COST * 2:
        return ("GATHER", None)
    
    return ("PEACE", None)

# ============ PLAYSTYLE REGISTRY ============
PLAYSTYLES = {
    "aggressive": aggressive_decide,
    "defensive": defensive_decide,
    "expansionist": expansionist_decide,
    "economic": economic_decide,
    "opportunist": opportunist_decide,
}

# Store bot playstyles (bot_name -> playstyle_name)
_bot_playstyles = {}

def assign_playstyle(bot_name):
    """Assign a random playstyle to a bot"""
    if bot_name not in _bot_playstyles:
        _bot_playstyles[bot_name] = random.choice(list(PLAYSTYLES.keys()))
    return _bot_playstyles[bot_name]

def get_playstyle(bot_name):
    """Get the playstyle for a bot"""
    return _bot_playstyles.get(bot_name, "aggressive")

def decide(game_state, player_name):
    """Main decision function that routes to the appropriate playstyle"""
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
            return ("PEACE", None)
        
        # Assign playstyle if not yet assigned
        playstyle_name = assign_playstyle(player_name)
        playstyle_func = PLAYSTYLES.get(playstyle_name, aggressive_decide)
        
        # Call the playstyle-specific decision function
        result = playstyle_func(gs, player_name, my_pins, my_money)
        
        return result
    except Exception as e:
        print(f"bot_playstyles exception in decide: {e}")
        return ("PEACE", None)