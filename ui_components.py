# ui_components.py
"""
Reusable UI components for GeoPolitical Domination.
Button, Slider, font/shadow caches, and drawing helpers.
"""

import time
import logging
import pygame

from constants import (
    U, TEXT_PRIMARY, TEXT_SECONDARY, HUD_BORDER, FONT_CACHE_MAX,
    HOVER_LERP_SPEED, PRESS_DECAY_SPEED,
)

logger = logging.getLogger(__name__)

# ============================================================
# Color helpers
# ============================================================


def lighten(color, amount=25):
    """Lighten an RGB color by a fixed amount."""
    return tuple(min(255, c + amount) for c in color[:3])


def darken(color, amount=25):
    """Darken an RGB color by a fixed amount."""
    return tuple(max(0, c - amount) for c in color[:3])


# ============================================================
# Font render cache
# ============================================================

_font_cache = {}


def cached_render(fnt, text, color):
    """Render text with caching to avoid re-rendering the same string each frame."""
    key = (id(fnt), text, color)
    surf = _font_cache.get(key)
    if surf is None:
        if len(_font_cache) >= FONT_CACHE_MAX:
            _font_cache.clear()
        surf = fnt.render(text, True, color)
        _font_cache[key] = surf
    return surf


# ============================================================
# Shadow cache
# ============================================================

_shadow_cache = {}


def draw_shadow_rect(surface, rect, radius=10, offset=3, alpha=50):
    """Draw a soft shadow rectangle (cached)."""
    x, y, w, h = rect
    key = (w, h, radius, offset, alpha)
    shadow = _shadow_cache.get(key)
    if shadow is None:
        shadow = pygame.Surface((w + offset * 2, h + offset * 2), pygame.SRCALPHA)
        pygame.draw.rect(
            shadow, (0, 0, 0, alpha), (offset, offset, w, h), border_radius=radius
        )
        _shadow_cache[key] = shadow
    surface.blit(shadow, (x - offset, y - offset))


def draw_rounded_rect(surface, rect, color, radius=10, border=0, border_color=None):
    """Draw a rounded rectangle with optional border."""
    x, y, w, h = rect
    if border > 0:
        pygame.draw.rect(
            surface, border_color or color, (x, y, w, h), border, border_radius=radius
        )
    else:
        pygame.draw.rect(surface, color, (x, y, w, h), border_radius=radius)


# ============================================================
# Button
# ============================================================


