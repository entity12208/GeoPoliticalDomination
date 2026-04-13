# constants.py
"""
Centralized constants, theme colors, and configuration for GeoPolitical Domination.
All magic numbers and tunable values live here.
"""

import os
import logging

logger = logging.getLogger(__name__)

# ============================================================
# Paths
# ============================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ASSET_DIR = os.path.join(BASE_DIR, "assets")
GEOJSON_CACHE = os.path.join(ASSET_DIR, "countries.geojson")
CONFIG_FILE = os.path.join(BASE_DIR, "config.txt")
VERSION_FILE = os.path.join(BASE_DIR, "version.txt")

# ============================================================
# Display & rendering
# ============================================================

WIDTH = 2560
HEIGHT = 1440
MAP_H = HEIGHT - 280
RENDER_FPS = 60       # visual frame rate (user-changeable: 60/120/240)
TPS = 10              # game logic ticks per second
U = 2                 # UI scale factor

# ============================================================
# Game economy
# ============================================================

CLAIM_COST = 200
TROOP_COST = 50
STARTING_MONEY = 500
PEACE_PAYOUT_PER_COUNTRY = 100

# ============================================================
# Map & projection
# ============================================================

MAX_MERCATOR_LAT = 85.05112878
ADJACENCY_TOUCH_THRESHOLD = 18
ADJACENCY_NEIGHBOR_RADIUS = 140
ADJACENCY_CLOSE_COST = 100    # cost for nearby but non-overlapping countries
ADJACENCY_FAR_COST = 300      # cost for distant connections
ADJACENCY_FAR_THRESHOLD = 220 # distance threshold for far cost

# ============================================================
# Camera
# ============================================================

MIN_CAMERA_SCALE = 1.0
MAX_CAMERA_SCALE = 4.0
CAMERA_LERP_FACTOR = 0.7
CAMERA_ZOOM_FACTOR = 1.18

# ============================================================
# Pins & troops display
# ============================================================

ARMY_PIN_RADIUS = 12
PIN_SCALE = 0.55
TROOP_BONUS_PER_5 = 1     # extra radius per 5 troops
TROOP_BONUS_MAX = 4

# ============================================================
# UI animation
# ============================================================

HOVER_LERP_SPEED = 12.0
PRESS_DECAY_SPEED = 6.0
DIALOG_OPEN_SPEED = 6.0
DIALOG_CLOSE_SPEED = 8.0
TRANSITION_FADE_SPEED = 4.0
TURN_FLASH_DURATION = 0.4
VFX_CAPTURE_DURATION = 0.6
VFX_FLOAT_TEXT_DURATION = 1.0
FLASH_MESSAGE_DEFAULT_SECS = 2.5
FLASH_FADE_IN_SECS = 0.2
FLASH_FADE_OUT_SECS = 0.4

# ============================================================
# Font & caching
# ============================================================

FONT_FAMILY = "segoeui,arial,sans"
FONT_SIZE_NORMAL = 16
FONT_SIZE_BIG = 26
FONT_SIZE_TITLE = 44
FONT_SIZE_PIN = 14
FONT_CACHE_MAX = 512

# ============================================================
# Color palette (players)
# ============================================================

HEX_PALETTE = [
    "#C85050", "#64C864", "#3C78C8", "#F5F5F5",
    "#D0C248", "#A050C8", "#50A0A0", "#C87A50",
]

COLOR_PALETTE = {
    "red":    (220, 70, 70),
    "green":  (60, 190, 110),
    "blue":   (55, 120, 220),
    "orange": (230, 150, 50),
    "yellow": (210, 200, 60),
    "violet": (150, 80, 200),
}
PALETTE = list(COLOR_PALETTE.values())

# ============================================================
# Theme colors
# ============================================================

SEA_COLOR       = (30, 48, 80)
SEA_COLOR_LIGHT = (38, 58, 95)
COUNTRY_BORDER_COLOR  = (20, 30, 50)
OWNED_BORDER_COLOR    = (255, 255, 255, 60)
DEFAULT_COUNTRY_FILL  = (55, 75, 105)

