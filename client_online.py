# client_online_full.py
"""
GeoPolitical Domination — Online client (full).
- You must type country names (exact spelling, case-insensitive) to claim starting country and to move to other countries.
- Country names are NOT displayed in logs or in the selected-country panel: logs use obfuscated/generic messages only.
Fixed input handling: single centralized KEYDOWN handler (no duplicate letters).
"""

import os
import sys
import json
import math
import random
import threading
import time
from collections import defaultdict
import pygame
from pygame import gfxdraw

from firebase_sync import FirebaseController

# Try to import updater (optional feature)
try:
    import updater
    UPDATER_AVAILABLE = True
except Exception as e:
    print(f"Updater not available: {e}")
    UPDATER_AVAILABLE = False

# --- constants & paths
BASE_DIR = os.path.dirname(__file__)
ASSET_DIR = os.path.join(BASE_DIR, "assets")
GEOJSON_CACHE = os.path.join(ASSET_DIR, "countries.geojson")

WIDTH, HEIGHT = 1280, 820
MAP_H = HEIGHT - 160
FPS = 45

CLAIM_COST = 200
TROOP_COST = 50

MAX_MERCATOR_LAT = 85.05112878

# local fallback palette (same strings as server)
HEX_PALETTE = [
    "#C85050", "#64C864", "#3C78C8", "#F5F5F5", "#D0C248", "#A050C8", "#50A0A0", "#C87A50"
]

COLOR_PALETTE = {
    "red": (200,80,80),
    "green": (100,200,100),
    "blue": (60,120,200),
    "white": (245,245,245),
    "yellow": (220,200,60),
    "violet": (160,80,200),
}
PALETTE = list(COLOR_PALETTE.values())

SEA_COLOR = (180,220,255)
COUNTRY_BORDER_COLOR = (90,90,90)
DEFAULT_COUNTRY_FILL = (210,220,230)
HUD_BG = (245,245,245)

ARMY_PIN_RADIUS = 5
PIN_SCALE = 0.5

# --- geometry helpers
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
    xs=[p[0] for p in poly]; ys=[p[1] for p in poly]; return (min(xs), min(ys), max(xs), max(ys))
def point_in_poly(x,y,poly):
    inside=False; n=len(poly); j=n-1
    for i in range(n):
        xi,yi = poly[i]; xj,yj = poly[j]
        intersect = ((yi>y) != (yj>y)) and (x < (xj-xi)*(y-yi)/(yj-yi+1e-12) + xi)
        if intersect: inside = not inside
        j=i
    return inside
def polygon_centroid(poly):
    area=0.0; cx=0.0; cy=0.0; n=len(poly)
    if n==0: return (0,0)
    for i in range(n):
        x0,y0=poly[i]; x1,y1=poly[(i+1)%n]; a=x0*y1 - x1*y0
        area += a; cx += (x0+x1)*a; cy += (y0+y1)*a
    if abs(area) < 1e-6:
        return (int(sum(p[0] for p in poly)/n), int(sum(p[1] for p in poly)/n))
    area = area/2.0
    cx = cx/(6.0*area); cy = cy/(6.0*area)
    return (int(round(cx)), int(round(cy)))

def polygon_area(poly):
    a=0.0; n=len(poly)
    for i in range(n):
        x0,y0=poly[i]; x1,y1=poly[(i+1)%n]; a += x0*y1 - x1*y0
    return a/2.0

# --- geojson loader (local file required per-user)
def load_countries_from_geojson(path, map_w, map_h):
    data = json.load(open(path,"r",encoding="utf-8"))
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
        polygons_world = []
        if gtype == "Polygon":
            for ring in coords:
                pts=[lonlat_to_pixel(lon, lat, map_w, map_h) for lon, lat in ring]
                polygons_world.append(pts)
        elif gtype == "MultiPolygon":
            for poly in coords:
                for ring in poly:
                    pts=[lonlat_to_pixel(lon, lat, map_w, map_h) for lon, lat in ring]
                    polygons_world.append(pts)
        else:
            cid += 1
            continue
        if not polygons_world:
            cid += 1
            continue
        largest = max(polygons_world, key=lambda r: abs(polygon_area(r)) if r else 0)
        centroid = polygon_centroid(largest) if largest else (0,0)
        bbox = None
        if polygons_world:
            xs=[p[0] for ring in polygons_world for p in ring]; ys=[p[1] for ring in polygons_world for p in ring]
            bbox = (min(xs), min(ys), max(xs), max(ys))
        countries[cid] = {"id":cid,"name":name,"continent":cont,"polygons":polygons_world,"centroid":centroid,"bbox":bbox,"owner":None,"troops":0,"adj":[]}
        cid += 1
    return countries

def build_adjacency(countries, touch_threshold=18, neigh_radius=140):
    ids = list(countries.keys())
    for i in range(len(ids)):
        a = countries[ids[i]]
        ax0,ay0,ax1,ay1 = a["bbox"] if a["bbox"] else (0,0,0,0)
        for j in range(i+1, len(ids)):
            b = countries[ids[j]]
            bx0,by0,bx1,by1 = b["bbox"] if b["bbox"] else (0,0,0,0)
            overlap = not (ax1 < bx0 or bx1 < ax0 or ay1 < by0 or by1 < ay0)
            cen_a = a["centroid"]; cen_b = b["centroid"]
            if cen_a and cen_b:
                dx=cen_a[0]-cen_b[0]; dy=cen_a[1]-cen_b[1]; d=math.hypot(dx,dy)
            else:
                d=9999
            if overlap or d <= neigh_radius:
                cost = 0 if overlap else 100 if d < 220 else 300
                a["adj"].append({"to":b["id"], "cost":cost})
                b["adj"].append({"to":a["id"], "cost":cost})

