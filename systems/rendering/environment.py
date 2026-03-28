# systems/rendering/environment.py – tiberium, fog, water shimmer, day/night, influence
import math, pygame
from config import P, W, H, HUD_H, TILE, MAP_W, MAP_H, TWATER, INFLUENCE_RADIUS
from components import Position, Team, BuildingData
from systems.rendering import _cfg
from systems.rendering.helpers import (
    _get_surf, _glow, _darker, _ensure_surfaces, _fog_dark, _fog_dim,
)


# ── Tiberium ──────────────────────────────────────────────────────────────────
def _draw_tiberium(surf, x, y, ratio, t):
    n = max(2, int(9 * ratio))
    pulse = 0.5 + 0.5 * math.sin(t * 2.0 + x * 0.02 + y * 0.03)
    for i in range(n):
        angle = i * 0.72 + (i % 3) * 0.4
        dist  = 3 + (i % 4) * 5
        # Crystal dimensions: taller, more varied
        h   = 5 + (i % 4) * 3 + int(2 * ratio)
        hw  = max(2, h // 3 + (i % 2))
        # Gentle sway
        sway = math.sin(t * 1.5 + i * 1.1) * 1.2
        cx = int(x + math.cos(angle) * dist * ratio + sway)
        cy = int(y + math.sin(angle) * dist * ratio)
        # Crystal: hexagonal prism shape (6-point)
        tip_y = cy - h
        base_y = cy + 2
        mid_y = cy - h // 3
        pts = [
            (cx, tip_y),                   # top point
            (cx + hw, mid_y),              # upper right
            (cx + hw - 1, base_y),         # lower right
            (cx, base_y + 1),              # bottom center
            (cx - hw + 1, base_y),         # lower left
            (cx - hw, mid_y),              # upper left
        ]
        # Darker fill for body
        body_c = (15 + (i * 7) % 15, 140 + (i * 11) % 50, 30 + (i * 5) % 20)
        pygame.draw.polygon(surf, body_c, pts)
        # Edge highlight (brighter on right face = light direction)
        pygame.draw.line(surf, P['tib_hi'], (cx, tip_y), (cx + hw, mid_y), 1)
        pygame.draw.line(surf, P['tib_hi'], (cx + hw, mid_y), (cx + hw - 1, base_y), 1)
        # Left edge darker
        edge_dk = _darker(body_c, 25)
        pygame.draw.line(surf, edge_dk, (cx, tip_y), (cx - hw, mid_y), 1)
        pygame.draw.line(surf, edge_dk, (cx - hw, mid_y), (cx - hw + 1, base_y), 1)
        # Specular highlight dot near tip
        spec_pulse = 0.6 + 0.4 * math.sin(t * 3.0 + i * 2.3)
        if spec_pulse > 0.7:
            pygame.draw.circle(surf, (180, 255, 180), (cx, tip_y + 2), 1)
        # Inner vein line (center of crystal)
        if h >= 8:
            vein_c = (40, 220, 70, 120)
            pygame.draw.line(surf, P['tib_hi'], (cx, tip_y + 2), (cx, base_y - 1), 1)


# ── Projectile ────────────────────────────────────────────────────────────────
def _draw_projectile(surf, pos, proj):
    c = P['proj_p'] if proj.team == _cfg.PLAYER else P['proj_e']
    ix, iy = int(pos.x), int(pos.y)
    # Direction for comet tail
    dx = proj.tx - pos.x
    dy = proj.ty - pos.y
    d = max(1, math.hypot(dx, dy))
    nx, ny = dx / d, dy / d
    # Outer glow (big)
    _glow(surf, ix, iy, c, 14, 100)
    # Hot core
    pygame.draw.circle(surf, (255, 255, 255), (ix, iy), 3)
    pygame.draw.circle(surf, c, (ix, iy), 4, 1)
    # Comet tail (3 fading circles behind projectile)
    for i in range(1, 4):
        tx = int(pos.x - nx * i * 6)
        ty = int(pos.y - ny * i * 6)
        a = max(0, 160 - i * 50)
        r = max(1, 4 - i)
        ts = _get_surf(r * 2 + 2, r * 2 + 2)
        pygame.draw.circle(ts, (*c[:3], a), (r + 1, r + 1), r)
        surf.blit(ts, (tx - r - 1, ty - r - 1))


# ── Fog of war ────────────────────────────────────────────────────────────────
_fog_zoom_cache = {}  # (tile_s, kind) → Surface

def _get_fog_tile(tile_s, kind):
    key = (tile_s, kind)
    s = _fog_zoom_cache.get(key)
    if s is None:
        import systems.rendering.helpers as _h
        src = _h._fog_dark if kind == 0 else _h._fog_dim
        if tile_s == TILE:
            s = src
        else:
            s = pygame.transform.scale(src, (tile_s, tile_s))
        _fog_zoom_cache[key] = s
    return s


def _draw_fog(surf, fog, cam_x, cam_y, zoom=1.0):
    _ensure_surfaces()
    tile_s  = max(1, int(TILE * zoom))
    sw = W
    sh = H - HUD_H
    tile_ox = int(cam_x * zoom) % tile_s
    tile_oy = int(cam_y * zoom) % tile_s
    tx0     = int(cam_x) // TILE
    ty0     = int(cam_y) // TILE
    cols    = sw // tile_s + 2
    rows    = sh // tile_s + 2
    fog_dark = _get_fog_tile(tile_s, 0)
    fog_dim  = _get_fog_tile(tile_s, 1)

    for drow in range(rows):
        my = ty0 + drow
        if not (0 <= my < MAP_H):
            continue
        for dcol in range(cols):
            mx = tx0 + dcol
            if not (0 <= mx < MAP_W):
                continue
            f  = fog[my, mx]
            sx = dcol * tile_s - tile_ox
            sy = drow * tile_s - tile_oy
            if f == 0:
                surf.blit(fog_dark, (sx, sy))
            elif f == 1:
                surf.blit(fog_dim,  (sx, sy))


# ── Water shimmer ─────────────────────────────────────────────────────────────
_water_overlay = None

def _draw_water_shimmer(surf, tiles, cam, t, zoom=1.0):
    """Cheaply animate water tiles with a subtle rolling highlight."""
    global _water_overlay
    sw = W
    sh = H - HUD_H
    if _water_overlay is None or _water_overlay.get_width() != sw or _water_overlay.get_height() != sh:
        _water_overlay = pygame.Surface((sw, sh), pygame.SRCALPHA)
    _water_overlay.fill((0, 0, 0, 0))
    tile_s  = max(1, int(TILE * zoom))
    tile_ox = int(cam[0] * zoom) % tile_s
    tile_oy = int(cam[1] * zoom) % tile_s
    tx0     = int(cam[0]) // TILE
    ty0     = int(cam[1]) // TILE
    cols    = sw // tile_s + 2
    rows    = sh // tile_s + 2
    phase   = t * 1.2  # slow roll
    drew = False
    for drow in range(rows):
        my = ty0 + drow
        if not (0 <= my < MAP_H):
            continue
        for dcol in range(cols):
            mx = tx0 + dcol
            if not (0 <= mx < MAP_W):
                continue
            if tiles[my][mx] != TWATER:
                continue
            sx = dcol * tile_s - tile_ox
            sy = drow * tile_s - tile_oy
            # Primary shimmer wave
            wave1 = math.sin(phase + mx * 0.35 + my * 0.25)
            # Secondary crossing wave for more natural look
            wave2 = math.sin(phase * 0.7 + mx * 0.2 - my * 0.4)
            alpha = int(14 + 10 * wave1 + 6 * wave2)
            if alpha > 2:
                pygame.draw.rect(_water_overlay, (50, 120, 210, alpha),
                                 (sx, sy, tile_s, tile_s))
                drew = True
            # Specular highlight streak (slow moving)
            spec = math.sin(phase * 0.5 + mx * 0.6 + my * 0.15)
            if spec > 0.75:
                sa = int(20 * (spec - 0.75) / 0.25)
                hw = tile_s // 2 + 2
                pygame.draw.line(_water_overlay, (140, 190, 255, sa),
                                 (sx + 2, sy + tile_s // 2),
                                 (sx + hw, sy + tile_s // 2), 1)
                drew = True
    if drew:
        surf.blit(_water_overlay, (0, 0), special_flags=pygame.BLEND_ADD)


# ── Day/night atmosphere ──────────────────────────────────────────────────────
_DAY_NIGHT_SURF = None

def _draw_day_night_tint(surf, t):
    """Slow subtle colour temperature cycle (120s period). Very cheap."""
    global _DAY_NIGHT_SURF
    sw = W
    sh = H - HUD_H
    if _DAY_NIGHT_SURF is None or _DAY_NIGHT_SURF.get_width() != sw or _DAY_NIGHT_SURF.get_height() != sh:
        _DAY_NIGHT_SURF = pygame.Surface((sw, sh), pygame.SRCALPHA)
    cycle = (math.sin(t * 0.05236) + 1) * 0.5  # 0 → 1 over ~120s
    # warm golden dusk tint near 0, cool blue night near 1
    r = int(12 * (1 - cycle))
    g = int(4  * (1 - cycle))
    b = int(14 * cycle)
    a = int(18 * (0.3 + 0.7 * abs(cycle - 0.5) * 2))  # stronger at extremes
    if a < 3:
        return
    _DAY_NIGHT_SURF.fill((r, g, b, a))
    surf.blit(_DAY_NIGHT_SURF, (0, 0))


# ── Influence overlay ─────────────────────────────────────────────────────────
_influence_surf = None

def _draw_influence_overlay(surf, world, cam, zoom=1.0):
    """Additive blue tint showing player influence on the map."""
    global _influence_surf
    sw = W
    sh = H - HUD_H
    if _influence_surf is None or _influence_surf.get_width() != sw or _influence_surf.get_height() != sh:
        _influence_surf = pygame.Surface((sw, sh))
    _influence_surf.fill((0, 0, 0))
    for _eid, pos, team, bd in world.q(Position, Team, BuildingData):
        if team.id != _cfg.PLAYER:
            continue
        cx = int((pos.x + bd.w // 2 - cam[0]) * zoom)
        cy = int((pos.y + bd.h // 2 - cam[1]) * zoom)
        r  = int(INFLUENCE_RADIUS.get(bd.kind, 200) * zoom)
        if cx + r < 0 or cx - r > sw or cy + r < 0 or cy - r > sh:
            continue
        pygame.draw.circle(_influence_surf, (0, 22, 44), (cx, cy), r)     # soft fill
        pygame.draw.circle(_influence_surf, (0, 42, 80), (cx, cy), r, 2)  # edge ring
    surf.blit(_influence_surf, (0, 0), special_flags=pygame.BLEND_ADD)
