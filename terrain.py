# terrain.py – procedural map generation + spatial queries
import random, math
import pygame
from config import *


# ── Value-noise FBM ───────────────────────────────────────────────────────────
def _smooth(t: float) -> float:
    return t * t * (3 - 2 * t)


def _vnoise(gw: int, gh: int, rng: random.Random) -> list[list[float]]:
    return [[rng.random() for _ in range(gw)] for _ in range(gh)]


def _sample(grid: list[list[float]], x: float, y: float) -> float:
    ix, iy = int(x), int(y)
    fx, fy = _smooth(x - ix), _smooth(y - iy)
    a = grid[iy][ix] * (1 - fx) + grid[iy][ix + 1] * fx
    b = grid[iy + 1][ix] * (1 - fx) + grid[iy + 1][ix + 1] * fx
    return a * (1 - fy) + b * fy


def fbm(w: int, h: int, scale: int, octaves: int = 4, seed: int = 0) -> list[list[float]]:
    rng = random.Random(seed)
    result = [[0.0] * w for _ in range(h)]
    amp, freq, total = 1.0, 1.0, 0.0
    for o in range(octaves):
        sc = max(2, int(scale / freq))
        gw, gh = w // sc + 2, h // sc + 2
        grid = _vnoise(gw, gh, rng)
        for y in range(h):
            for x in range(w):
                result[y][x] += _sample(grid, x / sc, y / sc) * amp
        total += amp
        amp  *= 0.5
        freq *= 2.0
        rng  = random.Random(rng.randint(0, 999999))
    for y in range(h):
        for x in range(w):
            result[y][x] /= total
    return result


# ── Map data ──────────────────────────────────────────────────────────────────
def generate(seed: int = 42) -> tuple[list[list[int]], list[list[float]]]:
    """Return (tile_type[y][x], height[y][x])."""
    height  = fbm(MAP_W, MAP_H, 20, 4, seed)
    detail  = fbm(MAP_W, MAP_H, 8,  3, seed + 1)
    tiles   = [[TGRASS] * MAP_W for _ in range(MAP_H)]

    for y in range(MAP_H):
        for x in range(MAP_W):
            h = height[y][x] + detail[y][x] * 0.15
            if   h < 0.30: tiles[y][x] = TWATER
            elif h < 0.42: tiles[y][x] = TDIRT
            elif h < 0.72: tiles[y][x] = TGRASS
            else:          tiles[y][x] = TROCK

    return tiles, height


