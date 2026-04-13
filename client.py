# client.py
"""
GeoPolitical Domination -- Unified Client (Local + Online)

States:
  login          -- Username/password auth screen
  main_menu      -- Hub: Play, My Games, Stats, Rules, Settings, Leaderboard, Friends, Notifications
  play           -- Sub-menu: Offline Play, Online Game, Spectate Bots
  local_setup    -- Player name + bot count slider -> Start
  spectate_setup -- Bot count slider -> Watch
  online_setup   -- Game ID, player name, player password, room password -> Create & Host / Join Room
  game_browser   -- Browse/join public online games
  online_create  -- Create a new online game (mode + map + public/private)
  game_lobby     -- Lobby showing players, host controls, game ID/password
  choose_start   -- Type starting country name
  playing        -- The actual game
  joined_games   -- My active online games
  settings       -- Graphics/Audio/Controls tabs
  stats          -- Per-mode player statistics
  rules          -- Scrollable rules viewer with tabs
  leaderboard    -- Global Elo leaderboard
  friends        -- Friend list with add/accept/invite
  notifications  -- Turn/game/invite notifications

A `mode` variable ("local", "spectate", or "online") is set when entering setup.
"""

import os
import sys
import math
import random
import subprocess
import threading
import time
import logging

import pygame
from pygame import gfxdraw

# ============================================================
# Logging setup
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ============================================================
# Import new modules
# ============================================================

from constants import (
    BASE_DIR, ASSET_DIR, GEOJSON_CACHE,
    WIDTH, HEIGHT, MAP_H, RENDER_FPS as DEFAULT_RENDER_FPS, TPS, U,
    CLAIM_COST, TROOP_COST,
    MAX_MERCATOR_LAT,
    HEX_PALETTE, COLOR_PALETTE, PALETTE,
    SEA_COLOR, SEA_COLOR_LIGHT, COUNTRY_BORDER_COLOR, OWNED_BORDER_COLOR,
    DEFAULT_COUNTRY_FILL,
    HUD_BG, HUD_BG_ACCENT, HUD_BORDER, TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED,
    ACCENT_GOLD, ACCENT_GREEN, ACCENT_RED, ACCENT_BLUE, ACCENT_CYAN,
    LOBBY_BG, LOBBY_CARD_BG, LOBBY_CARD_BORDER,
    SPECTATOR_DARKEN, HOST_STAR_COLOR, TURN_DOT_COLOR, KICK_BTN_COLOR,
    ARMY_PIN_RADIUS, PIN_SCALE, TROOP_BONUS_MAX,
    MIN_CAMERA_SCALE, MAX_CAMERA_SCALE, CAMERA_ZOOM_FACTOR,
    FONT_FAMILY, FONT_SIZE_NORMAL, FONT_SIZE_BIG, FONT_SIZE_TITLE, FONT_SIZE_PIN,
    FLASH_MESSAGE_DEFAULT_SECS, FLASH_FADE_IN_SECS, FLASH_FADE_OUT_SECS,
    TURN_FLASH_DURATION, VFX_CAPTURE_DURATION, VFX_FLOAT_TEXT_DURATION,
    DIALOG_OPEN_SPEED, DIALOG_CLOSE_SPEED, TRANSITION_FADE_SPEED,
    GAME_MODES, MAP_SCOPES, DEFAULT_GAME_MODE, DEFAULT_MAP_SCOPE,
    SETTINGS_TABS, CAMERA_INERTIA_DECAY, CAMERA_WASD_SPEED,
    CAMERA_EDGE_SCROLL_MARGIN, CAMERA_EDGE_SCROLL_SPEED,
    DEFAULT_MUSIC_VOLUME, DEFAULT_SFX_VOLUME,
    continent_value, load_config, save_config, load_version, RESOLUTION_PRESETS,
)

from geometry import (
    load_countries_from_geojson, build_adjacency,
    polygon_bbox, point_in_poly, polygon_centroid, polygon_area,
)

from models import Player

from game_logic import (
    Game, claim_country, attack_country,
    resolve_peace_if_needed, end_turn_housekeeping,
    check_and_pay_continent_bonus,
)

from ui_components import (
    lighten, darken, cached_render, draw_shadow_rect, draw_rounded_rect,
    Button, Slider, hex_to_rgb, get_player_color_rgb,
)

# --- optional imports (guarded) ---

try:
    from firebase_sync import FirebaseController, _AuthManager, AuthError
    FIREBASE_AVAILABLE = True
except ImportError as _fb_err:
    FirebaseController = None
    _AuthManager = None
    AuthError = Exception
    FIREBASE_AVAILABLE = False
    logger.warning("Firebase not available (online mode disabled): %s", _fb_err)
except Exception as _fb_err:
    FirebaseController = None
    _AuthManager = None
    AuthError = Exception
    FIREBASE_AVAILABLE = False
    logger.warning("Firebase init error (online mode disabled): %s", _fb_err)

try:
    import updater
    UPDATER_AVAILABLE = True
except ImportError as _upd_err:
    updater = None
    UPDATER_AVAILABLE = False
    logger.info("Updater not available: %s", _upd_err)

try:
    import heuristic_bot
except ImportError as _bot_err:
    heuristic_bot = None
    logger.warning("heuristic_bot not available: %s", _bot_err)

try:
    from audio_manager import AudioManager
    AUDIO_AVAILABLE = True
except ImportError:
    AudioManager = None
    AUDIO_AVAILABLE = False

from rules_content import RULES_TEXT


# ============================================================
# Helpers unique to client
# ============================================================

def ensure_assets():
    os.makedirs(ASSET_DIR, exist_ok=True)

def find_country_by_name(countries, name):
    if not name: return None
    name = name.strip().casefold()
    for cid, c in countries.items():
        if (c.get("name", "") or "").strip().casefold() == name: return c
    return None

def obf_claim_msg(player, continent, troops):
    return f"{player} claimed a country in {continent} with {troops} troops."

# ============================================================
# ONLINE mode: RemoteGameView
# ============================================================

class RemoteGameView:
    def __init__(self):
        self.players = []; self.countries = {}; self.turn_idx = 0
        self.turn_number = 1; self.logs = []; self.status = "waiting"
        self._lock = threading.Lock()
    def update_from_doc(self, doc):
        with self._lock:
            self.players = doc.get("players", []) or []
            self.countries = doc.get("countries", {}) or {}
            self.turn_idx = int(doc.get("turn_idx", 0) or 0)
            self.turn_number = int(doc.get("turn_number", 1) or 1)
            self.logs = doc.get("logs", []) or []
            self.status = doc.get("status", "waiting")
    def snapshot(self):
        with self._lock:
            return {"players": list(self.players), "countries": dict(self.countries),
                    "turn_idx": self.turn_idx, "turn_number": self.turn_number,
                    "logs": list(self.logs), "status": self.status}

# ============================================================
# Bot adapter (local only)
# ============================================================

def decide_local_bot(game, player):
    if heuristic_bot is None: return None
    snapshot = {"players": [], "pins": []}
    for pl in game.players:
        snapshot["players"].append(pl.to_snapshot_dict())
    for cid, c in game.countries.items():
        snapshot["pins"].append({
            "id": c["id"], "name": c["name"], "owner": c.get("owner"),
            "troops": int(c.get("troops", 0)),
            "adj": [{"to": a["to"], "cost": a.get("cost", 0)} for a in c.get("adj", [])],
            "continent": c.get("continent", ""),
        })
    try: return heuristic_bot.decide(snapshot, player.name)
    except (KeyError, TypeError, ValueError, IndexError) as e:
        logger.error("heuristic_bot error: %s", e); return None

# ============================================================
# Web input keymap
# ============================================================

def _web_keymap(wi):
    key_name = wi.get("key", "")
    _map = {"Escape": pygame.K_ESCAPE, "F11": pygame.K_F11, "Enter": pygame.K_RETURN,
            "Backspace": pygame.K_BACKSPACE, "Tab": pygame.K_TAB, " ": pygame.K_SPACE,
            "1": pygame.K_1, "2": pygame.K_2, "3": pygame.K_3, "4": pygame.K_4,
            "=": pygame.K_EQUALS, "+": pygame.K_PLUS, "-": pygame.K_MINUS,
            "ArrowUp": pygame.K_UP, "ArrowDown": pygame.K_DOWN,
            "ArrowLeft": pygame.K_LEFT, "ArrowRight": pygame.K_RIGHT}
    if key_name in _map: return _map[key_name]
    if len(key_name) == 1: return ord(key_name.lower())
    return None

# ============================================================
# Drawing helpers for polished UI
# ============================================================

def draw_gradient_rect(surf, rect, color_top, color_bot, radius=0):
    x, y, w, h = rect
    if h <= 0 or w <= 0: return
    temp = pygame.Surface((w, h), pygame.SRCALPHA)
    for row in range(h):
        t = row / max(1, h - 1)
        r = int(color_top[0] + (color_bot[0] - color_top[0]) * t)
        g = int(color_top[1] + (color_bot[1] - color_top[1]) * t)
        b = int(color_top[2] + (color_bot[2] - color_top[2]) * t)
        a = color_top[3] if len(color_top) > 3 else 255
        pygame.draw.line(temp, (r, g, b, a), (0, row), (w, row))
    if radius > 0:
        mask = pygame.Surface((w, h), pygame.SRCALPHA)
        pygame.draw.rect(mask, (255, 255, 255, 255), (0, 0, w, h), border_radius=radius)
        temp.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
    surf.blit(temp, (x, y))

def draw_host_star(surf, x, y, size=10):
    color = HOST_STAR_COLOR
    pts = []
    for i in range(10):
        angle = math.radians(-90 + i * 36)
        r = size if i % 2 == 0 else size * 0.4
        pts.append((x + r * math.cos(angle), y + r * math.sin(angle)))
    pygame.draw.polygon(surf, color, pts)
    pygame.draw.polygon(surf, darken(color, 40), pts, 1)

def draw_dot(surf, x, y, radius, color, pulse=False):
    if pulse:
        t = time.time(); alpha = int(180 + 75 * math.sin(t * 6)); r = radius + int(2 * abs(math.sin(t * 3)))
    else:
        alpha = 255; r = radius
    dot_surf = pygame.Surface((r * 2 + 2, r * 2 + 2), pygame.SRCALPHA)
    pygame.draw.circle(dot_surf, (*color[:3], alpha), (r + 1, r + 1), r)
    surf.blit(dot_surf, (x - r - 1, y - r - 1))

def wrap_text(text, font, max_width):
    """Wrap text to fit within max_width pixels."""
    if isinstance(text, list):
        lines = []
        for paragraph in text:
            lines.extend(wrap_text(paragraph, font, max_width))
            lines.append("")  # blank line between paragraphs
        return lines
    words = text.split()
    lines = []
    current = ""
    for word in words:
        test = current + (" " if current else "") + word
        if font.size(test)[0] <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines

# ============================================================
# main()
# ============================================================

