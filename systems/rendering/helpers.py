# systems/rendering/helpers.py – shared drawing utilities
import math, pygame
from functools import lru_cache
from config import *


# ── Shared game-math helpers ────────────────────────────────────────────
def _wall_line_centers(x0: float, y0: float, x1: float, y1: float,
                       step: int = TILE) -> list[tuple[float, float]]:
    """Return grid-snapped wall centre positions from (x0,y0) to (x1,y1)."""
    sx = round(x0 / step) * step
    sy = round(y0 / step) * step
    ex = round(x1 / step) * step
    ey = round(y1 / step) * step
    dx, dy = ex - sx, ey - sy
    n = max(abs(dx), abs(dy)) // step
    if n == 0:
        return [(sx, sy)]
    out: list = []
    seen: set = set()
    for i in range(n + 1):
        t = i / n
        cx = round(sx + dx * t)
        cy = round(sy + dy * t)
        cx = round(cx / step) * step
        cy = round(cy / step) * step
        if (cx, cy) not in seen:
            seen.add((cx, cy))
            out.append((cx, cy))
    return out


def _in_influence(world, wx: float, wy: float, team_id: int) -> bool:
    """Return True if (wx, wy) is within any friendly building's influence radius."""
    from components import Position, Team, BuildingData
    for _eid, pos, team, bd in world.q(Position, Team, BuildingData):
        if team.id != team_id:
            continue
        bx = pos.x + bd.w / 2
        by = pos.y + bd.h / 2
        r  = INFLUENCE_RADIUS.get(bd.kind, 200)
        if math.hypot(bx - wx, by - wy) <= r:
            return True
    return False


# ── Pre-allocated surfaces ────────────────────────────────────────────────────
_fog_dark   = None   # fully-opaque fog tile
_fog_dim    = None   # semi-transparent explored tile
_glow_cache: dict = {}
_water_shimmer_surf = None   # pre-built half-transparent blue overlay for water tiles

# ── Reusable surface pool (avoids per-frame Surface allocation) ───────────────
_surf_pool: dict[tuple[int, int], pygame.Surface] = {}


def _get_surf(w: int, h: int) -> pygame.Surface:
    key = (w, h)
    s = _surf_pool.get(key)
    if s is None:
        s = pygame.Surface((w, h), pygame.SRCALPHA)
        _surf_pool[key] = s
    else:
        s.fill((0, 0, 0, 0))
        s.set_alpha(None)
    return s


class _ScreenPos:
    __slots__ = ('x', 'y')

_spos = _ScreenPos()

# Pre-computed octagon offsets for turret base (radius=17)
_OCT_OFFSETS = tuple(
    (int(math.cos(math.pi / 8 + i * math.pi / 4) * 17),
     int(math.sin(math.pi / 8 + i * math.pi / 4) * 17))
    for i in range(8)
)


def _ensure_surfaces() -> None:
    global _fog_dark, _fog_dim, _water_shimmer_surf
    if _fog_dark is None:
        _fog_dark = pygame.Surface((TILE, TILE), pygame.SRCALPHA)
        _fog_dark.fill((0, 0, 0, 230))
        _fog_dim  = pygame.Surface((TILE, TILE), pygame.SRCALPHA)
        _fog_dim.fill((0, 0, 0, 145))
        _water_shimmer_surf = pygame.Surface((TILE, TILE), pygame.SRCALPHA)
        _water_shimmer_surf.fill((40, 100, 200, 18))


# ── Glow helper ───────────────────────────────────────────────────────────────
def _glow(surf: pygame.Surface, x: int, y: int,
          color: tuple, radius: int, alpha: int = 140) -> None:
    color = tuple(color)
    key = (color, radius, alpha)
    if key not in _glow_cache:
        s = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
        for r in range(radius, 0, -2):
            a = int(alpha * (r / radius) ** 1.6)
            pygame.draw.circle(s, (*color[:3], a), (radius, radius), r)
        _glow_cache[key] = s
    surf.blit(_glow_cache[key], (x - radius, y - radius),
              special_flags=pygame.BLEND_ADD)


# ── Trig helpers ──────────────────────────────────────────────────────────────
def _rot_rect(cx, cy, w, h, angle):
    ca, sa = math.cos(angle), math.sin(angle)
    hw, hh = w / 2, h / 2
    return [
        (int(cx + (-hw) * ca - (-hh) * sa), int(cy + (-hw) * sa + (-hh) * ca)),
        (int(cx + hw  * ca - (-hh) * sa), int(cy + hw  * sa + (-hh) * ca)),
        (int(cx + hw  * ca - hh  * sa), int(cy + hw  * sa + hh  * ca)),
        (int(cx + (-hw) * ca - hh  * sa), int(cy + (-hw) * sa + hh  * ca)),
    ]


@lru_cache(maxsize=512)
def _darker(c: tuple, amount: int = 40) -> tuple:
    return (max(0, c[0] - amount), max(0, c[1] - amount), max(0, c[2] - amount))


@lru_cache(maxsize=512)
def _lighter(c: tuple, amount: int = 40) -> tuple:
    return (min(255, c[0] + amount), min(255, c[1] + amount), min(255, c[2] + amount))