def _tile_color(tile: int, tx: int, ty: int, h: float) -> tuple[int, int, int]:
    """Per-tile colour with zone tint, height shading and hash variation."""
    zone  = ty / MAP_H                       # 0=north(green) … 1=south(red)
    idx   = hash((tx * 31337 + ty * 73891)) % 3
    base  = list(TCOLORS[tile][idx])

    # zone colour temperature shift
    if   zone < 0.33:  zt = ( 0,  8,  0)
    elif zone < 0.66:  zt = (15, 10, -8)
    else:              zt = (28, -8, -8)

    shade = int((h - 0.5) * 26)             # height-based brightness
    noise = (hash((tx * 7 + ty * 13)) % 14) - 7   # micro-variation

    r = max(0, min(255, base[0] + zt[0] + shade + noise // 2))
    g = max(0, min(255, base[1] + zt[1] + shade + noise // 2))
    b = max(0, min(255, base[2] + zt[2] + shade + noise // 2))
    return r, g, b


def build_surface(tiles: list[list[int]],
                  height: list[list[float]]) -> pygame.Surface:
    """Pre-render the world into one large surface for fast blitting."""
    rng = random.Random(12345)
    surf = pygame.Surface((MAP_W * TILE, MAP_H * TILE))
    for ty in range(MAP_H):
        for tx in range(MAP_W):
            color = _tile_color(tiles[ty][tx], tx, ty, height[ty][tx])
            surf.fill(color, (tx * TILE, ty * TILE, TILE, TILE))
            tile = tiles[ty][tx]
            # subtle grid lines on non-water tiles for ground texture
            if tile != TWATER:
                r, g, b = color
                dark = (max(0, r - 12), max(0, g - 12), max(0, b - 12))
                pygame.draw.line(surf, dark,
                                 (tx * TILE, ty * TILE + TILE - 1),
                                 (tx * TILE + TILE - 1, ty * TILE + TILE - 1))
                pygame.draw.line(surf, dark,
                                 (tx * TILE + TILE - 1, ty * TILE),
                                 (tx * TILE + TILE - 1, ty * TILE + TILE - 1))
            # ── Terrain decorations ──────────────────────────────
            px = tx * TILE
            py = ty * TILE
            if tile == TGRASS:
                # Grass tufts (small lines)
                for _ in range(rng.randint(0, 3)):
                    gx = px + rng.randint(2, TILE - 3)
                    gy = py + rng.randint(2, TILE - 3)
                    gh = rng.randint(3, 6)
                    gc = (rng.randint(16, 35), rng.randint(55, 85), rng.randint(10, 25))
                    pygame.draw.line(surf, gc, (gx, gy), (gx + rng.randint(-1, 1), gy - gh), 1)
                # Occasional tiny flower
                if rng.random() < 0.08:
                    fx = px + rng.randint(4, TILE - 5)
                    fy = py + rng.randint(4, TILE - 5)
                    fc = rng.choice([(180, 160, 40), (160, 60, 60), (140, 80, 160), (200, 200, 80)])
                    pygame.draw.circle(surf, fc, (fx, fy), 1)
            elif tile == TDIRT:
                # Small pebbles
                for _ in range(rng.randint(0, 2)):
                    rx = px + rng.randint(3, TILE - 4)
                    ry = py + rng.randint(3, TILE - 4)
                    rc = (rng.randint(55, 80), rng.randint(50, 70), rng.randint(35, 50))
                    pygame.draw.circle(surf, rc, (rx, ry), 1)
            elif tile == TWATER:
                # Subtle lighter streaks to suggest depth variation
                for _ in range(rng.randint(1, 3)):
                    wx = px + rng.randint(1, TILE - 2)
                    wy = py + rng.randint(1, TILE - 2)
                    wlen = rng.randint(4, 10)
                    wa = rng.randint(18, 40)
                    wc = (40 + rng.randint(0, 20), 80 + rng.randint(0, 30),
                          140 + rng.randint(0, 40))
                    pygame.draw.line(surf, wc,
                                     (wx, wy), (wx + wlen, wy + rng.randint(-1, 1)), 1)
                # Occasional foam/highlight dot near edges
                if rng.random() < 0.15:
                    fx = px + rng.randint(2, TILE - 3)
                    fy = py + rng.randint(2, TILE - 3)
                    pygame.draw.circle(surf, (80, 130, 180), (fx, fy), 1)
            elif tile == TROCK:
                # Cracks/fractures
                if rng.random() < 0.3:
                    cx = px + rng.randint(4, TILE - 5)
                    cy = py + rng.randint(4, TILE - 5)
                    cc = (max(0, color[0] - 18), max(0, color[1] - 18), max(0, color[2] - 18))
                    ex = cx + rng.randint(-8, 8)
                    ey = cy + rng.randint(-8, 8)
                    pygame.draw.line(surf, cc, (cx, cy), (ex, ey), 1)
    return surf


def build_minimap_surf(tiles: list[list[int]],
                       height: list[list[float]]) -> pygame.Surface:
    """Pre-render a small MINI×MINI surface of the terrain for the minimap."""
    raw = pygame.Surface((MAP_W, MAP_H))
    for ty in range(MAP_H):
        for tx in range(MAP_W):
            raw.set_at((tx, ty), _tile_color(tiles[ty][tx], tx, ty, height[ty][tx]))
    return pygame.transform.smoothscale(raw, (MINI, MINI))


# ── Spatial helpers ───────────────────────────────────────────────────────────
def is_walkable(tiles: list[list[int]], wx: float, wy: float) -> bool:
    tx, ty = int(wx // TILE), int(wy // TILE)
    if not (0 <= tx < MAP_W and 0 <= ty < MAP_H):
        return False
    return tiles[ty][tx] != TWATER


def clamp_to_map(x: float, y: float) -> tuple[float, float]:
    return (max(0.0, min(MAP_W * TILE - 1, x)),
            max(0.0, min(MAP_H * TILE - 1, y)))


def can_place_building(world, tiles, wx: float, wy: float, kind: str,
                       team_id: int) -> bool:
    """Full footprint check: no water, no overlapping buildings, no tiberium."""
    from components import Position, BuildingData, Resource
    from config import BDAT
    _, bw, bh = BDAT[kind]
    cx = wx - bw // 2
    cy = wy - bh // 2

    # Check all tiles under footprint for water
    tx0 = int(cx // TILE)
    ty0 = int(cy // TILE)
    tx1 = int((cx + bw - 1) // TILE)
    ty1 = int((cy + bh - 1) // TILE)
    for ty in range(max(0, ty0), min(MAP_H, ty1 + 1)):
        for tx in range(max(0, tx0), min(MAP_W, tx1 + 1)):
            if tiles[ty][tx] == TWATER:
                return False

    # Check for overlapping buildings
    for _eid, pos, bd in world.q(Position, BuildingData):
        if (pos.x < cx + bw and pos.x + bd.w > cx and
                pos.y < cy + bh and pos.y + bd.h > cy):
            return False

    # Check for tiberium resources in footprint
    for _eid, pos, res in world.q(Position, Resource):
        if res.amount <= 0:
            continue
        if cx <= pos.x <= cx + bw and cy <= pos.y <= cy + bh:
            return False

    return True