HUD_BG        = (22, 28, 42)
HUD_BG_ACCENT = (30, 38, 58)
HUD_BORDER    = (50, 60, 85)
TEXT_PRIMARY   = (230, 235, 245)
TEXT_SECONDARY = (150, 160, 180)
TEXT_MUTED     = (100, 110, 130)

ACCENT_GOLD   = (255, 200, 60)
ACCENT_GREEN  = (80, 210, 130)
ACCENT_RED    = (230, 80, 80)
ACCENT_BLUE   = (65, 140, 240)
ACCENT_CYAN   = (60, 200, 220)

# ============================================================
# Lobby & game state
# ============================================================

LOBBY_BG          = (18, 22, 35)
LOBBY_CARD_BG     = (28, 35, 55)
LOBBY_CARD_BORDER = (45, 55, 80)
ELIMINATED_ALPHA  = 100
SPECTATOR_DARKEN  = 60
HOST_STAR_COLOR   = ACCENT_GOLD
TURN_DOT_COLOR    = ACCENT_GREEN
KICK_BTN_COLOR    = (180, 50, 50)

# ============================================================
# Continent bonuses (canonical values — used by ALL modules)
# ============================================================

CONT_VALUES = {
    "Europe": 1000,
    "Asia": 1000,
    "North America": 800,
    "Africa": 400,
    "South America": 350,
    "Central America": 200,
}
DEFAULT_CONT_VALUE = 150


def continent_value(name):
    """Get the one-time bonus for capturing an entire continent."""
    return CONT_VALUES.get(name, DEFAULT_CONT_VALUE)


# ============================================================
# Bot difficulty presets
# ============================================================

BOT_DIFFICULTY_PRESETS = {
    "easy": {
        "attack_willingness_mult": 0.6,
        "peace_preference_mult": 1.5,
        "gather_preference_mult": 0.8,
        "continent_weight_mult": 0.7,
        "stalemate_aggression": 1.5,
        "description": "Bots prefer peace and are less aggressive",
    },
    "normal": {
        "attack_willingness_mult": 1.0,
        "peace_preference_mult": 1.0,
        "gather_preference_mult": 1.0,
        "continent_weight_mult": 1.0,
        "stalemate_aggression": 2.5,
        "description": "Balanced adaptive AI (default)",
    },
    "hard": {
        "attack_willingness_mult": 1.4,
        "peace_preference_mult": 0.6,
        "gather_preference_mult": 1.3,
        "continent_weight_mult": 1.5,
        "stalemate_aggression": 3.5,
        "description": "Bots are aggressive, strategic, and exploit weaknesses",
    },
}

DEFAULT_BOT_DIFFICULTY = "normal"


def load_config():
    """Load config.txt and return a dict of settings."""
    config = {
        "player_name": "Player",
        "default_bot_count": 3,
        "pin_x_adjust": -25,
        "pin_scale": 0.5,
        "bot_difficulty": DEFAULT_BOT_DIFFICULTY,
        "render_fps": 60,
        "resolution": "Native",
        "music_volume": DEFAULT_MUSIC_VOLUME,
        "sfx_volume": DEFAULT_SFX_VOLUME,
        "show_chat": 1,
        "show_logs": 0,
        "edge_scroll": 1,
    }
    if not os.path.exists(CONFIG_FILE):
        return config
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, _, val = line.partition("=")
                    key = key.strip()
                    val = val.strip()
                    if key in config:
                        # Try to preserve type
                        if isinstance(config[key], int):
                            try:
                                config[key] = int(val)
                            except ValueError:
                                logger.warning("Invalid int value for %s: %s", key, val)
                        elif isinstance(config[key], float):
                            try:
                                config[key] = float(val)
                            except ValueError:
                                logger.warning("Invalid float value for %s: %s", key, val)
                        else:
                            config[key] = val
    except OSError as e:
        logger.warning("Could not read config file: %s", e)
    return config


