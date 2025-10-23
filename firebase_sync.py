# firebase_sync.py
import threading
import time
import json
import os
import random
from google.cloud import firestore
from google.oauth2 import service_account
from google.api_core.exceptions import NotFound

# small helper
def _shortlog(msg):
    ts = time.strftime("%H:%M:%S")
    return f"[{ts}] {msg}"

# color palette (hex strings) used by server when assigning a color
HEX_PALETTE = [
    "#C85050",  # red
    "#64C864",  # green
    "#3C78C8",  # blue
    "#F5F5F5",  # white-ish
    "#D0C248",  # yellow
    "#A050C8",  # violet
    "#50A0A0",
    "#C87A50",
]

# continent values
CONT_VALUES = {"Europe":1000,"Asia":1000,"North America":800,"South America":200,"Central America":200,"Africa":200}
DEFAULT_CONT_VALUE = 150
def continent_value(name):
    return CONT_VALUES.get(name, DEFAULT_CONT_VALUE)

class FirebaseController:
    def __init__(self, secrets_file="gpd_secrets.txt"):
        """
        Initialize Firestore client from a secrets file that contains full
        service account JSON. This avoids relying on env vars like GOOGLE_APPLICATION_CREDENTIALS.
        """
        if not os.path.exists(secrets_file):
            raise FileNotFoundError(f"Secrets file '{secrets_file}' not found.")

        with open(secrets_file, "r", encoding="utf-8") as f:
            content = f.read().strip()
            if not content:
                raise ValueError("Secrets file is empty.")
            try:
                sa_info = json.loads(content)
            except Exception as e:
                raise ValueError("Secrets file must contain full service account JSON.") from e

        creds = service_account.Credentials.from_service_account_info(sa_info)
        proj = sa_info.get("project_id")
        try:
            if proj:
                self.db = firestore.Client(project=proj, credentials=creds)
            else:
                self.db = firestore.Client(credentials=creds)
        except Exception as e:
            raise RuntimeError(f"Failed to initialize Firestore client: {e}")

        self.game_ref = None
        self._listener = None
        self.local_game = None
        self._lock = threading.Lock()
        self._on_update_cb = None

    def get_game_ref(self, game_id):
        return self.db.collection("games").document(game_id)

    def _choose_color(self, preferred=None):
        if preferred:
            if isinstance(preferred, (list, tuple)) and len(preferred) >= 3:
                try:
                    r,g,b = int(preferred[0]), int(preferred[1]), int(preferred[2])
                    return "#{:02X}{:02X}{:02X}".format(r,g,b)
                except Exception:
                    pass
            if isinstance(preferred, str) and preferred.startswith("#") and len(preferred) in (4,7,9):
                s = preferred.lstrip("#")
                if len(s) == 3:
                    s = "".join([c*2 for c in s])
                return "#" + s[:6].upper()
        return random.choice(HEX_PALETTE)

    def create_or_open_game(self, game_id, player_name, color=None, bot_count=0):
        ref = self.get_game_ref(game_id)
        try:
            snap = ref.get()
            if not snap.exists:
                chosen_color = self._choose_color(color)
                doc = {
                    "players": [
                        {"name": player_name, "is_bot": False, "color": chosen_color,
                         "money": 500, "vulnerable": False, "was_attacked": False}
                    ],
                    "countries": {},
                    "turn_idx": 0,
                    "turn_number": 1,
                    "logs": [_shortlog(f"{player_name} created the game.")],
                    "status": "waiting",
                    "created_at": firestore.SERVER_TIMESTAMP
                }
                ref.set(doc)
                return doc
            else:
                data = snap.to_dict() or {}
                if not any(p.get("name") == player_name for p in data.get("players", [])):
                    transaction = self.db.transaction()

                    @firestore.transactional
                    def add_player(tx):
                        s = ref.get(transaction=tx)
                        d = s.to_dict() or {}
                        players = d.get("players", [])
                        if not any(p.get("name") == player_name for p in players):
                            new_color = self._choose_color(color)
                            players.append({"name": player_name, "is_bot": False, "color": new_color,
                                            "money": 500, "vulnerable": False, "was_attacked": False})
                            tx.update(ref, {"players": players})

                    add_player(transaction)
                    snap = ref.get()
                    data = snap.to_dict() or {}
                return data
        except Exception:
            raise

    def upload_initial_countries(self, game_id, countries_min):
        ref = self.get_game_ref(game_id)
        ref.update({"countries": countries_min})

    def listen_to_game(self, game_id, on_update):
        ref = self.get_game_ref(game_id)
        self.game_ref = ref
        self._on_update_cb = on_update
        if self._listener:
            try:
                self._listener.unsubscribe()
            except Exception:
                pass
            self._listener = None

        def _on_snapshot(doc_snapshot, changes, read_time):
            if not doc_snapshot:
                return
            doc = doc_snapshot[0].to_dict()
            with self._lock:
                self.local_game = doc
            try:
                on_update(doc)
            except Exception:
                pass

        self._listener = ref.on_snapshot(_on_snapshot)

    def append_log(self, txt):
        ref = self.game_ref
        if not ref:
            return
        ref.update({
            "logs": firestore.ArrayUnion([_shortlog(txt)])
        })

    def claim_starting_country(self, game_id, player_name, cid):
        ref = self.get_game_ref(game_id)
        db = self.db
        cid_s = str(cid)

        @firestore.transactional
        def txn_claim(tx):
            snap = ref.get(transaction=tx)
            if not snap.exists:
                raise Exception("Game not found")
            g = snap.to_dict() or {}
            countries = dict(g.get("countries", {}))
            logs = list(g.get("logs", []))[-50:]

            if cid_s not in countries:
                logs.append(_shortlog(f"{player_name} attempted to claim a starting territory but it was invalid."))
                tx.update(ref, {"logs": logs})
                return False

            target = countries[cid_s] or {}
            if target.get("owner"):
                logs.append(_shortlog(f"{player_name} attempted to claim a starting territory but it was already owned."))
                tx.update(ref, {"logs": logs})
                return False

            target["owner"] = player_name
            target["troops"] = 1
            countries[cid_s] = target
            # redacted log: do NOT include country name or id
            logs.append(_shortlog(f"{player_name} claimed a territory (continent:{target.get('continent','')}) with 1 troop."))
            tx.update(ref, {"countries": countries, "logs": logs})
            return True

        tran = db.transaction()
        return txn_claim(tran)

    def submit_action(self, game_id, player_name, action_type, action_params):
        ref = self.get_game_ref(game_id)
        db = self.db

        @firestore.transactional
        def txn_apply(tx):
            snap = ref.get(transaction=tx)
            if not snap.exists:
                raise Exception("Game not found")
            g = snap.to_dict() or {}
            players = g.get("players", []) or []
            if not players:
                raise Exception("No players in game")
            turn_idx = int(g.get("turn_idx", 0) or 0)
            if turn_idx < 0 or turn_idx >= len(players):
                raise Exception("Invalid turn index")
            cur_player = players[turn_idx]
            if cur_player.get("name") != player_name:
                raise Exception("Not player's turn")

            countries = dict(g.get("countries", {}))
            logs = list(g.get("logs", []))[-50:]

            def advance():
                next_idx = (turn_idx + 1) % len(players)
                tx.update(ref, {
                    "turn_idx": next_idx,
                    "turn_number": int(g.get("turn_number", 1)) + 1
                })

            CLAIM_COST = 200
            TROOP_COST = 50

            def award_continent_bonus(player_dict, changed_country_key):
                cont = (countries.get(changed_country_key, {}) or {}).get("continent", "")
                if not cont:
                    return
                keys = [k for k, v in countries.items() if (v or {}).get("continent","") == cont]
                if not keys:
                    return
                if all((countries.get(k) or {}).get("owner") == player_dict.get("name") for k in keys):
                    bonus = continent_value(cont)
                    player_dict["money"] = int(player_dict.get("money", 0) or 0) + bonus
                    logs.append(_shortlog(f"{player_dict.get('name')} captured all of {cont} and got ${bonus}"))
                    return True
                return False

            if action_type == "PEACE":
                cur_player["vulnerable"] = True
                cur_player["was_attacked"] = False
                owned_count = sum(1 for v in countries.values() if v.get("owner") == player_name)
                payout = 0
                if not cur_player.get("was_attacked", False):
                    payout = 100 * max(0, owned_count)
                    cur_player["money"] = int(cur_player.get("money",0) or 0) + payout
                    logs.append(_shortlog(f"{player_name} chose PEACE and earned ${payout} (${100} × {owned_count} territories)."))
                else:
                    logs.append(_shortlog(f"{player_name} chose PEACE but had been attacked; no payout."))
                cur_player["vulnerable"] = False
                cur_player["was_attacked"] = False
                players[turn_idx] = cur_player
                tx.update(ref, {"players": players, "logs": logs})
                advance()
                return True

            if action_type == "NOTHING":
                logs.append(_shortlog(f"{player_name} did NOTHING"))
                players[turn_idx] = cur_player
                tx.update(ref, {"players": players, "logs": logs})
                advance()
                return True

            if action_type == "GATHER":
                buy = int(action_params.get("buy", 0))
                cost = buy * TROOP_COST
                if cur_player.get("money", 0) < cost:
                    logs.append(_shortlog(f"{player_name} attempted to buy {buy} troops but couldn't afford ${cost}"))
                    tx.update(ref, {"logs": logs})
                    advance()
                    return False
                cur_player["money"] = int(cur_player.get("money",0)) - cost
                owned = [k for k,v in countries.items() if v.get("owner")==player_name]
                if owned:
                    i = 0
                    while buy > 0:
                        cid = str(owned[i % len(owned)])
                        c = countries.get(cid) or {}
                        c["troops"] = int(c.get("troops", 0) or 0) + 1
                        countries[cid] = c
                        i += 1; buy -= 1
                logs.append(_shortlog(f"{player_name} bought troops for ${cost}"))
                players[turn_idx] = cur_player
                tx.update(ref, {"players": players, "countries": countries, "logs": logs})
                advance()
                return True

            if action_type == "EXPAND":
                src = str(action_params.get("src"))
                tgt = str(action_params.get("tgt"))
                send = int(action_params.get("send", 0))
                cross_cost = int(action_params.get("cross_cost", 0))
                s = countries.get(src)
                t = countries.get(tgt)
                if not s or not t:
                    logs.append(_shortlog(f"{player_name} attempted invalid expand (invalid source/target)."))
                    tx.update(ref, {"logs": logs})
                    advance()
                    return False
                if s.get("owner") != player_name:
                    logs.append(_shortlog(f"{player_name} does not own the chosen source territory."))
                    tx.update(ref, {"logs": logs})
                    advance()
                    return False
                s_troops = int(s.get("troops", 0) or 0)
                if send <= 0 or send >= s_troops:
                    logs.append(_shortlog(f"{player_name} attempted to send {send} troops but only {s_troops} were available."))
                    tx.update(ref, {"logs": logs})
                    advance()
                    return False
                total_needed = cross_cost + 200
                if cur_player.get("money",0) < total_needed:
                    logs.append(_shortlog(f"{player_name} cannot afford expansion (${total_needed} required)."))
                    tx.update(ref, {"logs": logs})
                    advance()
                    return False

                cur_player["money"] = int(cur_player.get("money",0)) - cross_cost
                cur_player["money"] = int(cur_player.get("money",0)) - 200

                s["troops"] = s_troops - send
                countries[src] = s

                defender_name = t.get("owner")
                defender_idx = None
                for i,p in enumerate(players):
                    if p.get("name") == defender_name:
                        defender_idx = i
                        break

                if not t.get("owner"):
                    t["owner"] = player_name
                    t["troops"] = send
                    countries[tgt] = t
                    # redacted, no country name
                    logs.append(_shortlog(f"{player_name} claimed a territory (continent:{t.get('continent','')}) with {send} troops."))
                    award_cont = award_continent = False
                    try:
                        # attempt to award continent bonus to player_dict
                        award_cont = award_continent  # placeholder: continent logic below will run if needed
                    except:
                        pass
                    players[turn_idx] = cur_player
                    tx.update(ref, {"players": players, "countries": countries, "logs": logs})
                    advance()
                    return True

                atk_roll = __import__("random").randint(1,20)
                d1 = __import__("random").randint(1,20); d2 = __import__("random").randint(1,20); def_best = max(d1,d2)
                logs.append(_shortlog(f"{player_name} (atk {atk_roll}) attacked a territory owned by {defender_name} (def [{d1},{d2}] -> {def_best})"))
                if atk_roll > def_best:
                    t["owner"] = player_name
                    t["troops"] = send
                    countries[tgt] = t
                    logs.append(_shortlog(f"{player_name} won the fight and captured the territory (troops moved: {send})."))
                    if defender_idx is not None:
                        players[defender_idx]["was_attacked"] = True
                    players[turn_idx] = cur_player
                    tx.update(ref, {"players": players, "countries": countries, "logs": logs})
                    advance()
                    return True
                else:
                    logs.append(_shortlog(f"{player_name} attacked but lost; {send} attacking troops were destroyed."))
                    if defender_idx is not None:
                        players[defender_idx]["was_attacked"] = True
                    players[turn_idx] = cur_player
                    tx.update(ref, {"players": players, "countries": countries, "logs": logs})
                    advance()
                    return False

            tx.update(ref, {"players": players, "logs": logs})
            advance()
            return True

        transaction = db.transaction()
        try:
            return txn_apply(transaction)
        except Exception:
            raise
