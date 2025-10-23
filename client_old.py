# client.py
"""
GPD — clickable country polygons (auto-generated from GeoJSON).
UI tweaks:
 - Buttons moved below player status boxes (no longer hidden).
 - Buttons drawn after player boxes so they are visible on top.
 - HUD background is semi-transparent so the map shows behind player boxes/buttons.
Everything else (gameplay, bots, map parsing) unchanged.
"""

import os, sys, json, math, random, threading, time
from collections import defaultdict
import pygame
from pygame import gfxdraw

# attempt to import heuristic bot module (improved AI)
try:
    import heuristic_bot
except Exception as e:
    heuristic_bot = None
    print("Warning: heuristic_bot.py not found or failed to import:", e)

# optional requests (for downloading geojson)
try:
    import requests
except Exception:
    requests = None

# --- paths & constants
BASE_DIR = os.path.dirname(__file__)
ASSET_DIR = os.path.join(BASE_DIR, "assets")
GEOJSON_CACHE = os.path.join(ASSET_DIR, "countries.geojson")
CONFIG_PATH = os.path.join(BASE_DIR, "config.txt")

WIDTH, HEIGHT = 1280, 820
MAP_H = HEIGHT - 160
FPS = 45

# gameplay constants
CLAIM_COST = 200
TROOP_COST = 50

# rendering
PIN_SCALE = 0.5
ARMY_PIN_RADIUS = 5  # base radius (scaled by zoom)
COUNTRY_BORDER_COLOR = (90, 90, 90)
DEFAULT_COUNTRY_FILL = (210, 220, 230)
SEA_COLOR = (180, 220, 255)
HUD_BG = (245, 245, 245)  # used as base; we draw translucent overlay

COLOR_PALETTE = {
    "red": (200,80,80),
    "green": (100,200,100),
    "blue": (60,120,200),
    "white": (245,245,245),
    "yellow": (220,200,60),
    "violet": (160,80,200),
}
PALETTE = list(COLOR_PALETTE.values())

# GeoJSON raw URL (datasets/geo-countries)
GEOJSON_URL = "https://raw.githubusercontent.com/datasets/geo-countries/master/data/countries.geojson"
MAX_MERCATOR_LAT = 85.05112878

# --- helpers: projection + geometry
def ensure_assets():
    os.makedirs(ASSET_DIR, exist_ok=True)

def download_geojson(dest_path, url=GEOJSON_URL, timeout=15):
    if requests is None:
        print("requests not available; cannot download GeoJSON. Place a countries.geojson in assets/")
        return False
    try:
        r = requests.get(url, timeout=timeout)
        if r.status_code == 200:
            with open(dest_path, "wb") as f:
                f.write(r.content)
            print("Downloaded GeoJSON to", dest_path)
            return True
        else:
            print("GeoJSON download failed HTTP", r.status_code)
            return False
    except Exception as e:
        print("GeoJSON download error:", e)
        return False

def mercator_x(lon_deg, map_w):
    return (lon_deg + 180.0) / 360.0 * map_w

def mercator_y(lat_deg, map_h):
    lat = max(-MAX_MERCATOR_LAT, min(MAX_MERCATOR_LAT, lat_deg))
    lat_rad = math.radians(lat)
    merc_n = math.log(math.tan(math.pi/4 + lat_rad/2))
    y = (1 - merc_n / math.pi) / 2
    return y * map_h

def lonlat_to_pixel(lon, lat, map_w, map_h):
    return int(round(mercator_x(lon, map_w))), int(round(mercator_y(lat, map_h)))

def polygon_bbox(poly):
    xs = [p[0] for p in poly]; ys = [p[1] for p in poly]
    return (min(xs), min(ys), max(xs), max(ys))

def point_in_poly(x, y, poly):
    # ray casting algorithm — works for non-self-intersecting polygon (list of (x,y))
    inside = False
    n = len(poly)
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        intersect = ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi + 1e-12) + xi)
        if intersect:
            inside = not inside
        j = i
    return inside

def polygon_centroid(poly):
    # centroid of polygon using shoelace formula (works for non-self-intersecting)
    area = 0.0
    cx = 0.0
    cy = 0.0
    n = len(poly)
    if n == 0:
        return (0,0)
    for i in range(n):
        x0,y0 = poly[i]
        x1,y1 = poly[(i+1)%n]
        a = x0*y1 - x1*y0
        area += a
        cx += (x0 + x1) * a
        cy += (y0 + y1) * a
    if abs(area) < 1e-6:
        # fallback: simple average
        return (sum(p[0] for p in poly)/n, sum(p[1] for p in poly)/n)
    area = area / 2.0
    cx = cx / (6.0 * area)
    cy = cy / (6.0 * area)
    return (int(round(cx)), int(round(cy)))

def polygon_area(poly):
    a = 0.0
    n = len(poly)
    for i in range(n):
        x0,y0 = poly[i]
        x1,y1 = poly[(i+1)%n]
        a += x0*y1 - x1*y0
    return a / 2.0

# --- Game core
class Player:
    def __init__(self, name, is_bot=False, color=None):
        self.name = name
        self.money = 500
        self.is_bot = is_bot
        self.vulnerable = False
        self.was_attacked = False
        self.owned = set()
        self.color = color if color else random.choice(PALETTE)
    def troop_count(self, countries):
        return sum(int(c.get("troops",0)) for c in countries.values() if c.get("owner")==self.name)
    def country_count(self):
        return len(self.owned)

