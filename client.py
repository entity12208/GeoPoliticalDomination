# client.py
"""
GeoPolitical Domination -- Unified Client (Local + Online)
Merged from client_local.py and client_online.py.

States:
  main_menu      -- Choose Local Game, Spectate, Online Game, or Quit
  local_setup    -- Player name + bot count slider -> Start
  spectate_setup -- Bot count slider -> Watch
  online_setup   -- Game ID, player name, player password, room password -> Create & Host / Join Room
  choose_start   -- Type starting country name
  playing        -- The actual game

A `mode` variable ("local", "spectate", or "online") is set when entering setup.
"""

import os, sys, json, math, random, subprocess, threading, time
from collections import defaultdict
import pygame
from pygame import gfxdraw

# --- optional imports (guarded) ---

# Firebase controller -- only needed for online mode
try:
    from firebase_sync import FirebaseController
    FIREBASE_AVAILABLE = True
except Exception as _fb_err:
    FirebaseController = None
    FIREBASE_AVAILABLE = False
    print("Firebase not available (online mode disabled):", _fb_err)

# Updater -- optional feature for online mode
try:
    import updater
    UPDATER_AVAILABLE = True
except Exception as _upd_err:
    updater = None
    UPDATER_AVAILABLE = False
    print(f"Updater not available: {_upd_err}")

# Heuristic bot -- only needed for local mode
try:
    import heuristic_bot
except Exception as _bot_err:
    heuristic_bot = None
    print("Warning: heuristic_bot not available:", _bot_err)

# ============================================================
# Constants & theme
# ============================================================

BASE_DIR = os.path.dirname(__file__)
ASSET_DIR = os.path.join(BASE_DIR, "assets")
GEOJSON_CACHE = os.path.join(ASSET_DIR, "countries.geojson")

WIDTH, HEIGHT = 2560, 1440
MAP_H = HEIGHT - 280
FPS = 30
U = 2  # UI scale factor (all UI pixel dimensions multiplied by this)

CLAIM_COST = 200
TROOP_COST = 50

MAX_MERCATOR_LAT = 85.05112878

# local fallback palette (hex -- same strings as server)
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

ARMY_PIN_RADIUS = 12
PIN_SCALE = 0.55

# Continent bonuses
CONT_VALUES = {
    "Europe": 1000, "Asia": 1000, "North America": 800,
    "South America": 200, "Central America": 200, "Africa": 200,
}
DEFAULT_CONT_VALUE = 150
def continent_value(n):
    return CONT_VALUES.get(n, DEFAULT_CONT_VALUE)

# ============================================================
# Geometry & projection helpers
# ============================================================

def ensure_assets():
    os.makedirs(ASSET_DIR, exist_ok=True)

def mercator_x(lon_deg, map_w):
    return (lon_deg + 180.0) / 360.0 * map_w

def mercator_y(lat_deg, map_h):
    lat = max(-MAX_MERCATOR_LAT, min(MAX_MERCATOR_LAT, lat_deg))
    lat_rad = math.radians(lat)
    merc_n = math.log(math.tan(math.pi / 4 + lat_rad / 2))
    y = (1 - merc_n / math.pi) / 2
    return y * map_h

def lonlat_to_pixel(lon, lat, map_w, map_h):
    return int(round(mercator_x(lon, map_w))), int(round(mercator_y(lat, map_h)))

def polygon_bbox(poly):
    xs = [p[0] for p in poly]; ys = [p[1] for p in poly]
    return (min(xs), min(ys), max(xs), max(ys))

def point_in_poly(x, y, poly):
    inside = False; n = len(poly); j = n - 1
    for i in range(n):
        xi, yi = poly[i]; xj, yj = poly[j]
        intersect = ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi + 1e-12) + xi)
        if intersect:
            inside = not inside
        j = i
    return inside

