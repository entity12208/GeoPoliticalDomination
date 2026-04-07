# firebase_sync.py
"""
Firebase backend for GPD online mode.
Uses the public Firebase config + anonymous authentication via REST API.
No service account or gpd_secrets.txt required.
"""

import threading
import time
import json
import hashlib
import random
import requests

# ============================================================
# Public Firebase config (NOT a secret — designed to be public)
# ============================================================
FIREBASE_API_KEY = "AIzaSyA0QGbUDzgp3a3XkP1WGTXsW-JM0r2S36s"
FIREBASE_PROJECT_ID = "geopoliticaldomination"
FIRESTORE_BASE = f"https://firestore.googleapis.com/v1/projects/{FIREBASE_PROJECT_ID}/databases/(default)/documents"

# ============================================================
# Helpers
# ============================================================

def _shortlog(msg):
    ts = time.strftime("%H:%M:%S")
    return f"[{ts}] {msg}"

HEX_PALETTE = [
    "#C85050", "#64C864", "#3C78C8", "#F5F5F5",
    "#D0C248", "#A050C8", "#50A0A0", "#C87A50",
]

CONT_VALUES = {
    "Europe": 1000, "Asia": 1000, "North America": 800,
    "South America": 200, "Central America": 200, "Africa": 200,
}
DEFAULT_CONT_VALUE = 150

def continent_value(name):
    return CONT_VALUES.get(name, DEFAULT_CONT_VALUE)


# ============================================================
# Firestore REST document format converters
# ============================================================

def _to_fs(value):
    """Convert Python value to Firestore REST typed format."""
    if value is None:
        return {"nullValue": None}
    if isinstance(value, bool):
        return {"booleanValue": value}
    if isinstance(value, int):
        return {"integerValue": str(value)}
    if isinstance(value, float):
        return {"doubleValue": value}
    if isinstance(value, str):
        return {"stringValue": value}
    if isinstance(value, list):
        if not value:
            return {"arrayValue": {}}
        return {"arrayValue": {"values": [_to_fs(v) for v in value]}}
    if isinstance(value, dict):
        if not value:
            return {"mapValue": {}}
        return {"mapValue": {"fields": {str(k): _to_fs(v) for k, v in value.items()}}}
    return {"stringValue": str(value)}


def _from_fs(value):
    """Convert Firestore REST typed format to Python value."""
    if "nullValue" in value:
        return None
    if "booleanValue" in value:
        return value["booleanValue"]
    if "integerValue" in value:
        return int(value["integerValue"])
    if "doubleValue" in value:
        return value["doubleValue"]
    if "stringValue" in value:
        return value["stringValue"]
    if "arrayValue" in value:
        return [_from_fs(v) for v in value["arrayValue"].get("values", [])]
    if "mapValue" in value:
        fields = value["mapValue"].get("fields", {})
        return {k: _from_fs(v) for k, v in fields.items()}
    if "timestampValue" in value:
        return value["timestampValue"]
    return None


def _doc_to_dict(doc_json):
    """Convert a Firestore REST document to a plain Python dict."""
    fields = doc_json.get("fields", {})
    return {k: _from_fs(v) for k, v in fields.items()}


def _dict_to_fields(d):
    """Convert a plain Python dict to Firestore REST fields."""
    return {str(k): _to_fs(v) for k, v in d.items()}


# ============================================================
# Firebase Auth (anonymous sign-in via REST)
# ============================================================