class Game:
    def __init__(self, players, countries):
        self.players = players
        self.countries = countries  # dict id->country
        self.turn_idx = random.randrange(len(players)) if players else 0
        self.turn_number = 1
        self.logs = []
        self.bot_thread = None
    def log(self, msg):
        ts = time.strftime("%H:%M:%S")
        line = f"[{ts}] {msg}"
        self.logs.append(line)
        try:
            print(line)
        except Exception:
            pass
    def find_country_by_id(self, cid):
        return self.countries.get(cid)

# --- actions (same mechanics as before)
def claim_country(player, country, troops, game):
    if player.money < CLAIM_COST:
        game.log(f"{player.name} cannot afford to claim {country['name']} (need ${CLAIM_COST}).")
        return False
    player.money -= CLAIM_COST
    prev = country.get("owner")
    if prev:
        prevpl = next((p for p in game.players if p.name==prev), None)
        if prevpl and country["id"] in prevpl.owned:
            prevpl.owned.remove(country["id"])
    country["owner"] = player.name
    country["troops"] = troops
    player.owned.add(country["id"])
    game.log(f"{player.name} claimed {country['name']} with {troops} troops (paid ${CLAIM_COST}).")
    return True

def attack_country(attacker, source_country, target_country, send_troops, game):
    defender_name = target_country.get("owner")
    defender = next((p for p in game.players if p.name==defender_name), None) if defender_name else None
    if defender and defender.vulnerable:
        if attacker.money < CLAIM_COST:
            game.log(f"{attacker.name} cannot afford claim ${CLAIM_COST} to take {target_country['name']}. Attack aborted.")
            return False
        attacker.money -= CLAIM_COST
        target_country['owner'] = attacker.name
        target_country['troops'] = send_troops
        attacker.owned.add(target_country['id'])
        if defender and target_country['id'] in defender.owned:
            defender.owned.remove(target_country['id'])
        game.log(f"{attacker.name} swept vulnerable {target_country['name']} and took it with {send_troops} troops.")
        attacker.was_attacked = False; defender.was_attacked = True
        return True
    atk_roll = random.randint(1,20)
    d1 = random.randint(1,20); d2 = random.randint(1,20); def_best = max(d1,d2)
    game.log(f"{attacker.name} (atk {atk_roll}) attacks {target_country['name']} owned by {defender_name} (def [{d1},{d2}] -> {def_best})")
    if atk_roll > def_best:
        if attacker.money < CLAIM_COST:
            game.log(f"{attacker.name} cannot afford claim ${CLAIM_COST} to take {target_country['name']}. Attack failed by finance.")
            return False
        attacker.money -= CLAIM_COST
        target_country['owner'] = attacker.name
        target_country['troops'] = send_troops
        attacker.owned.add(target_country['id'])
        if defender and target_country['id'] in defender.owned:
            defender.owned.remove(target_country['id'])
        game.log(f"{attacker.name} won and captured {target_country['name']} with {send_troops} troops.")
        if defender: defender.was_attacked = True
        return True
    else:
        game.log(f"{attacker.name} attacked but lost; {send_troops} attacking troops were destroyed.")
        if defender: defender.was_attacked = True
        return False

def end_turn_housekeeping(game, player):
    # Peace payout: if player was vulnerable and not attacked, they earn $100 × number of countries owned
    if player.vulnerable:
        if not player.was_attacked:
            payout = 100 * max(0, player.country_count())
            player.money += payout
            game.log(f"{player.name} was peaceful and earned ${payout} (${100} × {player.country_count()} countries).")
        player.vulnerable = False; player.was_attacked = False
    game.turn_number += 1
    game.turn_idx = (game.turn_idx + 1) % len(game.players)

# --- GeoJSON parsing: build countries dict
def load_countries_from_geojson(path, map_w, map_h):
    data = json.load(open(path, "r", encoding="utf-8"))
    features = data.get("features", [])
    countries = {}
    cid = 1
    for feat in features:
        props = feat.get("properties", {})
        name = props.get("ADMIN") or props.get("name") or props.get("NAME") or f"Country {cid}"
        cont = props.get("REGION_UN") or props.get("continent") or props.get("region") or ""
        geom = feat.get("geometry", {})
        gtype = geom.get("type", "")
        coords = geom.get("coordinates", [])
        polygons_world = []  # list of rings (list of (x,y))
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
            continue
        # compute centroid using the largest polygon (by area) fallback
        largest = max(polygons_world, key=lambda r: abs(polygon_area(r)) if r else 0) if polygons_world else []
        centroid = polygon_centroid(largest) if largest else (0,0)
        bbox = None
        if polygons_world:
            xs=[p[0] for ring in polygons_world for p in ring]
            ys=[p[1] for ring in polygons_world for p in ring]
            bbox = (min(xs), min(ys), max(xs), max(ys))
        countries[cid] = {
            "id": cid,
            "name": name,
            "continent": cont,
            "polygons": polygons_world,
            "centroid": centroid,
            "bbox": bbox,
            "owner": None,
            "troops": 0,
            "adj": []  # adjacency will be generated heuristically below
        }
        cid += 1
    return countries

# adjacency heuristic: if centroids are near enough or polygons touch, make adjacency
def build_adjacency(countries, touch_threshold=18, neigh_radius=140):
    ids = list(countries.keys())
    for i in range(len(ids)):
        a = countries[ids[i]]
        ax0, ay0, ax1, ay1 = a["bbox"] if a["bbox"] else (0,0,0,0)
        for j in range(i+1, len(ids)):
            b = countries[ids[j]]
            bx0, by0, bx1, by1 = b["bbox"] if b["bbox"] else (0,0,0,0)
            # bbox overlap => likely adjacent -> cost 0
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

