# systems/tib_sys.py – tiberium spread + unit contact damage
import math
import random
from ecs import World, System
from components import Position, Resource, UnitData, Health, Team
from config import (
    TILE, MAP_W, MAP_H,
    TIB_SPREAD_INTERVAL, TIB_SPREAD_CHANCE, TIB_SPREAD_RADIUS,
    TIB_SPREAD_AMOUNT, TIB_MAX_FIELDS, TIB_DAMAGE_RATE,
    P,
)
import terrain as ter
import entities as ent


# Units that take tiberium contact damage (unarmoured)
_SOFT_UNITS = {'infantry', 'buggy'}

# How often (seconds) to spawn a damage particle so screen isn't spammed
_FX_INTERVAL = 0.4
_fx_timer: dict[int, float] = {}   # eid → seconds until next particle


class TibSys(System):
    def __init__(self):
        self._spread_timer = 0.0

    def update(self, world: World, dt: float) -> None:
        self._spread_timer += dt
        if self._spread_timer >= TIB_SPREAD_INTERVAL:
            self._spread_timer = 0.0
            _spread_tiberium(world)
        _damage_units_on_tib(world, dt)


# ── Spread logic ──────────────────────────────────────────────────────────────

def _spread_tiberium(world: World) -> None:
    tiles = world.meta['tiles']

    # Count existing fields; bail if already at cap
    fields = [(eid, pos, res)
               for eid, pos, res in world.q(Position, Resource)]
    if len(fields) >= TIB_MAX_FIELDS:
        return

    # Build a quick set of occupied tile coords to avoid overlap
    occupied: set[tuple[int, int]] = set()
    for _eid, pos, _res in fields:
        occupied.add((int(pos.x // TILE), int(pos.y // TILE)))

    new_spawns: list[tuple[float, float]] = []

    for _eid, pos, res in fields:
        # Only healthy (decently sized) fields spread
        if res.amount < 300:
            continue
        if random.random() >= TIB_SPREAD_CHANCE:
            continue
        if len(fields) + len(new_spawns) >= TIB_MAX_FIELDS:
            break

        cx_tile = int(pos.x // TILE)
        cy_tile = int(pos.y // TILE)

        # Collect candidate tiles in the spread radius
        candidates: list[tuple[int, int]] = []
        r = TIB_SPREAD_RADIUS
        for dy in range(-r, r + 1):
            for dx in range(-r, r + 1):
                if dx == 0 and dy == 0:
                    continue
                tx, ty = cx_tile + dx, cy_tile + dy
                if not (0 <= tx < MAP_W and 0 <= ty < MAP_H):
                    continue
                if (tx, ty) in occupied:
                    continue
                if not ter.is_walkable(tiles, tx * TILE, ty * TILE):
                    continue
                candidates.append((tx, ty))

        if not candidates:
            continue

        tx, ty = random.choice(candidates)
        wx = tx * TILE + TILE // 2
        wy = ty * TILE + TILE // 2

        # Double-check no existing tib is too close (pixel distance)
        too_close = any(
            math.hypot(p.x - wx, p.y - wy) < TILE * 1.5
            for _e, p, _r in fields
        )
        if too_close:
            continue

        new_spawns.append((wx, wy))
        occupied.add((tx, ty))

    for wx, wy in new_spawns:
        ent.spawn_tiberium(world, wx, wy, TIB_SPREAD_AMOUNT)


# ── Contact damage ────────────────────────────────────────────────────────────

def _damage_units_on_tib(world: World, dt: float) -> None:
    global _fx_timer

    # Gather tiberium positions once
    tib_positions: list[tuple[float, float]] = [
        (pos.x, pos.y)
        for _eid, pos, res in world.q(Position, Resource)
        if res.amount > 0
    ]
    if not tib_positions:
        return

    contact_radius_sq = (TILE * 0.9) ** 2   # within ~29 px of a tib centre

    fx = world.meta['fx']

    for eid, pos, ud, hp, _team in world.q(Position, UnitData, Health, Team):
        if ud.kind not in _SOFT_UNITS:
            continue

        px, py = pos.x, pos.y
        on_tib = any(
            (px - tx) ** 2 + (py - ty) ** 2 <= contact_radius_sq
            for tx, ty in tib_positions
        )
        if not on_tib:
            _fx_timer.pop(eid, None)
            continue

        hp.hp -= TIB_DAMAGE_RATE * dt

        # Occasional green particle so the player notices
        timer = _fx_timer.get(eid, 0.0)
        timer -= dt
        if timer <= 0.0:
            _fx_timer[eid] = _FX_INTERVAL
            fx.append({
                'kind':  'particle',
                'x':     px + random.uniform(-8, 8),
                'y':     py + random.uniform(-8, 8),
                'vx':    random.uniform(-10, 10),
                'vy':    random.uniform(-20, -6),
                't':     0.5, 'mt': 0.5,
                'color': P['tib_hi'],
                'sz':    3.0,
            })