class _AuthManager:
    """Manages anonymous Firebase auth tokens with auto-refresh."""

    def __init__(self):
        self.id_token = None
        self.refresh_token = None
        self.expires_at = 0

    def sign_in(self):
        resp = requests.post(
            f"https://identitytoolkit.googleapis.com/v1/accounts:signUp?key={FIREBASE_API_KEY}",
            json={"returnSecureToken": True},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        self.id_token = data["idToken"]
        self.refresh_token = data["refreshToken"]
        self.expires_at = time.time() + int(data.get("expiresIn", 3600)) - 60
        print("[Auth] Anonymous sign-in successful")

    def get_token(self):
        if not self.id_token or time.time() >= self.expires_at:
            if self.refresh_token:
                self._refresh()
            else:
                self.sign_in()
        return self.id_token

    def _refresh(self):
        try:
            resp = requests.post(
                f"https://securetoken.googleapis.com/v1/token?key={FIREBASE_API_KEY}",
                json={"grant_type": "refresh_token", "refresh_token": self.refresh_token},
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            self.id_token = data["id_token"]
            self.refresh_token = data["refresh_token"]
            self.expires_at = time.time() + int(data.get("expires_in", 3600)) - 60
        except Exception:
            # If refresh fails, do a fresh sign-in
            self.sign_in()

    def headers(self):
        return {"Authorization": f"Bearer {self.get_token()}"}


# ============================================================
# Firestore REST operations
# ============================================================

def _doc_url(game_id):
    return f"{FIRESTORE_BASE}/games/{game_id}"


def _get_doc(auth, game_id):
    """GET a game document. Returns (dict, exists)."""
    resp = requests.get(_doc_url(game_id), headers=auth.headers(), timeout=10)
    if resp.status_code == 404:
        return {}, False
    resp.raise_for_status()
    return _doc_to_dict(resp.json()), True


def _set_doc(auth, game_id, data):
    """Create or overwrite a game document."""
    body = {"fields": _dict_to_fields(data)}
    resp = requests.patch(_doc_url(game_id), headers=auth.headers(), json=body, timeout=10)
    resp.raise_for_status()


def _update_doc(auth, game_id, data, field_paths=None):
    """Update specific fields of a game document."""
    body = {"fields": _dict_to_fields(data)}
    params = {}
    if field_paths:
        params["updateMask.fieldPaths"] = field_paths
    resp = requests.patch(_doc_url(game_id), headers=auth.headers(), json=body,
                          params=params, timeout=10)
    resp.raise_for_status()


# ============================================================
# FirebaseController (same public API as before)
# ============================================================

class FirebaseController:
    def __init__(self, secrets_file=None):
        """Initialize with anonymous auth. No secrets file needed."""
        self._auth = _AuthManager()
        self._auth.sign_in()
        self.game_ref = None
        self._poll_thread = None
        self._poll_game_id = None
        self._poll_running = False
        self.local_game = None
        self._lock = threading.Lock()
        self._on_update_cb = None

    def _choose_color(self, preferred=None):
        if preferred:
            if isinstance(preferred, (list, tuple)) and len(preferred) >= 3:
                try:
                    r, g, b = int(preferred[0]), int(preferred[1]), int(preferred[2])
                    return "#{:02X}{:02X}{:02X}".format(r, g, b)
                except Exception:
                    pass
            if isinstance(preferred, str) and preferred.startswith("#") and len(preferred) in (4, 7, 9):
                s = preferred.lstrip("#")
                if len(s) == 3:
                    s = "".join([c * 2 for c in s])
                return "#" + s[:6].upper()
        return random.choice(HEX_PALETTE)

    def create_or_open_game(self, game_id, player_name, player_password="", color=None, bot_count=0, room_password=""):
        data, exists = _get_doc(self._auth, game_id)

        if not exists:
            # Create new game
            chosen_color = self._choose_color(color)
            player_pass_hash = hashlib.sha256((player_password or "").encode()).hexdigest()
            room_pass_hash = hashlib.sha256((room_password or "").encode()).hexdigest()

            doc = {
                "players": [
                    {"name": player_name, "is_bot": False, "color": chosen_color,
                     "money": 500, "vulnerable": False, "was_attacked": False,
                     "password_hash": player_pass_hash, "troop_buy_limit": 20}
                ],
                "countries": {},
                "turn_idx": 0,
                "turn_number": 1,
                "logs": [_shortlog(f"{player_name} created the game.")],
                "status": "waiting",
                "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "room_password_hash": room_pass_hash,
                "has_password": bool(room_password),
            }
            _set_doc(self._auth, game_id, doc)
            print(f"[Firebase] Created room: {game_id}")
            return doc
        else:
            # Join existing game
            if data.get("has_password", False):
                provided_hash = hashlib.sha256((room_password or "").encode()).hexdigest()
                stored_hash = data.get("room_password_hash") or ""
                if provided_hash != stored_hash:
                    raise Exception("Incorrect room password")

            existing = next((p for p in data.get("players", []) if p.get("name") == player_name), None)
            if existing:
                provided_hash = hashlib.sha256((player_password or "").encode()).hexdigest()
                stored_hash = existing.get("password_hash") or ""
                if provided_hash != stored_hash:
                    raise Exception("Incorrect player password")
                print(f"[Firebase] Player {player_name} rejoined room {game_id}")
                return data

            # Add new player
            players = list(data.get("players", []))
            player_pass_hash = hashlib.sha256((player_password or "").encode()).hexdigest()
            new_color = self._choose_color(color)
            players.append({
                "name": player_name, "is_bot": False, "color": new_color,
                "money": 500, "vulnerable": False, "was_attacked": False,
                "password_hash": player_pass_hash, "troop_buy_limit": 20,
            })
            _update_doc(self._auth, game_id, {"players": players}, ["players"])
            data["players"] = players
            print(f"[Firebase] Player {player_name} joined room {game_id}")
            return data

    def upload_initial_countries(self, game_id, countries_min):
        _update_doc(self._auth, game_id, {"countries": countries_min}, ["countries"])

    def listen_to_game(self, game_id, on_update):
        """Start polling the game document for changes."""
        self._poll_game_id = game_id
        self._on_update_cb = on_update

        # Stop existing poll
        self._poll_running = False
        if self._poll_thread and self._poll_thread.is_alive():
            self._poll_thread.join(timeout=3)

        self._poll_running = True
        self._poll_thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._poll_thread.start()

    def _poll_loop(self):
        last_hash = None
        while self._poll_running:
            try:
                data, exists = _get_doc(self._auth, self._poll_game_id)
                if exists:
                    # Simple change detection: hash the JSON
                    h = hash(json.dumps(data, sort_keys=True, default=str))
                    if h != last_hash:
                        last_hash = h
                        with self._lock:
                            self.local_game = data
                        if self._on_update_cb:
                            try:
                                self._on_update_cb(data)
                            except Exception as e:
                                print(f"[Poll] Callback error: {e}")
            except Exception as e:
                print(f"[Poll] Error: {e}")
            time.sleep(1.5)

    def append_log(self, txt):
        if not self._poll_game_id:
            return
        try:
            data, exists = _get_doc(self._auth, self._poll_game_id)
            if exists:
                logs = list(data.get("logs", []))[-50:]
                logs.append(_shortlog(txt))
                _update_doc(self._auth, self._poll_game_id, {"logs": logs}, ["logs"])
        except Exception as e:
            print(f"[Firebase] append_log error: {e}")

    def claim_starting_country(self, game_id, player_name, cid):
        cid_s = str(cid)
        data, exists = _get_doc(self._auth, game_id)
        if not exists:
            raise Exception("Game not found")

        countries = dict(data.get("countries", {}))
        logs = list(data.get("logs", []))[-50:]

        if cid_s not in countries:
            logs.append(_shortlog(f"{player_name} attempted to claim an invalid territory."))
            _update_doc(self._auth, game_id, {"logs": logs}, ["logs"])
            return False

        target = countries.get(cid_s) or {}
        if target.get("owner"):
            logs.append(_shortlog(f"{player_name} attempted to claim an already-owned territory."))
            _update_doc(self._auth, game_id, {"logs": logs}, ["logs"])
            return False

        target["owner"] = player_name
        target["troops"] = 1
        countries[cid_s] = target
        logs.append(_shortlog(f"{player_name} claimed a territory (continent:{target.get('continent', '')}) with 1 troop."))
        _update_doc(self._auth, game_id, {"countries": countries, "logs": logs}, ["countries", "logs"])
        return True

    def submit_action(self, game_id, player_name, action_type, action_params):
        data, exists = _get_doc(self._auth, game_id)
        if not exists:
            raise Exception("Game not found")

        players = list(data.get("players", []))
        if not players:
            raise Exception("No players in game")
        turn_idx = int(data.get("turn_idx", 0) or 0)
        if turn_idx < 0 or turn_idx >= len(players):
            raise Exception("Invalid turn index")
        cur = players[turn_idx]
        if cur.get("name") != player_name:
            raise Exception("Not player's turn")

        countries = dict(data.get("countries", {}))
        logs = list(data.get("logs", []))[-50:]
        turn_number = int(data.get("turn_number", 1) or 1)

        CLAIM_COST = 200
        TROOP_COST = 50

        def advance():
            next_idx = (turn_idx + 1) % len(players)
            # Resolve next player's PEACE vulnerability
            nxt = players[next_idx]
            if nxt.get("vulnerable"):
                if not nxt.get("was_attacked"):
                    owned = sum(1 for v in countries.values() if v.get("owner") == nxt.get("name"))
                    payout = 100 * max(0, owned)
                    nxt["money"] = int(nxt.get("money", 0) or 0) + payout
                    logs.append(_shortlog(f"{nxt.get('name')} was peaceful and earned ${payout} (${100} x {owned} territories)."))
                else:
                    logs.append(_shortlog(f"{nxt.get('name')} was attacked while vulnerable — no PEACE payout."))
                nxt["vulnerable"] = False
                nxt["was_attacked"] = False
                players[next_idx] = nxt
            _update_doc(self._auth, game_id, {
                "turn_idx": next_idx,
                "turn_number": turn_number + 1,
                "players": players,
                "countries": countries,
                "logs": logs,
            }, ["turn_idx", "turn_number", "players", "countries", "logs"])

        def award_continent_bonus(player_dict, country_key):
            cont = (countries.get(country_key) or {}).get("continent", "")
            if not cont:
                return
            keys = [k for k, v in countries.items() if (v or {}).get("continent", "") == cont]
            if keys and all((countries.get(k) or {}).get("owner") == player_dict.get("name") for k in keys):
                bonus = continent_value(cont)
                player_dict["money"] = int(player_dict.get("money", 0) or 0) + bonus
                logs.append(_shortlog(f"{player_dict.get('name')} captured all of {cont} and got ${bonus}"))

        if action_type == "PEACE":
            cur["vulnerable"] = True
            cur["was_attacked"] = False
            logs.append(_shortlog(f"{player_name} chose PEACE"))
            players[turn_idx] = cur
            advance()
            return True

        if action_type == "NOTHING":
            logs.append(_shortlog(f"{player_name} did NOTHING"))
            players[turn_idx] = cur
            advance()
            return True

        if action_type == "GATHER":
            buy = int(action_params.get("buy", 0))
            last_turn = cur.get("last_gather_turn", 0)
            if last_turn != turn_number:
                cur["troop_buy_limit"] = random.randint(1, 20)
                cur["last_gather_turn"] = turn_number
            buy_limit = cur.get("troop_buy_limit", 20)
            if buy > buy_limit:
                logs.append(_shortlog(f"{player_name} attempted to buy {buy} troops but limit is {buy_limit}"))
                players[turn_idx] = cur
                advance()
                return False
            cost = buy * TROOP_COST
            if int(cur.get("money", 0) or 0) < cost:
                logs.append(_shortlog(f"{player_name} can't afford {buy} troops (${cost})"))
                players[turn_idx] = cur
                advance()
                return False
            cur["money"] = int(cur.get("money", 0)) - cost
            owned = [k for k, v in countries.items() if v.get("owner") == player_name]
            if owned:
                i = 0
                remaining = buy
                while remaining > 0:
                    cid = str(owned[i % len(owned)])
                    c = countries.get(cid) or {}
                    c["troops"] = int(c.get("troops", 0) or 0) + 1
                    countries[cid] = c
                    i += 1; remaining -= 1
            logs.append(_shortlog(f"{player_name} bought {int(action_params.get('buy', 0))} troops for ${cost}"))
            players[turn_idx] = cur
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
                logs.append(_shortlog(f"{player_name} invalid expand."))
                players[turn_idx] = cur; advance(); return False
            if s.get("owner") != player_name:
                logs.append(_shortlog(f"{player_name} doesn't own source territory."))
                players[turn_idx] = cur; advance(); return False
            s_troops = int(s.get("troops", 0) or 0)
            if send <= 0 or send >= s_troops:
                logs.append(_shortlog(f"{player_name} invalid troop count."))
                players[turn_idx] = cur; advance(); return False
            total_needed = cross_cost + CLAIM_COST
            if int(cur.get("money", 0) or 0) < total_needed:
                logs.append(_shortlog(f"{player_name} can't afford expansion (${total_needed})."))
                players[turn_idx] = cur; advance(); return False

            cur["money"] = int(cur.get("money", 0)) - cross_cost - CLAIM_COST
            s["troops"] = s_troops - send
            countries[src] = s

            defender_name = t.get("owner")
            defender_idx = None
            for i, p in enumerate(players):
                if p.get("name") == defender_name:
                    defender_idx = i; break

            if not t.get("owner"):
                t["owner"] = player_name; t["troops"] = send
                countries[tgt] = t
                logs.append(_shortlog(f"{player_name} claimed a territory (continent:{t.get('continent', '')}) with {send} troops."))
                award_continent_bonus(cur, tgt)
                players[turn_idx] = cur; advance(); return True

            # Check if defender is vulnerable (auto-win)
            if defender_idx is not None and players[defender_idx].get("vulnerable"):
                t["owner"] = player_name; t["troops"] = send
                countries[tgt] = t
                logs.append(_shortlog(f"{player_name} swept vulnerable territory with {send} troops."))
                players[defender_idx]["was_attacked"] = True
                award_continent_bonus(cur, tgt)
                players[turn_idx] = cur; advance(); return True

            # Combat roll
            atk_roll = random.randint(1, 20)
            d1 = random.randint(1, 20); d2 = random.randint(1, 20); def_best = max(d1, d2)
            logs.append(_shortlog(f"{player_name} (atk {atk_roll}) attacked {defender_name} (def [{d1},{d2}]->{def_best})"))

            if atk_roll > def_best:
                t["owner"] = player_name; t["troops"] = send
                countries[tgt] = t
                logs.append(_shortlog(f"{player_name} won and captured the territory ({send} troops)."))
                if defender_idx is not None:
                    players[defender_idx]["was_attacked"] = True
                award_continent_bonus(cur, tgt)
                players[turn_idx] = cur; advance(); return True
            else:
                logs.append(_shortlog(f"{player_name} lost the attack; {send} troops destroyed."))
                if defender_idx is not None:
                    players[defender_idx]["was_attacked"] = True
                players[turn_idx] = cur; advance(); return False

        # Unknown action
        players[turn_idx] = cur; advance()
        return True
