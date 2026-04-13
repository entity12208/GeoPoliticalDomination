# firebase_sync.py
"""
Firebase backend for GPD online mode.
Uses the public Firebase config + anonymous authentication via REST API.
No service account or secrets file required.
"""

import os
import threading
import time
import json
import hashlib
import random
import logging

import requests

from constants import (
    CLAIM_COST, TROOP_COST, HEX_PALETTE, continent_value,
)

logger = logging.getLogger(__name__)

# ============================================================
# Public Firebase config (NOT a secret -- designed for anonymous auth)
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
# Firebase Auth (email/password via REST)
# ============================================================

_TOKEN_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".auth_token")

# Firebase Auth REST endpoints
_SIGN_UP_URL = f"https://identitytoolkit.googleapis.com/v1/accounts:signUp?key={FIREBASE_API_KEY}"
_SIGN_IN_URL = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={FIREBASE_API_KEY}"
_REFRESH_URL = f"https://securetoken.googleapis.com/v1/token?key={FIREBASE_API_KEY}"

# We use fake emails: "<username>@gpd.local" so Firebase Auth handles passwords.
_EMAIL_DOMAIN = "gpd.local"


def _username_to_email(username):
    """Convert a display username to the fake email used with Firebase Auth."""
    return f"{username.strip().lower()}@{_EMAIL_DOMAIN}"


class AuthError(Exception):
    """Raised for authentication failures with a user-friendly message."""
    pass


