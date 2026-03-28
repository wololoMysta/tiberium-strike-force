# systems/move_sys.py – movement, separation, building production
import math
from ecs import World, System
from components import *
from config import *
import entities as ent


# ── Pre-build wall lookup for fast collision ──────────────────────────────────
def _build_wall_rects(world: World) -> list[tuple[float, float, float, float]]:
    """Return list of (x, y, x2, y2) for all wall entities."""
    rects = []
    for _eid, pos, bd in world.q(Position, BuildingData):
        if bd.kind == 'wall':
            rects.append((pos.x, pos.y, pos.x + bd.w, pos.y + bd.h))
    return rects


class MoveSys(System):
    def update(self, world: World, dt: float) -> None:
        _age_construction(world, dt)
        _age_production(world, dt)
        _move_units(world, dt)
        _separate_units(world)
        _finish_construction(world)


# ── Construction aging ─────────────────────────────────────────────────────────
def _age_construction(world: World, dt: float) -> None:
    for eid, uc in world.q(UnderConstruction):
        uc.elapsed += dt


# ── Unit movement ─────────────────────────────────────────────────────────────
def _move_units(world: World, dt: float) -> None:
    wall_rects = _build_wall_rects(world)

    for eid, pos, ud, mv in world.q(Position, UnitData, Movement):
        if mv.tx is None:
            continue
        dx = mv.tx - pos.x
        dy = mv.ty - pos.y
        d  = math.hypot(dx, dy)
        if d < 3.0:
            pos.x, pos.y = mv.tx, mv.ty
            mv.tx = mv.ty = None
            continue
        step = ud.speed * dt
        if step >= d:
            nx, ny = mv.tx, mv.ty
            mv.tx = mv.ty = None
        else:
            # snap facing
            ud.facing = math.atan2(dy, dx)
            if ud.kind == 'tank':
                diff  = ud.turret - ud.facing
                diff  = (diff + math.pi) % (2 * math.pi) - math.pi
                ud.turret -= diff * min(1.0, dt * 4.0)
            nx = pos.x + (dx / d) * step
            ny = pos.y + (dy / d) * step

        # ── Wall slide collision ──────────────────────────────────────────────
        r = ud.radius
        blocked_x = blocked_y = False
        for wx1, wy1, wx2, wy2 in wall_rects:
            # Expand wall rect by unit radius
            ex1, ey1 = wx1 - r, wy1 - r
            ex2, ey2 = wx2 + r, wy2 + r
            if ex1 < nx < ex2 and ey1 < ny < ey2:
                # Try sliding along each axis
                if not (ex1 < pos.x < ex2 and ey1 < ny < ey2):
                    blocked_y = True
                    ny = pos.y
                if not (ex1 < nx < ex2 and ey1 < pos.y < ey2):
                    blocked_x = True
                    nx = pos.x
                if blocked_x and blocked_y:
                    mv.tx = mv.ty = None
                    break

        pos.x = max(0.0, min(MAP_W * TILE - 1, nx))
        pos.y = max(0.0, min(MAP_H * TILE - 1, ny))


# ── Spatial-grid circle separation (prevent stacking) ─────────────────────────
_SEP_CELL = 40  # cell size >= largest unit diameter

def _separate_units(world: World) -> None:
    grid: dict[tuple[int, int], list] = {}
    units = []
    for eid, pos, ud in world.q(Position, UnitData):
        cx = int(pos.x) // _SEP_CELL
        cy = int(pos.y) // _SEP_CELL
        entry = (pos, ud)
        units.append(entry)
        grid.setdefault((cx, cy), []).append(entry)

    _hypot = math.hypot
    for pos_a, ud_a in units:
        cx = int(pos_a.x) // _SEP_CELL
        cy = int(pos_a.y) // _SEP_CELL
        for nx in range(cx - 1, cx + 2):
            for ny in range(cy - 1, cy + 2):
                cell = grid.get((nx, ny))
                if cell is None:
                    continue
                for pos_b, ud_b in cell:
                    if pos_b is pos_a:
                        continue
                    dx = pos_a.x - pos_b.x
                    dy = pos_a.y - pos_b.y
                    min_d = ud_a.radius + ud_b.radius + 2
                    d = _hypot(dx, dy) or 0.001
                    if d < min_d:
                        push = (min_d - d) * 0.25  # half of 0.5 since each pair visited twice
                        inv = push / d
                        pos_a.x += dx * inv
                        pos_a.y += dy * inv


# ── Building production queue ─────────────────────────────────────────────────
def _age_production(world: World, dt: float) -> None:
    for eid, pos, bd, team in world.q(Position, BuildingData, Team):
        if not bd.prod_queue:
            continue
        pr = world.meta.get(f'power_ratio_{team.id}', 1.0)
        bd.prod_queue[0][1] -= dt * max(0.25, pr)
        if bd.prod_queue[0][1] <= 0:
            kind = bd.prod_queue.pop(0)[0]
            # Spawn at rally point
            ent.spawn_unit(world, bd.rally_x, bd.rally_y, team.id, kind)


# ── Construction completion ───────────────────────────────────────────────────
def _finish_construction(world: World) -> None:
    for eid, uc in world.q(UnderConstruction):
        if uc.done:
            world.rm(eid, UnderConstruction)
            # Refinery auto-spawns a free harvester on completion
            bd = world.get(eid, BuildingData)
            team = world.get(eid, Team)
            if bd and team and bd.kind == 'refinery':
                ent.spawn_unit(world, bd.rally_x, bd.rally_y,
                               team.id, 'harvester')