# --- UI helpers
def draw_rounded_rect(surface, rect, color, radius=8):
    x,y,w,h = rect
    gfxdraw.aacircle(surface, x+radius, y+radius, radius, color); gfxdraw.filled_circle(surface, x+radius, y+radius, radius, color)
    gfxdraw.aacircle(surface, x+w-radius-1, y+radius, radius, color); gfxdraw.filled_circle(surface, x+w-radius-1, y+radius, radius, color)
    gfxdraw.aacircle(surface, x+radius, y+h-radius-1, radius, color); gfxdraw.filled_circle(surface, x+radius, y+h-radius-1, radius, color)
    gfxdraw.aacircle(surface, x+w-radius-1, y+h-radius-1, radius, color); gfxdraw.filled_circle(surface, x+w-radius-1, y+h-radius-1, radius, color)
    pygame.draw.rect(surface, color, (x+radius, y, w-2*radius, h)); pygame.draw.rect(surface, color, (x, y+radius, w, h-2*radius))

class Button:
    def __init__(self, rect, text, font, bg=(60,120,200), fg=(255,255,255)):
        self.rect = pygame.Rect(rect); self.text=text; self.font=font; self.bg=bg; self.fg=fg; self.hover=False
    def draw(self,surf):
        col = tuple(min(255, c + (18 if self.hover else 0)) for c in self.bg)
        draw_rounded_rect(surf, (self.rect.x, self.rect.y, self.rect.w, self.rect.h), col, 8)
        t = self.font.render(self.text, True, self.fg)
        surf.blit(t, (self.rect.centerx - t.get_width()//2, self.rect.centery - t.get_height()//2))
    def handle_event(self, ev):
        if ev.type == pygame.MOUSEMOTION: self.hover = self.rect.collidepoint(ev.pos)
        if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1 and self.rect.collidepoint(ev.pos): return True
        return False

class Slider:
    def __init__(self, rect, a,b,initial):
        self.rect = pygame.Rect(rect); self.min=int(a); self.max=int(b); self.value=int(initial); self.dragging=False
    def draw(self, surf, font):
        track = pygame.Rect(self.rect.x, self.rect.centery-6, self.rect.width, 12)
        pygame.draw.rect(surf, (230,230,230), track, border_radius=6)
        frac = (self.value - self.min)/max(1,(self.max - self.min))
        fill = pygame.Rect(track.x, track.y, int(track.width*frac), track.height)
        pygame.draw.rect(surf, (80,160,220), fill, border_radius=6)
        thumb_x = track.x + int(track.width*frac); thumb_y = track.centery
        pygame.draw.circle(surf, (245,245,245), (thumb_x, thumb_y), 10); pygame.draw.circle(surf, (10,10,10), (thumb_x, thumb_y), 10, 2)
        t = font.render(str(self.value), True, (10,10,10)); surf.blit(t, (self.rect.x + self.rect.width + 8, self.rect.y))
    def handle_event(self, ev):
        if ev.type == pygame.MOUSEBUTTONDOWN and ev.button==1 and self.rect.collidepoint(ev.pos): self.dragging=True; self.update_from(ev.pos); return True
        if ev.type == pygame.MOUSEBUTTONUP and ev.button==1: self.dragging=False
        if ev.type == pygame.MOUSEMOTION and self.dragging: self.update_from(ev.pos)
        return False
    def update_from(self, pos):
        x=pos[0]; left=self.rect.x; w=self.rect.width
        frac = (x-left)/w if w else 0; frac = max(0.0, min(1.0, frac))
        self.value = int(round(self.min + frac*(self.max - self.min)))

# --- RemoteGameView keeps snapshot from Firestore
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
                "status": self.status
            }

# --- color helpers on client
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
        s = "".join([c*2 for c in s])
    if len(s) < 6:
        return None
    try:
        r = int(s[0:2], 16); g = int(s[2:4], 16); b = int(s[4:6], 16)
        return (r,g,b)
    except Exception:
        return None

def get_player_color_rgb(player_name, snapshot_players):
    if not player_name:
        return (120,120,120)
    for p in snapshot_players:
        if p.get("name") == player_name:
            col = p.get("color")
            rgb = hex_to_rgb(col)
            if rgb:
                return rgb
    # fallback deterministic by name into HEX_PALETTE
    idx = sum(ord(c) for c in (player_name or "")) % len(HEX_PALETTE)
    return hex_to_rgb(HEX_PALETTE[idx])

# --- small helpers for name lookup & obfuscated UI text
def find_country_by_name(countries, name):
    if not name:
        return None
    name = name.strip().casefold()
    for cid, c in countries.items():
        if (c.get("name","") or "").strip().casefold() == name:
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

# --- main app
def main():
    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("GeoPolitical Domination - Online")
    clock = pygame.time.Clock()
    font = pygame.font.SysFont(None, 16); bigfont = pygame.font.SysFont(None, 32)

    os.makedirs(ASSET_DIR, exist_ok=True)

    local_countries = {}
    if os.path.exists(GEOJSON_CACHE):
        try:
            local_countries = load_countries_from_geojson(GEOJSON_CACHE, WIDTH, MAP_H)
            print("Loaded local geojson countries:", len(local_countries))
        except Exception as e:
            print("Error parsing geojson:", e)
    if not local_countries:
        local_countries = {
            1: {"id":1,"name":"Aland","continent":"X","polygons":[[(200,120),(260,120),(260,170),(200,170)]],"centroid":(230,145),"bbox":(200,120,260,170),"owner":None,"troops":0,"adj":[]},
            2: {"id":2,"name":"Boria","continent":"X","polygons":[[(300,120),(360,120),(360,170),(300,170)]],"centroid":(330,145),"bbox":(300,120,360,170),"owner":None,"troops":0,"adj":[]},
        }
    build_adjacency(local_countries)

    map_surface = pygame.Surface((WIDTH, MAP_H))
    def render_base_map():
        map_surface.fill(SEA_COLOR)
        for cid, c in local_countries.items():
            color = DEFAULT_COUNTRY_FILL
            for ring in c["polygons"]:
                if len(ring) >= 3:
                    try:
                        pygame.draw.polygon(map_surface, color, ring)
                        pygame.draw.polygon(map_surface, COUNTRY_BORDER_COLOR, ring, 1)
                    except Exception:
                        pass
    render_base_map()

    try:
        fc = FirebaseController()
    except Exception as e:
        print("Failed to create FirebaseController:", e)
        print("Make sure your gpd_secrets.txt or service account file is present.")
        return

    remote = RemoteGameView()
    def on_game_update(doc):
        sanitized_logs = []
        for l in (doc.get("logs", []) or []):
            sanitized_logs.append(l)
        doc2 = dict(doc); doc2["logs"] = sanitized_logs
        remote.update_from_doc(doc2)

    # Check for updates (in background, non-blocking)
    update_info = None
    update_check_done = False
    
    def check_updates_background():
        nonlocal update_info, update_check_done
        try:
            if UPDATER_AVAILABLE:
                update_info = updater.silent_check()
            update_check_done = True
        except Exception as e:
            print(f"Update check failed: {e}")
            update_check_done = True
    
    # Start update check in background
    if UPDATER_AVAILABLE:
        update_thread = threading.Thread(target=check_updates_background, daemon=True)
        update_thread.start()
    else:
        update_check_done = True

    # UI & state
    state = "menu"   # menu | choose_start | playing
    message = ""; msg_until = 0
    current_game_id = None
    my_player_name = None

    input_active = {"game_id": False, "player_name": False, "player_password": False, "room_password": False, "starting_country": False, "move_target": False}
    user_inputs = {"game_id": "room1", "player_name": "Player", "player_password": "", "room_password": "", "starting_country": "", "move_target": ""}
    small_input_rects = {
        "game_id": pygame.Rect(WIDTH//2 - 260, 200, 520, 36),
        "player_name": pygame.Rect(WIDTH//2 - 260, 260, 520, 36),
        "player_password": pygame.Rect(WIDTH//2 - 260, 320, 520, 36),
        "room_password": pygame.Rect(WIDTH//2 - 260, 380, 520, 36),
        "starting_country": pygame.Rect(WIDTH//2 - 260, 420, 520, 36),
        "move_target": pygame.Rect(WIDTH//2 - 260, MAP_H + 8 + 120, 520, 28)
    }

    selected_country = None
    expand_src_id = None
    expand_mode = None
    expand_send_dialog = False
    expand_send_slider = None
    expand_send_confirm = None
    expand_send_cancel = None
    gather_dialog = False
    gather_slider = None
    gather_confirm = None
    gather_cancel = None

    buttons_y = MAP_H + 8 + 72 + 12
    btn_w=180; btn_h=40; gap=12; ax=8; ay=buttons_y
    b_peace = Button((ax, ay, btn_w, btn_h), "A: Peace", font, bg=(80,200,120))
    b_expand = Button((ax+btn_w+gap, ay, btn_w, btn_h), "B: Expand", font, bg=(80,160,220))
    b_gather = Button((ax+2*(btn_w+gap), ay, btn_w, btn_h), "C: Gather Troops", font, bg=(200,160,80))
    b_nothing = Button((ax+3*(btn_w+gap), ay, btn_w, btn_h), "D: Do Nothing", font, bg=(200,80,80))

    def flash(msg, secs=3.0):
        nonlocal message, msg_until
        message = msg; msg_until = time.time() + secs
        print("[UI]", msg)

    def draw_input_box(key, label, hide_password=False):
        r = small_input_rects[key]
        pygame.draw.rect(screen, (255,255,255), r); pygame.draw.rect(screen, (190,190,190), r, 2)
        txt = user_inputs.get(key, "")
        # Hide password fields with asterisks
        if hide_password and txt:
            display_txt = "*" * len(txt)
        else:
            display_txt = txt
        t = font.render(display_txt, True, (10,10,10))
        screen.blit(t, (r.x+8, r.y+6))
        label_surf = font.render(label, True, (120,120,120))
        screen.blit(label_surf, (r.x, r.y - 18))

    def build_minimal_countries_for_upload():
        minimal = {}
        for cid, c in local_countries.items():
            minimal[str(cid)] = {"owner": None, "troops": 0, "continent": c.get("continent","")}
        return minimal

    def snap():
        return remote.snapshot()

    def is_my_turn():
        s = snap()
        players = s["players"]
        if not players: return False
        idx = s["turn_idx"]
        if idx < 0 or idx >= len(players): return False
        return players[idx].get("name") == my_player_name

    def remote_country(cid):
        s = snap()
        return s["countries"].get(str(cid), {"owner": None, "troops": 0, "continent": local_countries.get(cid,{}).get("continent","")})

    # centralized key processing helper (single place to mutate inputs)
    def handle_key_input(ev):
        if ev.key == pygame.K_BACKSPACE:
            for k,v in input_active.items():
                if v:
                    user_inputs[k] = user_inputs[k][:-1]
        elif ev.key == pygame.K_RETURN:
            for k,v in input_active.items():
                if v:
                    input_active[k] = False
        else:
            ch = ev.unicode
            if ch and len(ch) == 1:
                for k,v in input_active.items():
                    if v:
                        user_inputs[k] += ch

    running = True
    while running:
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                running = False

            # global keyboard: handle full-screen / escape / centralized typing
            if ev.type == pygame.KEYDOWN:
                if ev.key == pygame.K_F11:
                    # toggle fullscreen
                    screen = pygame.display.set_mode((0,0), pygame.FULLSCREEN) if screen.get_flags() & pygame.FULLSCREEN == 0 else pygame.display.set_mode((WIDTH, HEIGHT))
                elif ev.key == pygame.K_ESCAPE:
                    if state == "menu":
                        running = False
                    else:
                        state = "menu"
                        flash("Returned to menu")
                else:
                    # centralized typing handler -> prevents duplicated characters
                    handle_key_input(ev)

                    # ----- NEW: treat Enter as Confirm/Send -----
                    if ev.key == pygame.K_RETURN:
                        # menu/choose_start: confirm starting-country claim if applicable
                        if state == "choose_start" and input_active.get("starting_country"):
                            name_in = user_inputs.get("starting_country","").strip()
                            if not name_in:
                                flash("Please type a country name to claim.")
                            else:
                                found = find_country_by_name(local_countries, name_in)
                                if not found:
                                    flash("No country matched that exact name. Check spelling.")
                                else:
                                    try:
                                        ok = fc.claim_starting_country(current_game_id, my_player_name, found["id"])
                                    except Exception as e:
                                        flash(f"Claim failed: {e}")
                                        ok = False
                                    if ok:
                                        flash("Successfully claimed that starting country. Waiting for game state to sync.")
                                        state = "playing"
                                    else:
                                        flash("That country was just taken by someone else. Pick another.")
                        # playing: if user typed a move target while in expand target mode
                        elif state == "playing" and expand_mode == "target" and expand_src_id:
                            name_in = user_inputs.get("move_target","").strip()
                            if not name_in:
                                flash("Please type a target country name.")
                            else:
                                tgt = find_country_by_name(local_countries, name_in)
                                if not tgt:
                                    flash("No country matched that exact name.")
                                else:
                                    adj = next((a for a in local_countries[expand_src_id].get("adj", []) if a["to"]==tgt["id"]), None)
                                    if not adj:
                                        flash("Target not adjacent to source; move aborted.")
                                    else:
                                        available = int(local_countries[expand_src_id].get("troops",0))
                                        cross_cost = int(adj.get("cost",0) or 0)
                                        # If only one troop -> send immediately
                                        if available <= 1:
                                            try:
                                                fc.submit_action(current_game_id, my_player_name, "EXPAND", {"src": expand_src_id, "tgt": tgt["id"], "send": 1, "cross_cost": cross_cost})
                                            except Exception as e:
                                                flash(f"Expand failed: {e}")
                                            expand_mode = None; expand_src_id = None; user_inputs["move_target"] = ""
                                        else:
                                            # open send dialog (user can adjust slider); pressing Enter again will confirm
                                            expand_send_dialog = True
                                            rect = (WIDTH//2 - 260, HEIGHT//2 - 20, 520, 36)
                                            expand_send_slider = Slider(rect, 1, available, 1)
                                            expand_send_confirm = Button((WIDTH//2+140, HEIGHT//2+28, 120,36), "Send", font, bg=(80,200,120))
                                            expand_send_cancel = Button((WIDTH//2-260, HEIGHT//2+28, 120,36), "Cancel", font, bg=(200,80,80))
                        # if gather dialog is open, confirm with current slider value
                        elif gather_dialog and gather_slider:
                            buy = gather_slider.value
                            try:
                                fc.submit_action(current_game_id, my_player_name, "GATHER", {"buy": buy})
                            except Exception as e:
                                flash(f"Gather failed: {e}")
                            gather_dialog=False; gather_slider=None; gather_confirm=None; gather_cancel=None
                        # if expand_send_dialog is open, confirm with slider current value
                        elif expand_send_dialog and expand_send_slider and expand_src_id:
                            send_amt = expand_send_slider.value
                            tgt_name = user_inputs.get("move_target","").strip()
                            if not tgt_name:
                                flash("Please type a target country in the Move Target box.")
                            else:
                                tgt = find_country_by_name(local_countries, tgt_name)
                                if not tgt:
                                    flash("Target name did not match any country.")
                                else:
                                    adj = next((a for a in local_countries[expand_src_id]["adj"] if a["to"]==tgt["id"]), None)
                                    if not adj:
                                        flash("Target not adjacent to source.")
                                    else:
                                        try:
                                            fc.submit_action(current_game_id, my_player_name, "EXPAND", {"src": expand_src_id, "tgt": tgt["id"], "send": send_amt, "cross_cost": int(adj.get("cost",0) or 0)})
                                        except Exception as e:
                                            flash(f"Expand failed: {e}")
                            expand_send_dialog=False; expand_src_id=None; user_inputs["move_target"] = ""


            # universal click: activate inputs if inside input boxes
            if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                for k,r in small_input_rects.items():
                    if r.collidepoint(ev.pos):
                        for kk in input_active: input_active[kk]=False
                        input_active[k] = True
                        break

            # state-specific handling (only click-based actions here; typing already centralized)
            if state == "menu":
                if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                    mx,my = ev.pos
                    # create & join handled via buttons drawn below (detect click on rectangles)
                    create_rect = pygame.Rect(WIDTH//2 - 260, 380, 240, 56)
                    join_rect = pygame.Rect(WIDTH//2 + 20, 380, 240, 56)
                    if create_rect.collidepoint((mx,my)):
                        gid = user_inputs["game_id"].strip(); pname = user_inputs["player_name"].strip()
                        if not gid or not pname:
                            flash("Please provide Game ID and Player name")
                        else:
                            player_pass = user_inputs.get("player_password", "").strip()
                            room_pass = user_inputs.get("room_password", "").strip()
                            try:
                                doc = fc.create_or_open_game(gid, pname, player_password=player_pass, room_password=room_pass)
                                current_game_id = gid; my_player_name = pname
                                if not doc.get("countries"):
                                    minimal = build_minimal_countries_for_upload()
                                    fc.upload_initial_countries(gid, minimal)
                                fc.listen_to_game(gid, on_game_update)
                                has_country = False
                                for k,v in (doc.get("countries") or {}).items():
                                    if v.get("owner") == pname:
                                        has_country = True; break
                                if has_country:
                                    state = "playing"; flash(f"Created and joined room '{gid}' as {pname}")
                                else:
                                    state = "choose_start"; flash("Type the exact name of the starting country to claim it.")
                            except Exception as e:
                                flash(f"Create failed: {e}")
                    elif join_rect.collidepoint((mx,my)):
                        gid = user_inputs["game_id"].strip(); pname = user_inputs["player_name"].strip()
                        if not gid or not pname:
                            flash("Please provide Game ID and Player name")
                        else:
                            player_pass = user_inputs.get("player_password", "").strip()
                            room_pass = user_inputs.get("room_password", "").strip()
                            try:
                                doc = fc.create_or_open_game(gid, pname, player_password=player_pass, room_password=room_pass)
                                current_game_id = gid; my_player_name = pname
                                if not doc.get("countries"):
                                    minimal = build_minimal_countries_for_upload()
                                    fc.upload_initial_countries(gid, minimal)
                                fc.listen_to_game(gid, on_game_update)
                                has_country = False
                                for k,v in (doc.get("countries") or {}).items():
                                    if v.get("owner") == pname:
                                        has_country = True; break
                                if has_country:
                                    state = "playing"; flash(f"Joined room '{gid}' as {pname}")
                                else:
                                    state = "choose_start"; flash("Type the exact name of the starting country to claim it.")
                            except Exception as e:
                                flash(f"Join failed: {e}")

            elif state == "choose_start":
                if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                    mx,my = ev.pos
                    confirm_rect = pygame.Rect(WIDTH//2 + 20, 500, 160, 44)
                    cancel_rect = pygame.Rect(WIDTH//2 - 200, 500, 160, 44)
                    if confirm_rect.collidepoint((mx,my)):
                        name_in = user_inputs.get("starting_country","").strip()
                        if not name_in:
                            flash("Please type a country name to claim.")
                        else:
                            found = find_country_by_name(local_countries, name_in)
                            if not found:
                                flash("No country matched that exact name. Check spelling.")
                            else:
                                try:
                                    ok = fc.claim_starting_country(current_game_id, my_player_name, found["id"])
                                except Exception as e:
                                    flash(f"Claim failed: {e}")
                                    ok = False
                                if ok:
                                    flash("Successfully claimed that starting country. Waiting for game state to sync.")
                                    state = "playing"
                                else:
                                    flash("That country was just taken by someone else. Pick another.")
                    elif cancel_rect.collidepoint((mx,my)):
                        state = "menu"; current_game_id = None; my_player_name = None

            elif state == "playing":
                # gather dialog, expand dialog and main action buttons are click-based; typing handled centrally
                if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                    mx,my = ev.pos
                    # action button clicks
                    if b_peace.rect.collidepoint((mx,my)):
                        if not is_my_turn():
                            flash("Not your turn")
                        else:
                            try:
                                fc.submit_action(current_game_id, my_player_name, "PEACE", {})
                            except Exception as e:
                                flash(f"PEACE failed: {e}")
                    elif b_gather.rect.collidepoint((mx,my)):
                        if not is_my_turn():
                            flash("Not your turn")
                        else:
                            s = snap()
                            player_money = 0
                            for p in s["players"]:
                                if p.get("name")==my_player_name:
                                    player_money = int(p.get("money", 0) or 0)
                            roll = random.randint(1,20)
                            max_allowed = min(roll, player_money // TROOP_COST) if TROOP_COST>0 else roll
                            rect = (WIDTH//2 - 260, HEIGHT//2 - 20, 520, 36)
                            gather_slider = Slider(rect, 0, max_allowed, 0)
                            gather_confirm = Button((WIDTH//2 + 140, HEIGHT//2 + 28, 120, 36), "Confirm", font, bg=(80,200,120))
                            gather_cancel = Button((WIDTH//2 - 260, HEIGHT//2 + 28, 120, 36), "Cancel", font, bg=(200,80,80))
                            gather_dialog = True
                    elif b_nothing.rect.collidepoint((mx,my)):
                        if not is_my_turn():
                            flash("Not your turn")
                        else:
                            try:
                                fc.submit_action(current_game_id, my_player_name, "NOTHING", {})
                            except Exception as e:
                                flash(f"NOTHING failed: {e}")
                    elif b_expand.rect.collidepoint((mx,my)):
                        if not is_my_turn():
                            flash("Not your turn")
                        else:
                            expand_mode = "source"; flash("Click your source country (owned by you).")
                    else:
                        # clicked on map -> select country (local polygons)
                        clicked = None
                        for cid, c in local_countries.items():
                            for ring in c["polygons"]:
                                if point_in_poly(mx, my, ring):
                                    clicked = c; break
                            if clicked: break
                        if not clicked:
                            selected_country = None
                        else:
                            selected_country = clicked["id"]
                            if expand_mode == "source":
                                rc = remote_country(selected_country)
                                if rc.get("owner") != my_player_name:
                                    flash("Select a country you own as source.")
                                else:
                                    expand_src_id = selected_country; expand_mode = "target"
                                    user_inputs["move_target"] = ""
                                    for kk in input_active: input_active[kk] = False
                                    input_active["move_target"] = True
                                    flash("Type the exact target country name (case-insensitive) and press Send.")
                            elif expand_mode == "target" and expand_src_id:
                                flash("Please type the target country name in the Move Target input (not by clicking).")

                # dialog buttons handled above; submit for expand/gather handled in separate blocks below
                if gather_dialog and gather_slider:
                    gather_slider.handle_event(ev)
                    if gather_confirm and gather_confirm.handle_event(ev):
                        buy = gather_slider.value
                        try:
                            fc.submit_action(current_game_id, my_player_name, "GATHER", {"buy": buy})
                        except Exception as e:
                            flash(f"Gather failed: {e}")
                        gather_dialog=False; gather_slider=None; gather_confirm=None; gather_cancel=None
                    if gather_cancel and gather_cancel.handle_event(ev):
                        gather_dialog=False; gather_slider=None; gather_confirm=None; gather_cancel=None
                if expand_send_dialog and expand_send_slider:
                    expand_send_slider.handle_event(ev)
                    if expand_send_confirm and expand_send_confirm.handle_event(ev):
                        send_amt = expand_send_slider.value
                        src = expand_src_id; tgt_name = user_inputs.get("move_target","").strip()
                        if not src or not tgt_name:
                            flash("Invalid selection or target name.")
                        else:
                            tgt = find_country_by_name(local_countries, tgt_name)
                            if not tgt:
                                flash("Target name did not match any country.")
                            else:
                                adj = next((a for a in local_countries[src]["adj"] if a["to"]==tgt["id"]), None)
                                if not adj:
                                    flash("Target not adjacent to source; move aborted.")
                                else:
                                    cross_cost = int(adj.get("cost",0) or 0)
                                    try:
                                        fc.submit_action(current_game_id, my_player_name, "EXPAND", {"src": src, "tgt": tgt["id"], "send": send_amt, "cross_cost": cross_cost})
                                    except Exception as e:
                                        flash(f"Expand failed: {e}")
                        expand_send_dialog=False; expand_src_id=None; user_inputs["move_target"] = ""
                    if expand_send_cancel and expand_send_cancel.handle_event(ev):
                        expand_send_dialog=False; expand_src_id=None; user_inputs["move_target"] = ""

        # rendering
        screen.fill((12,16,24))
        screen.blit(map_surface, (0,0))

        snapshot = snap()
        # draw ownership using server colors
        for cid, c in local_countries.items():
            rinfo = snapshot["countries"].get(str(cid), {}) if snapshot else {}
            owner = rinfo.get("owner")
            if owner:
                color = get_player_color_rgb(owner, snapshot["players"])
                if color is None: color = (160,160,160)
                for ring in c["polygons"]:
                    try:
                        pygame.draw.polygon(screen, color, ring)
                        pygame.draw.polygon(screen, COUNTRY_BORDER_COLOR, ring, 1)
                    except:
                        pass

        # troop pins using server colors
        for cid_str, rc in snapshot["countries"].items():
            try:
                cid = int(cid_str)
            except:
                continue
            c = local_countries.get(cid)
            if not c: continue
            cx, cy = c.get("centroid", (0,0))
            troops = int(rc.get("troops", 0) or 0)
            if troops > 0:
                owner = rc.get("owner")
                color = get_player_color_rgb(owner, snapshot["players"]) if owner else (40,40,40)
                sx = int(cx); sy = int(cy)
                r = max(1, int(ARMY_PIN_RADIUS * PIN_SCALE))
                pygame.draw.circle(screen, (0,0,0), (sx, sy), r+1)
                pygame.draw.circle(screen, color, (sx, sy), r)
                t = font.render(str(troops), True, (255,255,255) if sum(color[:3])<360 else (0,0,0))
                screen.blit(t, (sx - t.get_width()//2, sy - t.get_height()//2))

        # HUD
        hud_surf = pygame.Surface((WIDTH, HEIGHT - MAP_H), pygame.SRCALPHA); hud_surf.fill((245,245,245,230)); screen.blit(hud_surf, (0, MAP_H))
        pygame.draw.line(screen, (200,200,200), (0, MAP_H), (WIDTH, MAP_H), 2)

        # top-right turn indicator
        panel_x = WIDTH - 360
        pygame.draw.rect(screen, (240,240,240), (panel_x, 8, 340, 46)); pygame.draw.rect(screen, (200,200,200), (panel_x, 8, 340, 46), 2)
        cur_name = "..."
        players = snapshot["players"]
        if players and 0 <= snapshot["turn_idx"] < len(players):
            cur_name = players[snapshot["turn_idx"]].get("name", "...")
        screen.blit(bigfont.render(f"TURN: {cur_name}", True, (10,10,10)), (panel_x + 6, 14))

        # player panels - use server color for each player if available
        x0 = 8; y0 = MAP_H + 8
        for i, pl in enumerate(players):
            px = x0 + i*230; pr = pygame.Rect(px, y0, 220, 72)
            pl_color = hex_to_rgb(pl.get("color")) or PALETTE[i % len(PALETTE)]
            pygame.draw.rect(screen, pl_color, pr); pygame.draw.rect(screen, (10,10,10), pr, 2)
            screen.blit(bigfont.render(pl.get("name","?") + (" (BOT)" if pl.get("is_bot") else ""), True, (0,0,0)), (pr.x+8, pr.y+6))
            money = pl.get("money", 0)
            troop_count = sum(int(v.get("troops", 0) or 0) for v in snapshot["countries"].values() if v.get("owner")==pl.get("name"))
            country_count = sum(1 for v in snapshot["countries"].values() if v.get("owner")==pl.get("name"))
            stats = font.render(f"Money:${money}  Troops:{troop_count}  Countries:{country_count}", True, (0,0,0))
            screen.blit(stats, (pr.x+8, pr.y+38))
            if i == snapshot["turn_idx"]: pygame.draw.rect(screen, (255,255,255), pr, 3)

        # action buttons
        b_peace.draw(screen); b_expand.draw(screen); b_gather.draw(screen); b_nothing.draw(screen)

        # selected info — hide country name, show continent and owner & troops
        if selected_country:
            c = local_countries.get(selected_country)
            rc = snapshot["countries"].get(str(selected_country), {})
            pr = pygame.Rect(WIDTH - 340, MAP_H + 8, 320, 200)
            pygame.draw.rect(screen, HUD_BG, pr); pygame.draw.rect(screen, (200,200,200), pr, 1)
            screen.blit(font.render("Country (hidden)", True, (0,0,0)), (pr.x+8, pr.y+8))
            screen.blit(font.render(f"Owner: {rc.get('owner')}   Troops: {rc.get('troops')}", True, (10,10,10)), (pr.x+8, pr.y+36))
            screen.blit(font.render(f"Continent: {c.get('continent','')}", True, (10,10,10)), (pr.x+8, pr.y+64))
            screen.blit(font.render("Type exact target name to move into it (no clicking).", True, (80,80,80)), (pr.x+8, pr.y+108))
            inp = small_input_rects["move_target"]
            pygame.draw.rect(screen, (255,255,255), inp); pygame.draw.rect(screen, (180,180,180), inp, 2)
            screen.blit(font.render(user_inputs.get("move_target",""), True, (0,0,0)), (inp.x+6, inp.y+4))

        # dialogs
        if gather_dialog and gather_slider:
            overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA); overlay.fill((0,0,0,140)); screen.blit(overlay,(0,0))
            dw,dh = 680,180; dx = WIDTH//2 - dw//2; dy = HEIGHT//2 - dh//2
            pygame.draw.rect(screen, (250,250,250),(dx,dy,dw,dh)); pygame.draw.rect(screen,(190,190,190),(dx,dy,dw,dh),2)
            screen.blit(bigfont.render("Gather Troops", True, (10,10,10)), (dx+12, dy+10))
            info = font.render("Roll-based max available to buy. Cost ${}/troop.".format(TROOP_COST), True, (20,20,20))
            screen.blit(info, (dx+12, dy+60))
            gather_slider.draw(screen, font); gather_confirm.draw(screen); gather_cancel.draw(screen)

        if expand_send_dialog and expand_send_slider:
            overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA); overlay.fill((0,0,0,160)); screen.blit(overlay,(0,0))
            dw,dh = 640,160; dx = WIDTH//2 - dw//2; dy = HEIGHT//2 - dh//2
            pygame.draw.rect(screen,(250,250,250),(dx,dy,dw,dh)); pygame.draw.rect(screen,(190,190,190),(dx,dy,dw,dh),2)
            screen.blit(bigfont.render("Send troops (typed target)", True, (10,10,10)), (dx+12, dy+10))
            info = font.render("Choose number of troops to send. Crossing costs applied server-side.", True, (10,10,10))
            screen.blit(info, (dx+12, dy+56))
            input_rect = pygame.Rect(dx+12, dy+88, 520, 28)
            pygame.draw.rect(screen, (255,255,255), input_rect); pygame.draw.rect(screen, (180,180,180), input_rect, 2)
            screen.blit(font.render(user_inputs.get("move_target",""), True, (0,0,0)), (input_rect.x+6, input_rect.y+4))
            expand_send_slider.draw(screen, font); expand_send_confirm.draw(screen); expand_send_cancel.draw(screen)

        # logs (sanitized to avoid exposing country names)
        recent = snapshot["logs"][-8:]
        for i,l in enumerate(recent):
            safe_line = l
            for c in local_countries.values():
                cname = (c.get("name","") or "").strip()
                if cname and cname.lower() in safe_line.lower():
                    safe_line = safe_line.lower().replace(cname.lower(), "[country]")
            screen.blit(font.render(safe_line, True, (10,10,10)), (8, MAP_H - 20*(len(recent)-i)))

        # menu overlays (when in menu or choose_start)
        if state == "menu":
            title = bigfont.render("GeoPolitical Domination - Online", True, (255,255,255))
            screen.blit(title, (WIDTH//2 - title.get_width()//2, 60))
            draw_input_box("game_id", "Game ID:")
            draw_input_box("player_name", "Player name:")
            draw_input_box("player_password", "Player Password:", hide_password=True)
            draw_input_box("room_password", "Room Password (optional):", hide_password=True)
            hint = font.render("Create: new ID + optional room password. Join: ID + room password if required.", True, (180,180,180))
            screen.blit(hint, (WIDTH//2 - hint.get_width()//2, 440))
            create_btn = Button((WIDTH//2 - 260, 470, 240, 56), "Create & Host", bigfont)
            join_btn = Button((WIDTH//2 + 20, 470, 240, 56), "Join Room", bigfont)
            create_btn.draw(screen); join_btn.draw(screen)
            
            # Update notification
            if update_check_done and update_info and update_info.get('update_available'):
                update_rect = pygame.Rect(WIDTH - 320, HEIGHT - 90, 310, 80)
                pygame.draw.rect(screen, (255, 200, 100), update_rect)
                pygame.draw.rect(screen, (200, 150, 50), update_rect, 2)
                update_title = font.render("Update Available!", True, (20, 20, 20))
                screen.blit(update_title, (update_rect.x + 10, update_rect.y + 8))
                current_v = update_info.get('current', 'unknown')
                latest_v = update_info.get('latest', 'unknown')
                version_text = font.render(f"{current_v} -> {latest_v}", True, (20, 20, 20))
                screen.blit(version_text, (update_rect.x + 10, update_rect.y + 28))
                update_btn = Button((update_rect.x + 10, update_rect.y + 48, 140, 24), "Update Now", font, bg=(80, 160, 80))
                dismiss_btn = Button((update_rect.x + 160, update_rect.y + 48, 140, 24), "Ignore", font, bg=(140, 140, 140))
                update_btn.draw(screen)
                dismiss_btn.draw(screen)
                
                # Handle update button clicks
                for ev in pygame.event.get(pygame.MOUSEBUTTONDOWN):
                    if ev.button == 1:
                        if update_btn.rect.collidepoint(ev.pos):
                            # Launch updater in separate process
                            try:
                                import subprocess
                                if sys.platform == 'win32':
                                    subprocess.Popen([sys.executable, 'updater.py'], creationflags=subprocess.CREATE_NEW_CONSOLE)
                                else:
                                    subprocess.Popen([sys.executable, 'updater.py'])
                                flash("Updater launched! Close this window to update.")
                            except Exception as e:
                                flash(f"Failed to launch updater: {e}")
                        elif dismiss_btn.rect.collidepoint(ev.pos):
                            update_info = None

        if state == "choose_start":
            overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA); overlay.fill((0,0,0,120)); screen.blit(overlay,(0,0))
            ins = bigfont.render("Type the exact name of the country you want to start in.", True, (255,255,255))
            screen.blit(ins, (WIDTH//2 - ins.get_width()//2, 120))
            draw_input_box("starting_country", "Starting country name (exact, case-insensitive):")
            confirm_btn = Button((WIDTH//2 + 20, 500, 160, 44), "Confirm Claim", bigfont)
            cancel_btn = Button((WIDTH//2 - 200, 500, 160, 44), "Cancel", bigfont, bg=(200,80,80))
            confirm_btn.draw(screen); cancel_btn.draw(screen)

        # messages
        if message and time.time() < msg_until:
            screen.blit(font.render(message, True, (10,10,10)), (WIDTH//2 - 200, MAP_H + 12 + 72 + 60))

        pygame.display.flip(); clock.tick(FPS)

    pygame.quit()

if __name__ == "__main__":
    main()