class _AuthManager:
    """Manages Firebase email/password auth tokens with auto-refresh."""

    def __init__(self):
        self.id_token = None
        self.refresh_token = None
        self.expires_at = 0
        self.uid = None
        self.username = None  # display name chosen at registration

    # ----------------------------------------------------------
    # Public API
    # ----------------------------------------------------------

    def register(self, username, password):
        """Create a new account. Raises AuthError on failure."""
        username = username.strip()
        if not username:
            raise AuthError("Username cannot be empty.")
        if len(username) < 3:
            raise AuthError("Username must be at least 3 characters.")
        if len(username) > 20:
            raise AuthError("Username must be 20 characters or fewer.")
        if not password or len(password) < 4:
            raise AuthError("Password must be at least 4 characters.")

        email = _username_to_email(username)
        try:
            resp = requests.post(
                _SIGN_UP_URL,
                json={"email": email, "password": password, "returnSecureToken": True},
                timeout=10,
            )
        except requests.RequestException as e:
            raise AuthError(f"Network error: {e}")

        if resp.status_code != 200:
            err = resp.json().get("error", {})
            msg = err.get("message", "")
            if "EMAIL_EXISTS" in msg:
                raise AuthError("That username is already taken.")
            elif "WEAK_PASSWORD" in msg:
                raise AuthError("Password is too weak (min 6 chars for Firebase).")
            else:
                raise AuthError(f"Registration failed: {msg or resp.status_code}")

        data = resp.json()
        self._apply_auth_response(data, username)
        logger.info("Registered new account: %s (uid=%s)", username, self.uid)

    def login(self, username, password):
        """Sign into an existing account. Raises AuthError on failure."""
        username = username.strip()
        if not username:
            raise AuthError("Username cannot be empty.")
        if not password:
            raise AuthError("Password cannot be empty.")

        email = _username_to_email(username)
        try:
            resp = requests.post(
                _SIGN_IN_URL,
                json={"email": email, "password": password, "returnSecureToken": True},
                timeout=10,
            )
        except requests.RequestException as e:
            raise AuthError(f"Network error: {e}")

        if resp.status_code != 200:
            err = resp.json().get("error", {})
            msg = err.get("message", "")
            if "EMAIL_NOT_FOUND" in msg:
                raise AuthError("Account not found. Check your username.")
            elif "INVALID_PASSWORD" in msg or "INVALID_LOGIN_CREDENTIALS" in msg:
                raise AuthError("Incorrect password.")
            elif "TOO_MANY_ATTEMPTS" in msg:
                raise AuthError("Too many failed attempts. Try again later.")
            else:
                raise AuthError(f"Login failed: {msg or resp.status_code}")

        data = resp.json()
        self._apply_auth_response(data, username)
        logger.info("Logged in as %s (uid=%s)", username, self.uid)

    def sign_in(self):
        """Auto-restore a previous session, or fall back to anonymous sign-in.

        Called internally when no explicit login/register has happened yet.
        """
        if self._restore_token():
            return
        # Fall back to anonymous so the app doesn't crash
        resp = requests.post(
            _SIGN_UP_URL,
            json={"returnSecureToken": True},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        self._apply_auth_response(data, username=None)
        logger.info("Anonymous fallback sign-in (uid=%s)", self.uid)

    def logout(self):
        """Clear the saved session so next launch shows the login screen."""
        self.id_token = None
        self.refresh_token = None
        self.expires_at = 0
        self.uid = None
        self.username = None
        try:
            if os.path.exists(_TOKEN_FILE):
                os.remove(_TOKEN_FILE)
        except OSError:
            pass
        logger.info("Logged out, session cleared.")

    @property
    def is_logged_in(self):
        return bool(self.id_token and self.uid)

    @property
    def display_name(self):
        return self.username or "Guest"

    # ----------------------------------------------------------
    # Token management
    # ----------------------------------------------------------

    def _apply_auth_response(self, data, username):
        self.id_token = data.get("idToken") or data.get("id_token")
        self.refresh_token = data.get("refreshToken") or data.get("refresh_token")
        self.uid = data.get("localId") or data.get("user_id") or ""
        self.expires_at = time.time() + int(data.get("expiresIn", 3600)) - 60
        if username:
            self.username = username
        self._save_token()

    def _save_token(self):
        """Persist refresh token + username so the session survives restarts."""
        try:
            with open(_TOKEN_FILE, "w") as f:
                json.dump({
                    "refresh_token": self.refresh_token,
                    "uid": self.uid,
                    "username": self.username,
                }, f)
        except OSError:
            pass

    def _restore_token(self):
        """Try to restore a previous session from saved refresh token."""
        try:
            if not os.path.exists(_TOKEN_FILE):
                return False
            with open(_TOKEN_FILE, "r") as f:
                data = json.load(f)
            saved_rt = data.get("refresh_token")
            if not saved_rt:
                return False
            self.refresh_token = saved_rt
            self.uid = data.get("uid", "")
            self.username = data.get("username")
            self._refresh()
            logger.info("Restored session for %s (uid=%s)", self.username or "anon", self.uid)
            return True
        except (OSError, ValueError, KeyError, requests.RequestException) as e:
            logger.info("Could not restore session (%s), need fresh login", e)
            return False

    def get_token(self):
        if not self.id_token or time.time() >= self.expires_at:
            if self.refresh_token:
                try:
                    self._refresh()
                except (requests.RequestException, KeyError, ValueError) as e:
                    logger.warning("Token refresh failed (%s), re-signing in", e)
                    self.refresh_token = None
                    self.sign_in()
            else:
                self.sign_in()
        return self.id_token

    def _refresh(self):
        resp = requests.post(
            _REFRESH_URL,
            json={"grant_type": "refresh_token", "refresh_token": self.refresh_token},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        new_token = data.get("id_token")
        new_refresh = data.get("refresh_token")
        if not new_token or not new_refresh:
            raise AuthError("Token refresh returned incomplete data")
        self.id_token = new_token
        self.refresh_token = new_refresh
        self.uid = data.get("user_id", self.uid or "")
        self.expires_at = time.time() + int(data.get("expires_in", 3600)) - 60
        self._save_token()

    def headers(self):
        return {"Authorization": f"Bearer {self.get_token()}"}


# ============================================================
# Firestore REST operations
# ============================================================

def _doc_url(game_id):
    return f"{FIRESTORE_BASE}/games/{game_id}"

def _player_doc_url(uid):
    return f"{FIRESTORE_BASE}/player_sessions/{uid}"

def _lobby_url(game_id):
    return f"{FIRESTORE_BASE}/game_lobby/{game_id}"

def _stats_url(uid):
    return f"{FIRESTORE_BASE}/player_stats/{uid}"

def _chat_url(game_id):
    return f"{FIRESTORE_BASE}/games/{game_id}/chat"


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


def _update_doc(auth, game_id, data, field_paths=None, url_override=None):
    """Update specific fields of a document."""
    url = url_override if url_override else _doc_url(game_id)
    body = {"fields": _dict_to_fields(data)}
    params = {}
    if field_paths:
        params["updateMask.fieldPaths"] = field_paths
    resp = requests.patch(url, headers=auth.headers(), json=body,
                          params=params, timeout=10)
    resp.raise_for_status()


def _create_doc(auth, url, data):
    """Create a document at the given URL."""
    body = {"fields": _dict_to_fields(data)}
    resp = requests.patch(url, headers=auth.headers(), json=body, timeout=10)
    resp.raise_for_status()
    return _doc_to_dict(resp.json())


def _get_doc_at_url(auth, url):
    """GET a document at the given URL. Returns (dict, exists)."""
    resp = requests.get(url, headers=auth.headers(), timeout=10)
    if resp.status_code == 404:
        return {}, False
    resp.raise_for_status()
    return _doc_to_dict(resp.json()), True


def _delete_doc_at_url(auth, url):
    """DELETE a document at the given URL."""
    resp = requests.delete(url, headers=auth.headers(), timeout=10)
    if resp.status_code != 404:
        resp.raise_for_status()


def _generate_join_code():
    """Generate a 6-character alphanumeric join code."""
    import string
    chars = string.ascii_uppercase + string.digits
    return ''.join(random.choice(chars) for _ in range(6))


# ============================================================
# FirebaseController
# ============================================================

class FirebaseController:
    def __init__(self, secrets_file=None, auth_manager=None):
        """Initialize with an existing auth manager or create one.

        If *auth_manager* is provided (and already logged in), it is reused
        so the controller shares the same session/UID.  Otherwise a new
        _AuthManager is created and signed in (anonymous fallback).
        """
        if auth_manager and auth_manager.is_logged_in:
            self._auth = auth_manager
        else:
            self._auth = _AuthManager()
            self._auth.sign_in()
        self.game_ref = None
        self._poll_thread = None
        self._poll_game_id = None
        self._poll_running = False
        self.local_game = None
        self._lock = threading.Lock()
        self._on_update_cb = None
        # Register username→uid mapping for friend lookups
        self._register_username()

    def _choose_color(self, preferred=None):
        if preferred:
            if isinstance(preferred, (list, tuple)) and len(preferred) >= 3:
                try:
                    r, g, b = int(preferred[0]), int(preferred[1]), int(preferred[2])
                    return "#{:02X}{:02X}{:02X}".format(r, g, b)
                except (ValueError, TypeError, IndexError):
                    pass
            if isinstance(preferred, str) and preferred.startswith("#") and len(preferred) in (4, 7, 9):
                s = preferred.lstrip("#")
                if len(s) == 3:
                    s = "".join([c * 2 for c in s])
                return "#" + s[:6].upper()
        return random.choice(HEX_PALETTE)

    def create_or_open_game(self, game_id, player_name, player_password="", color=None, bot_count=0,
                            mode="classic", map_scope="world", is_private=False):
        data, exists = _get_doc(self._auth, game_id)

        if not exists:
            chosen_color = self._choose_color(color)
            player_pass_hash = hashlib.sha256((player_password or "").encode()).hexdigest()

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
                "game_mode": mode,
                "map_scope": map_scope,
                "is_private": is_private,
            }

            # Add join code if private
            if is_private:
                doc["join_code"] = _generate_join_code()

            _set_doc(self._auth, game_id, doc)

            # Publish to lobby if public
            if not is_private:
                self.publish_game(game_id, player_name, mode, map_scope,
                                max_players=6, is_private=False)

            logger.info("Created room: %s (mode=%s, map=%s, private=%s)",
                       game_id, mode, map_scope, is_private)
            return doc
        else:
            # For existing games, check join_code if is_private
            if data.get("is_private", False):
                # Private game logic handled via join_code
                pass

            existing = next((p for p in data.get("players", []) if p.get("name") == player_name), None)
            if existing:
                provided_hash = hashlib.sha256((player_password or "").encode()).hexdigest()
                stored_hash = existing.get("password_hash") or ""
                if provided_hash != stored_hash:
                    raise PermissionError("Incorrect player password")
                logger.info("Player %s rejoined room %s", player_name, game_id)
                return data

            players = list(data.get("players", []))
            player_pass_hash = hashlib.sha256((player_password or "").encode()).hexdigest()
            new_color = self._choose_color(color)
            players.append({
                "name": player_name, "is_bot": False, "color": new_color,
                "money": 500, "vulnerable": False, "was_attacked": False,
                "password_hash": player_pass_hash, "troop_buy_limit": 20,
            })
            _update_doc(self._auth, game_id, {"players": players}, ["players"])

            # Update player count in lobby if public
            if not data.get("is_private", False):
                self.update_lobby_player_count(game_id, len(players))

            data["players"] = players
            logger.info("Player %s joined room %s", player_name, game_id)
            return data

    def upload_initial_countries(self, game_id, countries_min):
        _update_doc(self._auth, game_id, {"countries": countries_min}, ["countries"])

    def listen_to_game(self, game_id, on_update):
        """Start polling the game document for changes."""
        self._poll_game_id = game_id
        self._on_update_cb = on_update

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
                    h = hash(json.dumps(data, sort_keys=True, default=str))
                    if h != last_hash:
                        last_hash = h
                        with self._lock:
                            self.local_game = data
                        if self._on_update_cb:
                            try:
                                self._on_update_cb(data)
                            except (TypeError, ValueError, KeyError) as e:
                                logger.warning("Poll callback error: %s", e)
            except requests.RequestException as e:
                logger.warning("Poll network error: %s", e)
            except (json.JSONDecodeError, ValueError) as e:
                logger.warning("Poll data error: %s", e)
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
        except requests.RequestException as e:
            logger.warning("append_log network error: %s", e)

    def save_joined_games(self, games_dict):
        """Save joined games list to Firestore under this user's UID.

        games_dict: {game_id: {"player_name": str, "player_password": str, "room_password": str}}
        Passwords are hashed before upload so raw credentials never leave the client.
        """
        uid = self._auth.uid
        if not uid:
            logger.warning("No UID available, cannot save joined games")
            return
        # Hash passwords before storing server-side
        safe_data = {}
        for gid, ginfo in games_dict.items():
            safe_data[gid] = {
                "player_name": ginfo.get("player_name", ""),
                "pp_hash": hashlib.sha256(
                    (ginfo.get("player_password", "") or "").encode()
                ).hexdigest(),
                "rp_hash": hashlib.sha256(
                    (ginfo.get("room_password", "") or "").encode()
                ).hexdigest(),
            }
        url = _player_doc_url(uid)
        body = {"fields": _dict_to_fields({"joined_games": safe_data})}
        try:
            # Use PATCH without updateMask to create-or-replace the whole doc
            resp = requests.patch(url, headers=self._auth.headers(), json=body, timeout=10)
            resp.raise_for_status()
            logger.info("Saved %d joined games to server (uid=%s)", len(safe_data), uid)
        except requests.RequestException as e:
            logger.warning("save_joined_games error: %s (status=%s, body=%s)",
                           e, getattr(e.response, 'status_code', '?'),
                           getattr(e.response, 'text', '')[:200] if hasattr(e, 'response') and e.response else '')

    def load_joined_games(self):
        """Load joined games list from Firestore for this user's UID.

        Returns {game_id: {"player_name": str}} (passwords are hashed on server,
        the client will need to re-enter them or use saved local credentials).
        """
        uid = self._auth.uid
        if not uid:
            return {}
        url = _player_doc_url(uid)
        try:
            resp = requests.get(url, headers=self._auth.headers(), timeout=10)
            if resp.status_code == 404:
                return {}
            resp.raise_for_status()
            doc = _doc_to_dict(resp.json())
            raw = doc.get("joined_games", {})
            result = {}
            for gid, ginfo in raw.items():
                if isinstance(ginfo, dict):
                    result[gid] = {
                        "player_name": ginfo.get("player_name", ""),
                    }
            logger.info("Loaded %d joined games from server (uid=%s)", len(result), uid)
            return result
        except (requests.RequestException, json.JSONDecodeError, ValueError) as e:
            logger.warning("load_joined_games error: %s", e)
            return {}

    def claim_starting_country(self, game_id, player_name, cid):
        cid_s = str(cid)
        data, exists = _get_doc(self._auth, game_id)
        if not exists:
            raise RuntimeError("Game not found")

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
            raise RuntimeError("Game not found")

        players = list(data.get("players", []))
        if not players:
            raise RuntimeError("No players in game")
        turn_idx = int(data.get("turn_idx", 0) or 0)
        if turn_idx < 0 or turn_idx >= len(players):
            raise IndexError("Invalid turn index")
        cur = players[turn_idx]
        if cur.get("name") != player_name:
            raise PermissionError("Not player's turn")

        countries = dict(data.get("countries", {}))
        logs = list(data.get("logs", []))[-50:]
        turn_number = int(data.get("turn_number", 1) or 1)

        def advance():
            next_idx = (turn_idx + 1) % len(players)
            nxt = players[next_idx]
            if nxt.get("vulnerable"):
                if not nxt.get("was_attacked"):
                    owned = sum(1 for v in countries.values() if v.get("owner") == nxt.get("name"))
                    payout = 100 * max(0, owned)
                    nxt["money"] = int(nxt.get("money", 0) or 0) + payout
                    logs.append(_shortlog(f"{nxt.get('name')} was peaceful and earned ${payout} (${100} x {owned} territories)."))
                else:
                    logs.append(_shortlog(f"{nxt.get('name')} was attacked while vulnerable -- no PEACE payout."))
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
                    i += 1
                    remaining -= 1
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
                players[turn_idx] = cur
                advance()
                return False
            if s.get("owner") != player_name:
                logs.append(_shortlog(f"{player_name} doesn't own source territory."))
                players[turn_idx] = cur
                advance()
                return False
            s_troops = int(s.get("troops", 0) or 0)
            if send <= 0 or send >= s_troops:
                logs.append(_shortlog(f"{player_name} invalid troop count."))
                players[turn_idx] = cur
                advance()
                return False
            total_needed = cross_cost + CLAIM_COST
            if int(cur.get("money", 0) or 0) < total_needed:
                logs.append(_shortlog(f"{player_name} can't afford expansion (${total_needed})."))
                players[turn_idx] = cur
                advance()
                return False

            cur["money"] = int(cur.get("money", 0)) - cross_cost - CLAIM_COST
            s["troops"] = s_troops - send
            countries[src] = s

            defender_name = t.get("owner")
            defender_idx = None
            for i, p in enumerate(players):
                if p.get("name") == defender_name:
                    defender_idx = i
                    break

            if not t.get("owner"):
                t["owner"] = player_name
                t["troops"] = send
                countries[tgt] = t
                logs.append(_shortlog(f"{player_name} claimed a territory (continent:{t.get('continent', '')}) with {send} troops."))
                award_continent_bonus(cur, tgt)
                players[turn_idx] = cur
                advance()
                return True

            if defender_idx is not None and players[defender_idx].get("vulnerable"):
                t["owner"] = player_name
                t["troops"] = send
                countries[tgt] = t
                logs.append(_shortlog(f"{player_name} swept vulnerable territory with {send} troops."))
                players[defender_idx]["was_attacked"] = True
                award_continent_bonus(cur, tgt)
                players[turn_idx] = cur
                advance()
                return True

            atk_roll = random.randint(1, 20)
            d1 = random.randint(1, 20)
            d2 = random.randint(1, 20)
            def_best = max(d1, d2)
            logs.append(_shortlog(f"{player_name} (atk {atk_roll}) attacked {defender_name} (def [{d1},{d2}]->{def_best})"))

            if atk_roll > def_best:
                t["owner"] = player_name
                t["troops"] = send
                countries[tgt] = t
                logs.append(_shortlog(f"{player_name} won and captured the territory ({send} troops)."))
                if defender_idx is not None:
                    players[defender_idx]["was_attacked"] = True
                award_continent_bonus(cur, tgt)
                players[turn_idx] = cur
                advance()
                return True
            else:
                logs.append(_shortlog(f"{player_name} lost the attack; {send} troops destroyed."))
                if defender_idx is not None:
                    players[defender_idx]["was_attacked"] = True
                players[turn_idx] = cur
                advance()
                return False

        # Unknown action
        players[turn_idx] = cur
        advance()
        return True

    # ============================================================
    # 1. Game lobby/browser system
    # ============================================================

    def list_public_games(self):
        """GET all docs from game_lobby collection. Return list of waiting games."""
        try:
            # Query game_lobby collection
            url = f"{FIRESTORE_BASE}/game_lobby"
            resp = requests.get(url, headers=self._auth.headers(), timeout=10)
            if resp.status_code == 404:
                return []
            resp.raise_for_status()
            data = resp.json()

            documents = data.get("documents", [])
            games = []
            for doc in documents:
                game_data = _doc_to_dict(doc)
                # Only return games with status "waiting"
                if game_data.get("status") == "waiting":
                    # Extract game_id from document name
                    game_id = doc.get("name", "").split("/")[-1]
                    games.append({
                        "id": game_id,
                        "host": game_data.get("host_name", ""),
                        "players": game_data.get("player_count", 0),
                        "max_players": game_data.get("max_players", 6),
                        "mode": game_data.get("mode", "classic"),
                        "map": game_data.get("map_scope", "world"),
                        "status": game_data.get("status", "waiting"),
                    })
            return games
        except requests.RequestException as e:
            logger.warning("list_public_games error: %s", e)
            return []

    def publish_game(self, game_id, host_name, mode, map_scope, max_players=6, is_private=False):
        """Create a doc in game_lobby/{game_id} if not private."""
        if is_private:
            return

        try:
            data = {
                "game_id": game_id,
                "host_name": host_name,
                "player_count": 1,
                "max_players": max_players,
                "mode": mode,
                "map_scope": map_scope,
                "status": "waiting",
                "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
            url = _lobby_url(game_id)
            _create_doc(self._auth, url, data)
            logger.info("Published game to lobby: %s", game_id)
        except requests.RequestException as e:
            logger.warning("publish_game error: %s", e)

    def update_lobby_player_count(self, game_id, count):
        """PATCH the player_count field in game_lobby/{game_id}."""
        try:
            url = _lobby_url(game_id)
            _update_doc(self._auth, game_id, {"player_count": count}, ["player_count"],
                       url_override=url)
            logger.info("Updated lobby player count for %s: %d", game_id, count)
        except requests.RequestException as e:
            logger.warning("update_lobby_player_count error: %s", e)

    def remove_from_lobby(self, game_id):
        """DELETE the game_lobby/{game_id} document."""
        try:
            url = _lobby_url(game_id)
            _delete_doc_at_url(self._auth, url)
            logger.info("Removed game from lobby: %s", game_id)
        except requests.RequestException as e:
            logger.warning("remove_from_lobby error: %s", e)

    # ============================================================
    # 2. Chat system
    # ============================================================

    def send_chat(self, game_id, username, message):
        """POST a new doc to games/{game_id}/chat subcollection."""
        try:
            data = {
                "sender": username,
                "message": message,
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
            url = _chat_url(game_id)
            # Create a new document in the subcollection (auto-generated ID)
            resp = requests.post(
                url,
                headers=self._auth.headers(),
                json={"fields": _dict_to_fields(data)},
                timeout=10
            )
            resp.raise_for_status()
            logger.info("Sent chat message in game %s by %s", game_id, username)
        except requests.RequestException as e:
            logger.warning("send_chat error: %s", e)

    def get_chat(self, game_id, limit=50):
        """GET the last N chat messages from the subcollection."""
        try:
            url = _chat_url(game_id)
            resp = requests.get(url, headers=self._auth.headers(), timeout=10)
            if resp.status_code == 404:
                return []
            resp.raise_for_status()
            data = resp.json()

            messages = []
            documents = data.get("documents", [])
            # Sort by timestamp descending and limit
            for doc in sorted(documents,
                            key=lambda d: _doc_to_dict(d).get("timestamp", ""),
                            reverse=True)[:limit]:
                msg_data = _doc_to_dict(doc)
                messages.append({
                    "sender": msg_data.get("sender", ""),
                    "message": msg_data.get("message", ""),
                    "timestamp": msg_data.get("timestamp", ""),
                })
            return list(reversed(messages))  # Return in chronological order
        except requests.RequestException as e:
            logger.warning("get_chat error: %s", e)
            return []

    # ============================================================
    # 3. Player stats
    # ============================================================

    def update_player_stats(self, mode, won, territories_conquered, turns_played):
        """Read and increment player stats for the given mode."""
        try:
            uid = self._auth.uid
            if not uid:
                logger.warning("No UID available, cannot update stats")
                return

            url = _stats_url(uid)
            doc_data, exists = _get_doc_at_url(self._auth, url)

            # Initialize stats structure if doesn't exist
            if not exists:
                doc_data = {}

            if mode not in doc_data:
                doc_data[mode] = {
                    "games_played": 0,
                    "wins": 0,
                    "losses": 0,
                    "territories_conquered": 0,
                    "turns_played": 0,
                }

            # Increment counters
            doc_data[mode]["games_played"] = int(doc_data[mode].get("games_played", 0)) + 1
            if won:
                doc_data[mode]["wins"] = int(doc_data[mode].get("wins", 0)) + 1
            else:
                doc_data[mode]["losses"] = int(doc_data[mode].get("losses", 0)) + 1
            doc_data[mode]["territories_conquered"] = int(doc_data[mode].get("territories_conquered", 0)) + territories_conquered
            doc_data[mode]["turns_played"] = int(doc_data[mode].get("turns_played", 0)) + turns_played

            # Write back
            _create_doc(self._auth, url, doc_data)
            logger.info("Updated player stats for mode %s (uid=%s)", mode, uid)
        except requests.RequestException as e:
            logger.warning("update_player_stats error: %s", e)

    def get_player_stats(self, uid=None):
        """GET player_stats/{uid} (defaults to self._auth.uid)."""
        try:
            if uid is None:
                uid = self._auth.uid
            if not uid:
                logger.warning("No UID available, cannot get stats")
                return {}

            url = _stats_url(uid)
            doc_data, exists = _get_doc_at_url(self._auth, url)
            if exists:
                logger.info("Retrieved player stats for uid=%s", uid)
                return doc_data
            return {}
        except requests.RequestException as e:
            logger.warning("get_player_stats error: %s", e)
            return {}

    # ============================================================
    # 4. Spectator tracking
    # ============================================================

    def join_as_spectator(self, game_id, username):
        """Add username to spectators list in game doc."""
        try:
            data, exists = _get_doc(self._auth, game_id)
            if not exists:
                logger.warning("Game not found: %s", game_id)
                return False

            spectators = list(data.get("spectators", []))
            if username not in spectators:
                spectators.append(username)
                _update_doc(self._auth, game_id, {"spectators": spectators}, ["spectators"])
                logger.info("Added spectator %s to game %s", username, game_id)
            return True
        except requests.RequestException as e:
            logger.warning("join_as_spectator error: %s", e)
            return False

    def leave_as_spectator(self, game_id, username):
        """Remove username from spectators list."""
        try:
            data, exists = _get_doc(self._auth, game_id)
            if not exists:
                logger.warning("Game not found: %s", game_id)
                return False

            spectators = list(data.get("spectators", []))
            if username in spectators:
                spectators.remove(username)
                _update_doc(self._auth, game_id, {"spectators": spectators}, ["spectators"])
                logger.info("Removed spectator %s from game %s", username, game_id)
            return True
        except requests.RequestException as e:
            logger.warning("leave_as_spectator error: %s", e)
            return False

    def get_spectator_count(self, game_id):
        """Read game doc and return len(spectators list)."""
        try:
            data, exists = _get_doc(self._auth, game_id)
            if not exists:
                logger.warning("Game not found: %s", game_id)
                return 0
            spectators = data.get("spectators", [])
            return len(spectators)
        except requests.RequestException as e:
            logger.warning("get_spectator_count error: %s", e)
            return 0

    # ============================================================
    # 5. Turn validation and action submission
    # ============================================================

    def validate_and_submit_action(self, game_id, player_name, action_type, action_params):
        """Validate turn and action, then apply if valid.

        Returns (success: bool, error_message: str)
        """
        data, exists = _get_doc(self._auth, game_id)
        if not exists:
            return False, "Game not found"

        players = list(data.get("players", []))
        if not players:
            return False, "No players in game"

        turn_idx = int(data.get("turn_idx", 0) or 0)
        if turn_idx < 0 or turn_idx >= len(players):
            return False, "Invalid turn index"

        cur = players[turn_idx]
        if cur.get("name") != player_name:
            return False, "Not player's turn"

        # Validate action-specific preconditions
        countries = dict(data.get("countries", {}))

        if action_type == "EXPAND":
            src = str(action_params.get("src", ""))
            tgt = str(action_params.get("tgt", ""))
            send = int(action_params.get("send", 0))
            cross_cost = int(action_params.get("cross_cost", 0))

            s = countries.get(src)
            t = countries.get(tgt)
            if not s or not t:
                return False, "Invalid territory"
            if s.get("owner") != player_name:
                return False, "Don't own source territory"

            s_troops = int(s.get("troops", 0) or 0)
            if send <= 0 or send >= s_troops:
                return False, "Invalid troop count"

            total_needed = cross_cost + CLAIM_COST
            if int(cur.get("money", 0) or 0) < total_needed:
                return False, f"Can't afford expansion (need ${total_needed})"

        elif action_type == "GATHER":
            buy = int(action_params.get("buy", 0))
            if buy < 0:
                return False, "Invalid troop count"
            buy_limit = cur.get("troop_buy_limit", 20)
            if buy > buy_limit:
                return False, f"Troop limit is {buy_limit}"

            cost = buy * TROOP_COST
            if int(cur.get("money", 0) or 0) < cost:
                return False, f"Can't afford {buy} troops (${cost})"

        # If validation passed, submit the action using existing logic
        try:
            result = self.submit_action(game_id, player_name, action_type, action_params)
            if result:
                return True, ""
            else:
                return False, "Action submission failed"
        except Exception as e:
            return False, str(e)

    # ============================================================
    # 6. Global Leaderboard (Elo rating)
    # ============================================================

    def get_leaderboard(self, limit=50):
        """Fetch top players from the leaderboard collection.
        Returns list of dicts: [{username, elo, wins, losses, games_played}, ...]
        """
        try:
            # Query leaderboard collection ordered by elo (desc) -- we fetch all and sort client-side
            url = f"{FIRESTORE_BASE}/leaderboard"
            resp = requests.get(url, headers=self._auth.headers(), timeout=10)
            if resp.status_code == 404:
                return []
            resp.raise_for_status()
            data = resp.json()
            documents = data.get("documents", [])
            entries = []
            for doc in documents:
                d = _doc_to_dict(doc)
                entries.append({
                    "username": d.get("username", "?"),
                    "elo": int(d.get("elo", 1000)),
                    "wins": int(d.get("wins", 0)),
                    "losses": int(d.get("losses", 0)),
                    "games_played": int(d.get("games_played", 0)),
                })
            entries.sort(key=lambda x: x["elo"], reverse=True)
            return entries[:limit]
        except requests.RequestException as e:
            logger.warning("get_leaderboard error: %s", e)
            return []

    def update_elo(self, won, opponent_elo=1000):
        """Update this player's Elo rating after a game.
        K-factor 32 for simplicity.
        """
        uid = self._auth.uid
        username = self._auth.username
        if not uid or not username:
            return
        try:
            url = f"{FIRESTORE_BASE}/leaderboard/{uid}"
            resp = requests.get(url, headers=self._auth.headers(), timeout=10)
            if resp.status_code == 404:
                current = {"username": username, "elo": 1000, "wins": 0, "losses": 0, "games_played": 0}
            else:
                resp.raise_for_status()
                current = _doc_to_dict(resp.json())

            my_elo = int(current.get("elo", 1000))
            expected = 1.0 / (1.0 + 10 ** ((opponent_elo - my_elo) / 400.0))
            score = 1.0 if won else 0.0
            new_elo = max(100, int(my_elo + 32 * (score - expected)))

            updated = {
                "username": username,
                "elo": new_elo,
                "wins": int(current.get("wins", 0)) + (1 if won else 0),
                "losses": int(current.get("losses", 0)) + (0 if won else 1),
                "games_played": int(current.get("games_played", 0)) + 1,
            }
            body = {"fields": _dict_to_fields(updated)}
            requests.patch(url, headers=self._auth.headers(), json=body, timeout=10).raise_for_status()
            logger.info("Updated Elo for %s: %d -> %d", username, my_elo, new_elo)
            return new_elo
        except requests.RequestException as e:
            logger.warning("update_elo error: %s", e)
            return None

    def get_my_elo(self):
        """Get current player's Elo rating."""
        uid = self._auth.uid
        if not uid:
            return 1000
        try:
            url = f"{FIRESTORE_BASE}/leaderboard/{uid}"
            resp = requests.get(url, headers=self._auth.headers(), timeout=10)
            if resp.status_code == 404:
                return 1000
            resp.raise_for_status()
            d = _doc_to_dict(resp.json())
            return int(d.get("elo", 1000))
        except requests.RequestException as e:
            logger.warning("get_my_elo error: %s", e)
            return 1000

    # ============================================================
    # 7. Friend list
    # ============================================================

    def get_friends(self):
        """Get this player's friend list from Firestore.
        Returns list of dicts: [{username, uid, status}, ...]
        status: 'accepted', 'pending_sent', 'pending_received'
        """
        uid = self._auth.uid
        if not uid:
            return []
        try:
            url = f"{FIRESTORE_BASE}/friends/{uid}"
            resp = requests.get(url, headers=self._auth.headers(), timeout=10)
            if resp.status_code == 404:
                return []
            resp.raise_for_status()
            d = _doc_to_dict(resp.json())
            friends_map = d.get("friends", {})
            result = []
            for friend_uid, info in friends_map.items():
                if isinstance(info, dict):
                    result.append({
                        "uid": friend_uid,
                        "username": info.get("username", "?"),
                        "status": info.get("status", "accepted"),
                    })
            return result
        except requests.RequestException as e:
            logger.warning("get_friends error: %s", e)
            return []

    def _find_uid_by_username(self, username):
        """Look up a user's UID by their username.
        Checks 'usernames' collection first (fast), falls back to leaderboard scan.
        """
        target = username.strip().lower()
        try:
            # Fast path: check usernames/{lowercase_name} document
            url = f"{FIRESTORE_BASE}/usernames/{target}"
            resp = requests.get(url, headers=self._auth.headers(), timeout=10)
            if resp.status_code == 200:
                d = _doc_to_dict(resp.json())
                uid = d.get("uid")
                if uid:
                    return uid
        except requests.RequestException:
            pass
        # Fallback: scan leaderboard
        try:
            url = f"{FIRESTORE_BASE}/leaderboard"
            resp = requests.get(url, headers=self._auth.headers(), timeout=10)
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            for doc in resp.json().get("documents", []):
                d = _doc_to_dict(doc)
                if d.get("username", "").lower() == target:
                    return doc.get("name", "").split("/")[-1]
            return None
        except requests.RequestException:
            return None

    def _register_username(self):
        """Register this user's username→uid mapping for friend lookups."""
        uid = self._auth.uid
        username = self._auth.username
        if not uid or not username:
            return
        try:
            url = f"{FIRESTORE_BASE}/usernames/{username.strip().lower()}"
            body = {"fields": _dict_to_fields({"uid": uid, "username": username})}
            requests.patch(url, headers=self._auth.headers(), json=body, timeout=10)
        except requests.RequestException:
            pass

    def send_friend_request(self, target_username):
        """Send a friend request to another player by username.
        Returns (success, message).
        """
        uid = self._auth.uid
        username = self._auth.username
        if not uid or not username:
            return False, "Not logged in"

        target_uid = self._find_uid_by_username(target_username)
        if not target_uid:
            return False, f"Player '{target_username}' not found"
        if target_uid == uid:
            return False, "Cannot add yourself"

        try:
            # Update my friends list
            my_url = f"{FIRESTORE_BASE}/friends/{uid}"
            resp = requests.get(my_url, headers=self._auth.headers(), timeout=10)
            my_friends = {}
            if resp.status_code != 404:
                resp.raise_for_status()
                my_friends = _doc_to_dict(resp.json()).get("friends", {})

            if target_uid in my_friends:
                status = my_friends[target_uid].get("status", "") if isinstance(my_friends[target_uid], dict) else ""
                if status == "accepted":
                    return False, f"Already friends with {target_username}"
                elif status == "pending_sent":
                    return False, "Friend request already sent"

            my_friends[target_uid] = {"username": target_username, "status": "pending_sent"}
            body = {"fields": _dict_to_fields({"friends": my_friends})}
            requests.patch(my_url, headers=self._auth.headers(), json=body, timeout=10).raise_for_status()

            # Update target's friends list
            target_url = f"{FIRESTORE_BASE}/friends/{target_uid}"
            resp = requests.get(target_url, headers=self._auth.headers(), timeout=10)
            target_friends = {}
            if resp.status_code != 404:
                resp.raise_for_status()
                target_friends = _doc_to_dict(resp.json()).get("friends", {})

            target_friends[uid] = {"username": username, "status": "pending_received"}
            body = {"fields": _dict_to_fields({"friends": target_friends})}
            requests.patch(target_url, headers=self._auth.headers(), json=body, timeout=10).raise_for_status()

            logger.info("Sent friend request from %s to %s", username, target_username)
            return True, f"Friend request sent to {target_username}"
        except requests.RequestException as e:
            logger.warning("send_friend_request error: %s", e)
            return False, f"Error: {e}"

    def accept_friend_request(self, friend_uid):
        """Accept a pending friend request."""
        uid = self._auth.uid
        username = self._auth.username
        if not uid:
            return False, "Not logged in"
        try:
            # Update my entry
            my_url = f"{FIRESTORE_BASE}/friends/{uid}"
            resp = requests.get(my_url, headers=self._auth.headers(), timeout=10)
            if resp.status_code == 404:
                return False, "No friends data"
            resp.raise_for_status()
            my_friends = _doc_to_dict(resp.json()).get("friends", {})
            if friend_uid not in my_friends:
                return False, "No pending request from this user"
            my_friends[friend_uid]["status"] = "accepted"
            body = {"fields": _dict_to_fields({"friends": my_friends})}
            requests.patch(my_url, headers=self._auth.headers(), json=body, timeout=10).raise_for_status()

            # Update friend's entry
            friend_url = f"{FIRESTORE_BASE}/friends/{friend_uid}"
            resp = requests.get(friend_url, headers=self._auth.headers(), timeout=10)
            if resp.status_code != 404:
                resp.raise_for_status()
                friend_friends = _doc_to_dict(resp.json()).get("friends", {})
                if uid in friend_friends:
                    friend_friends[uid]["status"] = "accepted"
                    body = {"fields": _dict_to_fields({"friends": friend_friends})}
                    requests.patch(friend_url, headers=self._auth.headers(), json=body, timeout=10).raise_for_status()

            friend_name = my_friends[friend_uid].get("username", "?") if isinstance(my_friends[friend_uid], dict) else "?"
            logger.info("Accepted friend request from %s", friend_name)
            return True, f"Now friends with {friend_name}"
        except requests.RequestException as e:
            logger.warning("accept_friend_request error: %s", e)
            return False, f"Error: {e}"

    def remove_friend(self, friend_uid):
        """Remove a friend or decline a request."""
        uid = self._auth.uid
        if not uid:
            return False, "Not logged in"
        try:
            my_url = f"{FIRESTORE_BASE}/friends/{uid}"
            resp = requests.get(my_url, headers=self._auth.headers(), timeout=10)
            if resp.status_code != 404:
                resp.raise_for_status()
                my_friends = _doc_to_dict(resp.json()).get("friends", {})
                my_friends.pop(friend_uid, None)
                body = {"fields": _dict_to_fields({"friends": my_friends})}
                requests.patch(my_url, headers=self._auth.headers(), json=body, timeout=10).raise_for_status()

            friend_url = f"{FIRESTORE_BASE}/friends/{friend_uid}"
            resp = requests.get(friend_url, headers=self._auth.headers(), timeout=10)
            if resp.status_code != 404:
                resp.raise_for_status()
                friend_friends = _doc_to_dict(resp.json()).get("friends", {})
                friend_friends.pop(uid, None)
                body = {"fields": _dict_to_fields({"friends": friend_friends})}
                requests.patch(friend_url, headers=self._auth.headers(), json=body, timeout=10).raise_for_status()

            return True, "Removed"
        except requests.RequestException as e:
            logger.warning("remove_friend error: %s", e)
            return False, f"Error: {e}"

    def invite_friend_to_game(self, friend_uid, game_id):
        """Send a game invite notification to a friend.
        Stores in notifications/{friend_uid} collection.
        """
        uid = self._auth.uid
        username = self._auth.username
        if not uid or not username:
            return False
        try:
            import time as _time
            notif_id = f"invite_{uid}_{int(_time.time())}"
            url = f"{FIRESTORE_BASE}/notifications/{friend_uid}/items/{notif_id}"
            body = {"fields": _dict_to_fields({
                "type": "game_invite",
                "from_uid": uid,
                "from_username": username,
                "game_id": game_id,
                "timestamp": int(_time.time()),
                "read": False,
            })}
            requests.patch(url, headers=self._auth.headers(), json=body, timeout=10).raise_for_status()
            return True
        except requests.RequestException as e:
            logger.warning("invite_friend_to_game error: %s", e)
            return False

    # ============================================================
    # 8. Notifications
    # ============================================================

    def get_notifications(self, limit=20):
        """Get pending notifications for this player.
        Returns list of dicts: [{id, type, from_username, game_id, timestamp, read}, ...]
        """
        uid = self._auth.uid
        if not uid:
            return []
        try:
            url = f"{FIRESTORE_BASE}/notifications/{uid}/items"
            resp = requests.get(url, headers=self._auth.headers(), timeout=10)
            if resp.status_code == 404:
                return []
            resp.raise_for_status()
            data = resp.json()
            documents = data.get("documents", [])
            result = []
            for doc in documents:
                d = _doc_to_dict(doc)
                notif_id = doc.get("name", "").split("/")[-1]
                result.append({
                    "id": notif_id,
                    "type": d.get("type", ""),
                    "from_username": d.get("from_username", ""),
                    "game_id": d.get("game_id", ""),
                    "message": d.get("message", ""),
                    "timestamp": int(d.get("timestamp") or 0) if str(d.get("timestamp", "0")).isdigit() else 0,
                    "read": d.get("read", False),
                })
            result.sort(key=lambda x: x["timestamp"], reverse=True)
            return result[:limit]
        except requests.RequestException as e:
            logger.warning("get_notifications error: %s", e)
            return []

    def mark_notification_read(self, notif_id):
        """Mark a notification as read."""
        uid = self._auth.uid
        if not uid:
            return
        try:
            url = f"{FIRESTORE_BASE}/notifications/{uid}/items/{notif_id}"
            body = {"fields": _dict_to_fields({"read": True})}
            requests.patch(url, headers=self._auth.headers(), json=body,
                          params={"updateMask.fieldPaths": "read"}, timeout=10)
        except requests.RequestException:
            pass

    def send_turn_notification(self, game_id, target_username, target_uid):
        """Notify a player that it's their turn."""
        uid = self._auth.uid
        username = self._auth.username
        if not uid:
            return
        try:
            import time as _time
            notif_id = f"turn_{game_id}_{int(_time.time())}"
            url = f"{FIRESTORE_BASE}/notifications/{target_uid}/items/{notif_id}"
            body = {"fields": _dict_to_fields({
                "type": "your_turn",
                "from_username": username or "Game",
                "game_id": game_id,
                "message": f"It's your turn in game {game_id}!",
                "timestamp": int(_time.time()),
                "read": False,
            })}
            requests.patch(url, headers=self._auth.headers(), json=body, timeout=10)
        except requests.RequestException:
            pass

    def send_game_notification(self, game_id, target_uid, message, notif_type="game_event"):
        """Send a generic game notification."""
        uid = self._auth.uid
        username = self._auth.username
        if not uid or not target_uid:
            return
        try:
            import time as _time
            notif_id = f"{notif_type}_{game_id}_{int(_time.time())}"
            url = f"{FIRESTORE_BASE}/notifications/{target_uid}/items/{notif_id}"
            body = {"fields": _dict_to_fields({
                "type": notif_type,
                "from_username": username or "Game",
                "game_id": game_id,
                "message": message,
                "timestamp": int(_time.time()),
                "read": False,
            })}
            requests.patch(url, headers=self._auth.headers(), json=body, timeout=10)
        except requests.RequestException:
            pass

    # ============================================================
    # 9. Join by code
    # ============================================================

    def join_by_code(self, join_code, player_name, player_password="", color=None):
        """Search game_lobby for a game with matching join_code, then join it.

        Returns (game_id, game_data) on success, (None, None) on failure.
        """
        try:
            # Find game with matching join_code by querying the games collection
            # Since we can't easily query by field in REST API, we search all games
            url = f"{FIRESTORE_BASE}/games"
            resp = requests.get(url, headers=self._auth.headers(), timeout=10)
            if resp.status_code == 404:
                logger.warning("No games found")
                return None, None
            resp.raise_for_status()

            data = resp.json()
            documents = data.get("documents", [])

            for doc in documents:
                game_data = _doc_to_dict(doc)
                if game_data.get("join_code") == join_code:
                    game_id = doc.get("name", "").split("/")[-1]
                    # Join the game
                    result = self.create_or_open_game(
                        game_id, player_name,
                        player_password=player_password,
                        color=color
                    )
                    logger.info("Joined game %s by code", game_id)
                    return game_id, result

            logger.warning("No game found with code: %s", join_code)
            return None, None
        except requests.RequestException as e:
            logger.warning("join_by_code error: %s", e)
            return None, None