def save_config(config):
    """Write config dict back to config.txt, preserving comments."""
    lines = []
    existing_keys = set()
    # Read existing file to preserve comments and order
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    stripped = line.strip()
                    if stripped and not stripped.startswith("#") and "=" in stripped:
                        key = stripped.partition("=")[0].strip()
                        if key in config:
                            lines.append(f"{key}={config[key]}\n")
                            existing_keys.add(key)
                            continue
                    lines.append(line if line.endswith("\n") else line + "\n")
        except OSError:
            pass
    # Append any new keys not already in the file
    for key, val in config.items():
        if key not in existing_keys:
            lines.append(f"{key}={val}\n")
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            f.writelines(lines)
    except OSError as e:
        logger.warning("Could not write config file: %s", e)


def load_version():
    """Read version string from version.txt."""
    try:
        with open(VERSION_FILE, "r", encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return "?.?.?"


# ============================================================
# Resolution presets (height -> label)
# ============================================================

RESOLUTION_PRESETS = [
    (144,  "144p",  256,  144),
    (240,  "240p",  426,  240),
    (360,  "360p",  640,  360),
    (480,  "480p",  854,  480),
    (720,  "720p",  1280, 720),
    (1080, "1080p", 1920, 1080),
]


def get_difficulty_preset(name=None):
    """Get a bot difficulty preset by name. Falls back to 'normal'."""
    if name is None:
        name = DEFAULT_BOT_DIFFICULTY
    preset = BOT_DIFFICULTY_PRESETS.get(name.lower())
    if preset is None:
        logger.warning("Unknown difficulty '%s', falling back to 'normal'", name)
        preset = BOT_DIFFICULTY_PRESETS["normal"]
    return preset


# ============================================================
# Game modes (online)
# ============================================================

GAME_MODES = {
    "classic": {
        "label": "Classic",
        "description": "Standard gameplay — full visibility, chat enabled, no time limit.",
        "fog_of_war": False,
        "chat_enabled": True,
        "logs_enabled": True,
        "blind_mode": False,
        "turn_timer": 0,        # 0 = no timer
    },
    "tournament": {
        "label": "Tournament",
        "description": "Competitive mode — fog of war, no chat, no logs, 10-minute total timer.",
        "fog_of_war": True,
        "chat_enabled": False,
        "logs_enabled": False,
        "blind_mode": False,
        "turn_timer": 600,      # 10 minutes total per player
    },
    "challenge": {
        "label": "Challenge",
        "description": "Blindfolded mode — cannot see claims or troop counts on any country.",
        "fog_of_war": False,
        "chat_enabled": True,
        "logs_enabled": True,
        "blind_mode": True,
        "turn_timer": 0,
    },
}

DEFAULT_GAME_MODE = "classic"

# Map scope options
MAP_SCOPES = {
    "world": "Whole World",
    "europe": "Europe",
    "asia": "Asia",
    "africa": "Africa",
    "north_america": "North America",
    "south_america": "South America",
}

DEFAULT_MAP_SCOPE = "world"

# ============================================================
# Audio
# ============================================================

AUDIO_DIR = os.path.join(ASSET_DIR, "audio")
DEFAULT_MUSIC_VOLUME = 0.3
DEFAULT_SFX_VOLUME = 0.5

# ============================================================
# Camera (extended)
# ============================================================

CAMERA_INERTIA_DECAY = 0.92       # velocity multiplier per frame (< 1 = friction)
CAMERA_WASD_SPEED = 800.0         # world-units per second for WASD panning
CAMERA_EDGE_SCROLL_MARGIN = 30    # pixels from edge to trigger scroll
CAMERA_EDGE_SCROLL_SPEED = 600.0  # world-units per second for edge-scroll

# ============================================================
# Settings tabs
# ============================================================

SETTINGS_TABS = ["Graphics", "Audio", "Controls"]