# --- Bot adapter (wrap heuristic_bot.decide)
def decide_local_bot(game, player):
    if heuristic_bot is None:
        return None
    snapshot = {"players": [], "pins": []}
    for pl in game.players:
        snapshot["players"].append({"name": pl.name, "money": pl.money, "is_bot": pl.is_bot})
    for cid, c in game.countries.items():
        snapshot["pins"].append({
            "id": c["id"],
            "name": c["name"],
            "owner": c.get("owner"),
            "troops": int(c.get("troops",0)),
            "adj": [{"to": a["to"], "cost": a.get("cost",0)} for a in c.get("adj", [])],
            "continent": c.get("continent","")
        })
    try:
        return heuristic_bot.decide(snapshot, player.name)
    except Exception as e:
        print("heuristic_bot error:", e)
        return None

# --- UI helpers
def draw_rounded_rect(surface, rect, color, radius=8):
    x,y,w,h = rect
    gfxdraw.aacircle(surface, x+radius, y+radius, radius, color)
    gfxdraw.filled_circle(surface, x+radius, y+radius, radius, color)
    gfxdraw.aacircle(surface, x+w-radius-1, y+radius, radius, color)
    gfxdraw.filled_circle(surface, x+w-radius-1, y+radius, radius, color)
    gfxdraw.aacircle(surface, x+radius, y+h-radius-1, radius, color)
    gfxdraw.filled_circle(surface, x+radius, y+h-radius-1, radius, color)
    gfxdraw.aacircle(surface, x+w-radius-1, y+h-radius-1, radius, color)
    gfxdraw.filled_circle(surface, x+w-radius-1, y+h-radius-1, radius, color)
    pygame.draw.rect(surface, color, (x+radius, y, w-2*radius, h))
    pygame.draw.rect(surface, color, (x, y+radius, w, h-2*radius))