def polygon_centroid(poly):
    area = 0.0; cx = 0.0; cy = 0.0; n = len(poly)
    if n == 0:
        return (0, 0)
    for i in range(n):
        x0, y0 = poly[i]; x1, y1 = poly[(i + 1) % n]
        a = x0 * y1 - x1 * y0
        area += a; cx += (x0 + x1) * a; cy += (y0 + y1) * a
    if abs(area) < 1e-6:
        return (sum(p[0] for p in poly) // n, sum(p[1] for p in poly) // n)
    area = area / 2.0
    cx = cx / (6.0 * area); cy = cy / (6.0 * area)
    return (int(round(cx)), int(round(cy)))

def polygon_area(poly):
    a = 0.0; n = len(poly)
    for i in range(n):
        x0, y0 = poly[i]; x1, y1 = poly[(i + 1) % n]
        a += x0 * y1 - x1 * y0
    return a / 2.0

# ============================================================
# GeoJSON loader & adjacency
# ============================================================

def load_countries_from_geojson(path, map_w, map_h):
    data = json.load(open(path, "r", encoding="utf-8"))
    features = data.get("features", [])
    countries = {}
    cid = 1
    for feat in features:
        props = feat.get("properties", {})
        name = props.get("ADMIN") or props.get("name") or props.get("NAME") or f"Country {cid}"
        cont = props.get("REGION_UN") or props.get("continent") or props.get("region") or ""
        geom = feat.get("geometry", {}); gtype = geom.get("type", ""); coords = geom.get("coordinates", [])
        polygons_world = []
        if gtype == "Polygon":
            for ring in coords:
                pts = [lonlat_to_pixel(lon, lat, map_w, map_h) for lon, lat in ring]
                polygons_world.append(pts)
        elif gtype == "MultiPolygon":
            for poly in coords:
                for ring in poly:
                    pts = [lonlat_to_pixel(lon, lat, map_w, map_h) for lon, lat in ring]
                    polygons_world.append(pts)
        else:
            cid += 1
            continue
        if not polygons_world:
            cid += 1
            continue
        largest = max(polygons_world, key=lambda r: abs(polygon_area(r)) if r else 0)
        centroid = polygon_centroid(largest) if largest else (0, 0)
        bbox = None
        if polygons_world:
            xs = [p[0] for ring in polygons_world for p in ring]
            ys = [p[1] for ring in polygons_world for p in ring]
            bbox = (min(xs), min(ys), max(xs), max(ys))
        countries[cid] = {
            "id": cid, "name": name, "continent": cont,
            "polygons": polygons_world, "centroid": centroid, "bbox": bbox,
            "owner": None, "troops": 0, "adj": [],
        }
        cid += 1
    return countries

def build_adjacency(countries, touch_threshold=18, neigh_radius=140):
    ids = list(countries.keys())
    for i in range(len(ids)):
        a = countries[ids[i]]
        ax0, ay0, ax1, ay1 = a["bbox"] if a["bbox"] else (0, 0, 0, 0)
        for j in range(i + 1, len(ids)):
            b = countries[ids[j]]
            bx0, by0, bx1, by1 = b["bbox"] if b["bbox"] else (0, 0, 0, 0)
            overlap = not (ax1 < bx0 or bx1 < ax0 or ay1 < by0 or by1 < ay0)
            cen_a = a["centroid"]; cen_b = b["centroid"]
            if cen_a and cen_b:
                dx = cen_a[0] - cen_b[0]; dy = cen_a[1] - cen_b[1]; d = math.hypot(dx, dy)
            else:
                d = 9999
            if overlap or d <= neigh_radius:
                cost = 0 if overlap else 100 if d < 220 else 300
                a["adj"].append({"to": b["id"], "cost": cost})
                b["adj"].append({"to": a["id"], "cost": cost})

# ============================================================
# UI helpers: lighten/darken, font cache, shadow cache, Button, Slider
# ============================================================

def _lighten(color, amount=25):
    return tuple(min(255, c + amount) for c in color[:3])

def _darken(color, amount=25):
    return tuple(max(0, c - amount) for c in color[:3])

# Font render cache (avoids re-rendering the same text every frame)
_font_cache = {}
_FONT_CACHE_MAX = 512

def cached_render(fnt, text, color):
    key = (id(fnt), text, color)
    surf = _font_cache.get(key)
    if surf is None:
        if len(_font_cache) >= _FONT_CACHE_MAX:
            _font_cache.clear()
        surf = fnt.render(text, True, color)
        _font_cache[key] = surf
    return surf

# Shadow cache (avoids allocating a new Surface per shadow per frame)
_shadow_cache = {}

def draw_shadow_rect(surface, rect, radius=10, offset=3, alpha=50):
    x, y, w, h = rect
    key = (w, h, radius, offset, alpha)
    shadow = _shadow_cache.get(key)
    if shadow is None:
        shadow = pygame.Surface((w + offset * 2, h + offset * 2), pygame.SRCALPHA)
        pygame.draw.rect(shadow, (0, 0, 0, alpha), (offset, offset, w, h), border_radius=radius)
        _shadow_cache[key] = shadow
    surface.blit(shadow, (x - offset, y - offset))

def draw_rounded_rect(surface, rect, color, radius=10, border=0, border_color=None):
    x, y, w, h = rect
    if border > 0:
        pygame.draw.rect(surface, border_color or color, (x, y, w, h), border, border_radius=radius)
    else:
        pygame.draw.rect(surface, color, (x, y, w, h), border_radius=radius)

class Button:
    """Cached button with hover highlighting."""
    def __init__(self, rect, text, font, bg=(55, 120, 220), fg=(255, 255, 255)):
        self.rect = pygame.Rect(rect)
        self.text = text; self.font = font; self.bg = bg; self.fg = fg
        self.hover = False; self._cache = None; self._cache_hover = None

    def _build_cache(self, hover):
        r = self.rect; col = _lighten(self.bg, 20) if hover else self.bg
        pad = max(4, r.h // 10)
        br = max(6, r.h // 4)
        surf = pygame.Surface((r.w + pad*2, r.h + pad*2), pygame.SRCALPHA)
        # shadow
        pygame.draw.rect(surf, (0, 0, 0, 40), (pad, pad+1, r.w, r.h), border_radius=br)
        # bg
        pygame.draw.rect(surf, col, (pad//2, pad//2, r.w, r.h), border_radius=br)
        # top highlight
        hl = pygame.Surface((r.w - pad, max(1, r.h // 3)), pygame.SRCALPHA)
        hl.fill((*_lighten(col, 40), 50))
        surf.blit(hl, (pad, pad//2 + 1))
        # text
        t = cached_render(self.font, self.text, self.fg)
        surf.blit(t, (pad//2 + r.w // 2 - t.get_width() // 2, pad//2 + r.h // 2 - t.get_height() // 2))
        return surf

    def draw(self, surf):
        pad = max(4, self.rect.h // 10)
        if self.hover:
            if self._cache_hover is None:
                self._cache_hover = self._build_cache(True)
            surf.blit(self._cache_hover, (self.rect.x - pad//2, self.rect.y - pad//2))
        else:
            if self._cache is None:
                self._cache = self._build_cache(False)
            surf.blit(self._cache, (self.rect.x - pad//2, self.rect.y - pad//2))

    def handle_event(self, ev):
        if ev.type == pygame.MOUSEMOTION:
            self.hover = self.rect.collidepoint(ev.pos)
        if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1 and self.rect.collidepoint(ev.pos):
            return True
        return False

class Slider:
    def __init__(self, rect, a, b, initial):
        self.rect = pygame.Rect(rect); self.min = int(a); self.max = int(b)
        self.value = int(initial); self.dragging = False

    def draw(self, surf, font):
        th = max(6, self.rect.h // 4)  # track height scales with rect
        tr = th // 2
        track = pygame.Rect(self.rect.x, self.rect.centery - th//2, self.rect.width, th)
        pygame.draw.rect(surf, (50, 60, 85), track, border_radius=tr)
        frac = (self.value - self.min) / max(1, (self.max - self.min))
        fill_w = int(track.width * frac)
        if fill_w > 0:
            pygame.draw.rect(surf, (55, 160, 220), (track.x, track.y, fill_w, track.height), border_radius=tr)
        thumb_x = track.x + int(track.width * frac); thumb_y = track.centery
        thumb_r = max(8, self.rect.h // 2)
        pygame.draw.circle(surf, (0, 0, 0), (thumb_x + 1, thumb_y + 1), thumb_r + 1)
        pygame.draw.circle(surf, (255, 255, 255), (thumb_x, thumb_y), thumb_r)
        pygame.draw.circle(surf, (55, 160, 220), (thumb_x, thumb_y), thumb_r, 2)
        t = cached_render(font, str(self.value), TEXT_PRIMARY)
        surf.blit(t, (self.rect.x + self.rect.width + 12*U, self.rect.y))

    def handle_event(self, ev):
        if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1 and self.rect.collidepoint(ev.pos):
            self.dragging = True; self.update_from(ev.pos); return True
        if ev.type == pygame.MOUSEBUTTONUP and ev.button == 1:
            self.dragging = False
        if ev.type == pygame.MOUSEMOTION and self.dragging:
            self.update_from(ev.pos)
        return False

    def update_from(self, pos):
        x = pos[0]; left = self.rect.x; w = self.rect.width
        frac = (x - left) / w if w else 0; frac = max(0.0, min(1.0, frac))
        self.value = int(round(self.min + frac * (self.max - self.min)))

# ============================================================
# Name lookup & obfuscated UI text (shared)
# ============================================================

def find_country_by_name(countries, name):
    if not name:
        return None
    name = name.strip().casefold()
    for cid, c in countries.items():
        if (c.get("name", "") or "").strip().casefold() == name:
            return c
    return None

def obf_claim_msg(player, continent, troops):
    return f"{player} claimed a country in {continent} with {troops} troops."

def obf_attack_msg(player, continent, attack_roll=None, defend_roll=None, success=False, send=0):
    if attack_roll is None:
        return f"{player} moved {send} troops into {continent}."
    if success:
        return f"{player} (atk {attack_roll}) attacked in {continent} and succeeded."
    else:
        return f"{player} (atk {attack_roll}) attacked in {continent} and failed."

# ============================================================
# LOCAL mode: Player, Game, actions, bot adapter
# ============================================================

class Player:
    def __init__(self, name, is_bot=False, color=None):
        self.name = name; self.money = 500; self.is_bot = is_bot
        self.vulnerable = False; self.was_attacked = False
        self.owned = set(); self.color = color if color else random.choice(PALETTE)
        self.troop_buy_limit = 20
        self.last_gather_turn = 0

    def troop_count(self, countries):
        return sum(int(c.get("troops", 0)) for c in countries.values() if c.get("owner") == self.name)

    def country_count(self):
        return len(self.owned)

class Game:
    def __init__(self, players, countries):
        self.players = players
        self.countries = countries
        self.turn_idx = random.randrange(len(players)) if players else 0
        self.turn_number = 1
        self.logs = []
        self.bot_thread = None

    def log(self, msg):
        ts = time.strftime("%H:%M:%S"); line = f"[{ts}] {msg}"; self.logs.append(line)
        try:
            print(line)
        except Exception:
            pass

def check_and_pay_continent_bonus(game, player, continent_name):
    if not continent_name:
        return
    cont_countries = [c for c in game.countries.values() if (c.get("continent", "") or "") == continent_name]
    if not cont_countries:
        return
    if all(c.get("owner") == player.name for c in cont_countries):
        bonus = continent_value(continent_name)
        player.money += bonus
        game.log(f"{player.name} captured a continent ({continent_name}) and received ${bonus}.")

def claim_country(player, country, troops, game):
    if player.money < CLAIM_COST:
        game.log(f"{player.name} cannot afford to claim that country (need ${CLAIM_COST}).")
        return False
    player.money -= CLAIM_COST
    prev = country.get("owner")
    if prev:
        prevpl = next((p for p in game.players if p.name == prev), None)
        if prevpl and country["id"] in prevpl.owned:
            prevpl.owned.remove(country["id"])
    country["owner"] = player.name; country["troops"] = troops; player.owned.add(country["id"])
    game.log(f"{player.name} claimed a country in {country.get('continent', 'unknown')} with {troops} troops (paid ${CLAIM_COST}).")
    try:
        check_and_pay_continent_bonus(game, player, country.get("continent", ""))
    except Exception:
        pass
    return True

def attack_country(attacker, source_country, target_country, send_troops, game):
    src_available = int(source_country.get("troops", 0) or 0)
    if send_troops <= 0 or send_troops >= src_available:
        game.log(f"{attacker.name} attempted to send {send_troops} troops but only {src_available} available (must leave at least 1).")
        return False
    source_country["troops"] = max(0, src_available - send_troops)
    defender_name = target_country.get("owner")
    defender = next((p for p in game.players if p.name == defender_name), None) if defender_name else None

    if defender and defender.vulnerable:
        if attacker.money < CLAIM_COST:
            game.log(f"{attacker.name} cannot afford the claim cost (${CLAIM_COST}); attack aborted.")
            source_country["troops"] += send_troops
            return False
        attacker.money -= CLAIM_COST
        if defender and target_country["id"] in defender.owned:
            defender.owned.remove(target_country["id"])
        target_country["owner"] = attacker.name; target_country["troops"] = send_troops
        attacker.owned.add(target_country["id"])
        game.log(f"{attacker.name} swept vulnerable territory in {target_country.get('continent', 'unknown')} and took it with {send_troops} troops (paid ${CLAIM_COST}).")
        if defender:
            defender.was_attacked = True
        try:
            check_and_pay_continent_bonus(game, attacker, target_country.get("continent", ""))
        except Exception:
            pass
        return True

    atk_roll = random.randint(1, 20)
    d1 = random.randint(1, 20); d2 = random.randint(1, 20); def_best = max(d1, d2)
    game.log(f"{attacker.name} (atk {atk_roll}) attacks territory in {target_country.get('continent', 'unknown')} owned by {defender_name or 'nobody'} (def [{d1},{d2}] -> {def_best})")
    if atk_roll > def_best:
        if attacker.money < CLAIM_COST:
            game.log(f"{attacker.name} won the fight but couldn't pay the claim (${CLAIM_COST}); troops returned to source.")
            source_country["troops"] += send_troops
            return False
        attacker.money -= CLAIM_COST
        if defender and target_country["id"] in defender.owned:
            defender.owned.remove(target_country["id"])
        target_country["owner"] = attacker.name; target_country["troops"] = send_troops
        attacker.owned.add(target_country["id"])
        game.log(f"{attacker.name} won and captured territory in {target_country.get('continent', 'unknown')} with {send_troops} troops (paid ${CLAIM_COST}).")
        if defender:
            defender.was_attacked = True
        try:
            check_and_pay_continent_bonus(game, attacker, target_country.get("continent", ""))
        except Exception:
            pass
        return True
    else:
        game.log(f"{attacker.name} attacked but lost; {send_troops} attacking troops were destroyed.")
        if defender:
            defender.was_attacked = True
        return False

def resolve_peace_if_needed(game, player):
    """Resolve a player's vulnerability from a previous PEACE.
    Called at the START of their turn, before they act."""
    if player.vulnerable:
        if not player.was_attacked:
            payout = 100 * max(0, player.country_count())
            player.money += payout
            game.log(f"{player.name} was peaceful and earned ${payout} (${100} x {player.country_count()} countries).")
        else:
            game.log(f"{player.name} was attacked while vulnerable — no PEACE payout.")
        player.vulnerable = False; player.was_attacked = False

def end_turn_housekeeping(game, player):
    """Advance to next player and resolve their vulnerability if any."""
    game.turn_number += 1
    if not game.players:
        return
    game.turn_idx = (game.turn_idx + 1) % len(game.players)
    # Resolve next player's PEACE vulnerability from their previous turn
    resolve_peace_if_needed(game, game.players[game.turn_idx])

# Bot adapter (local only)
def decide_local_bot(game, player):
    if heuristic_bot is None:
        return None
    snapshot = {"players": [], "pins": []}
    for pl in game.players:
        snapshot["players"].append({
            "name": pl.name, "money": pl.money, "is_bot": pl.is_bot,
            "vulnerable": bool(pl.vulnerable), "was_attacked": bool(pl.was_attacked),
        })
    for cid, c in game.countries.items():
        snapshot["pins"].append({
            "id": c["id"], "name": c["name"], "owner": c.get("owner"),
            "troops": int(c.get("troops", 0)),
            "adj": [{"to": a["to"], "cost": a.get("cost", 0)} for a in c.get("adj", [])],
            "continent": c.get("continent", ""),
        })
    try:
        return heuristic_bot.decide(snapshot, player.name)
    except Exception as e:
        print("heuristic_bot error:", e)
        return None

# ============================================================
# ONLINE mode: RemoteGameView, color helpers
# ============================================================

class RemoteGameView:
    def __init__(self):
        self.players = []
        self.countries = {}
        self.turn_idx = 0
        self.turn_number = 1
        self.logs = []
        self.status = "waiting"
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
            return {
                "players": list(self.players),
                "countries": dict(self.countries),
                "turn_idx": self.turn_idx,
                "turn_number": self.turn_number,
                "logs": list(self.logs),
                "status": self.status,
            }

def hex_to_rgb(hexstr):
    if not hexstr:
        return None
    if isinstance(hexstr, (list, tuple)):
        try:
            return (int(hexstr[0]), int(hexstr[1]), int(hexstr[2]))
        except Exception:
            return None
    s = hexstr.strip()
    if s.startswith("#"):
        s = s[1:]
    if len(s) == 3:
        s = "".join([c * 2 for c in s])
    if len(s) < 6:
        return None
    try:
        r = int(s[0:2], 16); g = int(s[2:4], 16); b = int(s[4:6], 16)
        return (r, g, b)
    except Exception:
        return None

def get_player_color_rgb(player_name, snapshot_players):
    if not player_name:
        return (120, 120, 120)
    for p in snapshot_players:
        if p.get("name") == player_name:
            col = p.get("color")
            rgb = hex_to_rgb(col)
            if rgb:
                return rgb
    # fallback deterministic by name into HEX_PALETTE
    idx = sum(ord(c) for c in (player_name or "")) % len(HEX_PALETTE)
    return hex_to_rgb(HEX_PALETTE[idx])

# ============================================================
# main()
# ============================================================

def main():
    ensure_assets()
    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("GeoPolitical Domination")
    clock = pygame.time.Clock()
    font = pygame.font.SysFont("segoeui,arial,sans", 16 * U)
    bigfont = pygame.font.SysFont("segoeui,arial,sans", 26 * U, bold=True)
    titlefont = pygame.font.SysFont("segoeui,arial,sans", 44 * U, bold=True)
    pinfont = pygame.font.SysFont("segoeui,arial,sans", 14 * U, bold=True)

    # Pre-allocate reusable overlay surfaces
    _overlay_surf = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
    _log_surf = pygame.Surface((580 * U, 160 * U), pygame.SRCALPHA)

    # Load local geojson countries (polygon data used in ALL modes for rendering)
    local_countries = {}
    if os.path.exists(GEOJSON_CACHE):
        try:
            local_countries = load_countries_from_geojson(GEOJSON_CACHE, WIDTH, MAP_H)
            print("Loaded geojson countries:", len(local_countries))
        except Exception as e:
            print("Error parsing geojson:", e)
    if not local_countries:
        local_countries = {
            1: {"id": 1, "name": "Aland", "continent": "X",
                "polygons": [[(200, 120), (260, 120), (260, 170), (200, 170)]],
                "centroid": (230, 145), "bbox": (200, 120, 260, 170),
                "owner": None, "troops": 0, "adj": []},
            2: {"id": 2, "name": "Boria", "continent": "X",
                "polygons": [[(300, 120), (360, 120), (360, 170), (300, 170)]],
                "centroid": (330, 145), "bbox": (300, 120, 360, 170),
                "owner": None, "troops": 0, "adj": []},
        }
    build_adjacency(local_countries)

    # Base map rendering
    map_surface = pygame.Surface((WIDTH, MAP_H))

    def render_base_map():
        for y in range(0, MAP_H, 2):
            t = y / MAP_H
            r = int(SEA_COLOR[0] + (SEA_COLOR_LIGHT[0] - SEA_COLOR[0]) * t)
            g = int(SEA_COLOR[1] + (SEA_COLOR_LIGHT[1] - SEA_COLOR[1]) * t)
            b = int(SEA_COLOR[2] + (SEA_COLOR_LIGHT[2] - SEA_COLOR[2]) * t)
            pygame.draw.line(map_surface, (r, g, b), (0, y), (WIDTH, y))
            if y + 1 < MAP_H:
                pygame.draw.line(map_surface, (r, g, b), (0, y + 1), (WIDTH, y + 1))
        for cid, c in local_countries.items():
            h = (cid * 37) % 20 - 10
            c_fill = (
                max(0, min(255, DEFAULT_COUNTRY_FILL[0] + h)),
                max(0, min(255, DEFAULT_COUNTRY_FILL[1] + h)),
                max(0, min(255, DEFAULT_COUNTRY_FILL[2] + h)),
            )
            for ring in c["polygons"]:
                if len(ring) >= 3:
                    try:
                        pygame.draw.polygon(map_surface, c_fill, ring)
                        pygame.draw.polygon(map_surface, COUNTRY_BORDER_COLOR, ring, 1)
                    except Exception:
                        pass

    render_base_map()

    # Camera (zoom/pan) -- available in ALL modes
    cam_scale = 1.0; cam_target_scale = 1.0
    cam_x = 0.0; cam_y = 0.0; cam_target_x = cam_x; cam_target_y = cam_y
    min_scale = 1.0; max_scale = 4.0
    dragging_pan = False; pan_start = (0, 0); cam_start = (0, 0)

    # Scaled map cache
    _cached_scaled_map = None; _cached_scale_key = None
    # Ownership surface cache (local mode)
    _own_surface = pygame.Surface((WIDTH, MAP_H), pygame.SRCALPHA)
    _own_dirty = True
    _own_turn = -1
    hovered_country = None

    # ----------------------------------------------------------------
    # State machine
    # ----------------------------------------------------------------
    mode = None          # "local" or "online"
    state = "main_menu"  # main_menu | local_setup | online_setup | choose_start | playing
    message = ""; msg_until = 0
    fullscreen = False
    # Internal render surface — always WIDTH x HEIGHT. Scaled to fit actual screen.
    game_surf = pygame.Surface((WIDTH, HEIGHT))

    # Local mode objects
    game = None  # Game instance

    # Online mode objects
    fc = None          # FirebaseController instance
    remote = None      # RemoteGameView instance
    current_game_id = None
    my_player_name = None
    network_thread = None
    network_result = None
    network_loading = False
    game_id_in_progress = None
    player_name_in_progress = None

    # Updater state
    update_info = None
    update_check_done = False
    update_btn = None
    dismiss_btn = None
    update_progress = None   # {"phase": str, "percent": float, "message": str} or None
    update_thread = None

    # Input fields -- all fields for both modes; only relevant ones shown per state
    input_active = {
        "player_name": False, "starting_country": False, "move_target": False,
        "game_id": False, "player_password": False, "room_password": False,
    }
    user_inputs = {
        "player_name": "Player", "starting_country": "", "move_target": "",
        "game_id": "room1", "player_password": "", "room_password": "",
    }
    small_input_rects = {
        "player_name": pygame.Rect(WIDTH // 2 - 260*U, 350*U, 520*U, 36*U),
        "starting_country": pygame.Rect(WIDTH // 2 - 260*U, 420*U, 520*U, 36*U),
        "move_target": pygame.Rect(WIDTH // 2 - 260*U, MAP_H + 8*U + 120*U, 520*U, 28*U),
        "game_id": pygame.Rect(WIDTH // 2 - 260*U, 160*U, 520*U, 36*U),
        "player_password": pygame.Rect(WIDTH // 2 - 260*U, 260*U, 520*U, 36*U),
        "room_password": pygame.Rect(WIDTH // 2 - 260*U, 310*U, 520*U, 36*U),
    }

    # Game-play state
    selected_country = None   # int cid or None
    expand_src = None          # int cid or None
    expand_mode = None
    expand_send_dialog = False; expand_send_slider = None
    expand_send_confirm = None; expand_send_cancel = None
    gather_dialog = False; gather_slider = None
    gather_confirm = None; gather_cancel = None

    # Main-menu buttons
    btn_local = Button((WIDTH // 2 - 200*U, 200*U, 400*U, 48*U), "Local Game", bigfont, bg=(55, 160, 120))
    btn_spectate = Button((WIDTH // 2 - 200*U, 260*U, 400*U, 48*U), "Spectate Bots", bigfont, bg=(180, 140, 50))
    btn_online = Button((WIDTH // 2 - 200*U, 320*U, 400*U, 48*U), "Online Game", bigfont, bg=(55, 130, 210))
    btn_quit_main = Button((WIDTH // 2 - 200*U, 380*U, 400*U, 48*U), "Quit", bigfont, bg=(160, 60, 60))

    # Local setup buttons
    bot_slider = Slider((WIDTH // 2 - 200*U, 380*U, 400*U, 36*U), 0, 6, 2)
    btn_start_local = Button((WIDTH // 2 - 200*U, 440*U, 400*U, 52*U), "Start", bigfont, bg=(55, 160, 120))

    # Spectate setup buttons
    spectate_slider = Slider((WIDTH // 2 - 200*U, 300*U, 400*U, 36*U), 2, 8, 4)
    btn_start_spectate = Button((WIDTH // 2 - 200*U, 380*U, 400*U, 52*U), "Watch", bigfont, bg=(180, 140, 50))

    # Playing action buttons (will be used for both modes)
    buttons_y = MAP_H + 8*U + 78*U + 12*U
    btn_w = 170*U; btn_h = 38*U; gap = 10*U; ax = 8*U; ay = buttons_y
    b_peace = Button((ax, ay, btn_w, btn_h), "Peace", font, bg=(50, 170, 110))
    b_expand = Button((ax + btn_w + gap, ay, btn_w, btn_h), "Expand", font, bg=(55, 130, 210))
    b_gather = Button((ax + 2 * (btn_w + gap), ay, btn_w, btn_h), "Gather Troops", font, bg=(200, 150, 40))
    b_nothing = Button((ax + 3 * (btn_w + gap), ay, btn_w, btn_h), "Do Nothing", font, bg=(150, 60, 60))

    # ----------------------------------------------------------------
    # Helper closures
    # ----------------------------------------------------------------

    def _screen_to_game(pos):
        """Convert actual screen mouse coords to game-surface coords."""
        if not fullscreen:
            return pos
        real_w, real_h = screen.get_size()
        scale = min(real_w / WIDTH, real_h / HEIGHT)
        ow = int(WIDTH * scale); oh = int(HEIGHT * scale)
        ox = (real_w - ow) // 2; oy = (real_h - oh) // 2
        gx = (pos[0] - ox) / scale; gy = (pos[1] - oy) / scale
        return (int(gx), int(gy))

    def flash(msg, secs=2.5):
        nonlocal message, msg_until
        message = msg; msg_until = time.time() + secs
        print("[UI]", msg)

    def draw_input_box(key, label, hide_password=False):
        r = small_input_rects[key]
        active = input_active.get(key, False)
        bg = (40, 50, 70) if not active else (50, 62, 88)
        border = (80, 140, 220) if active else HUD_BORDER
        pygame.draw.rect(screen, bg, r, border_radius=6*U)
        pygame.draw.rect(screen, border, r, 2, border_radius=6*U)
        txt = user_inputs.get(key, "")
        if hide_password and txt:
            display_txt = "*" * len(txt)
        else:
            display_txt = txt
        t = cached_render(font, display_txt, TEXT_PRIMARY)
        screen.blit(t, (r.x + 10*U, r.y + 9*U))
        label_surf = cached_render(font, label, TEXT_SECONDARY)
        screen.blit(label_surf, (r.x, r.y - 20*U))

    def handle_key_input(ev):
        if ev.key == pygame.K_BACKSPACE:
            for k, v in input_active.items():
                if v:
                    user_inputs[k] = user_inputs[k][:-1]
        elif ev.key == pygame.K_RETURN:
            for k, v in input_active.items():
                if v:
                    input_active[k] = False
        else:
            ch = ev.unicode
            if ch and len(ch) == 1:
                for k, v in input_active.items():
                    if v:
                        user_inputs[k] += ch

    def country_at_world_point(wx, wy):
        for cid, c in local_countries.items():
            bbox = c.get("bbox")
            if bbox:
                if wx < bbox[0] or wx > bbox[2] or wy < bbox[1] or wy > bbox[3]:
                    continue
            for ring in c["polygons"]:
                rx0, ry0, rx1, ry1 = polygon_bbox(ring)
                if wx < rx0 or wx > rx1 or wy < ry0 or wy > ry1:
                    continue
                if point_in_poly(wx, wy, ring):
                    return c
        return None

    # ---- unified snapshot ----
    def get_snapshot():
        """Return a unified snapshot dict regardless of mode."""
        if mode in ("local", "spectate") and game:
            players = []
            for pl in game.players:
                players.append({
                    "name": pl.name, "money": pl.money, "is_bot": pl.is_bot,
                    "color": pl.color,  # already RGB tuple
                    "vulnerable": bool(pl.vulnerable), "was_attacked": bool(pl.was_attacked),
                })
            countries = {}
            for cid, c in game.countries.items():
                countries[cid] = {
                    "owner": c.get("owner"), "troops": int(c.get("troops", 0)),
                    "continent": c.get("continent", ""),
                }
            return {
                "players": players,
                "countries": countries,
                "turn_idx": game.turn_idx,
                "turn_number": game.turn_number,
                "logs": list(game.logs),
            }
        elif mode == "online" and remote:
            raw = remote.snapshot()
            # Normalize: convert str country keys to int, hex colors to RGB
            players = []
            for p in raw.get("players", []):
                col = p.get("color")
                if isinstance(col, str):
                    col = hex_to_rgb(col)
                elif isinstance(col, (list, tuple)) and len(col) >= 3:
                    col = (int(col[0]), int(col[1]), int(col[2]))
                else:
                    col = (120, 120, 120)
                players.append({
                    "name": p.get("name", "?"),
                    "money": int(p.get("money", 0) or 0),
                    "is_bot": p.get("is_bot", False),
                    "color": col,
                    "vulnerable": p.get("vulnerable", False),
                    "was_attacked": p.get("was_attacked", False),
                })
            countries = {}
            for k, v in raw.get("countries", {}).items():
                try:
                    int_k = int(k)
                except (ValueError, TypeError):
                    continue
                countries[int_k] = {
                    "owner": v.get("owner"),
                    "troops": int(v.get("troops", 0) or 0),
                    "continent": v.get("continent", local_countries.get(int_k, {}).get("continent", "")),
                }
            return {
                "players": players,
                "countries": countries,
                "turn_idx": raw.get("turn_idx", 0),
                "turn_number": raw.get("turn_number", 1),
                "logs": raw.get("logs", []),
            }
        else:
            return {"players": [], "countries": {}, "turn_idx": 0, "turn_number": 1, "logs": []}

    # ---- action callbacks ----
    def do_action(action_type, params):
        nonlocal game
        if mode in ("local", "spectate") and game:
            cur = game.players[game.turn_idx]
            if action_type == "PEACE":
                cur.vulnerable = True; cur.was_attacked = False
                game.log(f"{cur.name} chose PEACE")
                end_turn_housekeeping(game, cur)
            elif action_type == "NOTHING":
                game.log(f"{cur.name} did NOTHING")
                end_turn_housekeeping(game, cur)
            elif action_type == "GATHER":
                buy = params.get("buy", 0)
                cost = buy * TROOP_COST
                if buy > 0 and cur.money >= cost:
                    cur.money -= cost
                    owned_countries = [c for c in game.countries.values() if c.get("owner") == cur.name]
                    if owned_countries:
                        i = 0
                        while buy > 0:
                            owned_countries[i % len(owned_countries)]["troops"] += 1
                            buy -= 1; i += 1
                    game.log(f"{cur.name} bought troops for ${cost}")
                else:
                    game.log(f"{cur.name} bought 0 troops")
                end_turn_housekeeping(game, cur)
            elif action_type == "EXPAND":
                src_id = params.get("src"); tgt_id = params.get("tgt")
                send_amt = params.get("send", 1)
                src = game.countries.get(src_id); tgt = game.countries.get(tgt_id)
                if not src or not tgt:
                    flash("Invalid source or target.")
                    return
                adj = next((a for a in src.get("adj", []) if a["to"] == tgt_id), None)
                if not adj:
                    flash("Not adjacent"); return
                cost = adj.get("cost", 0)
                if cost > 0:
                    if cur.money >= cost:
                        cur.money -= cost; game.log(f"{cur.name} paid crossing ${cost}")
                    else:
                        game.log(f"{cur.name} cannot pay crossing; cancelled")
                        return
                actual_available = int(src.get("troops", 0))
                if send_amt >= actual_available:
                    send_amt = max(1, actual_available - 1)
                    if send_amt <= 0:
                        game.log("Not enough troops to send.")
                        end_turn_housekeeping(game, cur)
                        return
                src["troops"] -= send_amt
                if src["troops"] <= 0:
                    prev = src.get("owner")
                    if prev:
                        op = next((pl for pl in game.players if pl.name == prev), None)
                        if op and src["id"] in op.owned:
                            op.owned.remove(src["id"])
                    src["owner"] = None; src["troops"] = 0
                    game.log(f"A territory is now unowned")
                if not tgt.get("owner"):
                    success = claim_country(cur, tgt, send_amt, game)
                    if not success:
                        src["troops"] += send_amt
                else:
                    attack_country(cur, src, tgt, send_amt, game)
                end_turn_housekeeping(game, cur)
        elif mode == "online" and fc:
            try:
                fc.submit_action(current_game_id, my_player_name, action_type, params)
            except Exception as e:
                flash(f"{action_type} failed: {e}")

    def do_start_claim(country_id):
        nonlocal state, game
        if mode in ("local", "spectate") and game:
            c = game.countries.get(country_id)
            if not c:
                flash("Invalid country."); return False
            if c.get("owner"):
                flash("That country is already owned. Pick another."); return False
            human = game.players[0]
            c["owner"] = human.name; c["troops"] = 1; human.owned.add(c["id"])
            game.log(obf_claim_msg(human.name, c.get("continent", "unknown"), 1))
            state = "playing"; flash("Starting country claimed. Game begins.")
            return True
        elif mode == "online" and fc:
            try:
                ok = fc.claim_starting_country(current_game_id, my_player_name, country_id)
            except Exception as e:
                flash(f"Claim failed: {e}"); return False
            if ok:
                flash("Successfully claimed that starting country.")
                state = "playing"
                return True
            else:
                flash("That country was just taken. Pick another.")
                return False
        return False

    def is_my_turn():
        snap = get_snapshot()
        players = snap["players"]
        if not players:
            return False
        idx = snap["turn_idx"]
        if idx < 0 or idx >= len(players):
            return False
        if mode == "local":
            return not players[idx].get("is_bot", False)
        else:
            return players[idx].get("name") == my_player_name

    # ---- local mode helpers ----
    def start_local_game(human_name, bot_count):
        nonlocal game
        for c in local_countries.values():
            c["owner"] = None; c["troops"] = 0
        palette = PALETTE.copy(); random.shuffle(palette)
        players = []
        human = Player(human_name, is_bot=False, color=palette.pop() if palette else random.choice(PALETTE))
        players.append(human)
        for i in range(bot_count):
            players.append(Player(f"bot{i + 1}", is_bot=True, color=palette.pop() if palette else random.choice(PALETTE)))
        for pl in players:
            if pl.is_bot:
                empty = [c for c in local_countries.values() if not c.get("owner")]
                if not empty:
                    break
                pick = random.choice(empty)
                pick["owner"] = pl.name; pick["troops"] = 1; pl.owned.add(pick["id"])
        game = Game(players, local_countries)

    def start_spectate_game(bot_count):
        """Start a game with only bots — human watches."""
        nonlocal game
        for c in local_countries.values():
            c["owner"] = None; c["troops"] = 0
        palette = PALETTE.copy(); random.shuffle(palette)
        players = []
        for i in range(bot_count):
            players.append(Player(f"bot{i + 1}", is_bot=True, color=palette.pop() if palette else random.choice(PALETTE)))
        for pl in players:
            empty = [c for c in local_countries.values() if not c.get("owner")]
            if not empty:
                break
            pick = random.choice(empty)
            pick["owner"] = pl.name; pick["troops"] = 1; pl.owned.add(pick["id"])
        game = Game(players, local_countries)

    # ---- online mode helpers ----
    def build_minimal_countries_for_upload():
        minimal = {}
        for cid, c in local_countries.items():
            minimal[str(cid)] = {"owner": None, "troops": 0, "continent": c.get("continent", "")}
        return minimal

    def init_online():
        nonlocal fc, remote
        if not FIREBASE_AVAILABLE:
            flash("Firebase not available. Cannot use online mode.")
            return False
        try:
            fc = FirebaseController()
        except Exception as e:
            flash(f"Failed to create FirebaseController: {e}")
            return False
        remote = RemoteGameView()
        return True

    # ----------------------------------------------------------------
    # Main loop
    # ----------------------------------------------------------------
    running = True

    # --- Check for updates at startup (background) ---
    if UPDATER_AVAILABLE:
        def _update_check_bg():
            nonlocal update_info, update_check_done
            try:
                update_info = updater.silent_check()
            except Exception as e:
                print(f"Update check failed: {e}")
            update_check_done = True
        threading.Thread(target=_update_check_bg, daemon=True).start()
    else:
        update_check_done = True

    while running:
        # --- Auto-restart after update ---
        if update_progress and update_progress.get("phase") == "done":
            # Wait a moment for the user to see the message, then restart
            time.sleep(1.5)
            pygame.quit()
            os.execv(sys.executable, [sys.executable, os.path.join(BASE_DIR, "client.py")])

        # --- network result check (online mode) ---
        if mode == "online" and network_loading and network_thread and not network_thread.is_alive():
            network_loading = False
            if isinstance(network_result, Exception):
                flash(f"Failed: {network_result}")
            elif network_result:
                doc = network_result
                current_game_id = game_id_in_progress
                my_player_name = player_name_in_progress
                if not doc.get("countries"):
                    minimal = build_minimal_countries_for_upload()
                    fc.upload_initial_countries(current_game_id, minimal)
                fc.listen_to_game(current_game_id, lambda d: remote.update_from_doc(d))
                has_country = False
                for k, v in (doc.get("countries") or {}).items():
                    if v.get("owner") == my_player_name:
                        has_country = True; break
                if has_country:
                    state = "playing"; flash(f"Joined room '{current_game_id}' as {my_player_name}")
                else:
                    state = "choose_start"; flash("Type the exact name of the starting country to claim it.")
            else:
                flash("Failed to create or join game.")

        # --- bot turn processing (local + spectate mode) ---
        if mode in ("local", "spectate") and state == "playing" and game:
            if game.players and game.players[game.turn_idx].is_bot:
                bot_player = game.players[game.turn_idx]
                if not getattr(game, "bot_thread", None) or not game.bot_thread.is_alive():
                    def _bot_worker(bp=bot_player):
                        try:
                            act = decide_local_bot(game, bp)
                            if not act:
                                act = ("NOTHING", None)
                            cmd, params = act
                            if cmd == "PEACE":
                                bp.vulnerable = True; bp.was_attacked = False
                                game.log(f"{bp.name} chooses PEACE")
                                end_turn_housekeeping(game, bp)
                            elif cmd == "GATHER":
                                roll = random.randint(1, 20)
                                max_afford = bp.money // TROOP_COST
                                buy = min(roll, max_afford)
                                cost = buy * TROOP_COST
                                bp.money -= cost
                                # Concentrate troops on BORDER countries (adjacent to enemies)
                                owned_c = [c for c in local_countries.values() if c.get("owner") == bp.name]
                                border_c = []
                                for c in owned_c:
                                    for a in c.get("adj", []):
                                        nb = local_countries.get(a.get("to"))
                                        if nb and nb.get("owner") and nb.get("owner") != bp.name:
                                            border_c.append(c)
                                            break
                                targets = border_c if border_c else owned_c
                                i = 0
                                while buy > 0 and targets:
                                    targets[i % len(targets)]["troops"] += 1
                                    buy -= 1; i += 1
                                game.log(f"{bp.name} bought troops for ${cost}")
                                end_turn_housekeeping(game, bp)
                            elif cmd == "NOTHING":
                                game.log(f"{bp.name} does NOTHING")
                                end_turn_housekeeping(game, bp)
                            elif cmd == "EXPAND" and params:
                                src_id, tgt_id, send = params
                                src = local_countries.get(src_id); tgt = local_countries.get(tgt_id)
                                if not src or not tgt or src.get("owner") != bp.name:
                                    game.log(f"{bp.name} invalid expand -> skip")
                                    end_turn_housekeeping(game, bp)
                                else:
                                    max_send = max(1, int(src.get("troops", 0)) - 1)
                                    send = max(1, min(send, max_send))
                                    adj = next((a for a in src.get("adj", []) if a["to"] == tgt_id), None)
                                    if adj and adj.get("cost", 0) > 0:
                                        if bp.money >= adj["cost"]:
                                            bp.money -= adj["cost"]
                                            game.log(f"{bp.name} paid crossing ${adj['cost']}")
                                        else:
                                            game.log(f"{bp.name} cannot pay crossing; move aborted")
                                            end_turn_housekeeping(game, bp)
                                            return
                                    src["troops"] -= send
                                    if src["troops"] <= 0:
                                        prev = src.get("owner")
                                        if prev:
                                            op = next((pl for pl in game.players if pl.name == prev), None)
                                            if op and src["id"] in op.owned:
                                                op.owned.remove(src["id"])
                                        src["owner"] = None; src["troops"] = 0
                                        game.log(f"A territory is now unowned")
                                    if not tgt.get("owner"):
                                        success = claim_country(bp, tgt, send, game)
                                        if not success:
                                            src["troops"] += send
                                    else:
                                        attack_country(bp, src, tgt, send, game)
                                    end_turn_housekeeping(game, bp)
                        except Exception as e:
                            print("bot_worker error:", e)
                            try:
                                end_turn_housekeeping(game, bp)
                            except Exception:
                                pass
                        finally:
                            game.bot_thread = None

                    game.bot_thread = threading.Thread(target=_bot_worker, daemon=True)
                    game.bot_thread.start()

        # --- event handling ---
        for _raw_ev in pygame.event.get():
            # Remap mouse coordinates from screen space to game-surface space
            # We wrap the event so ev.pos always returns game coords
            if fullscreen and hasattr(_raw_ev, 'pos'):
                _mapped_pos = _screen_to_game(_raw_ev.pos)
                ev = pygame.event.Event(_raw_ev.type, **{**_raw_ev.__dict__, 'pos': _mapped_pos})
            else:
                ev = _raw_ev

            if ev.type == pygame.QUIT:
                running = False

            # Handle hover for update buttons (online menu)
            if ev.type == pygame.MOUSEMOTION:
                if update_btn:
                    update_btn.handle_event(ev)
                if dismiss_btn:
                    dismiss_btn.handle_event(ev)

            # Global keyboard
            if ev.type == pygame.KEYDOWN:
                if ev.key == pygame.K_F11:
                    fullscreen = not fullscreen
                    if fullscreen:
                        screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
                    else:
                        screen = pygame.display.set_mode((WIDTH, HEIGHT))
                elif ev.key == pygame.K_ESCAPE:
                    # Dismiss update error overlay
                    if update_progress and update_progress.get("phase") == "error":
                        update_progress = None
                        continue
                    if state == "main_menu":
                        running = False
                    elif state in ("local_setup", "online_setup", "spectate_setup"):
                        state = "main_menu"; mode = None
                        flash("Returned to main menu")
                    elif state == "choose_start":
                        if mode == "local":
                            state = "main_menu"; game = None; mode = None
                        else:
                            state = "online_setup"
                        flash("Cancelled")
                    elif state == "playing":
                        state = "main_menu"; game = None; mode = None
                        flash("Returning to main menu")
                else:
                    # Centralized typing handler
                    handle_key_input(ev)

                    # Enter key special handling
                    if ev.key == pygame.K_RETURN:
                        # ---- choose_start: confirm starting country ----
                        if state == "choose_start" and input_active.get("starting_country"):
                            name_in = user_inputs.get("starting_country", "").strip()
                            if not name_in:
                                flash("Please type a country name to claim.")
                            else:
                                found = find_country_by_name(local_countries, name_in)
                                if not found:
                                    flash("No country matched that exact name. Check spelling.")
                                else:
                                    do_start_claim(found["id"])

                        # ---- playing: expand target typed ----
                        elif state == "playing" and expand_mode == "target" and expand_src:
                            target_key = "move_target" if mode == "online" else "starting_country"
                            name_in = user_inputs.get(target_key, "").strip()
                            if not name_in:
                                flash("Type the target country name to send troops.")
                            else:
                                tgt = find_country_by_name(local_countries, name_in)
                                if not tgt:
                                    flash("No country matched that exact name. Check spelling.")
                                else:
                                    src_c = local_countries.get(expand_src)
                                    if not src_c:
                                        flash("Source country lost.")
                                    else:
                                        adj = next((a for a in src_c.get("adj", []) if a["to"] == tgt["id"]), None)
                                        if not adj:
                                            flash("Target not adjacent; choose another.")
                                        else:
                                            if mode == "local":
                                                available = int(src_c.get("troops", 0))
                                            else:
                                                snap = get_snapshot()
                                                rc = snap["countries"].get(expand_src, {})
                                                available = int(rc.get("troops", 0))
                                            max_send = max(1, available - 1)
                                            expand_send_dialog = True
                                            rect = (WIDTH // 2 - 260*U, HEIGHT // 2 - 20*U, 520*U, 36*U)
                                            expand_send_slider = Slider(rect, 1, max_send, min(max_send, 1))
                                            expand_send_confirm = Button((WIDTH // 2 + 140*U, HEIGHT // 2 + 28*U, 120*U, 36*U), "Send", font, bg=(50, 170, 110))
                                            expand_send_cancel = Button((WIDTH // 2 - 260*U, HEIGHT // 2 + 28*U, 120*U, 36*U), "Cancel", font, bg=(150, 60, 60))

                        # ---- gather dialog open: confirm ----
                        elif gather_dialog and gather_slider:
                            amt = gather_slider.value
                            if mode == "local":
                                do_action("GATHER", {"buy": amt})
                            else:
                                do_action("GATHER", {"buy": amt})
                            gather_dialog = False; gather_slider = None
                            gather_confirm = None; gather_cancel = None

                        # ---- expand send dialog open: confirm ----
                        elif expand_send_dialog and expand_send_slider and expand_src:
                            send_amt = expand_send_slider.value
                            target_key = "move_target" if mode == "online" else "starting_country"
                            tgt_name = user_inputs.get(target_key, "").strip()
                            tgt = find_country_by_name(local_countries, tgt_name)
                            if not tgt:
                                flash("Target missing or invalid.")
                            else:
                                src_c = local_countries.get(expand_src)
                                if not src_c:
                                    flash("Source lost.")
                                else:
                                    adj = next((a for a in src_c.get("adj", []) if a["to"] == tgt["id"]), None)
                                    if not adj:
                                        flash("Not adjacent")
                                    else:
                                        cross_cost = int(adj.get("cost", 0) or 0)
                                        do_action("EXPAND", {
                                            "src": expand_src, "tgt": tgt["id"],
                                            "send": send_amt, "cross_cost": cross_cost,
                                        })
                            expand_send_dialog = False; expand_src = None
                            user_inputs[target_key] = ""
                            expand_send_slider = None; expand_send_confirm = None; expand_send_cancel = None

            # ---- Mouse wheel: zoom ----
            if ev.type == pygame.MOUSEWHEEL:
                mx, my = _screen_to_game(pygame.mouse.get_pos())
                factor = 1.18 ** ev.y
                new_scale = max(min_scale, min(max_scale, cam_target_scale * factor))
                world_x_before = cam_x + mx / cam_scale
                world_y_before = cam_y + my / cam_scale
                cam_target_scale = new_scale
                cam_target_x = world_x_before - mx / cam_target_scale
                cam_target_y = world_y_before - my / cam_target_scale
                cam_x = cam_target_x; cam_y = cam_target_y; cam_scale = cam_target_scale

            # ---- Middle/right click: pan ----
            if ev.type == pygame.MOUSEBUTTONDOWN and ev.button in (2, 3):
                dragging_pan = True; pan_start = ev.pos; cam_start = (cam_x, cam_y)
            if ev.type == pygame.MOUSEBUTTONUP and ev.button in (2, 3):
                dragging_pan = False
            if ev.type == pygame.MOUSEMOTION and dragging_pan:
                dx = (ev.pos[0] - pan_start[0]) / cam_scale
                dy = (ev.pos[1] - pan_start[1]) / cam_scale
                cam_x = cam_start[0] - dx; cam_y = cam_start[1] - dy

            # ---- Hover highlight ----
            if ev.type == pygame.MOUSEMOTION and state == "playing" and not dragging_pan:
                mx, my = ev.pos
                if my < MAP_H:
                    wx = cam_x + mx / cam_scale; wy = cam_y + my / cam_scale
                    hovered_country = country_at_world_point(wx, wy)
                else:
                    hovered_country = None

            # ---- Click into input boxes ----
            if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                for k, r in small_input_rects.items():
                    if r.collidepoint(ev.pos):
                        for kk in input_active:
                            input_active[kk] = False
                        input_active[k] = True
                        break

            # ================================================================
            # State-specific event handling
            # ================================================================

            # ---- MAIN MENU ----
            if state == "main_menu":
                btn_local.handle_event(ev)
                btn_spectate.handle_event(ev)
                btn_online.handle_event(ev)
                btn_quit_main.handle_event(ev)
                if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                    if btn_local.rect.collidepoint(ev.pos):
                        state = "local_setup"; mode = "local"
                        for kk in input_active:
                            input_active[kk] = False
                        input_active["player_name"] = True
                    elif btn_spectate.rect.collidepoint(ev.pos):
                        state = "spectate_setup"; mode = "spectate"
                    elif btn_online.rect.collidepoint(ev.pos):
                        mode = "online"
                        if fc is None:
                            ok = init_online()
                            if not ok:
                                mode = None
                                continue
                        state = "online_setup"
                        for kk in input_active:
                            input_active[kk] = False
                        input_active["game_id"] = True
                    elif btn_quit_main.rect.collidepoint(ev.pos):
                        running = False
                    # Update notification buttons (in-app update)
                    elif update_btn and update_btn.rect.collidepoint(ev.pos) and not update_progress:
                        release = update_info.get("release") if update_info else None
                        if release and UPDATER_AVAILABLE:
                            update_progress = {"phase": "download", "percent": 0, "message": "Starting..."}
                            def _do_update():
                                nonlocal update_progress
                                def _cb(phase, pct, msg):
                                    nonlocal update_progress
                                    update_progress = {"phase": phase, "percent": pct, "message": msg}
                                updater.download_update_with_callback(release, progress_cb=_cb)
                            update_thread = threading.Thread(target=_do_update, daemon=True)
                            update_thread.start()
                    elif dismiss_btn and dismiss_btn.rect.collidepoint(ev.pos):
                        update_info = None; update_btn = None; dismiss_btn = None

            # ---- SPECTATE SETUP ----
            elif state == "spectate_setup":
                spectate_slider.handle_event(ev)
                btn_start_spectate.handle_event(ev)
                if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                    if btn_start_spectate.rect.collidepoint(ev.pos):
                        start_spectate_game(spectate_slider.value)
                        state = "playing"
                        flash(f"Watching {spectate_slider.value} bots play!")

            # ---- LOCAL SETUP ----
            elif state == "local_setup":
                bot_slider.handle_event(ev)
                btn_start_local.handle_event(ev)
                if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                    if btn_start_local.rect.collidepoint(ev.pos):
                        pname = user_inputs.get("player_name", "Player").strip() or "Player"
                        start_local_game(pname, bot_slider.value)
                        state = "choose_start"
                        for kk in input_active:
                            input_active[kk] = False
                        input_active["starting_country"] = True
                        user_inputs["starting_country"] = ""
                        flash("Type the exact country name (case-insensitive) to claim your starting country.")

            # ---- ONLINE SETUP ----
            elif state == "online_setup":
                if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                    mx, my = ev.pos
                    create_rect = pygame.Rect(WIDTH // 2 - 260*U, 400*U, 240*U, 56*U)
                    join_rect = pygame.Rect(WIDTH // 2 + 20*U, 400*U, 240*U, 56*U)

                    if create_rect.collidepoint((mx, my)) and not network_loading:
                        gid = user_inputs["game_id"].strip(); pname = user_inputs["player_name"].strip()
                        if not gid or not pname:
                            flash("Please provide Game ID and Player name")
                        else:
                            network_loading = True
                            game_id_in_progress = gid
                            player_name_in_progress = pname
                            player_pass = user_inputs.get("player_password", "").strip()
                            room_pass = user_inputs.get("room_password", "").strip()

                            def _create_worker():
                                nonlocal network_result
                                try:
                                    network_result = fc.create_or_open_game(
                                        game_id_in_progress, player_name_in_progress,
                                        player_password=player_pass, room_password=room_pass)
                                except Exception as e:
                                    network_result = e

                            network_thread = threading.Thread(target=_create_worker, daemon=True)
                            network_thread.start()

                    elif join_rect.collidepoint((mx, my)) and not network_loading:
                        gid = user_inputs["game_id"].strip(); pname = user_inputs["player_name"].strip()
                        if not gid or not pname:
                            flash("Please provide Game ID and Player name")
                        else:
                            network_loading = True
                            game_id_in_progress = gid
                            player_name_in_progress = pname
                            player_pass = user_inputs.get("player_password", "").strip()
                            room_pass = user_inputs.get("room_password", "").strip()

                            def _join_worker():
                                nonlocal network_result
                                try:
                                    network_result = fc.create_or_open_game(
                                        game_id_in_progress, player_name_in_progress,
                                        player_password=player_pass, room_password=room_pass)
                                except Exception as e:
                                    network_result = e

                            network_thread = threading.Thread(target=_join_worker, daemon=True)
                            network_thread.start()

                    pass  # (update buttons handled in main_menu now)

            # ---- CHOOSE START ----
            elif state == "choose_start":
                if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                    mx, my = ev.pos
                    confirm_rect = pygame.Rect(WIDTH // 2 + 20*U, (460 if mode == "local" else 500)*U, 160*U, 44*U)
                    cancel_rect = pygame.Rect(WIDTH // 2 - 200*U, (460 if mode == "local" else 500)*U, 160*U, 44*U)
                    if confirm_rect.collidepoint((mx, my)):
                        name_in = user_inputs.get("starting_country", "").strip()
                        if not name_in:
                            flash("Please type a country name to claim.")
                        else:
                            found = find_country_by_name(local_countries, name_in)
                            if not found:
                                flash("No country matched that exact name. Check spelling.")
                            else:
                                do_start_claim(found["id"])
                    elif cancel_rect.collidepoint((mx, my)):
                        if mode == "local":
                            state = "main_menu"; game = None; mode = None
                        else:
                            state = "online_setup"; current_game_id = None; my_player_name = None
                        flash("Cancelled start.")

            # ---- PLAYING ----
            elif state == "playing":
                # Dialog interactions first
                if gather_dialog and gather_slider:
                    gather_slider.handle_event(ev)
                    if gather_confirm and gather_confirm.handle_event(ev):
                        amt = gather_slider.value
                        do_action("GATHER", {"buy": amt})
                        gather_dialog = False; gather_slider = None
                        gather_confirm = None; gather_cancel = None
                    if gather_cancel and gather_cancel.handle_event(ev):
                        gather_dialog = False; gather_slider = None
                        gather_confirm = None; gather_cancel = None
                    continue

                if expand_send_dialog and expand_send_slider:
                    expand_send_slider.handle_event(ev)
                    if expand_send_confirm and expand_send_confirm.handle_event(ev):
                        send_amt = expand_send_slider.value
                        target_key = "move_target" if mode == "online" else "starting_country"
                        tgt_name = user_inputs.get(target_key, "").strip()
                        tgt = find_country_by_name(local_countries, tgt_name)
                        if not tgt or not expand_src:
                            flash("Invalid selection or target name.")
                        else:
                            src_c = local_countries.get(expand_src)
                            if not src_c:
                                flash("Source lost.")
                            else:
                                adj = next((a for a in src_c.get("adj", []) if a["to"] == tgt["id"]), None)
                                if not adj:
                                    flash("Not adjacent")
                                else:
                                    cross_cost = int(adj.get("cost", 0) or 0)
                                    do_action("EXPAND", {
                                        "src": expand_src, "tgt": tgt["id"],
                                        "send": send_amt, "cross_cost": cross_cost,
                                    })
                        expand_send_dialog = False; expand_src = None
                        user_inputs[target_key] = ""
                        expand_send_slider = None; expand_send_confirm = None; expand_send_cancel = None
                    if expand_send_cancel and expand_send_cancel.handle_event(ev):
                        target_key = "move_target" if mode == "online" else "starting_country"
                        expand_send_dialog = False; expand_src = None
                        user_inputs[target_key] = ""
                        expand_send_slider = None; expand_send_confirm = None; expand_send_cancel = None
                    continue

                # Action buttons (not in spectate mode — bots play themselves)
                if mode == "spectate":
                    # In spectate, only allow map clicking for selection (no actions)
                    if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                        mx, my = ev.pos
                        wx = cam_x + mx / cam_scale; wy = cam_y + my / cam_scale
                        clicked = country_at_world_point(wx, wy)
                        selected_country = clicked["id"] if clicked else None
                    continue

                b_peace.handle_event(ev); b_expand.handle_event(ev)
                b_gather.handle_event(ev); b_nothing.handle_event(ev)

                if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                    mx, my = ev.pos

                    if b_peace.rect.collidepoint((mx, my)):
                        if not is_my_turn():
                            flash("Not your turn")
                        else:
                            do_action("PEACE", {})

                    elif b_gather.rect.collidepoint((mx, my)):
                        if not is_my_turn():
                            flash("Not your turn")
                        else:
                            snap = get_snapshot()
                            if mode == "local" and game:
                                cur = game.players[game.turn_idx]
                                if cur.last_gather_turn != game.turn_number:
                                    cur.troop_buy_limit = random.randint(1, 20)
                                    cur.last_gather_turn = game.turn_number
                                    game.log(f"{cur.name} can buy up to {cur.troop_buy_limit} troops this turn (rolled d20).")
                                max_buy_limit = cur.troop_buy_limit
                                max_afford = cur.money // TROOP_COST
                                max_allowed = min(max_buy_limit, max_afford)
                            else:
                                player_money = 0
                                for p in snap["players"]:
                                    if p.get("name") == my_player_name:
                                        player_money = int(p.get("money", 0) or 0)
                                roll = random.randint(1, 20)
                                max_allowed = min(roll, player_money // TROOP_COST) if TROOP_COST > 0 else roll
                            srect = (WIDTH // 2 - 260*U, HEIGHT // 2 - 20*U, 520*U, 36*U)
                            gather_slider = Slider(srect, 0, max_allowed, 0)
                            gather_confirm = Button((WIDTH // 2 + 140*U, HEIGHT // 2 + 28*U, 120*U, 36*U), "Confirm", font, bg=(80, 200, 120))
                            gather_cancel = Button((WIDTH // 2 - 260*U, HEIGHT // 2 + 28*U, 120*U, 36*U), "Cancel", font, bg=(200, 80, 80))
                            gather_dialog = True

                    elif b_nothing.rect.collidepoint((mx, my)):
                        if not is_my_turn():
                            flash("Not your turn")
                        else:
                            do_action("NOTHING", {})

                    elif b_expand.rect.collidepoint((mx, my)):
                        if not is_my_turn():
                            flash("Not your turn")
                        else:
                            expand_mode = "source"
                            flash("Click your source country (a country you own)")

                    else:
                        # Map click -- convert to world coords
                        wx = cam_x + mx / cam_scale
                        wy = cam_y + my / cam_scale
                        clicked = country_at_world_point(wx, wy)
                        if clicked:
                            selected_country = clicked["id"]
                            if expand_mode == "source":
                                snap = get_snapshot()
                                rc = snap["countries"].get(selected_country, {})
                                owner = rc.get("owner")
                                if mode == "local":
                                    cur_name = game.players[game.turn_idx].name if game else None
                                else:
                                    cur_name = my_player_name
                                if owner != cur_name:
                                    flash("Select a country you own as source.")
                                else:
                                    expand_src = selected_country
                                    expand_mode = "target"
                                    target_key = "move_target" if mode == "online" else "starting_country"
                                    for kk in input_active:
                                        input_active[kk] = False
                                    input_active[target_key] = True
                                    user_inputs[target_key] = ""
                                    flash("Now type the target country name (exact) and press Send.")
                            elif expand_mode == "target" and expand_src:
                                flash("Please type the target country's name in the input box; do not click.")
                        else:
                            selected_country = None

        # ---- Camera smoothing ----
        cam_scale += (cam_target_scale - cam_scale) * 0.30
        cam_x += (cam_target_x - cam_x) * 0.30
        cam_y += (cam_target_y - cam_y) * 0.30

        # Clamp camera
        screen_w = WIDTH; screen_h = HEIGHT
        vis_w = screen_w / max(cam_scale, 1e-6)
        vis_h = MAP_H / max(cam_scale, 1e-6)
        cam_x = max(0.0, min(cam_x, max(0.0, WIDTH - vis_w)))
        cam_y = max(0.0, min(cam_y, max(0.0, MAP_H - vis_h)))

        # ================================================================
        # RENDERING — when fullscreen, draw to game_surf then scale up
        # ================================================================
        actual_screen = screen  # keep reference to the real display
        if fullscreen:
            screen = game_surf  # redirect all rendering to the fixed-size surface
        screen.fill((14, 18, 30))
        sw = WIDTH; sh = HEIGHT

        # Scaled map
        scaled_w = max(1, int(WIDTH * cam_scale)); scaled_h = max(1, int(MAP_H * cam_scale))
        scale_key = (scaled_w, scaled_h)
        if _cached_scale_key != scale_key:
            try:
                _cached_scaled_map = pygame.transform.scale(map_surface, (scaled_w, scaled_h))
                _cached_scale_key = scale_key
            except Exception:
                _cached_scaled_map = map_surface; _cached_scale_key = None
        blit_x = int(-cam_x * cam_scale); blit_y = int(-cam_y * cam_scale)
        if _cached_scaled_map:
            screen.blit(_cached_scaled_map, (blit_x, blit_y))

        # ---- Draw ownership + hover + troops (playing/choose_start) ----
        if state in ("playing", "choose_start"):
            snapshot = get_snapshot()
            cam_ox = -cam_x * cam_scale; cam_oy = -cam_y * cam_scale
            vx0 = cam_x; vy0 = cam_y
            vx1 = cam_x + sw / max(cam_scale, 0.01)
            vy1 = cam_y + MAP_H / max(cam_scale, 0.01)

            if mode in ("local", "spectate") and game:
                # Rebuild ownership surface only when ownership changes
                player_by_name = {p.name: p for p in game.players}
                own_hash = hash(tuple((cid, c.get("owner", "")) for cid, c in local_countries.items() if c.get("owner")))
                if _own_dirty or _own_turn != own_hash:
                    _own_surface.fill((0, 0, 0, 0))
                    for cid, c in local_countries.items():
                        owner = c.get("owner")
                        if owner:
                            pl = player_by_name.get(owner)
                            fill_col = pl.color if pl else (100, 100, 100)
                            for ring in c["polygons"]:
                                if len(ring) >= 3:
                                    try:
                                        pygame.draw.polygon(_own_surface, fill_col, ring)
                                        pygame.draw.polygon(_own_surface, _lighten(fill_col, 35), ring, 1)
                                    except Exception:
                                        pass
                    _own_dirty = False; _own_turn = own_hash
                # blit ownership at camera transform
                try:
                    if cam_scale == 1.0:
                        screen.blit(_own_surface, (blit_x, blit_y))
                    else:
                        scaled_own = pygame.transform.scale(_own_surface, (scaled_w, scaled_h))
                        screen.blit(scaled_own, (blit_x, blit_y))
                except Exception:
                    pass
            else:
                # Online mode: draw ownership directly from snapshot
                for cid, c in local_countries.items():
                    rinfo = snapshot["countries"].get(cid, {})
                    owner = rinfo.get("owner")
                    if owner:
                        color = None
                        for p in snapshot["players"]:
                            if p.get("name") == owner:
                                color = p.get("color")
                                break
                        if color is None:
                            color = (100, 100, 100)
                        for ring in c["polygons"]:
                            if len(ring) >= 3:
                                transformed = [(int(x * cam_scale + cam_ox), int(y * cam_scale + cam_oy)) for x, y in ring]
                                try:
                                    pygame.draw.polygon(screen, color, transformed)
                                    pygame.draw.polygon(screen, _lighten(color, 40), transformed, 1)
                                except Exception:
                                    pass

            # Hover highlight
            if hovered_country and hovered_country.get("bbox"):
                bx0, by0, bx1, by1 = hovered_country["bbox"]
                if not (bx1 < vx0 or bx0 > vx1 or by1 < vy0 or by0 > vy1):
                    for ring in hovered_country["polygons"]:
                        if len(ring) >= 3:
                            transformed = [(int(x * cam_scale + cam_ox), int(y * cam_scale + cam_oy)) for x, y in ring]
                            try:
                                pygame.draw.polygon(screen, (255, 255, 255), transformed, 2)
                            except Exception:
                                pass

            # Troop pins
            for cid, c in local_countries.items():
                bbox = c.get("bbox")
                if bbox and (bbox[2] < vx0 or bbox[0] > vx1 or bbox[3] < vy0 or bbox[1] > vy1):
                    continue  # viewport culling
                cx, cy = c.get("centroid", (0, 0))
                sx = int((cx - cam_x) * cam_scale); sy = int((cy - cam_y) * cam_scale)
                cinfo = snapshot["countries"].get(cid, {})
                troops = int(cinfo.get("troops", 0) or 0)
                if troops > 0:
                    owner = cinfo.get("owner")
                    color = (60, 60, 60)
                    for p in snapshot["players"]:
                        if p.get("name") == owner:
                            color = p.get("color", (60, 60, 60))
                            break
                    base_r = max(6, int(ARMY_PIN_RADIUS * PIN_SCALE * cam_scale))
                    bonus = min(4, troops // 5)
                    r = base_r + bonus
                    pygame.draw.circle(screen, (0, 0, 0), (sx + 1, sy + 2), r + 2)
                    pygame.draw.circle(screen, (255, 255, 255), (sx, sy), r + 1)
                    pygame.draw.circle(screen, color, (sx, sy), r)
                    label = str(troops)
                    t = cached_render(pinfont, label, (255, 255, 255))
                    ts = cached_render(pinfont, label, (0, 0, 0))
                    tx = sx - t.get_width() // 2; ty = sy - t.get_height() // 2
                    screen.blit(ts, (tx + 1, ty + 1))
                    screen.blit(t, (tx, ty))

        # ---- HUD background ----
        pygame.draw.rect(screen, HUD_BG, (0, MAP_H, sw, sh - MAP_H))
        pygame.draw.line(screen, HUD_BORDER, (0, MAP_H), (sw, MAP_H), 2*U)

        # ================================================================
        # State-specific rendering
        # ================================================================

        if state == "main_menu":
            title_shadow = cached_render(titlefont, "GeoPolitical Domination", (20, 60, 120))
            title_main = cached_render(titlefont, "GeoPolitical Domination", TEXT_PRIMARY)
            tcx = sw // 2 - title_main.get_width() // 2
            screen.blit(title_shadow, (tcx + 2*U, 82*U))
            screen.blit(title_main, (tcx, 80*U))
            sub = cached_render(font, "A Strategy Game of World Conquest", TEXT_SECONDARY)
            screen.blit(sub, (sw // 2 - sub.get_width() // 2, 135*U))
            btn_local.draw(screen); btn_spectate.draw(screen)
            btn_online.draw(screen); btn_quit_main.draw(screen)
            note = cached_render(font, "F11 fullscreen  |  Right-drag to pan  |  Scroll to zoom", TEXT_MUTED)
            screen.blit(note, (WIDTH // 2 - note.get_width() // 2, 440*U))

            # Update notification banner
            if update_check_done and update_info and update_info.get("update_available") and not update_progress:
                update_rect = pygame.Rect(WIDTH - 320*U, HEIGHT - 90*U, 310*U, 80*U)
                pygame.draw.rect(screen, HUD_BG_ACCENT, update_rect, border_radius=10*U)
                pygame.draw.rect(screen, ACCENT_GOLD, update_rect, 2, border_radius=10*U)
                screen.blit(cached_render(font, "Update Available!", ACCENT_GOLD), (update_rect.x + 10*U, update_rect.y + 8*U))
                current_v = update_info.get("current", "unknown")
                latest_v = update_info.get("latest", "unknown")
                screen.blit(cached_render(font, f"{current_v} -> {latest_v}", TEXT_SECONDARY), (update_rect.x + 10*U, update_rect.y + 28*U))
                if update_btn is None:
                    update_btn = Button((update_rect.x + 10*U, update_rect.y + 48*U, 140*U, 24*U), "Update Now", font, bg=(50, 170, 110))
                if dismiss_btn is None:
                    dismiss_btn = Button((update_rect.x + 160*U, update_rect.y + 48*U, 140*U, 24*U), "Ignore", font, bg=(80, 80, 100))
                update_btn.draw(screen); dismiss_btn.draw(screen)

            # Update progress overlay
            if update_progress:
                _overlay_surf.fill((0, 0, 0, 200)); screen.blit(_overlay_surf, (0, 0))
                phase = update_progress.get("phase", "")
                pct = update_progress.get("percent", 0)
                msg = update_progress.get("message", "")
                # Title
                screen.blit(cached_render(bigfont, "Updating...", TEXT_PRIMARY), (sw // 2 - 80*U, sh // 2 - 60*U))
                # Message
                screen.blit(cached_render(font, msg, TEXT_SECONDARY), (sw // 2 - 200*U, sh // 2 - 20*U))
                # Progress bar
                bar_x = sw // 2 - 200*U; bar_y = sh // 2 + 10*U
                bar_w = 400*U; bar_h = 20*U
                pygame.draw.rect(screen, HUD_BORDER, (bar_x, bar_y, bar_w, bar_h), border_radius=6*U)
                fill_w = int(bar_w * max(0, min(1, pct)))
                if fill_w > 0:
                    col = ACCENT_GREEN if phase == "done" else ACCENT_RED if phase == "error" else (55, 160, 220)
                    pygame.draw.rect(screen, col, (bar_x, bar_y, fill_w, bar_h), border_radius=6*U)
                pct_text = f"{int(pct * 100)}%"
                screen.blit(cached_render(font, pct_text, TEXT_PRIMARY), (bar_x + bar_w + 10*U, bar_y))
                if phase == "error":
                    screen.blit(cached_render(font, "Press Escape to dismiss", TEXT_MUTED), (sw // 2 - 120*U, sh // 2 + 50*U))

        elif state == "spectate_setup":
            title_shadow = cached_render(titlefont, "Spectate Mode", (60, 50, 20))
            title_main = cached_render(titlefont, "Spectate Mode", TEXT_PRIMARY)
            tcx = sw // 2 - title_main.get_width() // 2
            screen.blit(title_shadow, (tcx + 2*U, 82*U))
            screen.blit(title_main, (tcx, 80*U))
            sub = cached_render(font, "Watch bots battle for world domination", TEXT_SECONDARY)
            screen.blit(sub, (sw // 2 - sub.get_width() // 2, 135*U))
            bot_label = cached_render(font, f"Number of Bots: {spectate_slider.value}", TEXT_SECONDARY)
            screen.blit(bot_label, (WIDTH // 2 - 200*U, 280*U))
            spectate_slider.draw(screen, font)
            btn_start_spectate.draw(screen)
            note = cached_render(font, "Press Escape to go back", TEXT_MUTED)
            screen.blit(note, (WIDTH // 2 - note.get_width() // 2, 460*U))

        elif state == "local_setup":
            title_shadow = cached_render(titlefont, "Local Game Setup", (20, 60, 120))
            title_main = cached_render(titlefont, "Local Game Setup", TEXT_PRIMARY)
            tcx = sw // 2 - title_main.get_width() // 2
            screen.blit(title_shadow, (tcx + 2*U, 82*U))
            screen.blit(title_main, (tcx, 80*U))
            sub = cached_render(font, "Configure your local game", TEXT_SECONDARY)
            screen.blit(sub, (sw // 2 - sub.get_width() // 2, 135*U))
            draw_input_box("player_name", "Player Name:")
            bot_label = cached_render(font, f"Bot Players: {bot_slider.value}", TEXT_SECONDARY)
            screen.blit(bot_label, (WIDTH // 2 - 200*U, 365*U))
            bot_slider.draw(screen, font)
            btn_start_local.draw(screen)
            note = cached_render(font, "Press Escape to go back", TEXT_MUTED)
            screen.blit(note, (WIDTH // 2 - note.get_width() // 2, 510*U))

        elif state == "online_setup":
            title_shadow = cached_render(titlefont, "Online Game", (20, 60, 120))
            title_main = cached_render(titlefont, "Online Game", TEXT_PRIMARY)
            tcx = sw // 2 - title_main.get_width() // 2
            screen.blit(title_shadow, (tcx + 2*U, 42*U))
            screen.blit(title_main, (tcx, 40*U))
            sub = cached_render(font, "Online Multiplayer", TEXT_SECONDARY)
            screen.blit(sub, (sw // 2 - sub.get_width() // 2, 95*U))
            small_input_rects["player_name"] = pygame.Rect(WIDTH // 2 - 260*U, 210*U, 520*U, 36*U)
            draw_input_box("game_id", "Game ID:")
            draw_input_box("player_name", "Player Name:")
            draw_input_box("player_password", "Player Password:", hide_password=True)
            draw_input_box("room_password", "Room Password (optional):", hide_password=True)
            hint = cached_render(font, "Create a new room or join an existing one.", TEXT_MUTED)
            screen.blit(hint, (WIDTH // 2 - hint.get_width() // 2, 360*U))
            create_btn = Button((WIDTH // 2 - 260*U, 400*U, 240*U, 52*U), "Create & Host", bigfont, bg=(50, 170, 110))
            join_btn = Button((WIDTH // 2 + 20*U, 400*U, 240*U, 52*U), "Join Room", bigfont, bg=(55, 130, 210))
            create_btn.draw(screen); join_btn.draw(screen)

            if network_loading:
                _overlay_surf.fill((0, 0, 0, 180))
                screen.blit(_overlay_surf, (0, 0))
                loading_text = cached_render(bigfont, "Connecting...", TEXT_PRIMARY)
                screen.blit(loading_text, (WIDTH // 2 - loading_text.get_width() // 2, HEIGHT // 2 - loading_text.get_height() // 2))

            small_input_rects["player_name"] = pygame.Rect(WIDTH // 2 - 260*U, 350*U, 520*U, 36*U)

        elif state == "choose_start":
            _overlay_surf.fill((0, 0, 0, 160)); screen.blit(_overlay_surf, (0, 0))
            dw, dh = 600*U, 200*U; dx = sw // 2 - dw // 2; dy = 100*U
            draw_shadow_rect(screen, (dx, dy, dw, dh), radius=12*U, offset=6*U, alpha=60)
            pygame.draw.rect(screen, HUD_BG_ACCENT, (dx, dy, dw, dh), border_radius=12*U)
            pygame.draw.rect(screen, HUD_BORDER, (dx, dy, dw, dh), 1, border_radius=12*U)
            ins = cached_render(bigfont, "Choose Your Starting Country", TEXT_PRIMARY)
            screen.blit(ins, (sw // 2 - ins.get_width() // 2, dy + 20*U))
            hint = cached_render(font, "Type the exact country name (case-insensitive).", TEXT_SECONDARY)
            screen.blit(hint, (sw // 2 - hint.get_width() // 2, dy + 55*U))
            draw_input_box("starting_country", "Country name:")
            btn_y = 460*U if mode == "local" else 500*U
            confirm_btn = Button((WIDTH // 2 + 20*U, btn_y, 160*U, 44*U), "Confirm", bigfont, bg=(50, 170, 110))
            cancel_btn = Button((WIDTH // 2 - 200*U, btn_y, 160*U, 44*U), "Cancel", bigfont, bg=(160, 60, 60))
            confirm_btn.draw(screen); cancel_btn.draw(screen)

        elif state == "playing":
            snapshot = get_snapshot()
            players = snapshot["players"]

            # Turn indicator
            panel_x = sw - 370*U
            draw_shadow_rect(screen, (panel_x, 6*U, 360*U, 48*U), radius=10*U, offset=3*U, alpha=50)
            pygame.draw.rect(screen, HUD_BG_ACCENT, (panel_x, 6*U, 360*U, 48*U), border_radius=10*U)
            pygame.draw.rect(screen, HUD_BORDER, (panel_x, 6*U, 360*U, 48*U), 1, border_radius=10*U)
            cur_name = "..."
            cur_color = (120, 120, 120)
            if players and 0 <= snapshot["turn_idx"] < len(players):
                cur_pl = players[snapshot["turn_idx"]]
                cur_name = cur_pl.get("name", "...")
                cur_color = cur_pl.get("color", (120, 120, 120))
            pygame.draw.circle(screen, cur_color, (panel_x + 18*U, 30*U), 8*U)
            if mode == "local":
                is_bot = players[snapshot["turn_idx"]].get("is_bot", False) if players and 0 <= snapshot["turn_idx"] < len(players) else False
                turn_text = f"{cur_name}'s Turn {'(BOT)' if is_bot else '(YOU)'}"
            else:
                turn_text = f"{cur_name}'s Turn"
            screen.blit(cached_render(bigfont, turn_text, TEXT_PRIMARY), (panel_x + 34*U, 16*U))

            # Player cards — dynamically sized to fill the HUD bar
            n_players = max(1, len(players))
            card_margin = 4 * U
            cards_right_edge = sw - 8 * U  # right margin
            cards_left = 8 * U
            total_cards_w = cards_right_edge - cards_left
            card_w = max(100*U, (total_cards_w - card_margin * (n_players - 1)) // n_players)
            card_h = 74 * U
            y0 = MAP_H + 6 * U
            # Pre-compute stats once
            _tc = {}; _lc = {}
            for v in snapshot["countries"].values():
                o = v.get("owner")
                if o:
                    _tc[o] = _tc.get(o, 0) + int(v.get("troops", 0) or 0)
                    _lc[o] = _lc.get(o, 0) + 1
            for i, pl in enumerate(players):
                px = cards_left + i * (card_w + card_margin)
                pr = pygame.Rect(px, y0, card_w, card_h)
                pygame.draw.rect(screen, HUD_BG_ACCENT, pr, border_radius=8*U)
                pl_color = pl.get("color", PALETTE[i % len(PALETTE)])
                pygame.draw.rect(screen, pl_color, (pr.x, pr.y, 5*U, pr.h), border_radius=3*U)
                if i == snapshot["turn_idx"]:
                    pygame.draw.rect(screen, ACCENT_GOLD, pr, 2, border_radius=8*U)
                else:
                    pygame.draw.rect(screen, HUD_BORDER, pr, 1, border_radius=8*U)
                name_lbl = pl.get("name", "?") + (" (BOT)" if pl.get("is_bot") else "")
                screen.blit(cached_render(font, name_lbl, TEXT_PRIMARY), (pr.x + 12*U, pr.y + 8*U))
                pname = pl.get("name")
                screen.blit(cached_render(font, f"${pl.get('money', 0)}", ACCENT_GOLD), (pr.x + 12*U, pr.y + 30*U))
                screen.blit(cached_render(font, f"{_tc.get(pname,0)} troops", TEXT_SECONDARY), (pr.x + 12*U, pr.y + 48*U))
                screen.blit(cached_render(font, f"{_lc.get(pname,0)} land", TEXT_SECONDARY), (pr.x + card_w // 2 + 4*U, pr.y + 48*U))

            # Action buttons (hidden in spectate mode)
            if mode != "spectate":
                b_peace.draw(screen); b_expand.draw(screen)
                b_gather.draw(screen); b_nothing.draw(screen)

            # Selected territory info panel
            if selected_country:
                c = local_countries.get(selected_country)
                rc = snapshot["countries"].get(selected_country, {})
                pr = pygame.Rect(sw - 330*U, MAP_H + 6*U, 320*U, 150*U)
                pygame.draw.rect(screen, HUD_BG_ACCENT, pr, border_radius=10*U)
                pygame.draw.rect(screen, HUD_BORDER, pr, 1, border_radius=10*U)
                screen.blit(cached_render(font, "Selected Territory", TEXT_MUTED), (pr.x + 12*U, pr.y + 8*U))
                cont = (c.get("continent", "") if c else rc.get("continent", ""))
                screen.blit(cached_render(font, f"Continent: {cont}", TEXT_PRIMARY), (pr.x + 12*U, pr.y + 28*U))
                screen.blit(cached_render(font, f"Owner: {rc.get('owner') or 'Unclaimed'}", TEXT_SECONDARY), (pr.x + 12*U, pr.y + 50*U))
                screen.blit(cached_render(font, f"Troops: {rc.get('troops', 0)}", TEXT_SECONDARY), (pr.x + 12*U, pr.y + 70*U))
                screen.blit(cached_render(font, "Type target name to expand.", TEXT_MUTED), (pr.x + 12*U, pr.y + 96*U))
                target_key = "move_target" if mode == "online" else "starting_country"
                inp = small_input_rects.get(target_key)
                if inp:
                    pygame.draw.rect(screen, (40, 50, 70), inp, border_radius=6*U)
                    pygame.draw.rect(screen, HUD_BORDER, inp, 1, border_radius=6*U)
                    screen.blit(cached_render(font, user_inputs.get(target_key, ""), TEXT_PRIMARY), (inp.x + 8*U, inp.y + 6*U))

            # Mini-log
            logs = snapshot.get("logs", [])
            recent = logs[-8:]
            if recent:
                log_h = len(recent) * 18*U + 10*U
                log_w = min(sw // 2, 580*U)
                _log_surf.fill((0, 0, 0, 0))
                pygame.draw.rect(_log_surf, (10, 14, 24, 180), (0, 0, log_w, log_h), border_radius=6*U)
                for i, l in enumerate(recent):
                    _log_surf.blit(cached_render(font, l, TEXT_SECONDARY), (8*U, 4*U + i * 18*U))
                screen.blit(_log_surf, (4*U, MAP_H - log_h - 2*U), (0, 0, log_w, log_h))

            # Dialogs
            if gather_dialog and gather_slider:
                _overlay_surf.fill((0, 0, 0, 160)); screen.blit(_overlay_surf, (0, 0))
                dw, dh = 500*U, 180*U; dx = sw // 2 - dw // 2; dy = sh // 2 - dh // 2
                draw_shadow_rect(screen, (dx, dy, dw, dh), radius=12*U, offset=6*U, alpha=60)
                pygame.draw.rect(screen, HUD_BG_ACCENT, (dx, dy, dw, dh), border_radius=12*U)
                pygame.draw.rect(screen, HUD_BORDER, (dx, dy, dw, dh), 1, border_radius=12*U)
                screen.blit(cached_render(bigfont, "Gather Troops", TEXT_PRIMARY), (dx + 16*U, dy + 14*U))
                screen.blit(cached_render(font, f"Cost: ${TROOP_COST} per troop", TEXT_SECONDARY), (dx + 16*U, dy + 50*U))
                gather_slider.draw(screen, font)
                gather_confirm.draw(screen); gather_cancel.draw(screen)

            if expand_send_dialog and expand_send_slider and expand_src:
                _overlay_surf.fill((0, 0, 0, 180)); screen.blit(_overlay_surf, (0, 0))
                dw, dh = 520*U, 200*U; dx = sw // 2 - dw // 2; dy = sh // 2 - dh // 2
                draw_shadow_rect(screen, (dx, dy, dw, dh), radius=12*U, offset=6*U, alpha=60)
                pygame.draw.rect(screen, HUD_BG_ACCENT, (dx, dy, dw, dh), border_radius=12*U)
                pygame.draw.rect(screen, HUD_BORDER, (dx, dy, dw, dh), 1, border_radius=12*U)
                screen.blit(cached_render(bigfont, "Send Troops", TEXT_PRIMARY), (dx + 16*U, dy + 14*U))
                src_c = local_countries.get(expand_src)
                if mode == "local" and src_c:
                    src_troops = int(src_c.get("troops", 0))
                else:
                    src_troops = int(snapshot["countries"].get(expand_src, {}).get("troops", 0))
                screen.blit(cached_render(font, f"Available in source: {src_troops} (must leave 1)", TEXT_SECONDARY), (dx + 16*U, dy + 48*U))
                target_key = "move_target" if mode == "online" else "starting_country"
                tgt_name = user_inputs.get(target_key, "").strip()
                tgt_c = find_country_by_name(local_countries, tgt_name) if tgt_name else None
                if tgt_c:
                    tgt_info = snapshot["countries"].get(tgt_c["id"], {})
                    if not tgt_info.get("owner"):
                        screen.blit(cached_render(font, "Target is unclaimed -- troops will garrison.", ACCENT_GREEN), (dx + 16*U, dy + 68*U))
                    else:
                        screen.blit(cached_render(font, f"Target owned by {tgt_info.get('owner')} -- this is an attack!", ACCENT_RED), (dx + 16*U, dy + 68*U))
                expand_send_slider.draw(screen, font)
                expand_send_confirm.draw(screen); expand_send_cancel.draw(screen)

        # ---- Flash message ----
        if message and time.time() < msg_until:
            remaining = msg_until - time.time()
            alpha = min(230, int(230 * min(1.0, remaining / 0.4)))
            msg_surf = cached_render(font, message, TEXT_PRIMARY)
            mw = msg_surf.get_width() + 24*U; mh = msg_surf.get_height() + 14*U
            mx = sw // 2 - mw // 2; my = MAP_H + (12 + 78 + 52)*U
            toast_bg = pygame.Surface((mw, mh), pygame.SRCALPHA)
            toast_bg.fill((30, 40, 60, alpha))
            screen.blit(toast_bg, (mx, my))
            pygame.draw.rect(screen, (80, 140, 220), (mx, my, mw, mh), 1, border_radius=6*U)
            ms = msg_surf.copy(); ms.set_alpha(alpha)
            screen.blit(ms, (mx + 12*U, my + 7*U))

        # If fullscreen, scale game_surf onto the actual display, then restore screen
        if fullscreen:
            screen = actual_screen
            real_w, real_h = screen.get_size()
            scale = min(real_w / WIDTH, real_h / HEIGHT)
            ow = int(WIDTH * scale); oh = int(HEIGHT * scale)
            ox = (real_w - ow) // 2; oy = (real_h - oh) // 2
            screen.fill((0, 0, 0))  # letterbox bars
            scaled = pygame.transform.scale(game_surf, (ow, oh))
            screen.blit(scaled, (ox, oy))

        pygame.display.flip()
        clock.tick(FPS)

    pygame.quit()


if __name__ == "__main__":
    main()