def main():
    _web_mode = "--web" in sys.argv
    config = load_config()
    VERSION_STR = load_version()

    # --- Load saved FPS ---
    _saved_fps = config.get("render_fps", 60)
    if isinstance(_saved_fps, str):
        try: _saved_fps = int(_saved_fps)
        except ValueError: _saved_fps = 60
    if _saved_fps not in (60, 120, 240): _saved_fps = 60
    RENDER_FPS = _saved_fps

    # --- Load saved resolution ---
    _saved_res_label = str(config.get("resolution", "Native"))
    _init_render_w = 0
    _init_render_h = 0
    _init_res_label = "Native"
    for _rkey, _rlbl, _rww, _rhh in RESOLUTION_PRESETS:
        if _rlbl == _saved_res_label:
            _init_render_w = _rww
            _init_render_h = _rhh
            _init_res_label = _rlbl
            break
    if _saved_res_label == "Native":
        _init_res_label = "Native"

    try:
        import bot_playstyles
        bot_playstyles.set_difficulty(config.get("bot_difficulty", "normal"))
    except (ImportError, AttributeError): pass

    ensure_assets()
    if _web_mode: os.environ["SDL_VIDEODRIVER"] = "dummy"
    pygame.init()
    if _web_mode:
        screen = pygame.display.set_mode((1, 1))
    else:
        if _init_res_label != "Native" and _init_render_w > 0:
            screen = pygame.display.set_mode((_init_render_w, _init_render_h), pygame.RESIZABLE)
        else:
            info = pygame.display.Info(); mon_w, mon_h = info.current_w, info.current_h
            win_w = int(mon_w * 0.9); win_h = int(win_w * HEIGHT / WIDTH)
            if win_h > int(mon_h * 0.9): win_h = int(mon_h * 0.9); win_w = int(win_h * WIDTH / HEIGHT)
            screen = pygame.display.set_mode((win_w, win_h), pygame.RESIZABLE)
    pygame.display.set_caption("GeoPolitical Domination")
    clock = pygame.time.Clock()
    font = pygame.font.SysFont(FONT_FAMILY, FONT_SIZE_NORMAL * U)
    smallfont = pygame.font.SysFont(FONT_FAMILY, (FONT_SIZE_NORMAL - 2) * U)
    bigfont = pygame.font.SysFont(FONT_FAMILY, FONT_SIZE_BIG * U, bold=True)
    titlefont = pygame.font.SysFont(FONT_FAMILY, FONT_SIZE_TITLE * U, bold=True)
    pinfont = pygame.font.SysFont(FONT_FAMILY, FONT_SIZE_PIN * U, bold=True)
    _overlay_surf = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
    _log_surf = pygame.Surface((580 * U, 160 * U), pygame.SRCALPHA)

    # Load local geojson countries
    local_countries = {}
    if os.path.exists(GEOJSON_CACHE):
        try:
            local_countries = load_countries_from_geojson(GEOJSON_CACHE, WIDTH, MAP_H)
            logger.info("Loaded geojson countries: %d", len(local_countries))
        except (OSError, ValueError, KeyError) as e:
            logger.error("Error parsing geojson: %s", e)
    if not local_countries:
        local_countries = {
            1: {"id": 1, "name": "Aland", "continent": "X",
                "polygons": [[(200,120),(260,120),(260,170),(200,170)]], "centroid": (230,145),
                "bbox": (200,120,260,170), "owner": None, "troops": 0, "adj": []},
            2: {"id": 2, "name": "Boria", "continent": "X",
                "polygons": [[(300,120),(360,120),(360,170),(300,170)]], "centroid": (330,145),
                "bbox": (300,120,360,170), "owner": None, "troops": 0, "adj": []},
        }
    build_adjacency(local_countries)

    map_surface = pygame.Surface((WIDTH, MAP_H))
    def render_base_map():
        for y in range(0, MAP_H, 2):
            t = y / MAP_H
            r = int(SEA_COLOR[0]+(SEA_COLOR_LIGHT[0]-SEA_COLOR[0])*t)
            g = int(SEA_COLOR[1]+(SEA_COLOR_LIGHT[1]-SEA_COLOR[1])*t)
            b = int(SEA_COLOR[2]+(SEA_COLOR_LIGHT[2]-SEA_COLOR[2])*t)
            pygame.draw.line(map_surface, (r,g,b), (0,y), (WIDTH,y))
            if y+1 < MAP_H: pygame.draw.line(map_surface, (r,g,b), (0,y+1), (WIDTH,y+1))
        for gx in range(0, WIDTH, 120):
            pygame.draw.line(map_surface, (35,55,90), (gx,0), (gx,MAP_H), 1)
        for gy in range(0, MAP_H, 80):
            pygame.draw.line(map_surface, (35,55,90), (0,gy), (WIDTH,gy), 1)
        for cid, c in local_countries.items():
            h = (cid * 37) % 20 - 10
            c_fill = (max(0,min(255,DEFAULT_COUNTRY_FILL[0]+h)), max(0,min(255,DEFAULT_COUNTRY_FILL[1]+h)), max(0,min(255,DEFAULT_COUNTRY_FILL[2]+h)))
            for ring in c["polygons"]:
                if len(ring) >= 3:
                    try:
                        pygame.draw.polygon(map_surface, c_fill, ring)
                        pygame.draw.polygon(map_surface, COUNTRY_BORDER_COLOR, ring, 1)
                    except pygame.error: pass
    render_base_map()

    # Camera state
    cam_scale = 1.0; cam_target_scale = 1.0; cam_x = 0.0; cam_y = 0.0
    cam_target_x = cam_x; cam_target_y = cam_y; dragging_pan = False; pan_start = (0,0); cam_start = (0,0)
    _cached_scaled_map = None; _cached_scale_key = None
    _own_surface = pygame.Surface((WIDTH, MAP_H), pygame.SRCALPHA); _own_dirty = True; _own_turn = -1
    hovered_country = None
    _last_pan_delta = (0, 0)
    _last_click_time = 0
    _last_click_pos = (0, 0)

    # State machine
    mode = None; state = "login"; _prev_state = None; _transition_t = 0.0
    message = ""; msg_until = 0; fullscreen = False; game_surf = pygame.Surface((WIDTH, HEIGHT))
    game = None

    # Account / auth state
    auth_manager = None
    logged_in_username = None
    if FIREBASE_AVAILABLE and _AuthManager:
        auth_manager = _AuthManager()
        # Try auto-restore — if it works, skip straight to main menu
        if auth_manager._restore_token() and auth_manager.username:
            logged_in_username = auth_manager.username
            state = "main_menu"
    login_mode = "login"  # "login" or "register"

    # Online state
    fc = None; remote = None; current_game_id = None; my_player_name = None
    network_thread = None; network_result = None; network_loading = False
    game_id_in_progress = None; player_name_in_progress = None
    joined_games = {}  # {game_id: {"player_name":..., "remote":..., "player_password":..., "room_password":...}}
    _JOINED_GAMES_FILE = os.path.join(BASE_DIR, ".joined_games")

    def _save_joined_games():
        """Persist joined games list to server and local backup."""
        import json as _json
        # Always save locally as backup (dotfile, not easily visible)
        _local = {}
        for gid, ginfo in joined_games.items():
            _local[gid] = {
                "player_name": ginfo.get("player_name", ""),
                "player_password": ginfo.get("player_password", ""),
                "room_password": ginfo.get("room_password", ""),
            }
        try:
            with open(_JOINED_GAMES_FILE, "w") as f:
                _json.dump(_local, f)
        except OSError as e:
            logger.warning("Failed to save local joined games: %s", e)
        # Also save to server if connected
        if fc:
            try:
                fc.save_joined_games(joined_games)
            except Exception as e:
                logger.warning("Failed to save joined games to server: %s", e)

    def _load_joined_games_from_local():
        """Load joined games from local backup file."""
        import json as _json
        if not os.path.exists(_JOINED_GAMES_FILE):
            return
        try:
            with open(_JOINED_GAMES_FILE, "r") as f:
                data = _json.load(f)
            for gid, ginfo in data.items():
                if gid not in joined_games:
                    joined_games[gid] = {
                        "player_name": ginfo.get("player_name", ""),
                        "player_password": ginfo.get("player_password", ""),
                        "room_password": ginfo.get("room_password", ""),
                        "remote": None,
                    }
            logger.info("Loaded %d joined games from local backup", len(data))
        except (OSError, ValueError, KeyError) as e:
            logger.warning("Failed to load local joined games: %s", e)

    def _load_joined_games_from_server():
        """Load joined games from Firebase. Call after fc is initialized."""
        if not fc:
            return
        try:
            server_games = fc.load_joined_games()
            for gid, ginfo in server_games.items():
                if gid not in joined_games:
                    joined_games[gid] = {
                        "player_name": ginfo.get("player_name", ""),
                        "player_password": "",
                        "room_password": "",
                        "remote": None,
                    }
        except Exception as e:
            logger.warning("Failed to load joined games from server: %s", e)

    # Load from local backup immediately (available before Firebase connects)
    _load_joined_games_from_local()

    # Game over / spectator state
    player_is_spectating = False; game_over_shown = False

    # Updater state
    update_info = None; update_check_done = False; update_btn = None; dismiss_btn = None
    update_progress = None; update_thread = None

    # Animation state
    turn_flash_time = 0; turn_flash_color = None; flash_start_time = 0
    _last_turn_idx = -1; _last_ownership = {}; _last_troops = {}; vfx = []
    tick_interval = 1.0/TPS; tick_accum = 0.0; last_time = time.time(); spectate_tps = TPS

    # Audio
    audio = AudioManager(
        sfx_volume=float(config.get("sfx_volume", DEFAULT_SFX_VOLUME)),
        music_volume=float(config.get("music_volume", DEFAULT_MUSIC_VOLUME))
    ) if AUDIO_AVAILABLE and AudioManager else None

    # Chat state
    chat_messages = []
    chat_input_active = False
    chat_input_text = ""
    show_chat = bool(int(config.get("show_chat", 1)))
    show_logs = bool(int(config.get("show_logs", 0)))
    last_chat_fetch = 0

    # Game mode state
    current_game_mode = "classic"
    current_map_scope = "world"
    is_private_game = False
    game_join_code = ""

    # Rules page state
    rules_scroll_y = 0
    rules_current_tab = "general"

    # Settings tab state
    settings_tab = "Graphics"

    # Game browser state
    public_games_list = []
    last_browser_refresh = 0
    browser_scroll_y = 0

    # Camera inertia
    cam_vel_x = 0.0
    cam_vel_y = 0.0

    # Spectator count
    spectator_count = 0

    # Player stats cache
    player_stats_cache = {}  # loaded from firebase

    # Tooltip state
    tooltip_country = None
    tooltip_pos = (0, 0)

    # Joined games scroll
    joined_games_scroll_y = 0

    # Leaderboard state
    leaderboard_cache = []  # [{username, elo, wins, losses, games_played}, ...]
    leaderboard_scroll_y = 0

    # Friends state
    friends_cache = []  # [{uid, username, status}, ...]
    friends_scroll_y = 0
    friend_add_input = ""
    friend_add_active = False

    # Notifications state
    notifications_cache = []  # [{id, type, from_username, game_id, message, timestamp, read}, ...]
    last_notif_check = 0
    notif_unread_count = 0
    notif_scroll_y = 0

    # Troop animation state
    troop_animations = []  # [{src_xy, dst_xy, count, color, start_time, duration, done}, ...]
    TROOP_ANIM_DURATION = 0.6  # seconds

    # Input fields
    input_active = {"player_name": False, "starting_country": False, "move_target": False,
                    "game_id": False, "player_password": False, "room_password": False,
                    "login_user": False, "login_pass": False}
    user_inputs = {"player_name": config.get("player_name", "Player"), "starting_country": "",
                   "move_target": "", "game_id": "room1", "player_password": "", "room_password": "",
                   "login_user": "", "login_pass": ""}
    # If starting on login screen, auto-focus the username field
    if state == "login":
        input_active["login_user"] = True
    # If auto-restored session, pre-fill player name with account username
    if logged_in_username:
        user_inputs["player_name"] = logged_in_username
    hide_password = True

    def layout_inputs(st):
        cx = WIDTH//2-260*U; w = 520*U; h = 36*U; rects = {}
        if st == "login":
            rects["login_user"] = pygame.Rect(cx,240*U,w,h)
            rects["login_pass"] = pygame.Rect(cx,320*U,w,h)
        elif st == "online_setup":
            rects["game_id"] = pygame.Rect(cx,160*U,w,h); rects["player_name"] = pygame.Rect(cx,216*U,w,h)
            rects["player_password"] = pygame.Rect(cx,272*U,w,h); rects["room_password"] = pygame.Rect(cx,328*U,w,h)
        elif st == "local_setup": rects["player_name"] = pygame.Rect(cx,200*U,w,h)
        elif st in ("choose_start",): rects["starting_country"] = pygame.Rect(cx,420*U,w,h)
        if st == "playing":
            rects["move_target"] = pygame.Rect(cx,MAP_H+8*U+120*U,w,28*U)
            rects["starting_country"] = pygame.Rect(cx,MAP_H+8*U+120*U,w,28*U)
        return rects
    small_input_rects = layout_inputs(state)

    # Game-play state
    selected_country = None; expand_src = None; expand_mode = None
    expand_send_dialog = False; expand_send_slider = None; expand_send_confirm = None; expand_send_cancel = None
    gather_dialog = False; gather_slider = None; gather_confirm = None; gather_cancel = None; _dialog_anim_t = 0.0

    # Login / register buttons
    btn_login_submit = Button((WIDTH//2-200*U,400*U,400*U,48*U), "Log In", bigfont, bg=(55,130,210))
    btn_login_toggle = Button((WIDTH//2-200*U,460*U,400*U,36*U), "Don't have an account? Register", font, bg=(60,60,80))
    btn_logout = Button((WIDTH//2+210*U,480*U,100*U,32*U), "Log Out", font, bg=(150,60,60))

    # Main menu buttons (left column)
    _mc_x = WIDTH//2-420*U; _mc_w = 400*U; _mc_h = 42*U
    btn_play = Button((_mc_x,180*U,_mc_w,_mc_h), "Play", bigfont, bg=(55,160,120))
    btn_mygames = Button((_mc_x,230*U,_mc_w,_mc_h), "My Games", bigfont, bg=(100,80,180))
    btn_stats = Button((_mc_x,280*U,_mc_w,_mc_h), "Stats", bigfont, bg=(55,130,210))
    btn_rules = Button((_mc_x,330*U,_mc_w,_mc_h), "Rules", bigfont, bg=(80,130,80))
    btn_settings = Button((_mc_x,380*U,_mc_w,_mc_h), "Settings", bigfont, bg=(80,80,110))
    btn_quit_main = Button((_mc_x,430*U,_mc_w,_mc_h), "Quit", bigfont, bg=(160,60,60))
    # Main menu buttons (right column)
    _rc_x = WIDTH//2+20*U
    btn_leaderboard = Button((_rc_x,180*U,_mc_w,_mc_h), "Leaderboard", bigfont, bg=(180,140,50))
    btn_friends = Button((_rc_x,230*U,_mc_w,_mc_h), "Friends", bigfont, bg=(70,150,170))
    btn_notifications = Button((_rc_x,280*U,_mc_w,_mc_h), "Notifications", bigfont, bg=(170,90,130))
    # Play sub-menu buttons
    btn_play_offline = Button((WIDTH//2-200*U,200*U,400*U,48*U), "Offline Play", bigfont, bg=(55,160,120))
    btn_play_online = Button((WIDTH//2-200*U,260*U,400*U,48*U), "Online Game", bigfont, bg=(55,130,210))
    btn_play_spectate = Button((WIDTH//2-200*U,320*U,400*U,48*U), "Spectate Bots", bigfont, bg=(180,140,50))
    btn_play_back = Button((WIDTH//2-200*U,400*U,400*U,42*U), "Back", bigfont, bg=(100,100,120))
    # Stats screen buttons
    btn_stats_back = Button((WIDTH//2-100*U,560*U,200*U,48*U), "Back", bigfont, bg=(100,100,120))
    # Leaderboard screen buttons
    btn_lb_back = Button((WIDTH//2-100*U,560*U,200*U,48*U), "Back", bigfont, bg=(100,100,120))
    # Friends screen buttons
    btn_friends_back = Button((WIDTH//2-100*U,560*U,200*U,48*U), "Back", bigfont, bg=(100,100,120))
    btn_friends_add = Button((WIDTH//2+140*U,80*U,140*U,36*U), "Add Friend", font, bg=(55,160,120))
    btn_friends_send = Button((WIDTH//2+290*U,80*U,80*U,36*U), "Send", font, bg=(55,130,210))
    # Notifications screen buttons
    btn_notif_back = Button((WIDTH//2-100*U,560*U,200*U,48*U), "Back", bigfont, bg=(100,100,120))
    btn_notif_refresh = Button((WIDTH//2+200*U,30*U,140*U,36*U), "Refresh", font, bg=(55,130,210))
    # Keep old references for backward compatibility in local_setup / online_setup
    btn_local = btn_play_offline
    btn_spectate = btn_play_spectate
    btn_online = btn_play_online
    btn_mygames_back = Button((WIDTH//2-100*U,560*U,200*U,48*U), "Back", bigfont, bg=(100,100,120))
    btn_fps_60 = Button((WIDTH//2-300*U,260*U,180*U,44*U), "60 FPS", bigfont, bg=(55,130,210))
    btn_fps_120 = Button((WIDTH//2-60*U,260*U,180*U,44*U), "120 FPS", bigfont, bg=(55,130,210))
    btn_fps_240 = Button((WIDTH//2+180*U,260*U,180*U,44*U), "240 FPS", bigfont, bg=(55,130,210))
    # Resolution buttons (including Native option)
    _all_res = list(RESOLUTION_PRESETS) + [(0, "Native", 0, 0)]  # Native = auto
    _res_btn_w = 95*U; _res_gap = 8*U
    _res_total = len(_all_res)*_res_btn_w + (len(_all_res)-1)*_res_gap
    _res_start_x = WIDTH//2 - _res_total//2
    btn_resolutions = []
    for ri, (_, label, rw, rh) in enumerate(_all_res):
        bx = _res_start_x + ri * (_res_btn_w + _res_gap)
        btn_resolutions.append((Button((bx, 390*U, _res_btn_w, 40*U), label, font, bg=(55,120,170)), rw, rh, label))
    current_resolution_label = _init_res_label  # tracks which resolution is active
    current_render_w = _init_render_w if _init_render_w > 0 else WIDTH   # render resolution width
    current_render_h = _init_render_h if _init_render_h > 0 else HEIGHT  # render resolution height
    btn_settings_back = Button((WIDTH//2-100*U,540*U,200*U,48*U), "Back", bigfont, bg=(100,100,120))
    bot_slider = Slider((WIDTH//2-200*U,380*U,400*U,36*U), 0, 6, config.get("default_bot_count", 2))
    btn_start_local = Button((WIDTH//2-200*U,440*U,400*U,52*U), "Start", bigfont, bg=(55,160,120))
    spectate_slider = Slider((WIDTH//2-200*U,300*U,400*U,36*U), 2, 8, 4)
    btn_start_spectate = Button((WIDTH//2-200*U,380*U,400*U,52*U), "Watch", bigfont, bg=(180,140,50))
    buttons_y = MAP_H+8*U+78*U+12*U; btn_w = 170*U; btn_h = 38*U; gap = 10*U
    b_peace = Button((8*U, buttons_y, btn_w, btn_h), "[1] Peace", font, bg=(50,170,110))
    b_expand = Button((8*U+btn_w+gap, buttons_y, btn_w, btn_h), "[2] Expand", font, bg=(55,130,210))
    b_gather = Button((8*U+2*(btn_w+gap), buttons_y, btn_w, btn_h), "[3] Gather", font, bg=(200,150,40))
    b_nothing = Button((8*U+3*(btn_w+gap), buttons_y, btn_w, btn_h), "[4] Nothing", font, bg=(150,60,60))
    btn_go_leave = Button((WIDTH//2-220*U, HEIGHT//2+20*U, 200*U, 48*U), "Leave Game", bigfont, bg=(180,55,55))
    btn_go_spectate = Button((WIDTH//2+20*U, HEIGHT//2+20*U, 200*U, 48*U), "Spectate", bigfont, bg=(55,130,210))
    btn_lobby_start = Button((WIDTH//2-120*U,560*U,240*U,52*U), "Start Game", bigfont, bg=(55,160,120))
    btn_lobby_back = Button((WIDTH//2-340*U,560*U,200*U,52*U), "Back", bigfont, bg=(100,100,120))
    # Player limit controls (host only)
    _plimit_x = WIDTH//2 + 180*U
    btn_plimit_minus = Button((_plimit_x, 130*U, 36*U, 30*U), "-", font, bg=(150,60,60))
    btn_plimit_plus = Button((_plimit_x + 44*U, 130*U, 36*U, 30*U), "+", font, bg=(55,160,120))
    btn_spectator_leave = Button((WIDTH-160*U, MAP_H+8*U+78*U+60*U, 150*U, 32*U), "Leave Game", font, bg=(180,55,55))

    # Rules page buttons
    btn_rules_back = Button((WIDTH//2-100*U, HEIGHT-60*U, 200*U, 48*U), "Back", bigfont, bg=(100,100,120))
    btn_rules_general = Button((WIDTH//2-420*U, 80*U, 190*U, 36*U), "General", font, bg=(55,130,210))
    btn_rules_classic = Button((WIDTH//2-210*U, 80*U, 190*U, 36*U), "Classic", font, bg=(55,160,120))
    btn_rules_tournament = Button((WIDTH//2+0*U, 80*U, 190*U, 36*U), "Tournament", font, bg=(200,150,40))
    btn_rules_challenge = Button((WIDTH//2+210*U, 80*U, 190*U, 36*U), "Challenge", font, bg=(180,55,55))

    # Online create screen buttons
    btn_mode_classic = Button((WIDTH//2-380*U, 200*U, 230*U, 44*U), "Classic", bigfont, bg=(55,160,120))
    btn_mode_tournament = Button((WIDTH//2-120*U, 200*U, 230*U, 44*U), "Tournament", bigfont, bg=(200,150,40))
    btn_mode_challenge = Button((WIDTH//2+140*U, 200*U, 230*U, 44*U), "Challenge", bigfont, bg=(180,55,55))
    btn_scope_world = Button((WIDTH//2-280*U, 290*U, 160*U, 36*U), "World", font, bg=(55,130,210))
    btn_scope_europe = Button((WIDTH//2-100*U, 290*U, 160*U, 36*U), "Europe", font, bg=(55,130,210))
    btn_scope_asia = Button((WIDTH//2+80*U, 290*U, 160*U, 36*U), "Asia", font, bg=(55,130,210))
    btn_private_toggle = Button((WIDTH//2-100*U, 360*U, 200*U, 36*U), "Public Game", font, bg=(55,160,120))
    btn_create_game = Button((WIDTH//2-120*U, 440*U, 240*U, 52*U), "Create Game", bigfont, bg=(55,160,120))
    btn_create_back = Button((WIDTH//2-120*U, 510*U, 240*U, 42*U), "Back", bigfont, bg=(100,100,120))

    # Game browser buttons
    btn_browser_back = Button((WIDTH//2-100*U, HEIGHT-60*U, 200*U, 48*U), "Back", bigfont, bg=(100,100,120))
    btn_browser_refresh = Button((WIDTH//2+140*U, 80*U, 140*U, 36*U), "Refresh", font, bg=(55,130,210))
    btn_join_code = Button((WIDTH//2-380*U, 80*U, 180*U, 36*U), "Join by Code", font, bg=(100,80,180))
    btn_create_new_game = Button((WIDTH//2-160*U, 80*U, 180*U, 36*U), "Create Game", font, bg=(55,160,120))

    # Settings tab buttons
    btn_tab_graphics = Button((WIDTH//2-300*U, 130*U, 180*U, 36*U), "Graphics", font, bg=(55,130,210))
    btn_tab_audio = Button((WIDTH//2-90*U, 130*U, 180*U, 36*U), "Audio", font, bg=(55,130,210))
    btn_tab_controls = Button((WIDTH//2+120*U, 130*U, 180*U, 36*U), "Controls", font, bg=(55,130,210))

    # Audio sliders (in settings)
    music_slider = Slider((WIDTH//2-200*U, 240*U, 400*U, 36*U), 0, 100, int(float(config.get("music_volume", DEFAULT_MUSIC_VOLUME)) * 100))
    sfx_slider = Slider((WIDTH//2-200*U, 330*U, 400*U, 36*U), 0, 100, int(float(config.get("sfx_volume", DEFAULT_SFX_VOLUME)) * 100))

    # Chat input
    btn_chat_send = Button((WIDTH-70*U, MAP_H+140*U, 60*U, 28*U), "Send", font, bg=(55,130,210))

    # ---- Helper closures ----
    def _screen_to_game(pos):
        try: real_w, real_h = pygame.display.get_surface().get_size()
        except (pygame.error, AttributeError): return pos
        if real_w <= 1 or real_h <= 1: return pos
        s = min(real_w/WIDTH, real_h/HEIGHT); ow = int(WIDTH*s); oh = int(HEIGHT*s)
        ox = (real_w-ow)//2; oy = (real_h-oh)//2
        gx = (pos[0]-ox)/s; gy = (pos[1]-oy)/s
        return (int(max(0,min(WIDTH,gx))), int(max(0,min(HEIGHT,gy))))

    def flash(msg, secs=FLASH_MESSAGE_DEFAULT_SECS):
        nonlocal message, msg_until, flash_start_time
        message = msg; msg_until = time.time()+secs; flash_start_time = time.time()
        logger.info("[UI] %s", msg)

    _input_hover_key = None

    def draw_input_box(key, label, hide_pw=False):
        r = small_input_rects.get(key)
        if not r: return
        active = input_active.get(key, False); hovered = _input_hover_key == key
        if active: bg=(50,62,88); border=(80,160,255); bw=3
        elif hovered: bg=(45,55,78); border=(70,120,190); bw=2
        else: bg=(40,50,70); border=HUD_BORDER; bw=2
        pygame.draw.rect(screen, bg, r, border_radius=6*U)
        pygame.draw.rect(screen, border, r, bw, border_radius=6*U)
        if active:
            glow = pygame.Surface((r.w+6*U, r.h+6*U), pygame.SRCALPHA)
            pygame.draw.rect(glow, (80,160,255,25), (0,0,r.w+6*U,r.h+6*U), border_radius=8*U)
            screen.blit(glow, (r.x-3*U, r.y-3*U))
        txt = user_inputs.get(key, ""); display_txt = "*"*len(txt) if (hide_pw and txt) else txt
        t = cached_render(font, display_txt, TEXT_PRIMARY); screen.blit(t, (r.x+10*U, r.y+9*U))
        label_surf = cached_render(font, label, TEXT_SECONDARY); screen.blit(label_surf, (r.x, r.y-20*U))

    def handle_key_input(ev):
        if ev.key == pygame.K_BACKSPACE:
            for k,v in input_active.items():
                if v: user_inputs[k] = user_inputs[k][:-1]
        elif ev.key in (pygame.K_RETURN, pygame.K_TAB):
            pass  # handled by state-specific logic
        else:
            ch = ev.unicode
            if ch and len(ch) == 1 and ch not in ('\t', '\r', '\n'):
                for k,v in input_active.items():
                    if v: user_inputs[k] += ch

    def country_at_world_point(wx, wy):
        for cid, c in local_countries.items():
            bbox = c.get("bbox")
            if bbox and (wx < bbox[0] or wx > bbox[2] or wy < bbox[1] or wy > bbox[3]): continue
            for ring in c["polygons"]:
                rx0,ry0,rx1,ry1 = polygon_bbox(ring)
                if wx < rx0 or wx > rx1 or wy < ry0 or wy > ry1: continue
                if point_in_poly(wx, wy, ring): return c
        return None

    def get_snapshot():
        if mode in ("local","spectate") and game: return game.snapshot()
        elif mode == "online" and remote:
            raw = remote.snapshot(); players = []
            for p in raw.get("players",[]):
                col = p.get("color")
                if isinstance(col,str): col = hex_to_rgb(col)
                elif isinstance(col,(list,tuple)) and len(col)>=3: col=(int(col[0]),int(col[1]),int(col[2]))
                else: col=(120,120,120)
                players.append({"name":p.get("name","?"),"money":int(p.get("money",0) or 0),
                    "is_bot":p.get("is_bot",False),"color":col,"vulnerable":p.get("vulnerable",False),
                    "was_attacked":p.get("was_attacked",False),"is_host":p.get("is_host",False),
                    "is_spectator":p.get("is_spectator",False),"eliminated":p.get("eliminated",False)})
            countries = {}
            for k,v in raw.get("countries",{}).items():
                try: int_k = int(k)
                except (ValueError,TypeError): continue
                countries[int_k] = {"owner":v.get("owner"),"troops":int(v.get("troops",0) or 0),
                    "continent":v.get("continent",local_countries.get(int_k,{}).get("continent",""))}
            return {"players":players,"countries":countries,"turn_idx":raw.get("turn_idx",0),
                    "turn_number":raw.get("turn_number",1),"logs":raw.get("logs",[]),
                    "started":raw.get("started",True),"host":raw.get("host",""),"winner":raw.get("winner")}
        return {"players":[],"countries":{},"turn_idx":0,"turn_number":1,"logs":[]}

    def do_action(action_type, params):
        nonlocal game, game_over_shown
        if mode in ("local","spectate") and game:
            cur = game.players[game.turn_idx]
            if cur.eliminated or cur.is_spectator: end_turn_housekeeping(game, cur); return
            if action_type == "PEACE":
                cur.vulnerable = True; cur.was_attacked = False; game.log(f"{cur.name} chose PEACE"); end_turn_housekeeping(game, cur)
            elif action_type == "NOTHING":
                game.log(f"{cur.name} did NOTHING"); end_turn_housekeeping(game, cur)
            elif action_type == "GATHER":
                buy = params.get("buy",0); cost = buy*TROOP_COST
                if buy > 0 and cur.money >= cost:
                    cur.money -= cost
                    owned_countries = [c for c in game.countries.values() if c.get("owner") == cur.name]
                    if owned_countries:
                        border_c = []
                        for c in owned_countries:
                            for a in c.get("adj",[]):
                                nb = local_countries.get(a.get("to"))
                                if nb and nb.get("owner") and nb.get("owner") != cur.name: border_c.append(c); break
                        targets = border_c if border_c else owned_countries
                        i = 0; remaining = buy
                        while remaining > 0: targets[i%len(targets)]["troops"] += 1; remaining -= 1; i += 1
                    game.log(f"{cur.name} bought troops for ${cost}")
                else: game.log(f"{cur.name} bought 0 troops")
                end_turn_housekeeping(game, cur)
            elif action_type == "EXPAND":
                src_id = params.get("src"); tgt_id = params.get("tgt"); send_amt = params.get("send",1)
                src = game.countries.get(src_id); tgt = game.countries.get(tgt_id)
                if not src or not tgt: flash("Invalid source or target."); return
                # Trigger troop movement animation
                src_xy = local_countries.get(src_id, {}).get("centroid", (0, 0))
                tgt_xy = local_countries.get(tgt_id, {}).get("centroid", (0, 0))
                troop_animations.append({
                    "src_xy": src_xy, "dst_xy": tgt_xy, "count": send_amt,
                    "color": cur.color, "start_time": time.time(), "duration": TROOP_ANIM_DURATION,
                })
                adj = next((a for a in src.get("adj",[]) if a["to"]==tgt_id), None)
                if not adj: flash("Not adjacent"); return
                cost = adj.get("cost",0)
                if cost > 0:
                    if cur.money >= cost: cur.money -= cost; game.log(f"{cur.name} paid crossing ${cost}")
                    else: game.log(f"{cur.name} cannot pay crossing; cancelled"); return
                actual_available = int(src.get("troops",0))
                if send_amt >= actual_available:
                    send_amt = max(1, actual_available-1)
                    if send_amt <= 0: game.log("Not enough troops."); end_turn_housekeeping(game, cur); return
                src["troops"] -= send_amt
                if src["troops"] <= 0:
                    prev = src.get("owner")
                    if prev:
                        op = next((pl for pl in game.players if pl.name==prev),None)
                        if op and src["id"] in op.owned: op.owned.remove(src["id"])
                    src["owner"] = None; src["troops"] = 0; game.log("A territory is now unowned")
                if not tgt.get("owner"):
                    success = claim_country(cur, tgt, send_amt, game)
                    if not success: src["troops"] += send_amt
                else: attack_country(cur, src, tgt, send_amt, game)
                end_turn_housekeeping(game, cur)
            # Check if human was eliminated
            if mode == "local" and game and not player_is_spectating:
                human = game.players[0] if game.players else None
                if human and human.eliminated and not game_over_shown: game_over_shown = True
        elif mode == "online" and fc:
            try:
                # Trigger animation for expand actions
                if action_type == "EXPAND":
                    src_id = params.get("src"); tgt_id = params.get("tgt"); send_amt = params.get("send",1)
                    src_xy = local_countries.get(src_id, {}).get("centroid", (0, 0))
                    tgt_xy = local_countries.get(tgt_id, {}).get("centroid", (0, 0))
                    troop_animations.append({
                        "src_xy": src_xy, "dst_xy": tgt_xy, "count": send_amt,
                        "color": (200, 200, 200), "start_time": time.time(), "duration": TROOP_ANIM_DURATION,
                    })
                fc.submit_action(current_game_id, my_player_name, action_type, params)
            except (RuntimeError, PermissionError, IndexError) as e: flash(f"{action_type} failed: {e}")

    def do_start_claim(country_id):
        nonlocal state, game
        if mode in ("local","spectate") and game:
            c = game.countries.get(country_id)
            if not c: flash("Invalid country."); return False
            if c.get("owner"): flash("That country is already owned."); return False
            human = game.players[0]
            c["owner"] = human.name; c["troops"] = 1; human.owned.add(c["id"]); human.had_territory = True
            game.log(obf_claim_msg(human.name, c.get("continent","unknown"), 1))
            game.started = True; state = "playing"; flash("Starting country claimed. Game begins."); return True
        elif mode == "online" and fc:
            try: ok = fc.claim_starting_country(current_game_id, my_player_name, country_id)
            except (RuntimeError, PermissionError) as e: flash(f"Claim failed: {e}"); return False
            if ok: flash("Claimed!"); state = "playing"; return True
            else: flash("That country was just taken."); return False
        return False

    def is_my_turn():
        if player_is_spectating: return False
        snap = get_snapshot(); players = snap["players"]
        if not players: return False
        idx = snap["turn_idx"]
        if idx < 0 or idx >= len(players): return False
        if mode == "local": return not players[idx].get("is_bot",False) and not players[idx].get("eliminated",False)
        else: return players[idx].get("name") == my_player_name

    def start_local_game(human_name, bot_count):
        nonlocal game, game_over_shown, player_is_spectating
        game_over_shown = False; player_is_spectating = False
        for c in local_countries.values(): c["owner"] = None; c["troops"] = 0
        palette = PALETTE.copy(); random.shuffle(palette); players = []
        human = Player(human_name, is_bot=False, color=palette.pop() if palette else random.choice(PALETTE), is_host=True)
        players.append(human)
        for i in range(bot_count):
            players.append(Player(f"bot{i+1}", is_bot=True, color=palette.pop() if palette else random.choice(PALETTE)))
        for pl in players:
            if pl.is_bot:
                empty = [c for c in local_countries.values() if not c.get("owner")]
                if not empty: break
                pick = random.choice(empty); pick["owner"] = pl.name; pick["troops"] = 1
                pl.owned.add(pick["id"]); pl.had_territory = True
        game = Game(players, local_countries); game.host_name = human_name

    def start_spectate_game(bot_count):
        nonlocal game
        for c in local_countries.values(): c["owner"] = None; c["troops"] = 0
        palette = PALETTE.copy(); random.shuffle(palette); players = []
        for i in range(bot_count):
            players.append(Player(f"bot{i+1}", is_bot=True, color=palette.pop() if palette else random.choice(PALETTE)))
        for pl in players:
            empty = [c for c in local_countries.values() if not c.get("owner")]
            if not empty: break
            pick = random.choice(empty); pick["owner"] = pl.name; pick["troops"] = 1
            pl.owned.add(pick["id"]); pl.had_territory = True
        game = Game(players, local_countries); game.started = True

    def build_minimal_countries_for_upload():
        return {str(cid): {"owner":None,"troops":0,"continent":c.get("continent","")} for cid,c in local_countries.items()}

    def init_online():
        nonlocal fc, remote, update_info, update_check_done
        if not FIREBASE_AVAILABLE: flash("Firebase not available."); return False
        try: fc = FirebaseController(auth_manager=auth_manager)
        except (RuntimeError, ConnectionError, OSError) as e: flash(f"Failed: {e}"); return False
        remote = RemoteGameView()
        # Load joined games from server now that we have auth
        _load_joined_games_from_server()
        if UPDATER_AVAILABLE:
            def check_updates_background():
                nonlocal update_info, update_check_done
                try: update_info = updater.silent_check(); update_check_done = True
                except (OSError, ValueError, RuntimeError) as e: logger.warning("Update check failed: %s", e); update_check_done = True
            try: threading.Thread(target=check_updates_background, daemon=True).start()
            except RuntimeError: update_check_done = True
        else: update_check_done = True
        return True

    def do_leave_game():
        nonlocal state, game, mode, player_is_spectating, game_over_shown
        if mode == "local" and game:
            human = game.players[0] if game.players else None
            if human: game.remove_player(human.name)
        elif mode == "online" and current_game_id:
            joined_games.pop(current_game_id, None)
            _save_joined_games()
        state = "main_menu"; game = None; mode = None; player_is_spectating = False; game_over_shown = False
        flash("Left the game.")

    def do_spectate_game():
        nonlocal player_is_spectating, game_over_shown
        if mode == "local" and game:
            human = game.players[0] if game.players else None
            if human: game.make_spectator(human.name)
        player_is_spectating = True; game_over_shown = False; flash("Now spectating.")

    # ================================================================
    # Main loop
    # ================================================================
    running = True
    while running:
        if update_progress and update_progress.get("phase") == "done":
            time.sleep(1.5); pygame.quit(); os.execv(sys.executable, [sys.executable, os.path.join(BASE_DIR, "client.py")])
        now = time.time(); dt = min(now-last_time, 0.1); last_time = now
        cur_tps = spectate_tps if mode == "spectate" or player_is_spectating else TPS
        tick_interval = 1.0/max(1,cur_tps); small_input_rects = layout_inputs(state)

        # Network result check (online)
        if mode == "online" and network_loading and network_thread and not network_thread.is_alive():
            network_loading = False
            if isinstance(network_result, Exception): flash(f"Failed: {network_result}")
            elif network_result:
                doc = network_result; current_game_id = game_id_in_progress; my_player_name = player_name_in_progress
                if not doc.get("countries"): fc.upload_initial_countries(current_game_id, build_minimal_countries_for_upload())
                fc.listen_to_game(current_game_id, lambda d: remote.update_from_doc(d))
                joined_games[current_game_id] = {
                    "player_name": my_player_name, "remote": remote,
                    "player_password": user_inputs.get("player_password", ""),
                    "room_password": user_inputs.get("room_password", ""),
                }
                _save_joined_games()
                # Check game status to decide where to go
                game_status = doc.get("status", "waiting")
                has_country = any(v.get("owner")==my_player_name for v in (doc.get("countries") or {}).values())
                if has_country: state = "playing"; flash(f"Re-entering '{current_game_id}'")
                elif game_status == "playing": state = "choose_start"; flash("Game in progress. Choose your starting country.")
                else: state = "game_lobby"; flash(f"Joined lobby for '{current_game_id}'")
            else: flash("Failed to create or join game.")

        # Bot turn processing
        if mode in ("local","spectate") and state == "playing" and game:
            if game.players and game.players[game.turn_idx].is_bot:
                bot_player = game.players[game.turn_idx]
                if bot_player.eliminated: end_turn_housekeeping(game, bot_player)
                elif not getattr(game,"bot_thread",None) or not game.bot_thread.is_alive():
                    def _bot_worker(bp=bot_player):
                        try:
                            if game is None: return
                            act = decide_local_bot(game, bp)
                            if not act: act = ("NOTHING", None)
                            cmd, params = act
                            if cmd == "PEACE": bp.vulnerable=True; bp.was_attacked=False; game.log(f"{bp.name} chooses PEACE"); end_turn_housekeeping(game,bp)
                            elif cmd == "GATHER":
                                roll=random.randint(1,20); max_afford=bp.money//TROOP_COST; buy=min(roll,max_afford); cost=buy*TROOP_COST; bp.money-=cost
                                owned_c = [c for c in local_countries.values() if c.get("owner")==bp.name]
                                border_c = []
                                for c in owned_c:
                                    for a in c.get("adj",[]):
                                        nb = local_countries.get(a.get("to"))
                                        if nb and nb.get("owner") and nb.get("owner")!=bp.name: border_c.append(c); break
                                targets = border_c if border_c else owned_c; i=0
                                while buy>0 and targets: targets[i%len(targets)]["troops"]+=1; buy-=1; i+=1
                                game.log(f"{bp.name} bought troops for ${cost}"); end_turn_housekeeping(game,bp)
                            elif cmd == "NOTHING": game.log(f"{bp.name} does NOTHING"); end_turn_housekeeping(game,bp)
                            elif cmd == "EXPAND" and params:
                                src_id,tgt_id,send = params
                                src=local_countries.get(src_id); tgt=local_countries.get(tgt_id)
                                if not src or not tgt or src.get("owner")!=bp.name:
                                    game.log(f"{bp.name} invalid expand -> skip"); end_turn_housekeeping(game,bp)
                                else:
                                    max_send = max(1,int(src.get("troops",0))-1); send=max(1,min(send,max_send))
                                    adj=next((a for a in src.get("adj",[]) if a["to"]==tgt_id),None)
                                    if adj and adj.get("cost",0)>0:
                                        if bp.money>=adj["cost"]: bp.money-=adj["cost"]; game.log(f"{bp.name} paid crossing ${adj['cost']}")
                                        else: game.log(f"{bp.name} cannot pay crossing"); end_turn_housekeeping(game,bp); return
                                    src["troops"]-=send
                                    if src["troops"]<=0:
                                        prev=src.get("owner")
                                        if prev:
                                            op=next((pl for pl in game.players if pl.name==prev),None)
                                            if op and src["id"] in op.owned: op.owned.remove(src["id"])
                                        src["owner"]=None; src["troops"]=0; game.log("A territory is now unowned")
                                    if not tgt.get("owner"):
                                        success=claim_country(bp,tgt,send,game)
                                        if not success: src["troops"]+=send
                                    else: attack_country(bp,src,tgt,send,game)
                                    end_turn_housekeeping(game,bp)
                        except (KeyError,TypeError,ValueError,IndexError) as e:
                            if game is not None:
                                logger.error("bot_worker error: %s", e)
                                try: end_turn_housekeeping(game,bp)
                                except (KeyError,TypeError,ValueError): pass
                        finally:
                            if game is not None: game.bot_thread = None
                    game.bot_thread = threading.Thread(target=_bot_worker, daemon=True)
                    game.bot_thread.start()

        # Check for human elimination
        if mode == "local" and state == "playing" and game and not player_is_spectating and not game_over_shown:
            human = game.players[0] if game.players else None
            if human and human.had_territory and human.country_count() == 0 and not human.eliminated:
                human.eliminated = True; game_over_shown = True
            # Check for winner (only 1 non-eliminated player left)
            alive = [p for p in game.players if not p.eliminated and not p.is_bot and not p.is_spectator]
            if len(alive) == 1 and alive[0].name == (human.name if human else ""):
                if fc and mode == "online" and not getattr(game, '_elo_updated', False):
                    try: fc.update_elo(won=True); game._elo_updated = True
                    except: pass
            elif human and human.eliminated:
                if fc and mode == "online" and not getattr(game, '_elo_updated', False):
                    try: fc.update_elo(won=False); game._elo_updated = True
                    except: pass

        # ---- Event handling ----
        if "--web" in sys.argv:
            import web_serve
            _web_scale_x = WIDTH / web_serve.WEB_W; _web_scale_y = HEIGHT / web_serve.WEB_H
            for wi in web_serve.get_pending_inputs():
                try:
                    wt=wi.get("type",""); wx=int(wi.get("x",0)*_web_scale_x); wy=int(wi.get("y",0)*_web_scale_y)
                    if wt=="mousedown": pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONDOWN,pos=(wx,wy),button=wi.get("button",1)))
                    elif wt=="mouseup": pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONUP,pos=(wx,wy),button=wi.get("button",1)))
                    elif wt=="mousemove": pygame.event.post(pygame.event.Event(pygame.MOUSEMOTION,pos=(wx,wy),rel=(0,0),buttons=(0,0,0)))
                    elif wt=="wheel": pygame.event.post(pygame.event.Event(pygame.MOUSEWHEEL,x=0,y=wi.get("y",0)))
                    elif wt=="keydown":
                        key=_web_keymap(wi)
                        if key: pygame.event.post(pygame.event.Event(pygame.KEYDOWN,key=key,unicode=wi.get("key",""),mod=0))
                    elif wt=="keyup":
                        key=_web_keymap(wi)
                        if key: pygame.event.post(pygame.event.Event(pygame.KEYUP,key=key,mod=0))
                except (KeyError,ValueError,TypeError): pass

        for _raw_ev in pygame.event.get():
            if hasattr(_raw_ev,'pos'):
                _mapped_pos = _screen_to_game(_raw_ev.pos)
                ev = pygame.event.Event(_raw_ev.type, **{**_raw_ev.__dict__, 'pos': _mapped_pos})
            else: ev = _raw_ev

            if ev.type == pygame.QUIT: running = False
            if ev.type == pygame.MOUSEMOTION:
                if update_btn: update_btn.handle_event(ev)
                if dismiss_btn: dismiss_btn.handle_event(ev)

            if ev.type == pygame.KEYDOWN:
                if ev.key == pygame.K_F11:
                    fullscreen = not fullscreen
                    if fullscreen:
                        # Fullscreen at the chosen render resolution (or native if "Native")
                        if current_resolution_label == "Native":
                            screen = pygame.display.set_mode((0,0), pygame.FULLSCREEN)
                        else:
                            screen = pygame.display.set_mode((current_render_w, current_render_h), pygame.FULLSCREEN)
                    else:
                        # Windowed: use chosen resolution, or auto-size if Native
                        if current_resolution_label == "Native":
                            info=pygame.display.Info(); mon_w,mon_h=info.current_w,info.current_h
                            win_w=int(mon_w*0.9); win_h=int(win_w*HEIGHT/WIDTH)
                            if win_h>int(mon_h*0.9): win_h=int(mon_h*0.9); win_w=int(win_h*WIDTH/HEIGHT)
                            screen = pygame.display.set_mode((win_w,win_h), pygame.RESIZABLE)
                        else:
                            screen = pygame.display.set_mode((current_render_w, current_render_h), pygame.RESIZABLE)
                elif ev.key == pygame.K_ESCAPE:
                    if update_progress and update_progress.get("phase")=="error": update_progress = None
                    elif state=="playing" and game_over_shown: pass
                    elif state=="playing" and gather_dialog: gather_dialog=False; gather_slider=None; gather_confirm=None; gather_cancel=None
                    elif state=="playing" and expand_send_dialog: expand_send_dialog=False; expand_src=None; expand_send_slider=None; expand_send_confirm=None; expand_send_cancel=None
                    elif state=="playing" and expand_mode: expand_mode=None; expand_src=None; flash("Expand cancelled")
                    elif state=="login": running=False
                    elif state=="main_menu": running=False
                    elif state in ("play","stats","leaderboard","friends","notifications"):
                        state="main_menu"; flash("Returned to main menu")
                    elif state in ("local_setup","online_setup","spectate_setup","game_browser","online_create"):
                        state="play"; flash("Back")
                    elif state in ("settings","joined_games","game_lobby","rules"):
                        state="main_menu"; mode=None; game=None; flash("Returned to main menu")
                    elif state=="choose_start":
                        if mode=="local": state="play"; game=None; mode=None
                        else: state="game_browser"
                        flash("Cancelled")
                    elif state=="playing":
                        if player_is_spectating: do_leave_game()
                        else: state="main_menu"; game=None; mode=None; flash("Returning to main menu")
                else:
                    any_input_active = any(input_active.values())
                    if state=="playing" and mode!="spectate" and not any_input_active and not gather_dialog and not expand_send_dialog and not game_over_shown and not player_is_spectating:
                        if ev.key==pygame.K_1: do_action("PEACE",{}); continue
                        elif ev.key==pygame.K_2: expand_mode="source"; flash("Click your source country"); continue
                        elif ev.key==pygame.K_4: do_action("NOTHING",{}); continue
                    if state=="playing" and (mode=="spectate" or player_is_spectating):
                        if ev.key in (pygame.K_EQUALS,pygame.K_PLUS,pygame.K_KP_PLUS): spectate_tps=min(120,spectate_tps+5); flash(f"Speed: {spectate_tps} TPS")
                        elif ev.key in (pygame.K_MINUS,pygame.K_KP_MINUS): spectate_tps=max(2,spectate_tps-5); flash(f"Speed: {spectate_tps} TPS")
                        elif ev.key==pygame.K_SPACE: spectate_tps=TPS if spectate_tps!=TPS else 60; flash(f"Speed: {'Normal' if spectate_tps==TPS else 'Fast'}")
                    handle_key_input(ev)
                    if ev.key == pygame.K_RETURN:
                        if state=="choose_start" and input_active.get("starting_country"):
                            name_in = user_inputs.get("starting_country","").strip()
                            if not name_in: flash("Please type a country name.")
                            else:
                                found = find_country_by_name(local_countries,name_in)
                                if not found: flash("No country matched.");
                                else: do_start_claim(found["id"])
                        elif state=="playing" and expand_mode=="target" and expand_src:
                            target_key = "move_target" if mode=="online" else "starting_country"
                            name_in = user_inputs.get(target_key,"").strip()
                            if not name_in: flash("Type the target country name.")
                            else:
                                tgt = find_country_by_name(local_countries,name_in)
                                if not tgt: flash("No country matched.")
                                else:
                                    src_c = local_countries.get(expand_src)
                                    if not src_c: flash("Source lost.")
                                    else:
                                        adj = next((a for a in src_c.get("adj",[]) if a["to"]==tgt["id"]),None)
                                        if not adj: flash("Target not adjacent.")
                                        else:
                                            if mode=="local": available=int(src_c.get("troops",0))
                                            else:
                                                snap=get_snapshot(); rc=snap["countries"].get(expand_src,{}); available=int(rc.get("troops",0))
                                            max_send=max(1,available-1); expand_send_dialog=True
                                            rect=(WIDTH//2-260*U,HEIGHT//2-20*U,520*U,36*U)
                                            expand_send_slider=Slider(rect,1,max_send,min(max_send,1))
                                            expand_send_confirm=Button((WIDTH//2+140*U,HEIGHT//2+28*U,120*U,36*U),"Send",font,bg=(50,170,110))
                                            expand_send_cancel=Button((WIDTH//2-260*U,HEIGHT//2+28*U,120*U,36*U),"Cancel",font,bg=(150,60,60))
                        elif gather_dialog and gather_slider:
                            do_action("GATHER",{"buy":gather_slider.value}); gather_dialog=False; gather_slider=None; gather_confirm=None; gather_cancel=None
                        elif expand_send_dialog and expand_send_slider and expand_src:
                            send_amt=expand_send_slider.value; target_key="move_target" if mode=="online" else "starting_country"
                            tgt_name=user_inputs.get(target_key,"").strip(); tgt=find_country_by_name(local_countries,tgt_name)
                            if not tgt: flash("Target missing.")
                            else:
                                src_c=local_countries.get(expand_src)
                                if not src_c: flash("Source lost.")
                                else:
                                    adj=next((a for a in src_c.get("adj",[]) if a["to"]==tgt["id"]),None)
                                    if not adj: flash("Not adjacent")
                                    else: do_action("EXPAND",{"src":expand_src,"tgt":tgt["id"],"send":send_amt,"cross_cost":int(adj.get("cost",0) or 0)})
                            expand_send_dialog=False; expand_src=None; user_inputs[target_key]=""; expand_send_slider=None; expand_send_confirm=None; expand_send_cancel=None

            if ev.type == pygame.MOUSEWHEEL and state in ("playing", "choose_start"):
                mx,my = _screen_to_game(pygame.mouse.get_pos()); factor = CAMERA_ZOOM_FACTOR**ev.y
                new_scale = max(MIN_CAMERA_SCALE, min(MAX_CAMERA_SCALE, cam_target_scale*factor))
                world_x_before = cam_x+mx/cam_scale; world_y_before = cam_y+my/cam_scale
                cam_target_scale=new_scale; cam_target_x=world_x_before-mx/cam_target_scale; cam_target_y=world_y_before-my/cam_target_scale
                cam_x=cam_target_x; cam_y=cam_target_y; cam_scale=cam_target_scale

            if ev.type==pygame.MOUSEBUTTONDOWN and ev.button in (2,3) and state in ("playing", "choose_start"): dragging_pan=True; pan_start=ev.pos; cam_start=(cam_x,cam_y); _last_pan_delta=(0,0)
            if ev.type==pygame.MOUSEBUTTONUP and ev.button in (2,3):
                dragging_pan=False
                # Set inertia velocity based on last mouse delta
                if _last_pan_delta and dt > 0:
                    cam_vel_x = -_last_pan_delta[0] / cam_scale / dt
                    cam_vel_y = -_last_pan_delta[1] / cam_scale / dt
            if ev.type==pygame.MOUSEMOTION and dragging_pan:
                dx=(ev.pos[0]-pan_start[0])/cam_scale; dy=(ev.pos[1]-pan_start[1])/cam_scale; cam_x=cam_start[0]-dx; cam_y=cam_start[1]-dy
                _last_pan_delta=(ev.pos[0]-pan_start[0], ev.pos[1]-pan_start[1])

            if ev.type==pygame.MOUSEMOTION and state=="playing" and not dragging_pan:
                mx,my=ev.pos
                if my<MAP_H: wx=cam_x+mx/cam_scale; wy=cam_y+my/cam_scale; hovered_country=country_at_world_point(wx,wy)
                else: hovered_country=None
            if ev.type==pygame.MOUSEMOTION:
                _input_hover_key=None
                for k,r in small_input_rects.items():
                    if r.collidepoint(ev.pos): _input_hover_key=k; break
            if ev.type==pygame.MOUSEBUTTONDOWN and ev.button==1:
                for k,r in small_input_rects.items():
                    if r.collidepoint(ev.pos):
                        for kk in input_active: input_active[kk]=False
                        input_active[k]=True; break

            # ---- State-specific events ----
            if state == "login":
                btn_login_submit.handle_event(ev); btn_login_toggle.handle_event(ev)
                if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                    if btn_login_submit.rect.collidepoint(ev.pos):
                        _lu = user_inputs.get("login_user", "").strip()
                        _lp = user_inputs.get("login_pass", "")
                        if not _lu or not _lp:
                            flash("Please enter both username and password.")
                        elif auth_manager:
                            try:
                                if login_mode == "register":
                                    auth_manager.register(_lu, _lp)
                                else:
                                    auth_manager.login(_lu, _lp)
                                logged_in_username = auth_manager.username
                                user_inputs["player_name"] = logged_in_username
                                state = "main_menu"
                                flash(f"Welcome, {logged_in_username}!")
                            except AuthError as ae:
                                flash(str(ae))
                            except Exception as ae:
                                flash(f"Error: {ae}")
                        else:
                            flash("Firebase not available. Cannot log in.")
                    elif btn_login_toggle.rect.collidepoint(ev.pos):
                        if login_mode == "login":
                            login_mode = "register"
                            btn_login_submit.text = "Register"
                            btn_login_toggle.text = "Already have an account? Log In"
                        else:
                            login_mode = "login"
                            btn_login_submit.text = "Log In"
                            btn_login_toggle.text = "Don't have an account? Register"
                if ev.type == pygame.KEYDOWN and ev.key == pygame.K_TAB:
                    if input_active.get("login_user"):
                        for kk in input_active: input_active[kk] = False
                        input_active["login_pass"] = True
                    elif input_active.get("login_pass"):
                        for kk in input_active: input_active[kk] = False
                        input_active["login_user"] = True
                if ev.type == pygame.KEYDOWN and ev.key == pygame.K_RETURN:
                    if any(input_active.get(k) for k in ("login_user", "login_pass")):
                        _lu = user_inputs.get("login_user", "").strip()
                        _lp = user_inputs.get("login_pass", "")
                        if not _lu or not _lp:
                            flash("Please enter both username and password.")
                        elif auth_manager:
                            try:
                                if login_mode == "register":
                                    auth_manager.register(_lu, _lp)
                                else:
                                    auth_manager.login(_lu, _lp)
                                logged_in_username = auth_manager.username
                                user_inputs["player_name"] = logged_in_username
                                state = "main_menu"
                                flash(f"Welcome, {logged_in_username}!")
                            except AuthError as ae:
                                flash(str(ae))
                            except Exception as ae:
                                flash(f"Error: {ae}")

            elif state == "main_menu":
                btn_play.handle_event(ev); btn_mygames.handle_event(ev); btn_stats.handle_event(ev)
                btn_rules.handle_event(ev); btn_settings.handle_event(ev); btn_quit_main.handle_event(ev); btn_logout.handle_event(ev)
                btn_leaderboard.handle_event(ev); btn_friends.handle_event(ev); btn_notifications.handle_event(ev)
                if ev.type==pygame.MOUSEBUTTONDOWN and ev.button==1:
                    if btn_logout.rect.collidepoint(ev.pos):
                        if auth_manager:
                            auth_manager.logout()
                        logged_in_username = None
                        fc = None; remote = None
                        user_inputs["login_user"] = ""; user_inputs["login_pass"] = ""
                        for kk in input_active: input_active[kk] = False
                        input_active["login_user"] = True
                        state = "login"; flash("Logged out.")
                    elif btn_play.rect.collidepoint(ev.pos): state="play"
                    elif btn_mygames.rect.collidepoint(ev.pos):
                        if fc is None:
                            ok = init_online()
                            if not ok: flash("Could not connect to server."); continue
                        state="joined_games"
                    elif btn_stats.rect.collidepoint(ev.pos):
                        if fc is None:
                            ok = init_online()
                            if not ok: flash("Could not connect to server."); continue
                        try: player_stats_cache = fc.get_player_stats()
                        except Exception as e: player_stats_cache = {}; flash(f"Could not load stats: {e}")
                        state="stats"
                    elif btn_leaderboard.rect.collidepoint(ev.pos):
                        if fc is None:
                            ok = init_online()
                            if not ok: flash("Could not connect to server."); continue
                        try: leaderboard_cache = fc.get_leaderboard()
                        except Exception as e: leaderboard_cache = []; flash(f"Could not load leaderboard: {e}")
                        leaderboard_scroll_y = 0; state="leaderboard"
                    elif btn_friends.rect.collidepoint(ev.pos):
                        if fc is None:
                            ok = init_online()
                            if not ok: flash("Could not connect to server."); continue
                        try: friends_cache = fc.get_friends()
                        except Exception as e: friends_cache = []; flash(f"Could not load friends: {e}")
                        friends_scroll_y = 0; friend_add_input = ""; friend_add_active = False; state="friends"
                    elif btn_notifications.rect.collidepoint(ev.pos):
                        if fc is None:
                            ok = init_online()
                            if not ok: flash("Could not connect to server."); continue
                        try: notifications_cache = fc.get_notifications()
                        except Exception as e: notifications_cache = []; flash(f"Could not load notifications: {e}")
                        notif_scroll_y = 0; state="notifications"
                    elif btn_rules.rect.collidepoint(ev.pos): state="rules"; rules_current_tab="general"; rules_scroll_y=0
                    elif btn_settings.rect.collidepoint(ev.pos): state="settings"; settings_tab="Graphics"
                    elif btn_quit_main.rect.collidepoint(ev.pos): running=False

            elif state == "play":
                btn_play_offline.handle_event(ev); btn_play_online.handle_event(ev); btn_play_spectate.handle_event(ev); btn_play_back.handle_event(ev)
                if ev.type==pygame.MOUSEBUTTONDOWN and ev.button==1:
                    if btn_play_offline.rect.collidepoint(ev.pos): state="local_setup"; mode="local"; input_active["player_name"]=True
                    elif btn_play_online.rect.collidepoint(ev.pos):
                        mode="online"
                        if fc is None:
                            ok=init_online()
                            if not ok: mode=None; continue
                        state="game_browser"; last_browser_refresh=0
                    elif btn_play_spectate.rect.collidepoint(ev.pos): state="spectate_setup"; mode="spectate"
                    elif btn_play_back.rect.collidepoint(ev.pos): state="main_menu"

            elif state == "stats":
                btn_stats_back.handle_event(ev)
                if ev.type==pygame.MOUSEBUTTONDOWN and ev.button==1:
                    if btn_stats_back.rect.collidepoint(ev.pos): state="main_menu"

            elif state == "leaderboard":
                btn_lb_back.handle_event(ev)
                if ev.type==pygame.MOUSEBUTTONDOWN and ev.button==1:
                    if btn_lb_back.rect.collidepoint(ev.pos): state="main_menu"
                if ev.type==pygame.MOUSEWHEEL:
                    leaderboard_scroll_y = max(0, leaderboard_scroll_y - ev.y * 50*U)

            elif state == "friends":
                btn_friends_back.handle_event(ev); btn_friends_add.handle_event(ev); btn_friends_send.handle_event(ev)
                if ev.type==pygame.MOUSEBUTTONDOWN and ev.button==1:
                    # Check if clicking the friend add input box
                    _add_r = pygame.Rect(WIDTH//2-200*U, 80*U, 330*U, 36*U)
                    if btn_friends_back.rect.collidepoint(ev.pos): state="main_menu"
                    elif _add_r.collidepoint(ev.pos) or btn_friends_add.rect.collidepoint(ev.pos):
                        friend_add_active = True
                    elif btn_friends_send.rect.collidepoint(ev.pos) and friend_add_input.strip():
                        if fc:
                            ok, msg = fc.send_friend_request(friend_add_input.strip())
                            flash(msg); friend_add_input = ""; friend_add_active = False
                            if ok:
                                try: friends_cache = fc.get_friends()
                                except: pass
                    else:
                        # Check accept / remove buttons per friend row
                        for fi, fr in enumerate(friends_cache):
                            fy = 140*U + fi * 56*U - friends_scroll_y
                            if fy < 120*U or fy > HEIGHT - 80*U: continue
                            if fr.get("status") == "pending_received":
                                acc_r = pygame.Rect(WIDTH//2+100*U, int(fy)+6*U, 90*U, 32*U)
                                dec_r = pygame.Rect(WIDTH//2+200*U, int(fy)+6*U, 90*U, 32*U)
                                if acc_r.collidepoint(ev.pos) and fc:
                                    ok, msg = fc.accept_friend_request(fr["uid"]); flash(msg)
                                    try: friends_cache = fc.get_friends()
                                    except: pass
                                    break
                                elif dec_r.collidepoint(ev.pos) and fc:
                                    ok, msg = fc.remove_friend(fr["uid"]); flash(msg)
                                    try: friends_cache = fc.get_friends()
                                    except: pass
                                    break
                            elif fr.get("status") == "accepted":
                                rem_r = pygame.Rect(WIDTH//2+200*U, int(fy)+6*U, 90*U, 32*U)
                                inv_r = pygame.Rect(WIDTH//2+100*U, int(fy)+6*U, 90*U, 32*U)
                                if rem_r.collidepoint(ev.pos) and fc:
                                    ok, msg = fc.remove_friend(fr["uid"]); flash(msg)
                                    try: friends_cache = fc.get_friends()
                                    except: pass
                                    break
                                elif inv_r.collidepoint(ev.pos) and fc and current_game_id:
                                    ok = fc.invite_friend_to_game(fr["uid"], current_game_id)
                                    flash(f"Invited {fr['username']}" if ok else "Failed to invite")
                                    break
                if ev.type==pygame.MOUSEWHEEL:
                    friends_scroll_y = max(0, friends_scroll_y - ev.y * 50*U)
                if ev.type==pygame.KEYDOWN and friend_add_active:
                    if ev.key == pygame.K_RETURN and friend_add_input.strip():
                        if fc:
                            ok, msg = fc.send_friend_request(friend_add_input.strip())
                            flash(msg); friend_add_input = ""; friend_add_active = False
                            if ok:
                                try: friends_cache = fc.get_friends()
                                except: pass
                    elif ev.key == pygame.K_BACKSPACE:
                        friend_add_input = friend_add_input[:-1]
                    elif ev.key == pygame.K_ESCAPE:
                        friend_add_active = False
                    elif ev.unicode and ev.unicode.isprintable() and len(friend_add_input) < 20:
                        friend_add_input += ev.unicode

            elif state == "notifications":
                btn_notif_back.handle_event(ev); btn_notif_refresh.handle_event(ev)
                if ev.type==pygame.MOUSEBUTTONDOWN and ev.button==1:
                    if btn_notif_back.rect.collidepoint(ev.pos): state="main_menu"
                    elif btn_notif_refresh.rect.collidepoint(ev.pos):
                        if fc:
                            try: notifications_cache = fc.get_notifications()
                            except: pass
                    else:
                        # Check action buttons per notification
                        for ni, notif in enumerate(notifications_cache):
                            ny = 130*U + ni * 60*U - notif_scroll_y
                            if ny < 110*U or ny > HEIGHT - 80*U: continue
                            if notif.get("type") == "game_invite":
                                join_r = pygame.Rect(WIDTH//2+180*U, int(ny)+8*U, 90*U, 32*U)
                                if join_r.collidepoint(ev.pos) and fc:
                                    gid = notif.get("game_id","")
                                    pname = user_inputs.get("player_name","Player").strip() or "Player"
                                    try:
                                        doc = fc.create_or_open_game(gid, pname)
                                        if doc and isinstance(doc, dict):
                                            current_game_id = gid; my_player_name = pname
                                            remote = RemoteGameView(); remote.update_from_doc(doc)
                                            fc.listen_to_game(gid, lambda d: remote.update_from_doc(d))
                                            joined_games[gid] = {"player_name": pname, "remote": remote, "player_password": "", "room_password": ""}
                                            _save_joined_games(); mode = "online"; state = "game_lobby"
                                            fc.mark_notification_read(notif["id"])
                                            flash(f"Joined game {gid}")
                                    except Exception as e: flash(f"Failed: {e}")
                                    break
                            dismiss_r = pygame.Rect(WIDTH//2+280*U, int(ny)+8*U, 70*U, 32*U)
                            if dismiss_r.collidepoint(ev.pos) and fc:
                                fc.mark_notification_read(notif["id"])
                                notifications_cache = [n for n in notifications_cache if n["id"] != notif["id"]]
                                break
                if ev.type==pygame.MOUSEWHEEL:
                    notif_scroll_y = max(0, notif_scroll_y - ev.y * 50*U)

            elif state == "rules":
                btn_rules_back.handle_event(ev); btn_rules_general.handle_event(ev); btn_rules_classic.handle_event(ev); btn_rules_tournament.handle_event(ev); btn_rules_challenge.handle_event(ev)
                if ev.type==pygame.MOUSEBUTTONDOWN and ev.button==1:
                    if btn_rules_back.rect.collidepoint(ev.pos): state="main_menu"
                    elif btn_rules_general.rect.collidepoint(ev.pos): rules_current_tab="general"; rules_scroll_y=0
                    elif btn_rules_classic.rect.collidepoint(ev.pos): rules_current_tab="classic"; rules_scroll_y=0
                    elif btn_rules_tournament.rect.collidepoint(ev.pos): rules_current_tab="tournament"; rules_scroll_y=0
                    elif btn_rules_challenge.rect.collidepoint(ev.pos): rules_current_tab="challenge"; rules_scroll_y=0
                if ev.type==pygame.MOUSEWHEEL:
                    rules_scroll_y = max(0, rules_scroll_y - ev.y * 50*U)
                if ev.type==pygame.KEYDOWN:
                    if ev.key==pygame.K_UP: rules_scroll_y = max(0, rules_scroll_y - 50*U)
                    elif ev.key==pygame.K_DOWN: rules_scroll_y += 50*U

            elif state == "game_browser":
                btn_browser_back.handle_event(ev); btn_browser_refresh.handle_event(ev); btn_join_code.handle_event(ev); btn_create_new_game.handle_event(ev)
                if ev.type==pygame.MOUSEBUTTONDOWN and ev.button==1:
                    if btn_browser_back.rect.collidepoint(ev.pos): state="play"
                    elif btn_browser_refresh.rect.collidepoint(ev.pos): last_browser_refresh=0
                    elif btn_join_code.rect.collidepoint(ev.pos): flash("Join by code feature coming soon")
                    elif btn_create_new_game.rect.collidepoint(ev.pos): state="online_create"
                    elif public_games_list:
                        header_y = 130*U
                        for gi, game_info in enumerate(public_games_list):
                            row_y = header_y + 40*U + gi * 50*U - browser_scroll_y
                            join_r = pygame.Rect(820*U, int(row_y)-4*U, 90*U, 32*U)
                            if join_r.collidepoint(ev.pos):
                                gid = game_info.get("id","")
                                pname = user_inputs.get("player_name","Player").strip() or "Player"
                                if fc and gid:
                                    try:
                                        doc = fc.create_or_open_game(gid, pname)
                                        if doc and isinstance(doc, dict):
                                            current_game_id = gid; my_player_name = pname
                                            remote = RemoteGameView(); remote.update_from_doc(doc)
                                            fc.listen_to_game(gid, lambda d: remote.update_from_doc(d))
                                            joined_games[gid] = {"player_name": pname, "remote": remote, "player_password": "", "room_password": ""}
                                            _save_joined_games(); mode = "online"
                                            game_status = doc.get("status", "waiting")
                                            has_country = any(v.get("owner")==pname for v in (doc.get("countries") or {}).values())
                                            if has_country: state="playing"; flash(f"Joined '{gid}'")
                                            elif game_status=="playing": state="choose_start"; flash("Choose your starting country.")
                                            else: state="game_lobby"; flash(f"Joined lobby for '{gid}'")
                                    except Exception as e: flash(f"Failed to join: {e}")
                                break
                if ev.type==pygame.MOUSEWHEEL:
                    browser_scroll_y = max(0, browser_scroll_y - ev.y * 50*U)

            elif state == "online_create":
                btn_mode_classic.handle_event(ev); btn_mode_tournament.handle_event(ev); btn_mode_challenge.handle_event(ev)
                btn_scope_world.handle_event(ev); btn_scope_europe.handle_event(ev); btn_scope_asia.handle_event(ev)
                btn_private_toggle.handle_event(ev); btn_create_game.handle_event(ev); btn_create_back.handle_event(ev)
                if ev.type==pygame.MOUSEBUTTONDOWN and ev.button==1:
                    if btn_mode_classic.rect.collidepoint(ev.pos): current_game_mode="classic"
                    elif btn_mode_tournament.rect.collidepoint(ev.pos): current_game_mode="tournament"
                    elif btn_mode_challenge.rect.collidepoint(ev.pos): current_game_mode="challenge"
                    elif btn_scope_world.rect.collidepoint(ev.pos): current_map_scope="world"
                    elif btn_scope_europe.rect.collidepoint(ev.pos): current_map_scope="europe"
                    elif btn_scope_asia.rect.collidepoint(ev.pos): current_map_scope="asia"
                    elif btn_private_toggle.rect.collidepoint(ev.pos): is_private_game=not is_private_game
                    elif btn_create_back.rect.collidepoint(ev.pos): state="play"
                    elif btn_create_game.rect.collidepoint(ev.pos):
                        pname=user_inputs.get("player_name","Player").strip() or "Player"
                        if fc:
                            try:
                                result=fc.create_or_open_game(current_game_mode+"_"+current_map_scope, pname, is_private=is_private_game)
                                if result and isinstance(result, dict):
                                    current_game_id=result.get("game_id"); my_player_name=pname; remote=RemoteGameView()
                                    remote.update_from_doc(result); mode="online"; state="game_lobby"
                                    joined_games[current_game_id] = {
                                        "player_name": my_player_name, "remote": remote,
                                        "player_password": "", "room_password": "",
                                    }
                                    _save_joined_games()
                                    fc.listen_to_game(current_game_id, lambda d: remote.update_from_doc(d))
                                    flash(f"Game created: {current_game_mode} {current_map_scope}")
                            except Exception as e: flash(f"Game creation failed: {e}")
                        else: flash("Not connected to server")

            elif state == "settings":
                btn_fps_60.handle_event(ev); btn_fps_120.handle_event(ev); btn_fps_240.handle_event(ev); btn_settings_back.handle_event(ev)
                btn_tab_graphics.handle_event(ev); btn_tab_audio.handle_event(ev); btn_tab_controls.handle_event(ev)
                music_slider.handle_event(ev); sfx_slider.handle_event(ev)
                for _rb, _, _, _ in btn_resolutions: _rb.handle_event(ev)
                if ev.type==pygame.MOUSEBUTTONDOWN and ev.button==1:
                    if btn_tab_graphics.rect.collidepoint(ev.pos): settings_tab="Graphics"
                    elif btn_tab_audio.rect.collidepoint(ev.pos): settings_tab="Audio"
                    elif btn_tab_controls.rect.collidepoint(ev.pos): settings_tab="Controls"
                    elif btn_fps_60.rect.collidepoint(ev.pos):
                        RENDER_FPS=60; flash("Set to 60 FPS"); config["render_fps"]=60; save_config(config)
                    elif btn_fps_120.rect.collidepoint(ev.pos):
                        RENDER_FPS=120; flash("Set to 120 FPS"); config["render_fps"]=120; save_config(config)
                    elif btn_fps_240.rect.collidepoint(ev.pos):
                        RENDER_FPS=240; flash("Set to 240 FPS"); config["render_fps"]=240; save_config(config)
                    elif btn_settings_back.rect.collidepoint(ev.pos): state="main_menu"
                    else:
                        for _rb, rw, rh, rlabel in btn_resolutions:
                            if _rb.rect.collidepoint(ev.pos):
                                current_resolution_label = rlabel
                                current_render_w = rw
                                current_render_h = rh
                                config["resolution"] = rlabel; save_config(config)
                                if not _web_mode:
                                    if rlabel == "Native":
                                        # Reset to auto window size
                                        if not fullscreen:
                                            info=pygame.display.Info(); mon_w,mon_h=info.current_w,info.current_h
                                            win_w=int(mon_w*0.9); win_h=int(win_w*HEIGHT/WIDTH)
                                            if win_h>int(mon_h*0.9): win_h=int(mon_h*0.9); win_w=int(win_h*WIDTH/HEIGHT)
                                            screen=pygame.display.set_mode((win_w,win_h),pygame.RESIZABLE)
                                        else:
                                            screen=pygame.display.set_mode((0,0),pygame.FULLSCREEN)
                                        flash("Resolution: Native")
                                    else:
                                        if fullscreen:
                                            screen=pygame.display.set_mode((rw,rh),pygame.FULLSCREEN)
                                        else:
                                            screen=pygame.display.set_mode((rw,rh),pygame.RESIZABLE)
                                        flash(f"Resolution: {rlabel} ({rw}x{rh})")
                                break
                # Update audio volumes when sliders change
                if music_slider.value != int(float(config.get("music_volume", DEFAULT_MUSIC_VOLUME)) * 100):
                    config["music_volume"] = music_slider.value / 100.0
                    if audio: audio.set_music_volume(config["music_volume"])
                    save_config(config)
                if sfx_slider.value != int(float(config.get("sfx_volume", DEFAULT_SFX_VOLUME)) * 100):
                    config["sfx_volume"] = sfx_slider.value / 100.0
                    if audio: audio.set_sfx_volume(config["sfx_volume"])
                    save_config(config)

            elif state == "spectate_setup":
                spectate_slider.handle_event(ev); btn_start_spectate.handle_event(ev)
                if ev.type==pygame.MOUSEBUTTONDOWN and ev.button==1:
                    if btn_start_spectate.rect.collidepoint(ev.pos):
                        start_spectate_game(spectate_slider.value); state="playing"; flash(f"Watching {spectate_slider.value} bots!")

            elif state == "local_setup":
                bot_slider.handle_event(ev); btn_start_local.handle_event(ev)
                if ev.type==pygame.MOUSEBUTTONDOWN and ev.button==1:
                    if btn_start_local.rect.collidepoint(ev.pos):
                        pname = user_inputs.get("player_name","Player").strip() or "Player"
                        start_local_game(pname, bot_slider.value); state="game_lobby"
                        flash("Game lobby. Press Start Game when ready.")

            elif state == "online_setup":
                if ev.type==pygame.MOUSEBUTTONDOWN and ev.button==1:
                    mx,my=ev.pos
                    create_rect=pygame.Rect(WIDTH//2-260*U,400*U,240*U,56*U); join_rect=pygame.Rect(WIDTH//2+20*U,400*U,240*U,56*U)
                    if create_rect.collidepoint((mx,my)) and not network_loading:
                        gid=user_inputs["game_id"].strip(); pname=user_inputs["player_name"].strip()
                        if not gid or not pname: flash("Provide Game ID and Player name")
                        else:
                            network_loading=True; game_id_in_progress=gid; player_name_in_progress=pname
                            player_pass=user_inputs.get("player_password","").strip(); room_pass=user_inputs.get("room_password","").strip()
                            def _create_worker():
                                nonlocal network_result
                                try: network_result=fc.create_or_open_game(game_id_in_progress,player_name_in_progress,player_password=player_pass,room_password=room_pass)
                                except Exception as e: network_result=e
                            network_thread=threading.Thread(target=_create_worker,daemon=True); network_thread.start()
                    elif join_rect.collidepoint((mx,my)) and not network_loading:
                        gid=user_inputs["game_id"].strip(); pname=user_inputs["player_name"].strip()
                        if not gid or not pname: flash("Provide Game ID and Player name")
                        else:
                            network_loading=True; game_id_in_progress=gid; player_name_in_progress=pname
                            player_pass=user_inputs.get("player_password","").strip(); room_pass=user_inputs.get("room_password","").strip()
                            def _join_worker():
                                nonlocal network_result
                                try: network_result=fc.create_or_open_game(game_id_in_progress,player_name_in_progress,player_password=player_pass,room_password=room_pass)
                                except Exception as e: network_result=e
                            network_thread=threading.Thread(target=_join_worker,daemon=True); network_thread.start()
                    if update_btn and update_btn.rect.collidepoint((mx,my)):
                        try:
                            updater_path=os.path.join(BASE_DIR,"updater.py")
                            if sys.platform=="win32": subprocess.Popen([sys.executable,updater_path],creationflags=subprocess.CREATE_NEW_CONSOLE)
                            else: subprocess.Popen([sys.executable,updater_path])
                            flash("Updater launched!")
                        except OSError as e: flash(f"Failed to launch updater: {e}")
                    elif dismiss_btn and dismiss_btn.rect.collidepoint((mx,my)): update_info=None; update_btn=None; dismiss_btn=None

            elif state == "game_lobby":
                btn_lobby_start.handle_event(ev); btn_lobby_back.handle_event(ev)
                btn_plimit_minus.handle_event(ev); btn_plimit_plus.handle_event(ev)
                if ev.type==pygame.MOUSEBUTTONDOWN and ev.button==1:
                    mx,my=ev.pos
                    # Player limit +/- (host only)
                    _is_lobby_host = False
                    if mode == "local" and game:
                        _is_lobby_host = True
                    elif mode == "online" and remote:
                        _rsnap = remote.snapshot()
                        _rplayers = _rsnap.get("players", [])
                        if _rplayers and _rplayers[0].get("name") == my_player_name:
                            _is_lobby_host = True
                    if _is_lobby_host:
                        if btn_plimit_minus.rect.collidepoint((mx,my)):
                            if mode == "local" and game:
                                game.player_limit = max(0, game.player_limit - 1)
                                lv = game.player_limit
                                flash(f"Player limit: {'None' if lv == 0 else lv}")
                        elif btn_plimit_plus.rect.collidepoint((mx,my)):
                            if mode == "local" and game:
                                game.player_limit = min(16, game.player_limit + 1)
                                lv = game.player_limit
                                flash(f"Player limit: {lv}")
                    if btn_lobby_back.rect.collidepoint((mx,my)):
                        state="main_menu"; game=None; mode=None; flash("Left lobby")
                    elif btn_lobby_start.rect.collidepoint((mx,my)):
                        if mode == "local" and game:
                            human = game.players[0] if game.players else None
                            if human and human.name == game.host_name:
                                game.started=True; state="choose_start"
                                for kk in input_active: input_active[kk]=False
                                input_active["starting_country"]=True; user_inputs["starting_country"]=""
                                flash("Game started! Choose your starting country.")
                            else: flash("Only the host can start.")
                        elif mode == "online" and fc and current_game_id:
                            # Online: update game status on server
                            try:
                                from firebase_sync import _update_doc
                                _update_doc(fc._auth, current_game_id, {"status": "playing"}, ["status"])
                                state = "choose_start"
                                for kk in input_active: input_active[kk]=False
                                input_active["starting_country"]=True; user_inputs["starting_country"]=""
                                flash("Game started! Choose your starting country.")
                            except (AttributeError, RuntimeError, OSError) as e:
                                flash(f"Failed to start: {e}")
                    # Kick buttons (host only, local mode)
                    if mode == "local" and game and game.host_name:
                        for i, pl in enumerate(game.players):
                            if pl.name != game.host_name and not pl.is_bot:
                                kick_r = pygame.Rect(WIDTH//2+180*U, 170*U+i*56*U+10*U, 80*U, 28*U)
                                if kick_r.collidepoint((mx,my)):
                                    human = game.players[0] if game.players else None
                                    if human and human.name == game.host_name:
                                        game.kick_player(human.name, pl.name)

            elif state == "joined_games":
                btn_mygames_back.handle_event(ev)
                if ev.type==pygame.MOUSEWHEEL:
                    joined_games_scroll_y = max(0, joined_games_scroll_y - ev.y * 50*U)
                if ev.type==pygame.MOUSEBUTTONDOWN and ev.button==1:
                    mx,my=ev.pos
                    if btn_mygames_back.rect.collidepoint((mx,my)): state="main_menu"
                    # Handle enter/leave buttons for each joined game
                    _jg_list = list(joined_games.items())
                    for gi, (gid, ginfo) in enumerate(_jg_list):
                        row_y = 160*U + gi * 70*U - joined_games_scroll_y
                        if row_y < 140*U or row_y > HEIGHT - 80*U: continue
                        enter_r = pygame.Rect(WIDTH//2+100*U, row_y+12*U, 100*U, 36*U)
                        leave_r = pygame.Rect(WIDTH//2+210*U, row_y+12*U, 100*U, 36*U)
                        if enter_r.collidepoint((mx, my)):
                            # Re-enter this game — reconnect if needed
                            mode = "online"
                            if fc is None:
                                ok = init_online()
                                if not ok: mode=None; flash("Firebase not available."); continue
                            current_game_id = gid; my_player_name = ginfo.get("player_name") or logged_in_username or "Player"
                            _rem = ginfo.get("remote")
                            if _rem is None:
                                # Need to reconnect
                                _rem = RemoteGameView()
                                ppass = ginfo.get("player_password", "")
                                rpass = ginfo.get("room_password", "")
                                try:
                                    doc = fc.create_or_open_game(gid, my_player_name, player_password=ppass)
                                    if doc:
                                        fc.listen_to_game(gid, lambda d: _rem.update_from_doc(d))
                                        ginfo["remote"] = _rem; remote = _rem
                                        has_country = any(v.get("owner")==my_player_name for v in (doc.get("countries") or {}).values())
                                        if has_country: state="playing"; flash(f"Re-entering '{gid}'")
                                        else:
                                            game_status = doc.get("status","waiting")
                                            if game_status == "playing":
                                                state="choose_start"; flash("Choose your starting country.")
                                            else:
                                                state="game_lobby"; flash(f"Rejoined lobby for '{gid}'")
                                    else: flash("Failed to reconnect.")
                                except (PermissionError, RuntimeError, OSError) as e:
                                    flash(f"Reconnect failed: {e}")
                            else:
                                # Already connected — check game status from snapshot
                                remote = _rem
                                snap = _rem.snapshot()
                                game_status = snap.get("status", "waiting")
                                pl_list = snap.get("players", [])
                                has_country = any(
                                    v.get("owner") == my_player_name
                                    for v in snap.get("countries", {}).values()
                                )
                                if has_country:
                                    state = "playing"; flash(f"Re-entering '{gid}'")
                                elif game_status == "playing":
                                    state = "choose_start"
                                    for kk in input_active: input_active[kk] = False
                                    input_active["starting_country"] = True; user_inputs["starting_country"] = ""
                                    flash("Choose your starting country.")
                                else:
                                    state = "game_lobby"; flash(f"Returning to lobby for '{gid}'")
                        elif leave_r.collidepoint((mx, my)):
                            joined_games.pop(gid, None)
                            _save_joined_games()
                            flash(f"Left '{gid}'")

            elif state == "choose_start":
                if ev.type==pygame.MOUSEBUTTONDOWN and ev.button==1:
                    mx,my=ev.pos
                    confirm_rect=pygame.Rect(WIDTH//2+20*U,(460 if mode=="local" else 500)*U,160*U,44*U)
                    cancel_rect=pygame.Rect(WIDTH//2-200*U,(460 if mode=="local" else 500)*U,160*U,44*U)
                    if confirm_rect.collidepoint((mx,my)):
                        name_in=user_inputs.get("starting_country","").strip()
                        if not name_in: flash("Please type a country name.")
                        else:
                            found=find_country_by_name(local_countries,name_in)
                            if not found: flash("No country matched.")
                            else: do_start_claim(found["id"])
                    elif cancel_rect.collidepoint((mx,my)):
                        if mode=="local": state="play"; game=None; mode=None
                        else: state="game_browser"; current_game_id=None; my_player_name=None
                        flash("Cancelled.")

            elif state == "playing":
                if game_over_shown:
                    btn_go_leave.handle_event(ev); btn_go_spectate.handle_event(ev)
                    if ev.type==pygame.MOUSEBUTTONDOWN and ev.button==1:
                        mx,my=ev.pos
                        if btn_go_leave.rect.collidepoint((mx,my)): do_leave_game()
                        elif btn_go_spectate.rect.collidepoint((mx,my)): do_spectate_game()
                    continue
                if player_is_spectating:
                    btn_spectator_leave.handle_event(ev)
                    if ev.type==pygame.MOUSEBUTTONDOWN and ev.button==1:
                        if btn_spectator_leave.rect.collidepoint(ev.pos): do_leave_game()
                if gather_dialog and gather_slider:
                    gather_slider.handle_event(ev)
                    if gather_confirm and gather_confirm.handle_event(ev):
                        do_action("GATHER",{"buy":gather_slider.value}); gather_dialog=False; gather_slider=None; gather_confirm=None; gather_cancel=None
                    if gather_cancel and gather_cancel.handle_event(ev):
                        gather_dialog=False; gather_slider=None; gather_confirm=None; gather_cancel=None
                    continue
                if expand_send_dialog and expand_send_slider:
                    expand_send_slider.handle_event(ev)
                    if expand_send_confirm and expand_send_confirm.handle_event(ev):
                        send_amt=expand_send_slider.value; target_key="move_target" if mode=="online" else "starting_country"
                        tgt_name=user_inputs.get(target_key,"").strip(); tgt=find_country_by_name(local_countries,tgt_name)
                        if not tgt or not expand_src: flash("Invalid selection.")
                        else:
                            src_c=local_countries.get(expand_src)
                            if not src_c: flash("Source lost.")
                            else:
                                adj=next((a for a in src_c.get("adj",[]) if a["to"]==tgt["id"]),None)
                                if not adj: flash("Not adjacent")
                                else: do_action("EXPAND",{"src":expand_src,"tgt":tgt["id"],"send":send_amt,"cross_cost":int(adj.get("cost",0) or 0)})
                        expand_send_dialog=False; expand_src=None; user_inputs[target_key]=""; expand_send_slider=None; expand_send_confirm=None; expand_send_cancel=None
                    if expand_send_cancel and expand_send_cancel.handle_event(ev):
                        target_key="move_target" if mode=="online" else "starting_country"
                        expand_send_dialog=False; expand_src=None; user_inputs[target_key]=""; expand_send_slider=None; expand_send_confirm=None; expand_send_cancel=None
                    continue
                if mode=="spectate" or player_is_spectating:
                    if ev.type==pygame.MOUSEBUTTONDOWN and ev.button==1:
                        mx,my=ev.pos; wx=cam_x+mx/cam_scale; wy=cam_y+my/cam_scale
                        clicked=country_at_world_point(wx,wy); selected_country=clicked["id"] if clicked else None
                    continue
                b_peace.handle_event(ev); b_expand.handle_event(ev); b_gather.handle_event(ev); b_nothing.handle_event(ev)
                if ev.type==pygame.MOUSEBUTTONDOWN and ev.button==1:
                    mx,my=ev.pos
                    if b_peace.rect.collidepoint((mx,my)):
                        if not is_my_turn(): flash("Not your turn")
                        else: do_action("PEACE",{})
                    elif b_gather.rect.collidepoint((mx,my)):
                        if not is_my_turn(): flash("Not your turn")
                        else:
                            snap=get_snapshot()
                            if mode=="local" and game:
                                cur=game.players[game.turn_idx]
                                if cur.last_gather_turn!=game.turn_number:
                                    cur.troop_buy_limit=random.randint(1,20); cur.last_gather_turn=game.turn_number
                                    game.log(f"{cur.name} can buy up to {cur.troop_buy_limit} troops (d20).")
                                max_allowed=min(cur.troop_buy_limit,cur.money//TROOP_COST)
                            else:
                                player_money=0
                                for p in snap["players"]:
                                    if p.get("name")==my_player_name: player_money=int(p.get("money",0) or 0)
                                roll=random.randint(1,20); max_allowed=min(roll,player_money//TROOP_COST) if TROOP_COST>0 else roll
                            srect=(WIDTH//2-260*U,HEIGHT//2-20*U,520*U,36*U)
                            gather_slider=Slider(srect,0,max_allowed,0)
                            gather_confirm=Button((WIDTH//2+140*U,HEIGHT//2+28*U,120*U,36*U),"Confirm",font,bg=(80,200,120))
                            gather_cancel=Button((WIDTH//2-260*U,HEIGHT//2+28*U,120*U,36*U),"Cancel",font,bg=(200,80,80))
                            gather_dialog=True
                    elif b_nothing.rect.collidepoint((mx,my)):
                        if not is_my_turn(): flash("Not your turn")
                        else: do_action("NOTHING",{})
                    elif b_expand.rect.collidepoint((mx,my)):
                        if not is_my_turn(): flash("Not your turn")
                        else: expand_mode="source"; flash("Click your source country")
                    else:
                        wx=cam_x+mx/cam_scale; wy=cam_y+my/cam_scale; clicked=country_at_world_point(wx,wy)
                        if clicked:
                            selected_country=clicked["id"]
                            # Check for double-click to center camera
                            now = time.time()
                            if (now - _last_click_time) < 0.3 and abs(mx - _last_click_pos[0]) < 10 and abs(my - _last_click_pos[1]) < 10:
                                # Double-click: center camera on country
                                cx, cy = clicked.get("centroid", (WIDTH//2, MAP_H//2))
                                cam_target_x = max(0, cx - WIDTH/(2*cam_target_scale))
                                cam_target_y = max(0, cy - MAP_H/(2*cam_target_scale))
                                flash(f"Centered on {clicked.get('name', '?')}")
                            _last_click_time = now
                            _last_click_pos = (mx, my)
                            if expand_mode=="source":
                                snap=get_snapshot(); rc=snap["countries"].get(selected_country,{}); owner=rc.get("owner")
                                cur_name=game.players[game.turn_idx].name if (mode=="local" and game) else my_player_name
                                if owner!=cur_name: flash("Select a country you own.")
                                else:
                                    expand_src=selected_country; expand_mode="target"
                                    target_key="move_target" if mode=="online" else "starting_country"
                                    for kk in input_active: input_active[kk]=False
                                    input_active[target_key]=True; user_inputs[target_key]=""
                                    flash("Type target country name and press Send.")
                            elif expand_mode=="target" and expand_src: flash("Type the target name in the input box.")
                        else: selected_country=None

        # ---- Camera smoothing & inertia (only during gameplay) ----
        if state in ("playing", "choose_start"):
            lerp=min(1.0,1.0-(0.7**(dt*30))); cam_scale+=(cam_target_scale-cam_scale)*lerp
            cam_x+=(cam_target_x-cam_x)*lerp; cam_y+=(cam_target_y-cam_y)*lerp
            cam_x += cam_vel_x * dt
            cam_y += cam_vel_y * dt
            cam_vel_x *= (CAMERA_INERTIA_DECAY ** dt)
            cam_vel_y *= (CAMERA_INERTIA_DECAY ** dt)
            if abs(cam_vel_x) < 0.5: cam_vel_x = 0
            if abs(cam_vel_y) < 0.5: cam_vel_y = 0
            keys_held = pygame.key.get_pressed()
            if keys_held[pygame.K_w]: cam_target_y = max(0, cam_target_y - CAMERA_WASD_SPEED * dt / max(cam_scale, 0.01))
            if keys_held[pygame.K_s]: cam_target_y += CAMERA_WASD_SPEED * dt / max(cam_scale, 0.01)
            if keys_held[pygame.K_a]: cam_target_x = max(0, cam_target_x - CAMERA_WASD_SPEED * dt / max(cam_scale, 0.01))
            if keys_held[pygame.K_d]: cam_target_x += CAMERA_WASD_SPEED * dt / max(cam_scale, 0.01)
            vis_w=WIDTH/max(cam_scale,1e-6); vis_h=MAP_H/max(cam_scale,1e-6)
            cam_x=max(0.0,min(cam_x,max(0.0,WIDTH-vis_w))); cam_y=max(0.0,min(cam_y,max(0.0,MAP_H-vis_h)))

        # ---- Game browser auto-refresh ----
        if state == "game_browser" and fc:
            now_t = time.time()
            if now_t - last_browser_refresh > 5:
                try: public_games_list = fc.list_public_games()
                except Exception: pass
                last_browser_refresh = now_t

        # ---- Notification polling (every 30s when on main_menu or playing) ----
        if fc and state in ("main_menu", "playing", "game_lobby"):
            now_t = time.time()
            if now_t - last_notif_check > 30:
                try:
                    _notifs = fc.get_notifications()
                    notif_unread_count = sum(1 for n in _notifs if not n.get("read"))
                    if state == "notifications": notifications_cache = _notifs
                    # Play notification sound for new unread turn notifications
                    if notif_unread_count > 0 and audio:
                        _new_turn_notifs = [n for n in _notifs if n.get("type") == "your_turn" and not n.get("read")]
                        if _new_turn_notifs:
                            audio.play_sfx("turn")
                except Exception:
                    pass
                last_notif_check = now_t

        # ---- Troop animation updates ----
        now_t = time.time()
        troop_animations = [a for a in troop_animations if now_t - a["start_time"] < a["duration"]]

        # ================================================================
        # RENDERING
        # ================================================================
        actual_screen = screen; screen = game_surf; sw=WIDTH; sh=HEIGHT
        if state!=_prev_state: _transition_t=1.0; _prev_state=state
        if _transition_t>0: _transition_t=max(0,_transition_t-dt*TRANSITION_FADE_SPEED)
        screen.fill((14,18,30))

        if state in ("playing", "choose_start"):
            scaled_w=max(1,int(WIDTH*cam_scale)); scaled_h=max(1,int(MAP_H*cam_scale)); scale_key=(scaled_w,scaled_h)
            if _cached_scale_key!=scale_key:
                try: _cached_scaled_map=pygame.transform.scale(map_surface,(scaled_w,scaled_h)); _cached_scale_key=scale_key
                except pygame.error: _cached_scaled_map=map_surface; _cached_scale_key=None
            blit_x=int(-cam_x*cam_scale); blit_y=int(-cam_y*cam_scale)
            if _cached_scaled_map: screen.blit(_cached_scaled_map,(blit_x,blit_y))

        # ---- Draw ownership + hover + troops ----
        if state in ("playing","choose_start"):
            snapshot = get_snapshot(); cam_ox=-cam_x*cam_scale; cam_oy=-cam_y*cam_scale
            vx0=cam_x; vy0=cam_y; vx1=cam_x+sw/max(cam_scale,0.01); vy1=cam_y+MAP_H/max(cam_scale,0.01)
            if mode in ("local","spectate") and game:
                player_by_name = {p.name:p for p in game.players}
                own_hash=hash(tuple((cid,c.get("owner","")) for cid,c in local_countries.items() if c.get("owner")))
                if _own_dirty or _own_turn!=own_hash:
                    _own_surface.fill((0,0,0,0))
                    for cid,c in local_countries.items():
                        owner=c.get("owner")
                        if owner:
                            pl=player_by_name.get(owner); fill_col=pl.color if pl else (100,100,100)
                            for ring in c["polygons"]:
                                if len(ring)>=3:
                                    try: pygame.draw.polygon(_own_surface,fill_col,ring); pygame.draw.polygon(_own_surface,lighten(fill_col,35),ring,1)
                                    except pygame.error: pass
                    _own_dirty=False; _own_turn=own_hash
                try:
                    if cam_scale==1.0: screen.blit(_own_surface,(blit_x,blit_y))
                    else: screen.blit(pygame.transform.scale(_own_surface,(scaled_w,scaled_h)),(blit_x,blit_y))
                except pygame.error: pass
            else:
                for cid,c in local_countries.items():
                    rinfo=snapshot["countries"].get(cid,{}); owner=rinfo.get("owner")
                    if owner:
                        color=None
                        for p in snapshot["players"]:
                            if p.get("name")==owner: color=p.get("color"); break
                        if color is None: color=(100,100,100)
                        for ring in c["polygons"]:
                            if len(ring)>=3:
                                transformed=[(int(x*cam_scale+cam_ox),int(y*cam_scale+cam_oy)) for x,y in ring]
                                try: pygame.draw.polygon(screen,color,transformed); pygame.draw.polygon(screen,lighten(color,40),transformed,1)
                                except pygame.error: pass
            if hovered_country and hovered_country.get("bbox"):
                bx0,by0,bx1,by1=hovered_country["bbox"]
                if not (bx1<vx0 or bx0>vx1 or by1<vy0 or by0>vy1):
                    for ring in hovered_country["polygons"]:
                        if len(ring)>=3:
                            transformed=[(int(x*cam_scale+cam_ox),int(y*cam_scale+cam_oy)) for x,y in ring]
                            try: pygame.draw.polygon(screen,(255,255,255),transformed,2)
                            except pygame.error: pass
            for cid,c in local_countries.items():
                bbox=c.get("bbox")
                if bbox and (bbox[2]<vx0 or bbox[0]>vx1 or bbox[3]<vy0 or bbox[1]>vy1): continue
                cx,cy=c.get("centroid",(0,0)); sx=int((cx-cam_x)*cam_scale); sy=int((cy-cam_y)*cam_scale)
                cinfo=snapshot["countries"].get(cid,{}); troops=int(cinfo.get("troops",0) or 0)
                if troops>0:
                    owner=cinfo.get("owner"); color=(60,60,60)
                    for p in snapshot["players"]:
                        if p.get("name")==owner: color=p.get("color",(60,60,60)); break
                    base_r=max(6,int(ARMY_PIN_RADIUS*PIN_SCALE*cam_scale)); bonus=min(TROOP_BONUS_MAX,troops//5); r=base_r+bonus; so=max(1,U)
                    pygame.draw.circle(screen,(0,0,0),(sx+so,sy+so*2),r+2)
                    pygame.draw.circle(screen,(255,255,255),(sx,sy),r+1)
                    pygame.draw.circle(screen,color,(sx,sy),r)
                    if r>6: pygame.draw.circle(screen,lighten(color,40),(sx-1,sy-1),max(2,r//2))
                    label=str(troops); t=cached_render(pinfont,label,(255,255,255)); ts=cached_render(pinfont,label,(0,0,0))
                    tx=sx-t.get_width()//2; ty=sy-t.get_height()//2; screen.blit(ts,(tx+so,ty+so)); screen.blit(t,(tx,ty))

        # ---- Troop movement animations ----
        if state in ("playing", "choose_start") and troop_animations:
            now_t = time.time()
            for anim in troop_animations:
                t_frac = min(1.0, (now_t - anim["start_time"]) / anim["duration"])
                # Ease-out curve
                t_ease = 1.0 - (1.0 - t_frac) ** 2
                sx_w, sy_w = anim["src_xy"]
                dx_w, dy_w = anim["dst_xy"]
                # Interpolate world coords
                wx = sx_w + (dx_w - sx_w) * t_ease
                wy = sy_w + (dy_w - sy_w) * t_ease
                # Convert to screen coords
                ax = int((wx - cam_x) * cam_scale)
                ay = int((wy - cam_y) * cam_scale)
                color = anim.get("color", (200, 200, 200))
                count = anim.get("count", 1)
                # Draw marching dot with trail
                trail_count = 4
                for ti in range(trail_count):
                    tt = max(0, t_frac - ti * 0.05)
                    tt_e = 1.0 - (1.0 - tt) ** 2
                    twx = sx_w + (dx_w - sx_w) * tt_e
                    twy = sy_w + (dy_w - sy_w) * tt_e
                    tax = int((twx - cam_x) * cam_scale)
                    tay = int((twy - cam_y) * cam_scale)
                    alpha = max(40, 220 - ti * 50)
                    tr = max(3, int(8 * cam_scale) - ti)
                    trail_surf = pygame.Surface((tr*2, tr*2), pygame.SRCALPHA)
                    pygame.draw.circle(trail_surf, (*color, alpha), (tr, tr), tr)
                    screen.blit(trail_surf, (tax - tr, tay - tr))
                # Draw troop count label on lead dot
                lbl = cached_render(pinfont, str(count), (255, 255, 255))
                screen.blit(lbl, (ax - lbl.get_width()//2, ay - lbl.get_height()//2))

        # ---- HUD ----
        draw_gradient_rect(screen,(0,MAP_H,sw,sh-MAP_H),(22,28,42),(16,20,32))
        pygame.draw.line(screen,HUD_BORDER,(0,MAP_H),(sw,MAP_H),2*U)
        glow_line=pygame.Surface((sw,3*U),pygame.SRCALPHA); glow_line.fill((60,100,180,40)); screen.blit(glow_line,(0,MAP_H))

        # ---- State-specific rendering ----
        if state == "login":
            title_glow=cached_render(titlefont,"GeoPolitical Domination",(40,80,160))
            title_shadow=cached_render(titlefont,"GeoPolitical Domination",(20,60,120))
            title_main=cached_render(titlefont,"GeoPolitical Domination",TEXT_PRIMARY)
            tcx=sw//2-title_main.get_width()//2; screen.blit(title_glow,(tcx,78*U)); screen.blit(title_shadow,(tcx+2*U,82*U)); screen.blit(title_main,(tcx,80*U))
            screen.blit(cached_render(font,"A Strategy Game of World Conquest",TEXT_SECONDARY),(sw//2-cached_render(font,"A Strategy Game of World Conquest",TEXT_SECONDARY).get_width()//2,135*U))
            # Login / Register header
            _login_title = "Create Account" if login_mode == "register" else "Sign In"
            lt = cached_render(bigfont, _login_title, ACCENT_CYAN)
            screen.blit(lt, (sw//2 - lt.get_width()//2, 190*U))
            # Username & password input boxes
            draw_input_box("login_user", "Username:")
            draw_input_box("login_pass", "Password:", hide_pw=True)
            btn_login_submit.draw(screen)
            btn_login_toggle.draw(screen)
            if not FIREBASE_AVAILABLE:
                warn = cached_render(font, "Firebase unavailable -- online features disabled", ACCENT_RED)
                screen.blit(warn, (sw//2 - warn.get_width()//2, 510*U))

        elif state == "main_menu":
            title_glow=cached_render(titlefont,"GeoPolitical Domination",(40,80,160))
            title_shadow=cached_render(titlefont,"GeoPolitical Domination",(20,60,120))
            title_main=cached_render(titlefont,"GeoPolitical Domination",TEXT_PRIMARY)
            tcx=sw//2-title_main.get_width()//2; screen.blit(title_glow,(tcx,78*U)); screen.blit(title_shadow,(tcx+2*U,82*U)); screen.blit(title_main,(tcx,80*U))
            screen.blit(cached_render(font,"A Strategy Game of World Conquest",TEXT_SECONDARY),(sw//2-cached_render(font,"A Strategy Game of World Conquest",TEXT_SECONDARY).get_width()//2,135*U))
            btn_play.draw(screen); btn_mygames.draw(screen); btn_stats.draw(screen); btn_rules.draw(screen); btn_settings.draw(screen); btn_quit_main.draw(screen)
            btn_leaderboard.draw(screen); btn_friends.draw(screen); btn_notifications.draw(screen)
            # Show notification badge
            if notif_unread_count > 0:
                badge_r = pygame.Rect(btn_notifications.rect.right-30*U, btn_notifications.rect.y-4*U, 28*U, 22*U)
                pygame.draw.rect(screen, ACCENT_RED, badge_r, border_radius=11*U)
                bs=cached_render(font, str(notif_unread_count), TEXT_PRIMARY); screen.blit(bs, (badge_r.x+badge_r.w//2-bs.get_width()//2, badge_r.y+2*U))
            # Show logged-in username + logout
            if logged_in_username:
                _uname_surf = cached_render(font, f"Signed in as {logged_in_username}", ACCENT_GREEN)
                screen.blit(_uname_surf, (WIDTH//2-200*U, 484*U))
                btn_logout.draw(screen)
            # Show active games badge on My Games button
            if joined_games:
                _mg_r = btn_mygames.rect
                badge_r = pygame.Rect(_mg_r.right-30*U, _mg_r.y-6*U, 28*U, 22*U)
                pygame.draw.rect(screen, ACCENT_GREEN, badge_r, border_radius=11*U)
                bs=cached_render(font, str(len(joined_games)), (0,0,0)); screen.blit(bs, (badge_r.x+badge_r.w//2-bs.get_width()//2, badge_r.y+2*U))
            note=cached_render(font,"F11 fullscreen | Right-drag pan | Scroll zoom | 1-4 actions | Esc cancel",TEXT_MUTED)
            screen.blit(note,(WIDTH//2-note.get_width()//2,530*U))

        elif state == "play":
            t=cached_render(titlefont,"Play",TEXT_PRIMARY); screen.blit(t,(sw//2-t.get_width()//2,100*U))
            screen.blit(cached_render(font,"Choose a game mode",TEXT_SECONDARY),(sw//2-cached_render(font,"Choose a game mode",TEXT_SECONDARY).get_width()//2,155*U))
            btn_play_offline.draw(screen); btn_play_online.draw(screen); btn_play_spectate.draw(screen); btn_play_back.draw(screen)

        elif state == "stats":
            t=cached_render(titlefont,"Player Stats",TEXT_PRIMARY); screen.blit(t,(sw//2-t.get_width()//2,40*U))
            if not player_stats_cache:
                nt=cached_render(font,"No stats available yet. Play some online games!",TEXT_MUTED)
                screen.blit(nt,(sw//2-nt.get_width()//2,200*U))
            else:
                col_x = sw//2 - 360*U
                hdr_y = 120*U
                cols = [("Mode", 0), ("Games", 160*U), ("Wins", 280*U), ("Losses", 380*U), ("Territories", 500*U), ("Turns", 620*U)]
                for label, dx in cols:
                    screen.blit(cached_render(font, label, ACCENT_GOLD), (col_x+dx, hdr_y))
                pygame.draw.line(screen, HUD_BORDER, (col_x, hdr_y+28*U), (col_x+700*U, hdr_y+28*U), 1)
                row_i = 0
                for mode_key in ["classic", "tournament", "challenge"]:
                    mdata = player_stats_cache.get(mode_key, {})
                    games = mdata.get("games_played", 0)
                    wins = mdata.get("wins", 0)
                    losses = mdata.get("losses", 0)
                    territories = mdata.get("territories_captured", 0)
                    turns = mdata.get("turns_played", 0)
                    ry = hdr_y + 40*U + row_i * 44*U
                    screen.blit(cached_render(bigfont, GAME_MODES.get(mode_key, {}).get("label", mode_key.title()), TEXT_PRIMARY), (col_x, ry))
                    screen.blit(cached_render(font, str(games), TEXT_PRIMARY), (col_x+160*U, ry+4*U))
                    screen.blit(cached_render(font, str(wins), ACCENT_GREEN), (col_x+280*U, ry+4*U))
                    screen.blit(cached_render(font, str(losses), ACCENT_RED), (col_x+380*U, ry+4*U))
                    screen.blit(cached_render(font, str(territories), TEXT_SECONDARY), (col_x+500*U, ry+4*U))
                    screen.blit(cached_render(font, str(turns), TEXT_SECONDARY), (col_x+620*U, ry+4*U))
                    row_i += 1
                total_games = sum(player_stats_cache.get(m, {}).get("games_played", 0) for m in ["classic","tournament","challenge"])
                total_wins = sum(player_stats_cache.get(m, {}).get("wins", 0) for m in ["classic","tournament","challenge"])
                ty = hdr_y + 40*U + row_i * 44*U + 10*U
                pygame.draw.line(screen, HUD_BORDER, (col_x, ty-5*U), (col_x+700*U, ty-5*U), 1)
                screen.blit(cached_render(bigfont, "Total", ACCENT_CYAN), (col_x, ty))
                screen.blit(cached_render(font, str(total_games), TEXT_PRIMARY), (col_x+160*U, ty+4*U))
                screen.blit(cached_render(font, str(total_wins), ACCENT_GREEN), (col_x+280*U, ty+4*U))
                if total_games > 0:
                    wr = total_wins / total_games * 100
                    screen.blit(cached_render(font, f"Win Rate: {wr:.1f}%", ACCENT_GOLD), (col_x, ty+50*U))
            btn_stats_back.draw(screen)

        elif state == "leaderboard":
            t=cached_render(titlefont,"Global Leaderboard",TEXT_PRIMARY); screen.blit(t,(sw//2-t.get_width()//2,20*U))
            if not leaderboard_cache:
                nt=cached_render(font,"No leaderboard data yet. Play online games to get ranked!",TEXT_MUTED)
                screen.blit(nt,(sw//2-nt.get_width()//2,200*U))
            else:
                col_x = sw//2 - 400*U; hdr_y = 90*U
                cols = [("#", 0), ("Player", 60*U), ("Elo", 340*U), ("Wins", 460*U), ("Losses", 560*U), ("Games", 660*U)]
                for label, dx in cols:
                    screen.blit(cached_render(font, label, ACCENT_GOLD), (col_x+dx, hdr_y))
                pygame.draw.line(screen, HUD_BORDER, (col_x, hdr_y+28*U), (col_x+760*U, hdr_y+28*U), 1)
                my_username = logged_in_username or ""
                for ri, entry in enumerate(leaderboard_cache):
                    ry = hdr_y + 40*U + ri * 36*U - leaderboard_scroll_y
                    if ry < hdr_y + 30*U or ry > HEIGHT - 80*U: continue
                    is_me = entry.get("username","").lower() == my_username.lower()
                    txt_col = ACCENT_CYAN if is_me else TEXT_PRIMARY
                    rank_col = ACCENT_GOLD if ri < 3 else txt_col
                    screen.blit(cached_render(font, str(ri+1), rank_col), (col_x, int(ry)))
                    screen.blit(cached_render(font, entry.get("username","?"), txt_col), (col_x+60*U, int(ry)))
                    screen.blit(cached_render(bigfont, str(entry.get("elo",1000)), ACCENT_GOLD if ri<3 else TEXT_PRIMARY), (col_x+340*U, int(ry)-2*U))
                    screen.blit(cached_render(font, str(entry.get("wins",0)), ACCENT_GREEN), (col_x+460*U, int(ry)))
                    screen.blit(cached_render(font, str(entry.get("losses",0)), ACCENT_RED), (col_x+560*U, int(ry)))
                    screen.blit(cached_render(font, str(entry.get("games_played",0)), TEXT_SECONDARY), (col_x+660*U, int(ry)))
                    if is_me:
                        pygame.draw.rect(screen, ACCENT_CYAN, (col_x-8*U, int(ry)-2*U, 770*U, 30*U), 1, border_radius=4*U)
            btn_lb_back.draw(screen)

        elif state == "friends":
            t=cached_render(titlefont,"Friends",TEXT_PRIMARY); screen.blit(t,(sw//2-t.get_width()//2,20*U))
            btn_friends_add.draw(screen); btn_friends_send.draw(screen)
            # Friend add input box
            add_r = pygame.Rect(sw//2-200*U, 80*U, 330*U, 36*U)
            pygame.draw.rect(screen, (30,35,50), add_r, border_radius=6*U)
            pygame.draw.rect(screen, ACCENT_CYAN if friend_add_active else HUD_BORDER, add_r, 2, border_radius=6*U)
            if friend_add_input:
                screen.blit(cached_render(font, friend_add_input, TEXT_PRIMARY), (add_r.x+8*U, add_r.y+8*U))
            else:
                screen.blit(cached_render(font, "Enter username...", TEXT_MUTED), (add_r.x+8*U, add_r.y+8*U))
            if not friends_cache:
                nt=cached_render(font,"No friends yet. Add someone above!",TEXT_MUTED)
                screen.blit(nt,(sw//2-nt.get_width()//2,240*U))
            else:
                for fi, fr in enumerate(friends_cache):
                    fy = 140*U + fi * 56*U - friends_scroll_y
                    if fy < 120*U or fy > HEIGHT - 80*U: continue
                    cr = pygame.Rect(sw//2-320*U, int(fy), 640*U, 48*U)
                    pygame.draw.rect(screen, LOBBY_CARD_BG, cr, border_radius=8*U)
                    pygame.draw.rect(screen, LOBBY_CARD_BORDER, cr, 1, border_radius=8*U)
                    screen.blit(cached_render(bigfont, fr.get("username","?"), TEXT_PRIMARY), (cr.x+16*U, cr.y+6*U))
                    status = fr.get("status","")
                    if status == "accepted":
                        screen.blit(cached_render(font, "Friend", ACCENT_GREEN), (cr.x+16*U, cr.y+28*U))
                        inv_r = pygame.Rect(WIDTH//2+100*U, int(fy)+6*U, 90*U, 32*U)
                        pygame.draw.rect(screen, (55,130,210), inv_r, border_radius=5*U)
                        screen.blit(cached_render(font, "Invite", TEXT_PRIMARY), (inv_r.x+20*U, inv_r.y+7*U))
                        rem_r = pygame.Rect(WIDTH//2+200*U, int(fy)+6*U, 90*U, 32*U)
                        pygame.draw.rect(screen, (160,60,60), rem_r, border_radius=5*U)
                        screen.blit(cached_render(font, "Remove", TEXT_PRIMARY), (rem_r.x+14*U, rem_r.y+7*U))
                    elif status == "pending_sent":
                        screen.blit(cached_render(font, "Request Sent", ACCENT_GOLD), (cr.x+16*U, cr.y+28*U))
                    elif status == "pending_received":
                        screen.blit(cached_render(font, "Wants to be friends", ACCENT_CYAN), (cr.x+16*U, cr.y+28*U))
                        acc_r = pygame.Rect(WIDTH//2+100*U, int(fy)+6*U, 90*U, 32*U)
                        pygame.draw.rect(screen, (55,160,120), acc_r, border_radius=5*U)
                        screen.blit(cached_render(font, "Accept", TEXT_PRIMARY), (acc_r.x+16*U, acc_r.y+7*U))
                        dec_r = pygame.Rect(WIDTH//2+200*U, int(fy)+6*U, 90*U, 32*U)
                        pygame.draw.rect(screen, (160,60,60), dec_r, border_radius=5*U)
                        screen.blit(cached_render(font, "Decline", TEXT_PRIMARY), (dec_r.x+12*U, dec_r.y+7*U))
            btn_friends_back.draw(screen)

        elif state == "notifications":
            t=cached_render(titlefont,"Notifications",TEXT_PRIMARY); screen.blit(t,(sw//2-t.get_width()//2,20*U))
            btn_notif_refresh.draw(screen)
            if not notifications_cache:
                nt=cached_render(font,"No notifications.",TEXT_MUTED)
                screen.blit(nt,(sw//2-nt.get_width()//2,200*U))
            else:
                for ni, notif in enumerate(notifications_cache):
                    ny = 130*U + ni * 60*U - notif_scroll_y
                    if ny < 110*U or ny > HEIGHT - 80*U: continue
                    cr = pygame.Rect(sw//2-380*U, int(ny), 760*U, 52*U)
                    bg_col = (35,40,55) if not notif.get("read") else (25,28,38)
                    pygame.draw.rect(screen, bg_col, cr, border_radius=8*U)
                    pygame.draw.rect(screen, LOBBY_CARD_BORDER, cr, 1, border_radius=8*U)
                    if not notif.get("read"):
                        pygame.draw.circle(screen, ACCENT_CYAN, (cr.x+14*U, cr.y+26*U), 5*U)
                    ntype = notif.get("type","")
                    if ntype == "game_invite":
                        screen.blit(cached_render(font, f"Game invite from {notif.get('from_username','?')}", TEXT_PRIMARY), (cr.x+28*U, cr.y+6*U))
                        screen.blit(cached_render(font, f"Game: {notif.get('game_id','?')}", TEXT_MUTED), (cr.x+28*U, cr.y+28*U))
                        join_r = pygame.Rect(WIDTH//2+180*U, int(ny)+8*U, 90*U, 32*U)
                        pygame.draw.rect(screen, (55,160,120), join_r, border_radius=5*U)
                        screen.blit(cached_render(font, "Join", TEXT_PRIMARY), (join_r.x+26*U, join_r.y+7*U))
                    elif ntype == "your_turn":
                        screen.blit(cached_render(font, notif.get("message","It's your turn!"), ACCENT_GOLD), (cr.x+28*U, cr.y+6*U))
                        screen.blit(cached_render(font, f"Game: {notif.get('game_id','?')}", TEXT_MUTED), (cr.x+28*U, cr.y+28*U))
                    else:
                        screen.blit(cached_render(font, notif.get("message","Notification"), TEXT_PRIMARY), (cr.x+28*U, cr.y+6*U))
                        screen.blit(cached_render(font, f"From: {notif.get('from_username','?')}", TEXT_MUTED), (cr.x+28*U, cr.y+28*U))
                    dismiss_r = pygame.Rect(WIDTH//2+280*U, int(ny)+8*U, 70*U, 32*U)
                    pygame.draw.rect(screen, (80,80,100), dismiss_r, border_radius=5*U)
                    ds=cached_render(font, "X", TEXT_PRIMARY); screen.blit(ds, (dismiss_r.x+dismiss_r.w//2-ds.get_width()//2, dismiss_r.y+7*U))
            btn_notif_back.draw(screen)

        elif state == "settings":
            t=cached_render(titlefont,"Settings",TEXT_PRIMARY); screen.blit(t,(sw//2-t.get_width()//2,60*U))
            # Tab buttons
            btn_tab_graphics.draw(screen); btn_tab_audio.draw(screen); btn_tab_controls.draw(screen)
            tab_map = {"Graphics": btn_tab_graphics, "Audio": btn_tab_audio, "Controls": btn_tab_controls}
            if settings_tab in tab_map: pygame.draw.rect(screen, ACCENT_GOLD, tab_map[settings_tab].rect, 3, border_radius=8*U)
            # Graphics tab
            if settings_tab == "Graphics":
                screen.blit(cached_render(bigfont,"Render FPS",TEXT_SECONDARY),(sw//2-80*U,200*U))
                btn_fps_60.draw(screen); btn_fps_120.draw(screen); btn_fps_240.draw(screen)
                active_btn={60:btn_fps_60,120:btn_fps_120,240:btn_fps_240}.get(RENDER_FPS)
                if active_btn: pygame.draw.rect(screen,ACCENT_GOLD,active_btn.rect,3,border_radius=10*U)
                screen.blit(cached_render(font,f"Current: {RENDER_FPS} FPS",TEXT_MUTED),(sw//2-60*U,316*U))
                screen.blit(cached_render(bigfont,"Resolution",TEXT_SECONDARY),(sw//2-80*U,350*U))
                for _rb, rw, rh, rlabel in btn_resolutions:
                    _rb.draw(screen)
                    if rlabel == current_resolution_label:
                        pygame.draw.rect(screen,ACCENT_GOLD,_rb.rect,3,border_radius=10*U)
                screen.blit(cached_render(font,f"Current: {current_resolution_label}",TEXT_MUTED),(sw//2-60*U,436*U))
            # Audio tab
            elif settings_tab == "Audio":
                screen.blit(cached_render(bigfont,"Music Volume",TEXT_SECONDARY),(sw//2-200*U,200*U))
                music_slider.draw(screen,font)
                screen.blit(cached_render(font,f"{int(music_slider.value)}%",TEXT_MUTED),(sw//2+220*U,240*U))
                screen.blit(cached_render(bigfont,"SFX Volume",TEXT_SECONDARY),(sw//2-200*U,290*U))
                sfx_slider.draw(screen,font)
                screen.blit(cached_render(font,f"{int(sfx_slider.value)}%",TEXT_MUTED),(sw//2+220*U,330*U))
            # Controls tab
            elif settings_tab == "Controls":
                for i,line in enumerate(["1=Peace 2=Expand 3=Gather 4=Nothing","F11=Fullscreen Esc=Back","Right-drag=Pan Scroll=Zoom","WASD=Pan (always on)","Spectate: +/-=Speed Space=Toggle"]):
                    screen.blit(cached_render(font,line,TEXT_MUTED),(sw//2-200*U,200*U+i*30*U))
            btn_settings_back.draw(screen)

        elif state == "spectate_setup":
            t=cached_render(titlefont,"Spectate Mode",TEXT_PRIMARY); screen.blit(t,(sw//2-t.get_width()//2,80*U))
            screen.blit(cached_render(font,f"Number of Bots: {spectate_slider.value}",TEXT_SECONDARY),(WIDTH//2-200*U,280*U))
            spectate_slider.draw(screen,font); btn_start_spectate.draw(screen)

        elif state == "local_setup":
            t=cached_render(titlefont,"Local Game Setup",TEXT_PRIMARY); screen.blit(t,(sw//2-t.get_width()//2,80*U))
            draw_input_box("player_name","Player Name:")
            screen.blit(cached_render(font,f"Bot Players: {bot_slider.value}",TEXT_SECONDARY),(WIDTH//2-200*U,365*U))
            bot_slider.draw(screen,font); btn_start_local.draw(screen)

        elif state == "online_setup":
            t=cached_render(titlefont,"Online Game",TEXT_PRIMARY); screen.blit(t,(sw//2-t.get_width()//2,40*U))
            screen.blit(cached_render(font,"Online Multiplayer",TEXT_SECONDARY),(sw//2-80*U,95*U))
            draw_input_box("game_id","Game ID:"); draw_input_box("player_name","Player Name:")
            draw_input_box("player_password","Player Password:",hide_pw=True); draw_input_box("room_password","Room Password (optional):",hide_pw=True)
            screen.blit(cached_render(font,"Create a new room or join an existing one.",TEXT_MUTED),(WIDTH//2-180*U,360*U))
            Button((WIDTH//2-260*U,400*U,240*U,52*U),"Create & Host",bigfont,bg=(50,170,110)).draw(screen)
            Button((WIDTH//2+20*U,400*U,240*U,52*U),"Join Room",bigfont,bg=(55,130,210)).draw(screen)
            if network_loading:
                _overlay_surf.fill((0,0,0,180)); screen.blit(_overlay_surf,(0,0))
                lt=cached_render(bigfont,"Connecting...",TEXT_PRIMARY); screen.blit(lt,(WIDTH//2-lt.get_width()//2,HEIGHT//2-lt.get_height()//2))
            if update_check_done and update_info and update_info.get("update_available"):
                ur=pygame.Rect(WIDTH-320*U,HEIGHT-90*U,310*U,80*U); pygame.draw.rect(screen,HUD_BG_ACCENT,ur,border_radius=10*U)
                pygame.draw.rect(screen,ACCENT_GOLD,ur,2,border_radius=10*U)
                screen.blit(cached_render(font,"Update Available!",ACCENT_GOLD),(ur.x+10*U,ur.y+8*U))
                screen.blit(cached_render(font,f"{update_info.get('current','?')} -> {update_info.get('latest','?')}",TEXT_SECONDARY),(ur.x+10*U,ur.y+28*U))
                if update_btn is None: update_btn=Button((ur.x+10*U,ur.y+48*U,140*U,24*U),"Update Now",font,bg=(50,170,110))
                if dismiss_btn is None: dismiss_btn=Button((ur.x+160*U,ur.y+48*U,140*U,24*U),"Ignore",font,bg=(80,80,100))
                update_btn.draw(screen); dismiss_btn.draw(screen)

        elif state == "game_lobby":
            t=cached_render(titlefont,"Game Lobby",TEXT_PRIMARY); screen.blit(t,(sw//2-t.get_width()//2,40*U))
            # Build player list and game info from either local game or online remote
            _lobby_players = []
            _lobby_game_id = "Local"
            _lobby_pw = ""
            _lobby_limit = 0
            _lobby_is_host = False
            if mode == "local" and game:
                _lobby_game_id = game.game_id or "Local"
                _lobby_pw = game.password or ""
                _lobby_limit = game.player_limit
                _lobby_is_host = True  # local creator is always host
                for pl in game.players:
                    _lobby_players.append({"name": pl.name, "is_bot": pl.is_bot, "is_host": pl.is_host,
                                           "color": pl.color, "eliminated": pl.eliminated, "is_spectator": pl.is_spectator})
            elif mode == "online" and remote:
                snap = remote.snapshot()
                _lobby_game_id = current_game_id or "Online"
                _lobby_pw = user_inputs.get("room_password", "") or ""
                _lobby_players = snap.get("players", [])
                # Check if current player is the first (host)
                if _lobby_players and _lobby_players[0].get("name") == my_player_name:
                    _lobby_is_host = True

            screen.blit(cached_render(font,"Game ID:",TEXT_MUTED),(sw//2-280*U,100*U))
            screen.blit(cached_render(bigfont,_lobby_game_id,ACCENT_CYAN),(sw//2-180*U,96*U))
            pw_text=_lobby_pw if not hide_password else ("*"*len(_lobby_pw) if _lobby_pw else "None")
            screen.blit(cached_render(font,f"Password: {pw_text or 'None'}",TEXT_MUTED),(sw//2+40*U,100*U))
            limit_str = str(_lobby_limit) if _lobby_limit > 0 else "None"
            screen.blit(cached_render(font,f"Player Limit: {limit_str}",TEXT_MUTED),(sw//2-280*U,130*U))
            if _lobby_is_host:
                btn_plimit_minus.draw(screen)
                btn_plimit_plus.draw(screen)
            screen.blit(cached_render(font,f"Players: {len(_lobby_players)}",TEXT_SECONDARY),(sw//2+40*U,130*U))
            for i,pl in enumerate(_lobby_players):
                cy=170*U+i*56*U; cr=pygame.Rect(sw//2-280*U,cy,560*U,48*U)
                pygame.draw.rect(screen,LOBBY_CARD_BG,cr,border_radius=8*U); pygame.draw.rect(screen,LOBBY_CARD_BORDER,cr,1,border_radius=8*U)
                # Color bar — handle both Player objects and dicts
                pl_color = pl.color if hasattr(pl, "color") else (hex_to_rgb(pl.get("color","#888")) if isinstance(pl.get("color"), str) else pl.get("color",(120,120,120)))
                pygame.draw.rect(screen,pl_color,(cr.x,cr.y,6*U,cr.h),border_radius=3*U)
                pl_name = pl.name if hasattr(pl,"name") else pl.get("name","?")
                pl_bot = pl.is_bot if hasattr(pl,"is_bot") else pl.get("is_bot",False)
                pl_host = pl.is_host if hasattr(pl,"is_host") else pl.get("is_host",False)
                name_lbl = pl_name + (" (BOT)" if pl_bot else "")
                ns=cached_render(font,name_lbl,TEXT_PRIMARY); screen.blit(ns,(cr.x+16*U,cr.y+8*U))
                # Host star: first player in online is host, or is_host flag for local
                is_host_p = pl_host or (i == 0 and mode == "online")
                if is_host_p: draw_host_star(screen,cr.x+16*U+ns.get_width()+12*U,cr.y+16*U,size=8*U)
                role = "Host" if is_host_p else ("Bot" if pl_bot else "Player")
                screen.blit(cached_render(smallfont,role,TEXT_MUTED),(cr.x+16*U,cr.y+28*U))
                # Kick button for non-host human players (local mode only for now)
                if mode == "local" and _lobby_is_host and pl_name != (game.host_name if game else "") and not pl_bot:
                    kick_r=pygame.Rect(cr.right-90*U,cr.y+10*U,80*U,28*U)
                    pygame.draw.rect(screen,KICK_BTN_COLOR,kick_r,border_radius=4*U)
                    ks=cached_render(smallfont,"Kick",TEXT_PRIMARY); screen.blit(ks,(kick_r.x+kick_r.w//2-ks.get_width()//2,kick_r.y+6*U))
            # Only show Start button if this player is the host
            if _lobby_is_host:
                btn_lobby_start.draw(screen)
            else:
                wt = cached_render(font, "Waiting for host to start...", TEXT_MUTED)
                screen.blit(wt, (sw//2-wt.get_width()//2, 560*U+10*U))
            btn_lobby_back.draw(screen)

        elif state == "joined_games":
            t=cached_render(titlefont,"My Games",TEXT_PRIMARY); screen.blit(t,(sw//2-t.get_width()//2,40*U))
            if not joined_games:
                nt=cached_render(font,"No active games. Join or create one from Online Game.",TEXT_MUTED)
                screen.blit(nt,(sw//2-nt.get_width()//2,240*U))
            else:
                _jg_list = list(joined_games.items())
                for gi, (gid, ginfo) in enumerate(_jg_list):
                    row_y = 160*U + gi * 70*U - joined_games_scroll_y
                    if row_y < 140*U or row_y > HEIGHT - 80*U: continue
                    cr = pygame.Rect(sw//2-320*U, row_y, 640*U, 60*U)
                    pygame.draw.rect(screen, LOBBY_CARD_BG, cr, border_radius=8*U)
                    pygame.draw.rect(screen, LOBBY_CARD_BORDER, cr, 1, border_radius=8*U)
                    # Game ID
                    screen.blit(cached_render(bigfont, gid, ACCENT_CYAN), (cr.x+16*U, cr.y+6*U))
                    # Player name in this game
                    pn = ginfo.get("player_name", "?")
                    screen.blit(cached_render(font, f"as {pn}", TEXT_MUTED), (cr.x+16*U, cr.y+34*U))
                    # Flashing green dot if it's this player's turn
                    _rem = ginfo.get("remote")
                    is_turn = False
                    if _rem:
                        try:
                            snap = _rem.snapshot()
                            pl_list = snap.get("players", [])
                            tidx = snap.get("turn_idx", 0)
                            if pl_list and 0 <= tidx < len(pl_list):
                                if pl_list[tidx].get("name") == pn:
                                    is_turn = True
                        except (KeyError, TypeError, IndexError): pass
                    if is_turn:
                        draw_dot(screen, cr.x + cr.w - 260*U, cr.y + 30*U, 6*U, TURN_DOT_COLOR, pulse=True)
                        screen.blit(cached_render(font, "Your turn!", ACCENT_GREEN), (cr.x + cr.w - 248*U, cr.y + 22*U))
                    # Enter / Leave buttons
                    enter_r = pygame.Rect(WIDTH//2+100*U, row_y+12*U, 100*U, 36*U)
                    leave_r = pygame.Rect(WIDTH//2+210*U, row_y+12*U, 100*U, 36*U)
                    pygame.draw.rect(screen, (55,130,210), enter_r, border_radius=6*U)
                    es=cached_render(font, "Enter", TEXT_PRIMARY); screen.blit(es, (enter_r.x+enter_r.w//2-es.get_width()//2, enter_r.y+8*U))
                    pygame.draw.rect(screen, (180,55,55), leave_r, border_radius=6*U)
                    ls=cached_render(font, "Leave", TEXT_PRIMARY); screen.blit(ls, (leave_r.x+leave_r.w//2-ls.get_width()//2, leave_r.y+8*U))
            btn_mygames_back.draw(screen)

        elif state == "choose_start":
            _overlay_surf.fill((0,0,0,160)); screen.blit(_overlay_surf,(0,0))
            dw,dh=600*U,200*U; dx=sw//2-dw//2; dy=100*U
            draw_shadow_rect(screen,(dx,dy,dw,dh),radius=12*U,offset=6*U,alpha=60)
            pygame.draw.rect(screen,HUD_BG_ACCENT,(dx,dy,dw,dh),border_radius=12*U); pygame.draw.rect(screen,HUD_BORDER,(dx,dy,dw,dh),1,border_radius=12*U)
            screen.blit(cached_render(bigfont,"Choose Your Starting Country",TEXT_PRIMARY),(sw//2-cached_render(bigfont,"Choose Your Starting Country",TEXT_PRIMARY).get_width()//2,dy+20*U))
            screen.blit(cached_render(font,"Type the exact country name (case-insensitive).",TEXT_SECONDARY),(sw//2-200*U,dy+55*U))
            draw_input_box("starting_country","Country name:")
            btn_y=460*U if mode=="local" else 500*U
            Button((WIDTH//2+20*U,btn_y,160*U,44*U),"Confirm",bigfont,bg=(50,170,110)).draw(screen)
            Button((WIDTH//2-200*U,btn_y,160*U,44*U),"Cancel",bigfont,bg=(160,60,60)).draw(screen)

        elif state == "rules":
            t=cached_render(titlefont,"Game Rules",TEXT_PRIMARY); screen.blit(t,(sw//2-t.get_width()//2,20*U))
            btn_rules_general.draw(screen); btn_rules_classic.draw(screen); btn_rules_tournament.draw(screen); btn_rules_challenge.draw(screen)
            # Highlight current tab
            tabs_map = {"general": btn_rules_general, "classic": btn_rules_classic, "tournament": btn_rules_tournament, "challenge": btn_rules_challenge}
            if rules_current_tab in tabs_map: pygame.draw.rect(screen, ACCENT_GOLD, tabs_map[rules_current_tab].rect, 3, border_radius=8*U)
            # Render scrollable text content
            rules_text = RULES_TEXT.get(rules_current_tab, [])
            wrapped_lines = wrap_text(rules_text, font, sw - 80*U) if isinstance(rules_text, str) else []
            if isinstance(rules_text, list):
                for para in rules_text:
                    wrapped_lines.extend(wrap_text(para, font, sw - 80*U))
                    wrapped_lines.append("")
            line_h = 20*U; start_y = 130*U; max_y = HEIGHT - 120*U; visible_y = 0
            for i, line in enumerate(wrapped_lines):
                ly = start_y + i * line_h - rules_scroll_y
                if ly < start_y or ly > max_y: continue
                if line:
                    screen.blit(cached_render(font, line, TEXT_PRIMARY), (40*U, int(ly)))
                visible_y = ly + line_h
            btn_rules_back.draw(screen)

        elif state == "game_browser":
            t=cached_render(titlefont,"Browse Games",TEXT_PRIMARY); screen.blit(t,(sw//2-t.get_width()//2,20*U))
            btn_join_code.draw(screen); btn_create_new_game.draw(screen); btn_browser_refresh.draw(screen)
            # Render table header
            header_y = 130*U
            screen.blit(cached_render(font, "Game ID", TEXT_SECONDARY), (40*U, header_y))
            screen.blit(cached_render(font, "Host", TEXT_SECONDARY), (200*U, header_y))
            screen.blit(cached_render(font, "Mode", TEXT_SECONDARY), (400*U, header_y))
            screen.blit(cached_render(font, "Map", TEXT_SECONDARY), (550*U, header_y))
            screen.blit(cached_render(font, "Players", TEXT_SECONDARY), (700*U, header_y))
            # Render game list
            if public_games_list:
                for gi, game_info in enumerate(public_games_list):
                    row_y = header_y + 40*U + gi * 50*U - browser_scroll_y
                    if row_y < header_y + 40*U or row_y > HEIGHT - 80*U: continue
                    screen.blit(cached_render(font, game_info.get("id", "?"), TEXT_PRIMARY), (40*U, int(row_y)))
                    screen.blit(cached_render(font, game_info.get("host", "?"), TEXT_PRIMARY), (200*U, int(row_y)))
                    screen.blit(cached_render(font, game_info.get("mode", "?"), TEXT_PRIMARY), (400*U, int(row_y)))
                    screen.blit(cached_render(font, game_info.get("map", "?"), TEXT_PRIMARY), (550*U, int(row_y)))
                    screen.blit(cached_render(font, str(game_info.get("players", 0)), TEXT_PRIMARY), (700*U, int(row_y)))
                    # Join button
                    join_r = pygame.Rect(820*U, int(row_y)-4*U, 90*U, 32*U)
                    pygame.draw.rect(screen, (55,160,120), join_r, border_radius=6*U)
                    js=cached_render(font, "Join", TEXT_PRIMARY); screen.blit(js, (join_r.x+join_r.w//2-js.get_width()//2, join_r.y+7*U))
            else:
                nt=cached_render(font,"No public games available.",TEXT_MUTED); screen.blit(nt,(sw//2-nt.get_width()//2,300*U))
            btn_browser_back.draw(screen)

        elif state == "online_create":
            t=cached_render(titlefont,"Create Online Game",TEXT_PRIMARY); screen.blit(t,(sw//2-t.get_width()//2,80*U))
            screen.blit(cached_render(bigfont,"Select Game Mode:",TEXT_SECONDARY),(sw//2-200*U,150*U))
            btn_mode_classic.draw(screen); btn_mode_tournament.draw(screen); btn_mode_challenge.draw(screen)
            # Highlight selected mode
            mode_map = {"classic": btn_mode_classic, "tournament": btn_mode_tournament, "challenge": btn_mode_challenge}
            if current_game_mode in mode_map: pygame.draw.rect(screen, ACCENT_GOLD, mode_map[current_game_mode].rect, 3, border_radius=10*U)
            screen.blit(cached_render(bigfont,"Select Map Scope:",TEXT_SECONDARY),(sw//2-200*U,260*U))
            btn_scope_world.draw(screen); btn_scope_europe.draw(screen); btn_scope_asia.draw(screen)
            # Highlight selected scope
            scope_map = {"world": btn_scope_world, "europe": btn_scope_europe, "asia": btn_scope_asia}
            if current_map_scope in scope_map: pygame.draw.rect(screen, ACCENT_GOLD, scope_map[current_map_scope].rect, 3, border_radius=8*U)
            btn_private_toggle.draw(screen)
            btn_private_toggle.text = "Private Game" if is_private_game else "Public Game"
            btn_create_game.draw(screen); btn_create_back.draw(screen)

        elif state == "playing":
            snapshot=get_snapshot(); players=snapshot["players"]
            winner=snapshot.get("winner")
            host_disbanded=snapshot.get("host_disbanded",False)
            if host_disbanded:
                _overlay_surf.fill((0,0,0,200)); screen.blit(_overlay_surf,(0,0))
                dt=cached_render(titlefont,"Game Disbanded",ACCENT_RED)
                screen.blit(dt,(sw//2-dt.get_width()//2,sh//3))
                msg2=cached_render(font,"The host has left. Returning to menu...",TEXT_SECONDARY)
                screen.blit(msg2,(sw//2-msg2.get_width()//2,sh//3+60*U))
                pygame.display.flip(); pygame.time.wait(2000)
                state="main_menu"; game=None; mode=None; player_is_spectating=False; game_over_shown=False
                flash("Game disbanded by host."); continue
            if winner:
                _overlay_surf.fill((0,0,0,140)); screen.blit(_overlay_surf,(0,0))
                wt=cached_render(titlefont,f"{winner} Wins!",ACCENT_GOLD); screen.blit(wt,(sw//2-wt.get_width()//2,sh//3))
            turn_num=snapshot.get("turn_number",1); panel_x=sw-370*U
            draw_shadow_rect(screen,(panel_x,6*U,360*U,48*U),radius=10*U,offset=3*U,alpha=50)
            draw_gradient_rect(screen,(panel_x,6*U,360*U,48*U),(35,45,68),(25,32,50),radius=10)
            pygame.draw.rect(screen,HUD_BORDER,(panel_x,6*U,360*U,48*U),1,border_radius=10*U)
            cur_name="..."; cur_color=(120,120,120); is_my_turn_now=False
            if players and 0<=snapshot["turn_idx"]<len(players):
                cur_pl=players[snapshot["turn_idx"]]; cur_name=cur_pl.get("name","..."); cur_color=cur_pl.get("color",(120,120,120))
                if mode=="online" and cur_name==my_player_name: is_my_turn_now=True
            pygame.draw.circle(screen,cur_color,(panel_x+18*U,30*U),8*U)
            if mode in ("local","spectate") or player_is_spectating:
                is_bot=players[snapshot["turn_idx"]].get("is_bot",False) if players and 0<=snapshot["turn_idx"]<len(players) else False
                tag="(BOT)" if is_bot else ("(SPECTATING)" if player_is_spectating else "(YOU)")
                turn_text=f"Turn {turn_num} - {cur_name} {tag}"
            elif mode=="online": tag="YOUR TURN!" if is_my_turn_now else "waiting..."; turn_text=f"Turn {turn_num} - {cur_name}"
            else: turn_text=f"Turn {turn_num} - {cur_name}"
            screen.blit(cached_render(bigfont,turn_text,TEXT_PRIMARY),(panel_x+34*U,10*U))
            if mode=="online": screen.blit(cached_render(font,tag,ACCENT_GOLD if is_my_turn_now else TEXT_MUTED),(panel_x+34*U,32*U))
            if mode=="spectate" or player_is_spectating:
                screen.blit(cached_render(font,f"+/- speed Space=toggle ({spectate_tps} TPS)",TEXT_MUTED),(panel_x+34*U,36*U))

            # VFX detection
            cur_tidx=snapshot.get("turn_idx",0); snap_countries=snapshot.get("countries",{})
            for cid,rc in snap_countries.items():
                owner=rc.get("owner"); troops=int(rc.get("troops",0) or 0)
                old_owner=_last_ownership.get(cid); old_troops=_last_troops.get(cid,0)
                c=local_countries.get(cid)
                if c:
                    cx_pos,cy_pos=c.get("centroid",(0,0)); sx=int((cx_pos-cam_x)*cam_scale); sy=int((cy_pos-cam_y)*cam_scale)
                    if owner and owner!=old_owner and old_owner is not None:
                        cap_color=(255,255,255)
                        for p in players:
                            if p.get("name")==owner: cap_color=p.get("color",(255,255,255)); break
                        vfx.append({"type":"capture","x":sx,"y":sy,"t0":time.time(),"duration":VFX_CAPTURE_DURATION,"color":cap_color})
                    if troops!=old_troops and old_troops>0:
                        diff=troops-old_troops; color=ACCENT_GREEN if diff>0 else ACCENT_RED; text=f"+{diff}" if diff>0 else str(diff)
                        vfx.append({"type":"float_text","x":sx,"y":sy-10*U,"t0":time.time(),"duration":VFX_FLOAT_TEXT_DURATION,"text":text,"color":color})
                _last_ownership[cid]=owner; _last_troops[cid]=troops
            if cur_tidx!=_last_turn_idx and _last_turn_idx>=0: turn_flash_time=time.time(); turn_flash_color=cur_color
            _last_turn_idx=cur_tidx
            if time.time()-turn_flash_time<TURN_FLASH_DURATION and turn_flash_color:
                t_prog=(time.time()-turn_flash_time)/TURN_FLASH_DURATION; flash_alpha=int(100*(1.0-t_prog))
                flash_surf=pygame.Surface((sw,MAP_H),pygame.SRCALPHA); flash_surf.fill((*turn_flash_color[:3],flash_alpha)); screen.blit(flash_surf,(0,0))

            # Render VFX
            now_t=time.time(); new_vfx=[]
            for fx in vfx:
                age=now_t-fx["t0"]
                if age>fx["duration"]: continue
                new_vfx.append(fx); prog=age/fx["duration"]
                if fx["type"]=="capture":
                    r=int(15*U*prog); a=int(200*(1.0-prog))
                    pygame.draw.circle(screen,(*fx["color"][:3],a),(fx["x"],fx["y"]),r,max(1,3*U-int(2*U*prog)))
                elif fx["type"]=="float_text":
                    fy=fx["y"]-int(30*U*prog); a=int(255*(1.0-prog))
                    txt=cached_render(font,fx["text"],fx["color"]); txt_copy=txt.copy(); txt_copy.set_alpha(a)
                    screen.blit(txt_copy,(fx["x"]-txt.get_width()//2,fy))
            vfx=new_vfx

            # Player cards
            n_players=max(1,len(players)); card_margin=4*U; cards_left=8*U; cards_right=sw-8*U
            total_w=cards_right-cards_left
            card_w=max(100*U,(total_w-card_margin*(n_players-1))//n_players); card_h=74*U; y0=MAP_H+6*U
            _tc={}; _lc={}
            for v in snapshot["countries"].values():
                o=v.get("owner")
                if o: _tc[o]=_tc.get(o,0)+int(v.get("troops",0) or 0); _lc[o]=_lc.get(o,0)+1
            for i,pl in enumerate(players):
                px=cards_left+i*(card_w+card_margin); pr=pygame.Rect(px,y0,card_w,card_h)
                is_elim=pl.get("eliminated",False); is_spec=pl.get("is_spectator",False); is_host_p=pl.get("is_host",False)
                if is_elim: card_bg=(20,22,30)
                elif is_spec: card_bg=darken(HUD_BG_ACCENT,SPECTATOR_DARKEN)
                else: card_bg=HUD_BG_ACCENT
                pygame.draw.rect(screen,card_bg,pr,border_radius=8*U)
                pl_color=pl.get("color",PALETTE[i%len(PALETTE)])
                if is_elim: pl_color=darken(pl_color,100)
                pygame.draw.rect(screen,pl_color,(pr.x,pr.y,7*U,pr.h),border_radius=4*U)
                if i==snapshot["turn_idx"] and not is_elim and not is_spec:
                    pulse_w=2+int(2*abs(math.sin(time.time()*3))); pygame.draw.rect(screen,ACCENT_GOLD,pr,pulse_w,border_radius=8*U)
                else: pygame.draw.rect(screen,HUD_BORDER,pr,1,border_radius=8*U)
                name_str=pl.get("name","?");
                if pl.get("is_bot"): name_str+=" (BOT)"
                name_color=TEXT_MUTED if (is_elim or is_spec) else TEXT_PRIMARY
                ns=cached_render(font,name_str,name_color); screen.blit(ns,(pr.x+12*U,pr.y+8*U))
                if is_host_p: draw_host_star(screen,pr.x+12*U+ns.get_width()+10*U,pr.y+16*U,size=7*U)
                if is_elim: screen.blit(cached_render(smallfont,"ELIMINATED",ACCENT_RED),(pr.x+12*U,pr.y+30*U))
                elif is_spec: screen.blit(cached_render(smallfont,"SPECTATING",ACCENT_BLUE),(pr.x+12*U,pr.y+30*U))
                else:
                    pname=pl.get("name"); screen.blit(cached_render(font,f"${pl.get('money',0)}",ACCENT_GOLD),(pr.x+12*U,pr.y+30*U))
                    screen.blit(cached_render(font,f"{_tc.get(pname,0)} troops",TEXT_SECONDARY),(pr.x+12*U,pr.y+48*U))
                    screen.blit(cached_render(font,f"{_lc.get(pname,0)} land",TEXT_SECONDARY),(pr.x+card_w//2+4*U,pr.y+48*U))

            if mode!="spectate" and not player_is_spectating:
                b_peace.draw(screen); b_expand.draw(screen); b_gather.draw(screen); b_nothing.draw(screen)
            elif player_is_spectating:
                screen.blit(cached_render(font,"Spectating | +/- speed | Esc to leave",TEXT_MUTED),(8*U,buttons_y+4*U))
                btn_spectator_leave.draw(screen)

            # Render tooltip for hovered country
            if hovered_country and state == "playing":
                c = hovered_country
                rc = snapshot["countries"].get(c.get("id"), {})
                mx, my = pygame.mouse.get_pos()
                try:
                    real_w, real_h = pygame.display.get_surface().get_size()
                    s = min(real_w/WIDTH, real_h/HEIGHT)
                    if s > 0:
                        mx = int((mx - (real_w - WIDTH*s)//2) / s)
                        my = int((my - (real_h - HEIGHT*s)//2) / s)
                except:
                    pass
                tooltip_x, tooltip_y = mx + 15, my + 15
                lines = [
                    f"{c.get('name', '?')}",
                    f"Continent: {c.get('continent', '?')}",
                    f"Owner: {rc.get('owner') or 'Unclaimed'}",
                ]
                # Only show troops if fog of war allows it
                if current_game_mode != "tournament" or my_player_name:
                    show_troops = True
                    if current_game_mode == "tournament":
                        owner = rc.get('owner')
                        if owner and owner != my_player_name:
                            # Only show if owned by us or adjacent
                            show_troops = False
                            for c_adj in c.get("adj", []):
                                tgt_c = local_countries.get(c_adj["to"], {})
                                if tgt_c.get("owner") == my_player_name:
                                    show_troops = True
                                    break
                    if current_game_mode == "challenge":
                        show_troops = False
                    if show_troops:
                        lines.append(f"Troops: {rc.get('troops', 0)}")
                    else:
                        lines.append("Troops: ?")
                # Draw tooltip box
                line_h = 16*U; box_h = len(lines) * line_h + 8*U; box_w = 180*U
                tooltip_x = min(tooltip_x, sw - box_w - 4*U)
                tooltip_y = min(tooltip_y, MAP_H - box_h - 4*U)
                pygame.draw.rect(screen, HUD_BG_ACCENT, (tooltip_x, tooltip_y, box_w, box_h), border_radius=6*U)
                pygame.draw.rect(screen, HUD_BORDER, (tooltip_x, tooltip_y, box_w, box_h), 1, border_radius=6*U)
                for i, line in enumerate(lines):
                    screen.blit(cached_render(smallfont, line, TEXT_PRIMARY), (tooltip_x + 8*U, tooltip_y + 4*U + i*line_h))

            if selected_country:
                c=local_countries.get(selected_country); rc=snapshot["countries"].get(selected_country,{})
                if mode!="spectate" and not player_is_spectating:
                    screen.blit(cached_render(font,"Type target to expand.",TEXT_MUTED),(8*U,MAP_H+6*U))
                    target_key="move_target" if mode=="online" else "starting_country"; inp=small_input_rects.get(target_key)
                    if inp:
                        pygame.draw.rect(screen,(40,50,70),inp,border_radius=6*U); pygame.draw.rect(screen,HUD_BORDER,inp,1,border_radius=6*U)
                        screen.blit(cached_render(font,user_inputs.get(target_key,""),TEXT_PRIMARY),(inp.x+8*U,inp.y+6*U))

            logs=snapshot.get("logs",[]); recent=logs[-8:]
            if recent:
                log_h=len(recent)*18*U+10*U; log_w=min(sw//2,580*U); _log_surf.fill((0,0,0,0))
                pygame.draw.rect(_log_surf,(10,14,24,180),(0,0,log_w,log_h),border_radius=6*U)
                for i,l in enumerate(recent): _log_surf.blit(cached_render(font,l,TEXT_SECONDARY),(8*U,4*U+i*18*U))
                screen.blit(_log_surf,(4*U,MAP_H-log_h-2*U),(0,0,log_w,log_h))

            any_dialog=gather_dialog or (expand_send_dialog and expand_src)
            if any_dialog: _dialog_anim_t=min(1.0,_dialog_anim_t+dt*DIALOG_OPEN_SPEED)
            else: _dialog_anim_t=max(0.0,_dialog_anim_t-dt*DIALOG_CLOSE_SPEED)

            if gather_dialog and gather_slider:
                da=_dialog_anim_t; ease=1.0-(1.0-da)**3; overlay_alpha=int(160*ease)
                _overlay_surf.fill((0,0,0,overlay_alpha)); screen.blit(_overlay_surf,(0,0))
                dw,dh=500*U,180*U; dx=sw//2-dw//2; dy=int(sh//2-dh//2+40*U*(1.0-ease))
                draw_shadow_rect(screen,(dx,dy,dw,dh),radius=12*U,offset=6*U,alpha=int(60*ease))
                pygame.draw.rect(screen,HUD_BG_ACCENT,(dx,dy,dw,dh),border_radius=12*U); pygame.draw.rect(screen,HUD_BORDER,(dx,dy,dw,dh),1,border_radius=12*U)
                screen.blit(cached_render(bigfont,"Gather Troops",TEXT_PRIMARY),(dx+16*U,dy+14*U))
                screen.blit(cached_render(font,f"Cost: ${TROOP_COST} per troop",TEXT_SECONDARY),(dx+16*U,dy+50*U))
                gather_slider.draw(screen,font); gather_confirm.draw(screen); gather_cancel.draw(screen)

            if expand_send_dialog and expand_send_slider and expand_src:
                da=_dialog_anim_t; ease=1.0-(1.0-da)**3; overlay_alpha=int(180*ease)
                _overlay_surf.fill((0,0,0,overlay_alpha)); screen.blit(_overlay_surf,(0,0))
                dw,dh=520*U,200*U; dx=sw//2-dw//2; dy=int(sh//2-dh//2+40*U*(1.0-ease))
                draw_shadow_rect(screen,(dx,dy,dw,dh),radius=12*U,offset=6*U,alpha=int(60*ease))
                pygame.draw.rect(screen,HUD_BG_ACCENT,(dx,dy,dw,dh),border_radius=12*U); pygame.draw.rect(screen,HUD_BORDER,(dx,dy,dw,dh),1,border_radius=12*U)
                screen.blit(cached_render(bigfont,"Send Troops",TEXT_PRIMARY),(dx+16*U,dy+14*U))
                src_c=local_countries.get(expand_src)
                if mode=="local" and src_c: src_troops=int(src_c.get("troops",0))
                else: src_troops=int(snapshot["countries"].get(expand_src,{}).get("troops",0))
                screen.blit(cached_render(font,f"Available: {src_troops} (must leave 1)",TEXT_SECONDARY),(dx+16*U,dy+48*U))
                target_key="move_target" if mode=="online" else "starting_country"; tgt_name=user_inputs.get(target_key,"").strip()
                tgt_c=find_country_by_name(local_countries,tgt_name) if tgt_name else None
                if tgt_c:
                    tgt_info=snapshot["countries"].get(tgt_c["id"],{})
                    if not tgt_info.get("owner"): screen.blit(cached_render(font,"Unclaimed -- troops will garrison.",ACCENT_GREEN),(dx+16*U,dy+68*U))
                    else: screen.blit(cached_render(font,f"Owned by {tgt_info.get('owner')} -- attack!",ACCENT_RED),(dx+16*U,dy+68*U))
                expand_send_slider.draw(screen,font); expand_send_confirm.draw(screen); expand_send_cancel.draw(screen)

            # Game Over Dialog
            if game_over_shown:
                _overlay_surf.fill((0,0,0,200)); screen.blit(_overlay_surf,(0,0))
                dw,dh=500*U,200*U; dx=sw//2-dw//2; dy=sh//2-dh//2
                draw_shadow_rect(screen,(dx,dy,dw,dh),radius=14*U,offset=8*U,alpha=80)
                draw_gradient_rect(screen,(dx,dy,dw,dh),(40,20,20),(25,15,15),radius=14)
                pygame.draw.rect(screen,ACCENT_RED,(dx,dy,dw,dh),2,border_radius=14*U)
                dt_text=cached_render(titlefont,"DEFEATED",ACCENT_RED); screen.blit(dt_text,(sw//2-dt_text.get_width()//2,dy+20*U))
                screen.blit(cached_render(font,"You have lost all your territory.",TEXT_SECONDARY),(sw//2-140*U,dy+70*U))
                screen.blit(cached_render(font,"Leave the game or stay to spectate.",TEXT_MUTED),(sw//2-150*U,dy+95*U))
                btn_go_leave.draw(screen); btn_go_spectate.draw(screen)

        # Flash message
        if message and time.time()<msg_until:
            remaining=msg_until-time.time(); elapsed=time.time()-flash_start_time
            fade_in=min(1.0,elapsed/FLASH_FADE_IN_SECS); fade_out=min(1.0,remaining/FLASH_FADE_OUT_SECS)
            alpha=int(230*min(fade_in,fade_out)); msg_surf=cached_render(font,message,TEXT_PRIMARY)
            mw=msg_surf.get_width()+24*U; mh=msg_surf.get_height()+14*U; mx=sw//2-mw//2; my=MAP_H+(12+78+52)*U
            toast_bg=pygame.Surface((mw,mh),pygame.SRCALPHA); toast_bg.fill((30,40,60,alpha)); screen.blit(toast_bg,(mx,my))
            pygame.draw.rect(screen,(80,140,220),(mx,my,mw,mh),1,border_radius=6*U)
            ms=msg_surf.copy(); ms.set_alpha(alpha); screen.blit(ms,(mx+12*U,my+7*U))

        # Version indicator (bottom-right, all screens)
        _ver_surf = cached_render(smallfont, f"v{VERSION_STR}", TEXT_MUTED)
        screen.blit(_ver_surf, (sw - _ver_surf.get_width() - 6*U, sh - _ver_surf.get_height() - 4*U))

        if _transition_t>0.01:
            trans_alpha=int(200*_transition_t); trans_surf=pygame.Surface((sw,sh),pygame.SRCALPHA)
            trans_surf.fill((14,18,30,trans_alpha)); screen.blit(trans_surf,(0,0))

        screen = actual_screen; real_w,real_h=screen.get_size()
        if real_w>1 and real_h>1:
            s=min(real_w/WIDTH,real_h/HEIGHT); ow=int(WIDTH*s); oh=int(HEIGHT*s)
            ox=(real_w-ow)//2; oy=(real_h-oh)//2
            if ox>0 or oy>0: screen.fill((0,0,0))
            screen.blit(pygame.transform.scale(game_surf,(ow,oh)),(ox,oy))
        pygame.display.flip()
        if "--web" in sys.argv:
            import web_serve; web_serve.set_frame(game_surf, pygame)
        clock.tick(RENDER_FPS)
    pygame.quit()

if __name__ == "__main__":
    if "--web" in sys.argv:
        import web_serve; web_serve.start_server(port=1232)
        logger.info("Open http://localhost:1232 in your browser")
    main()
