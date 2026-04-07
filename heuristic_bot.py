# heuristic_bot.py
"""
Bot AI for GPD (client snapshot interface).
Delegates to bot_playstyles for the actual decision logic.

Interface:
  decide(game_state, player_name) -> ("PEACE"/"GATHER"/"EXPAND"/"NOTHING", params)
    where params for EXPAND is (src_id, tgt_id, send_amount)
"""

import bot_playstyles


def decide(game_state, player_name):
    """Main decision function — routes to bot_playstyles."""
    return bot_playstyles.decide(game_state, player_name)


# Test harness
if __name__ == "__main__":
    sample = {
        "players": [
            {"name": "bot1", "money": 900, "is_bot": True, "vulnerable": False, "was_attacked": False},
            {"name": "bot2", "money": 500, "is_bot": True, "vulnerable": True, "was_attacked": False},
            {"name": "player", "money": 500, "is_bot": False, "vulnerable": False, "was_attacked": False},
        ],
        "pins": [
            {"id": 1, "name": "A", "owner": "bot1", "troops": 8,
             "adj": [{"to": 2, "cost": 0}, {"to": 3, "cost": 0}], "continent": "Europe"},
            {"id": 2, "name": "B", "owner": "bot2", "troops": 3,
             "adj": [{"to": 1, "cost": 0}], "continent": "Europe"},
            {"id": 3, "name": "C", "owner": None, "troops": 0,
             "adj": [{"to": 1, "cost": 0}, {"to": 4, "cost": 100}], "continent": "Europe"},
            {"id": 4, "name": "D", "owner": "player", "troops": 5,
             "adj": [{"to": 3, "cost": 100}], "continent": "Asia"},
        ]
    }

    # Test bot1: has 8 troops on A, adjacent to vulnerable bot2 on B and free C
    # Should prioritize: free claim C or attack vulnerable bot2
    result = decide(sample, "bot1")
    print(f"bot1 decision: {result}")
    print(f"bot1 playstyle: {bot_playstyles.get_playstyle('bot1')}")

    # Test multiple times to see variety
    for i in range(5):
        bot_playstyles._bot_playstyles.clear()
        r = decide(sample, "bot1")
        ps = bot_playstyles.get_playstyle("bot1")
        print(f"  [{ps}] -> {r}")