class Button:
    def __init__(self, rect, text, font, bg=(60,120,200), fg=(255,255,255)):
        self.rect = pygame.Rect(rect)
        self.text = text
        self.font = font
        self.bg = bg
        self.fg = fg
        self.hover = False
    def draw(self, surf):
        col = tuple(min(255, c + (18 if self.hover else 0)) for c in self.bg)
        draw_rounded_rect(surf, (self.rect.x, self.rect.y, self.rect.w, self.rect.h), col, 8)
        t = self.font.render(self.text, True, self.fg)
        surf.blit(t, (self.rect.centerx - t.get_width()//2, self.rect.centery - t.get_height()//2))
    def handle_event(self, ev):
        if ev.type == pygame.MOUSEMOTION:
            self.hover = self.rect.collidepoint(ev.pos)
        if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
            if self.rect.collidepoint(ev.pos):
                return True
        return False

class Slider:
    def __init__(self, rect, a, b, initial):
        self.rect = pygame.Rect(rect)
        self.min = int(a); self.max = int(b)
        self.value = int(initial)
        self.dragging = False
    def draw(self, surf, font):
        track = pygame.Rect(self.rect.x, self.rect.centery-6, self.rect.width, 12)
        pygame.draw.rect(surf, (230,230,230), track, border_radius=6)
        frac = (self.value - self.min)/max(1,(self.max - self.min))
        fill = pygame.Rect(track.x, track.y, int(track.width*frac), track.height)
        pygame.draw.rect(surf, (80,160,220), fill, border_radius=6)
        thumb_x = track.x + int(track.width*frac); thumb_y = track.centery
        pygame.draw.circle(surf, (245,245,245), (thumb_x, thumb_y), 10)
        pygame.draw.circle(surf, (10,10,10), (thumb_x, thumb_y), 10, 2)
        t = font.render(str(self.value), True, (10,10,10))
        surf.blit(t, (self.rect.x + self.rect.width + 8, self.rect.y))
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
        self.value = int(round(self.min + frac*(self.max - self.min)))

# --- main UI / game loop
def main():
    ensure_assets()
    # download geojson if not present
    if not os.path.exists(GEOJSON_CACHE):
        ok = download_geojson(GEOJSON_CACHE)
        if not ok:
            print("Failed to obtain GeoJSON. Please place countries.geojson inside assets/ and re-run.")
    # load countries
    countries = {}
    if os.path.exists(GEOJSON_CACHE):
        try:
            countries = load_countries_from_geojson(GEOJSON_CACHE, WIDTH, MAP_H)
            print("Loaded", len(countries), "countries.")
        except Exception as e:
            print("Error parsing geojson:", e)
    if not countries:
        # fallback: create a tiny synthetic map
        countries = {
            1: {"id":1,"name":"Aland","continent":"X","polygons":[[(200,120),(260,120),(260,170),(200,170)]],"centroid":(230,145),"bbox":(200,120,260,170),"owner":None,"troops":0,"adj":[]},
            2: {"id":2,"name":"Boria","continent":"X","polygons":[[(300,120),(360,120),(360,170),(300,170)]],"centroid":(330,145),"bbox":(300,120,360,170),"owner":None,"troops":0,"adj":[]},
        }
    # build adjacency heuristically
    build_adjacency(countries)

    # create players (menu will replace these)
    players = []
    game = None

    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("GeoPolitical Domination 1.0.0")
    clock = pygame.time.Clock()
    font = pygame.font.SysFont(None, 16)
    bigfont = pygame.font.SysFont(None, 32)

    # map surface (base)
    map_surface = pygame.Surface((WIDTH, MAP_H))
    def render_base_map():
        map_surface.fill(SEA_COLOR)
        # draw country fills (default)
        for cid, c in countries.items():
            color = DEFAULT_COUNTRY_FILL
            for ring in c["polygons"]:
                if len(ring) >= 3:
                    try:
                        pygame.draw.polygon(map_surface, color, ring)
                        pygame.draw.polygon(map_surface, COUNTRY_BORDER_COLOR, ring, 1)
                    except Exception:
                        pass
    render_base_map()

    # camera
    cam_scale = 1.0
    cam_target_scale = 1.0
    cam_x = 0.0
    cam_y = 0.0
    cam_target_x = cam_x
    cam_target_y = cam_y
    min_scale = 1.0  # do not allow zooming out further than the full map
    max_scale = 4.0

    dragging_pan = False
    pan_start = (0,0)
    cam_start = (0,0)

    state = "menu"
    message = ""
    msg_until = 0

    # menu UI
    btn_new = Button((WIDTH//2 - 200, 180, 400, 56), "New Game", bigfont)
    btn_quit = Button((WIDTH//2 - 200, 260, 400, 56), "Quit", bigfont)
    bot_slider = Slider((WIDTH//2 - 200, 340, 400, 36), 0, 6, 2)

    selected_country = None
    expand_src = None
    expand_mode = None
    expand_send_dialog = False
    expand_send_slider = None
    expand_send_confirm = None
    expand_send_cancel = None

    gather_dialog = False
    gather_slider = None
    gather_confirm = None
    gather_cancel = None

    fullscreen = False

    def flash(msg, secs=2.5):
        nonlocal message, msg_until
        message = msg; msg_until = time.time() + secs

    def start_game(human_name, bot_count, chosen_country_id):
        # reset country ownership
        for c in countries.values():
            c["owner"] = None; c["troops"] = 0
        # assign colors
        palette = PALETTE.copy(); random.shuffle(palette)
        players = []
        human = Player(human_name, is_bot=False, color=palette.pop() if palette else random.choice(PALETTE))
        players.append(human)
        for i in range(bot_count):
            players.append(Player(f"bot{i+1}", is_bot=True, color=palette.pop() if palette else random.choice(PALETTE)))
        # give starting country to human
        chosen = countries.get(chosen_country_id)
        if chosen:
            chosen["owner"] = human.name; chosen["troops"] = 1; human.owned.add(chosen_country_id)
        # give bots a random starting country each
        for pl in players:
            if pl.is_bot:
                empty = [c for c in countries.values() if not c.get("owner")]
                if not empty: break
                pick = random.choice(empty)
                pick["owner"] = pl.name; pick["troops"] = 1; pl.owned.add(pick["id"])
        return Game(players, countries)

    # helper: find which country contains world_point (wx,wy)
    def country_at_world_point(wx, wy):
        # iterate countries (reverse order could be used to prioritize small islands later)
        for cid, c in countries.items():
            bbox = c.get("bbox")
            if bbox:
                if wx < bbox[0] or wx > bbox[2] or wy < bbox[1] or wy > bbox[3]:
                    continue
            # test each polygon ring
            for ring in c["polygons"]:
                # bbox check per ring
                rx0, ry0, rx1, ry1 = polygon_bbox(ring)
                if wx < rx0 or wx > rx1 or wy < ry0 or wy > ry1:
                    continue
                if point_in_poly(wx, wy, ring):
                    return c
        return None

    # main loop
    running = True
    last_click_t = 0; double_thresh = 0.35
    while running:
        # --- Create action buttons at frame start when playing so they are available in event handling & drawing
        # We will place the buttons below the player status boxes (which sit at MAP_H + 8 and are 72 tall).
        # So buttons' Y will be MAP_H + 8 + 72 + 12
        buttons_y = MAP_H + 8 + 72 + 12
        if state == "playing" and game:
            btn_w = 180; btn_h = 40; gap = 12
            ax = 8; ay = buttons_y
            # make these variables available in the whole scope of the loop iteration
            b_peace = Button((ax, ay, btn_w, btn_h), "A: Peace", font, bg=(80,200,120))
            b_expand = Button((ax+btn_w+gap, ay, btn_w, btn_h), "B: Expand", font, bg=(80,160,220))
            b_gather = Button((ax+2*(btn_w+gap), ay, btn_w, btn_h), "C: Gather Troops", font, bg=(200,160,80))
            b_nothing = Button((ax+3*(btn_w+gap), ay, btn_w, btn_h), "D: Do Nothing", font, bg=(200,80,80))
        else:
            b_peace = b_expand = b_gather = b_nothing = None

        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                running = False
            if ev.type == pygame.KEYDOWN:
                if ev.key == pygame.K_F11:
                    fullscreen = not fullscreen
                    if fullscreen:
                        screen = pygame.display.set_mode((0,0), pygame.FULLSCREEN)
                    else:
                        screen = pygame.display.set_mode((WIDTH, HEIGHT))
                if ev.key == pygame.K_ESCAPE:
                    if state == "menu":
                        running = False
                    else:
                        # return to menu (save not implemented)
                        state = "menu"
                        flash("Returning to menu")
            if ev.type == pygame.MOUSEWHEEL:
                # zooming centered on mouse
                mx, my = pygame.mouse.get_pos()
                factor = 1.18 ** ev.y
                new_scale = max(min_scale, min(max_scale, cam_target_scale * factor))
                # maintain world point under cursor
                world_x_before = cam_x + mx / cam_scale
                world_y_before = cam_y + my / cam_scale
                cam_target_scale = new_scale
                cam_target_x = world_x_before - mx / cam_target_scale
                cam_target_y = world_y_before - my / cam_target_scale
                cam_x = cam_target_x; cam_y = cam_target_y; cam_scale = cam_target_scale
            if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 2:
                # middle click to pan
                dragging_pan = True
                pan_start = ev.pos
                cam_start = (cam_x, cam_y)
            if ev.type == pygame.MOUSEBUTTONUP and ev.button == 2:
                dragging_pan = False
            if ev.type == pygame.MOUSEMOTION and dragging_pan:
                dx = (ev.pos[0] - pan_start[0]) / cam_scale
                dy = (ev.pos[1] - pan_start[1]) / cam_scale
                cam_x = cam_start[0] - dx
                cam_y = cam_start[1] - dy

            # UI -> menu
            if state == "menu":
                bot_slider.handle_event(ev)
                if btn_new.handle_event(ev):
                    state = "choose_start"
                    flash("Click on a country to choose your starting country.")
                if btn_quit.handle_event(ev):
                    running = False

            elif state == "choose_start":
                if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                    mx,my = ev.pos
                    # convert to world coords
                    wx = cam_x + mx / cam_scale
                    wy = cam_y + my / cam_scale
                    c = country_at_world_point(wx, wy)
                    if c:
                        human_name = "Player"
                        bot_count = bot_slider.value
                        game = start_game(human_name, bot_count, c["id"])
                        state = "playing"
                        flash(f"Game started. You start in {c['name']}")
                if ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE:
                    state = "menu"; flash("Cancelled")

            elif state == "playing" and game:
                cur = game.players[game.turn_idx]
                # handle dialog interactions first
                if gather_dialog and gather_slider:
                    gather_slider.handle_event(ev)
                    if gather_confirm and gather_confirm.handle_event(ev):
                        amt = gather_slider.value
                        cost = amt * TROOP_COST
                        if amt > 0 and cur.money >= cost:
                            cur.money -= cost
                            owned_countries = [c for c in countries.values() if c.get("owner")==cur.name]
                            if owned_countries:
                                i = 0
                                while amt > 0:
                                    owned_countries[i % len(owned_countries)]["troops"] += 1
                                    amt -= 1; i += 1
                            game.log(f"{cur.name} bought troops for ${cost}")
                        else:
                            game.log(f"{cur.name} bought 0 troops")
                        end_turn_housekeeping(game, cur)
                        gather_dialog=False; gather_slider=None; gather_confirm=None; gather_cancel=None
                    if gather_cancel and gather_cancel.handle_event(ev):
                        gather_dialog=False; gather_slider=None; gather_confirm=None; gather_cancel=None
                    continue

                if expand_send_dialog and expand_send_slider:
                    expand_send_slider.handle_event(ev)
                    if expand_send_confirm and expand_send_confirm.handle_event(ev):
                        send_amt = expand_send_slider.value
                        src = expand_src; tgt = selected_country
                        if not src or not tgt:
                            flash("Invalid selection")
                        else:
                            adj = next((a for a in src["adj"] if a["to"]==tgt["id"]), None)
                            if not adj:
                                flash("Not adjacent")
                            else:
                                cost = adj.get("cost",0)
                                if cost > 0:
                                    if cur.money >= cost:
                                        cur.money -= cost; game.log(f"{cur.name} paid crossing ${cost}")
                                    else:
                                        game.log(f"{cur.name} cannot pay crossing; cancelled")
                                        src["troops"] += send_amt
                                        expand_send_dialog=False
                                        expand_src=None; selected_country=None; expand_send_slider=None; expand_send_confirm=None; expand_send_cancel=None
                                        continue
                                src["troops"] -= send_amt
                                if src["troops"] <= 0:
                                    prev = src.get("owner")
                                    if prev:
                                        op = next((pl for pl in game.players if pl.name==prev), None)
                                        if op and src["id"] in op.owned:
                                            op.owned.remove(src["id"])
                                    src["owner"] = None; src["troops"] = 0
                                    game.log(f"{src['name']} now has 0 troops and is unowned.")
                                if not tgt.get("owner"):
                                    success = claim_country(cur, tgt, send_amt, game)
                                    if not success:
                                        src["troops"] += send_amt
                                else:
                                    attack_country(cur, src, tgt, send_amt, game)
                        end_turn_housekeeping(game, cur)
                        expand_send_dialog=False
                        expand_src=None; selected_country=None; expand_send_slider=None; expand_send_confirm=None; expand_send_cancel=None
                    if expand_send_cancel and expand_send_cancel.handle_event(ev):
                        if expand_src and expand_send_slider:
                            expand_src["troops"] += expand_send_slider.value
                        expand_send_dialog=False
                        expand_src=None; selected_country=None; expand_send_slider=None; expand_send_confirm=None; expand_send_cancel=None
                    continue

                # handle action button events (the buttons were created earlier)
                if b_peace and b_peace.handle_event(ev) and not cur.is_bot:
                    cur.vulnerable = True; cur.was_attacked = False
                    game.log(f"{cur.name} chose PEACE")
                    end_turn_housekeeping(game, cur)
                elif b_gather and b_gather.handle_event(ev) and not cur.is_bot:
                    roll = random.randint(1,20)
                    max_afford = cur.money // TROOP_COST
                    max_allowed = min(roll, max_afford)
                    srect = (WIDTH//2 - 260, HEIGHT//2 - 20, 520, 36)
                    gather_slider = Slider(srect, 0, max_allowed, 0)
                    gather_confirm = Button((WIDTH//2 + 140, HEIGHT//2 + 28, 120, 36), "Confirm", font, bg=(80,200,120))
                    gather_cancel = Button((WIDTH//2 - 260, HEIGHT//2 + 28, 120, 36), "Cancel", font, bg=(200,80,80))
                    gather_dialog = True
                elif b_nothing and b_nothing.handle_event(ev) and not cur.is_bot:
                    game.log(f"{cur.name} did NOTHING"); end_turn_housekeeping(game, cur)
                elif b_expand and b_expand.handle_event(ev) and not cur.is_bot:
                    expand_mode = "source"; flash("Click your source country (a country you own)")
                else:
                    # map clicks & expand flow (left click)
                    if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                        mx,my = ev.pos
                        # convert to world coords
                        wx = cam_x + mx / cam_scale
                        wy = cam_y + my / cam_scale
                        clicked = country_at_world_point(wx, wy)
                        if clicked:
                            selected_country = clicked
                            # expand flow
                            if expand_mode == "source":
                                if selected_country.get("owner") != cur.name:
                                    flash("Select a country you own as source.")
                                else:
                                    expand_src = selected_country
                                    expand_mode = "target"
                                    flash("Now click the target country to expand/attack")
                            elif expand_mode == "target" and expand_src:
                                tgt = selected_country
                                adj = next((a for a in expand_src["adj"] if a["to"]==tgt["id"]), None)
                                if not adj:
                                    flash("Target not adjacent; choose another.")
                                    expand_src = None; expand_mode = None
                                else:
                                    available = expand_src.get("troops", 0)
                                    if available <= 0:
                                        flash("No troops available at source.")
                                        expand_src=None; expand_mode=None
                                    else:
                                        if available == 1:
                                            send_amt = 1
                                            cost = adj.get("cost", 0)
                                            if cost > 0:
                                                if cur.money >= cost:
                                                    cur.money -= cost; game.log(f"{cur.name} paid crossing ${cost}")
                                                else:
                                                    game.log(f"{cur.name} cannot pay crossing; cancelled")
                                                    expand_src=None; expand_mode=None; selected_country=None
                                                    continue
                                            expand_src["troops"] -= send_amt
                                            if expand_src["troops"] <= 0:
                                                prev = expand_src.get("owner")
                                                if prev:
                                                    op = next((pl for pl in game.players if pl.name==prev), None)
                                                    if op and expand_src["id"] in op.owned:
                                                        op.owned.remove(expand_src["id"])
                                                expand_src["owner"] = None; expand_src["troops"]=0; game.log(f"{expand_src['name']} now unowned")
                                            if not tgt.get("owner"):
                                                success = claim_country(cur, tgt, send_amt, game)
                                                if not success:
                                                    expand_src["troops"] += send_amt
                                            else:
                                                attack_country(cur, expand_src, tgt, send_amt, game)
                                            end_turn_housekeeping(game, cur)
                                            expand_src=None; expand_mode=None; selected_country=None
                                        else:
                                            # open slider dialog
                                            expand_send_dialog = True
                                            rect = (WIDTH//2 - 260, HEIGHT//2 - 20, 520, 36)
                                            expand_send_slider = Slider(rect, 1, available, 1)
                                            expand_send_confirm = Button((WIDTH//2+140, HEIGHT//2+28, 120,36), "Send", font, bg=(80,200,120))
                                            expand_send_cancel = Button((WIDTH//2-260, HEIGHT//2+28, 120,36), "Cancel", font, bg=(200,80,80))
                        else:
                            # clicked empty sea
                            selected_country = None

                # Bot turn processing: ensure bots wait until player's turn is over
                if game.players and game.players[game.turn_idx].is_bot:
                    bot_player = game.players[game.turn_idx]
                    if not getattr(game, "bot_thread", None) or not game.bot_thread.is_alive():
                        def bot_worker():
                            try:
                                act = decide_local_bot(game, bot_player)
                                if not act:
                                    act = ("NOTHING", None)
                                cmd, params = act
                                if cmd == "PEACE":
                                    bot_player.vulnerable=True; bot_player.was_attacked=False; game.log(f"{bot_player.name} chooses PEACE")
                                    end_turn_housekeeping(game, bot_player)
                                elif cmd == "GATHER":
                                    roll = random.randint(1,20)
                                    max_afford = bot_player.money // TROOP_COST
                                    buy = min(roll, max_afford)
                                    cost = buy * TROOP_COST
                                    bot_player.money -= cost
                                    owned_countries = [c for c in countries.values() if c.get("owner")==bot_player.name]
                                    i=0
                                    while buy>0 and owned_countries:
                                        owned_countries[i%len(owned_countries)]["troops"] += 1
                                        buy-=1; i+=1
                                    game.log(f"{bot_player.name} bought troops for ${cost}")
                                    end_turn_housekeeping(game, bot_player)
                                elif cmd == "NOTHING":
                                    game.log(f"{bot_player.name} does NOTHING"); end_turn_housekeeping(game, bot_player)
                                elif cmd == "EXPAND" and params:
                                    src_id,tgt_id,send = params
                                    src = countries.get(src_id); tgt = countries.get(tgt_id)
                                    if not src or not tgt or src.get("owner") != bot_player.name:
                                        game.log(f"{bot_player.name} invalid expand -> skip"); end_turn_housekeeping(game, bot_player)
                                    else:
                                        send = max(1, min(send, int(src.get("troops",0))))
                                        adj = next((a for a in src.get("adj",[]) if a["to"]==tgt_id), None)
                                        if adj and adj.get("cost",0) > 0:
                                            if bot_player.money >= adj["cost"]:
                                                bot_player.money -= adj["cost"]; game.log(f"{bot_player.name} paid crossing ${adj['cost']}")
                                            else:
                                                game.log(f"{bot_player.name} cannot pay crossing; move aborted"); end_turn_housekeeping(game, bot_player); return
                                        src["troops"] -= send
                                        if src["troops"] <= 0:
                                            prev = src.get("owner")
                                            if prev:
                                                op = next((pl for pl in game.players if pl.name==prev), None)
                                                if op and src["id"] in op.owned: op.owned.remove(src["id"])
                                            src["owner"] = None; src["troops"]=0
                                            game.log(f"{src['name']} now unowned")
                                        if not tgt.get("owner"):
                                            success = claim_country(bot_player, tgt, send, game)
                                            if not success: src["troops"] += send
                                        else:
                                            attack_country(bot_player, src, tgt, send, game)
                                        end_turn_housekeeping(game, bot_player)
                            except Exception as e:
                                print("bot_worker error:", e)
                                try: end_turn_housekeeping(game, bot_player)
                                except: pass
                            finally:
                                game.bot_thread = None
                        game.bot_thread = threading.Thread(target=bot_worker, daemon=True)
                        game.bot_thread.start()

        # camera smoothing
        if 'cam_target_scale' in locals():
            cam_scale += (cam_target_scale - cam_scale) * 0.30
        if 'cam_target_x' in locals():
            cam_x += (cam_target_x - cam_x) * 0.30
        if 'cam_target_y' in locals():
            cam_y += (cam_target_y - cam_y) * 0.30

        # clamp camera so visible window stays inside map boundaries
        screen_w = screen.get_width() if fullscreen else WIDTH
        screen_h = screen.get_height() if fullscreen else HEIGHT
        vis_w = screen_w / max(cam_scale, 1e-6)
        vis_h = MAP_H / max(cam_scale, 1e-6)
        cam_x = max(0.0, min(cam_x, max(0.0, WIDTH - vis_w)))
        cam_y = max(0.0, min(cam_y, max(0.0, MAP_H - vis_h)))

        # draw map scaled
        screen.fill((12,16,24))
        scaled_w = max(1, int(WIDTH * cam_scale))
        scaled_h = max(1, int(MAP_H * cam_scale))
        try:
            scaled_map = pygame.transform.smoothscale(map_surface, (scaled_w, scaled_h))
            blit_x = int(-cam_x * cam_scale)
            blit_y = int(-cam_y * cam_scale)
            screen.blit(scaled_map, (blit_x, blit_y))
        except Exception:
            screen.blit(map_surface, (0,0))

        # draw ownership fills & borders (re-draw owned countries on top of base)
        for cid, c in countries.items():
            owner = c.get("owner")
            if owner:
                pl = next((p for p in (game.players if game else []) if p.name==owner), None)
                fill_col = pl.color if pl else (160,160,160)
                for ring in c["polygons"]:
                    transformed = [((int(round(x*cam_scale + (-cam_x*cam_scale)))), (int(round(y*cam_scale + (-cam_y*cam_scale))))) for x,y in ring]
                    try:
                        pygame.draw.polygon(screen, fill_col, transformed)
                        pygame.draw.polygon(screen, COUNTRY_BORDER_COLOR, transformed, 1)
                    except Exception:
                        pass

        # draw armies (small pins at centroid, scaled)
        if game:
            for cid, c in countries.items():
                cx, cy = c.get("centroid", (0,0))
                sx = int((cx - cam_x) * cam_scale)
                sy = int((cy - cam_y) * cam_scale)
                troops = int(c.get("troops", 0))
                if troops > 0:
                    owner = c.get("owner")
                    pl = next((p for p in game.players if p.name==owner), None) if game else None
                    color = pl.color if pl else (40,40,40)
                    r = max(1, int(ARMY_PIN_RADIUS * PIN_SCALE * cam_scale))
                    pygame.draw.circle(screen, (0,0,0), (sx, sy), r+1)
                    pygame.draw.circle(screen, color, (sx, sy), r)
                    t = font.render(str(troops), True, (255,255,255) if sum(color[:3])<360 else (0,0,0))
                    screen.blit(t, (sx - t.get_width()//2, sy - t.get_height()//2))

        # draw translucent HUD background so map is visible beneath
        hud_surf = pygame.Surface((screen.get_width(), screen.get_height() - MAP_H), pygame.SRCALPHA)
        hud_surf.fill((245,245,245, 230))  # alpha 230 -> slightly translucent
        screen.blit(hud_surf, (0, MAP_H))

        # draw a faint separator line
        pygame.draw.line(screen, (200,200,200), (0, MAP_H), (screen.get_width(), MAP_H), 2)

        if state == "menu":
            title = bigfont.render("GeoPolitical Domination", True, (255,255,255))
            tx = (screen.get_width()//2 - title.get_width()//2) if fullscreen else (WIDTH//2 - title.get_width()//2)
            screen.blit(title, (tx, 80))
            btn_new.draw(screen); btn_quit.draw(screen)
            bot_slider.draw(screen, font)
            note = font.render("New Game → choose starting country on the map. F11 toggles fullscreen.", True, (220,220,220))
            nx = (screen.get_width()//2 - note.get_width()//2) if fullscreen else (WIDTH//2 - note.get_width()//2)
            screen.blit(note, (nx, 460))

        elif state == "choose_start":
            # overlay
            overlay = pygame.Surface((screen.get_width(), screen.get_height()), pygame.SRCALPHA)
            overlay.fill((0,0,0,110))
            screen.blit(overlay, (0,0))
            ins = bigfont.render("Choose your starting country (click). ESC to cancel", True, (255,255,255))
            screen.blit(ins, (screen.get_width()//2 - ins.get_width()//2, screen.get_height()//2 - 40))

        elif state == "playing" and game:
            # top-right turn indicator
            cur = game.players[game.turn_idx]
            panel_x = screen.get_width() - 360
            pygame.draw.rect(screen, (240,240,240), (panel_x, 8, 340, 46))
            pygame.draw.rect(screen, (200,200,200), (panel_x, 8, 340, 46), 2)
            turn_text = f"TURN: {cur.name} {'(BOT)' if cur.is_bot else '(YOU)'}"
            screen.blit(bigfont.render(turn_text, True, (10,10,10)), (panel_x + 6, 14))
            if not cur.is_bot:
                screen.blit(font.render("It's your turn — make a choice.", True, (10,10,10)), (panel_x+6, 34))

            # player panels along HUD
            x0 = 8; y0 = MAP_H + 8
            for i, pl in enumerate(game.players):
                px = x0 + i*230
                pr = pygame.Rect(px, y0, 220, 72)
                pygame.draw.rect(screen, pl.color, pr)
                pygame.draw.rect(screen, (10,10,10), pr, 2)
                screen.blit(bigfont.render(pl.name + (" (BOT)" if pl.is_bot else ""), True, (0,0,0)), (pr.x+8, pr.y+6))
                stats = font.render(f"Money:${pl.money}  Troops:{pl.troop_count(countries)}  Countries:{pl.country_count()}", True, (0,0,0))
                screen.blit(stats, (pr.x+8, pr.y+38))
                if i == game.turn_idx:
                    pygame.draw.rect(screen, (255,255,255), pr, 3)

            # draw action buttons after player panels so they sit on top
            if b_peace:
                b_peace.draw(screen); b_expand.draw(screen); b_gather.draw(screen); b_nothing.draw(screen)

            # selected country info panel
            if selected_country:
                pr = pygame.Rect(screen.get_width() - 340, MAP_H + 8, 320, 200)
                pygame.draw.rect(screen, HUD_BG, pr); pygame.draw.rect(screen, (200,200,200), pr, 1)
                screen.blit(font.render(selected_country["name"], True, (0,0,0)), (pr.x+8, pr.y+8))
                screen.blit(font.render(f"Owner: {selected_country.get('owner')}   Troops: {selected_country.get('troops')}", True, (10,10,10)), (pr.x+8, pr.y+36))
                screen.blit(font.render(f"Continent: {selected_country.get('continent','')}", True, (10,10,10)), (pr.x+8, pr.y+64))
                screen.blit(font.render("Click source then target to expand/attack. Gather uses a roll slider.", True, (80,80,80)), (pr.x+8, pr.y+108))

            # mini-log
            recent = game.logs[-8:]
            for i, l in enumerate(recent):
                screen.blit(font.render(l, True, (10,10,10)), (8, MAP_H - 20*(len(recent)-i)))

            # show dialogs (gather / expand send)
            if gather_dialog and gather_slider:
                overlay = pygame.Surface((screen.get_width(), screen.get_height()), pygame.SRCALPHA); overlay.fill((0,0,0,140)); screen.blit(overlay,(0,0))
                dw,dh = 680,180; dx = screen.get_width()//2 - dw//2; dy = screen.get_height()//2 - dh//2
                pygame.draw.rect(screen, (250,250,250),(dx,dy,dw,dh)); pygame.draw.rect(screen,(190,190,190),(dx,dy,dw,dh),2)
                screen.blit(bigfont.render("Gather Troops", True, (10,10,10)), (dx+12, dy+10))
                info = font.render("Roll-based max available to buy. Cost ${}/troop.".format(TROOP_COST), True, (20,20,20))
                screen.blit(info, (dx+12, dy+60))
                gather_slider.draw(screen, font)
                gather_confirm.draw(screen); gather_cancel.draw(screen)

            if expand_send_dialog and expand_send_slider and expand_src and selected_country:
                overlay = pygame.Surface((screen.get_width(), screen.get_height()), pygame.SRCALPHA); overlay.fill((0,0,0,160)); screen.blit(overlay,(0,0))
                dw,dh = 640,160; dx = screen.get_width()//2 - dw//2; dy = screen.get_height()//2 - dh//2
                pygame.draw.rect(screen,(250,250,250),(dx,dy,dw,dh)); pygame.draw.rect(screen,(190,190,190),(dx,dy,dw,dh),2)
                screen.blit(bigfont.render(f"Send troops from {expand_src['name']} to {selected_country['name']}", True, (10,10,10)), (dx+12, dy+10))
                info = font.render(f"Source troops: {expand_src['troops']}   Crossing costs will be applied if any.", True, (10,10,10))
                screen.blit(info, (dx+12, dy+56))
                expand_send_slider.draw(screen, font)
                expand_send_confirm.draw(screen); expand_send_cancel.draw(screen)

        # flash message
        if message and time.time() < msg_until:
            mx = (screen.get_width()//2 - 200) if fullscreen else (WIDTH//2 - 200)
            screen.blit(font.render(message, True, (10,10,10)), (mx, MAP_H + 12 + 72 + 60))

        pygame.display.flip()
        clock.tick(FPS)

    pygame.quit()

if __name__ == "__main__":
    main()