class Button:
    """Animated button with smooth hover scale, glow, and click press."""

    def __init__(self, rect, text, font, bg=(55, 120, 220), fg=(255, 255, 255)):
        self.rect = pygame.Rect(rect)
        self.text = text
        self.font = font
        self.bg = bg
        self.fg = fg
        self.hover = False
        self._hover_t = 0.0
        self._press_t = 0.0
        self._last_time = time.time()

    def draw(self, surf):
        now = time.time()
        dt = min(now - self._last_time, 0.05)
        self._last_time = now

        # Animate hover (smooth lerp)
        target = 1.0 if self.hover else 0.0
        self._hover_t += (target - self._hover_t) * min(1.0, dt * HOVER_LERP_SPEED)
        ht = self._hover_t

        # Press animation decay
        if self._press_t > 0:
            self._press_t = max(0, self._press_t - dt * PRESS_DECAY_SPEED)
        pt = self._press_t

        r = self.rect
        br = max(6, r.h // 4)
        pad = max(4, r.h // 10)

        # Scale effect: grow slightly on hover, shrink on press
        scale_offset = int(3 * U * ht) - int(4 * U * pt)
        dx = r.x - scale_offset
        dy = r.y - scale_offset
        dw = r.w + scale_offset * 2
        dh = r.h + scale_offset * 2

        # Shadow (bigger on hover)
        shadow_off = pad + int(2 * U * ht)
        shadow_alpha = 30 + int(30 * ht)
        pygame.draw.rect(
            surf,
            (0, 0, 0, shadow_alpha),
            (dx + shadow_off // 2, dy + shadow_off // 2 + U, dw, dh),
            border_radius=br,
        )

        # Background color interpolation
        col = tuple(
            int(self.bg[i] + (min(255, self.bg[i] + 30) - self.bg[i]) * ht)
            for i in range(3)
        )
        pygame.draw.rect(surf, col, (dx, dy, dw, dh), border_radius=br)

        # Top highlight (more visible on hover)
        hl_alpha = 40 + int(30 * ht)
        hl = pygame.Surface((dw - pad, max(1, dh // 3)), pygame.SRCALPHA)
        hl.fill((*lighten(col, 40), hl_alpha))
        surf.blit(hl, (dx + pad // 2, dy + 1))

        # Hover glow border
        if ht > 0.05:
            glow_alpha = int(80 * ht)
            pygame.draw.rect(
                surf,
                (*lighten(col, 60), glow_alpha),
                (dx - 1, dy - 1, dw + 2, dh + 2),
                max(1, int(2 * U * ht)),
                border_radius=br,
            )

        # Text
        t = cached_render(self.font, self.text, self.fg)
        surf.blit(
            t, (dx + dw // 2 - t.get_width() // 2, dy + dh // 2 - t.get_height() // 2)
        )

    def handle_event(self, ev):
        if ev.type == pygame.MOUSEMOTION:
            self.hover = self.rect.collidepoint(ev.pos)
        if (
            ev.type == pygame.MOUSEBUTTONDOWN
            and ev.button == 1
            and self.rect.collidepoint(ev.pos)
        ):
            self._press_t = 1.0
            return True
        return False


# ============================================================
# Slider
# ============================================================


class Slider:
    """Horizontal slider for selecting integer values in a range."""

    def __init__(self, rect, a, b, initial):
        self.rect = pygame.Rect(rect)
        self.min = int(a)
        self.max = int(b)
        self.value = max(self.min, min(self.max, int(initial)))
        self.dragging = False

    def draw(self, surf, font):
        th = max(6, self.rect.h // 4)
        tr = th // 2
        track = pygame.Rect(
            self.rect.x, self.rect.centery - th // 2, self.rect.width, th
        )
        pygame.draw.rect(surf, (50, 60, 85), track, border_radius=tr)

        frac = (self.value - self.min) / max(1, (self.max - self.min))
        fill_w = int(track.width * frac)
        if fill_w > 0:
            pygame.draw.rect(
                surf,
                (55, 160, 220),
                (track.x, track.y, fill_w, track.height),
                border_radius=tr,
            )

        thumb_x = track.x + int(track.width * frac)
        thumb_y = track.centery
        thumb_r = max(8, self.rect.h // 2)
        pygame.draw.circle(surf, (0, 0, 0), (thumb_x + 1, thumb_y + 1), thumb_r + 1)
        pygame.draw.circle(surf, (255, 255, 255), (thumb_x, thumb_y), thumb_r)
        pygame.draw.circle(surf, (55, 160, 220), (thumb_x, thumb_y), thumb_r, 2)

        t = cached_render(font, str(self.value), TEXT_PRIMARY)
        surf.blit(t, (self.rect.x + self.rect.width + 12 * U, self.rect.y))

    def handle_event(self, ev):
        if (
            ev.type == pygame.MOUSEBUTTONDOWN
            and ev.button == 1
            and self.rect.collidepoint(ev.pos)
        ):
            self.dragging = True
            self._update_from(ev.pos)
            return True
        if ev.type == pygame.MOUSEBUTTONUP and ev.button == 1:
            self.dragging = False
        if ev.type == pygame.MOUSEMOTION and self.dragging:
            self._update_from(ev.pos)
        return False

    def _update_from(self, pos):
        x = pos[0]
        left = self.rect.x
        w = self.rect.width
        frac = (x - left) / w if w else 0
        frac = max(0.0, min(1.0, frac))
        self.value = int(round(self.min + frac * (self.max - self.min)))


# ============================================================
# Hex color conversion
# ============================================================


def hex_to_rgb(hexstr):
    """Convert a hex color string or RGB list/tuple to an (R, G, B) tuple."""
    if not hexstr:
        return None
    if isinstance(hexstr, (list, tuple)):
        try:
            return (int(hexstr[0]), int(hexstr[1]), int(hexstr[2]))
        except (ValueError, IndexError, TypeError):
            return None
    s = hexstr.strip()
    if s.startswith("#"):
        s = s[1:]
    if len(s) == 3:
        s = "".join([c * 2 for c in s])
    if len(s) < 6:
        return None
    try:
        r = int(s[0:2], 16)
        g = int(s[2:4], 16)
        b = int(s[4:6], 16)
        return (r, g, b)
    except ValueError:
        return None


def get_player_color_rgb(player_name, snapshot_players):
    """Get the RGB color for a player from a snapshot player list."""
    from constants import HEX_PALETTE

    if not player_name:
        return (120, 120, 120)
    for p in snapshot_players:
        if p.get("name") == player_name:
            col = p.get("color")
            rgb = hex_to_rgb(col)
            if rgb:
                return rgb
    # Fallback: deterministic color by name
    idx = sum(ord(c) for c in (player_name or "")) % len(HEX_PALETTE)
    return hex_to_rgb(HEX_PALETTE[idx])
