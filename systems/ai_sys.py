# systems/ai_sys.py – enemy faction AI (build → gather → raid loop)
import math
import random
from ecs import World, System
from components import *
from config import *
import entities as ent


class AISys(System):
    def update(self, world: World, dt: float) -> None:
        _passive_income(world, dt)
        for eid, ai, team in world.q(AIController, Team):
            _tick_ai(world, eid, ai, team.id, dt)


def _passive_income(world: World, dt: float) -> None:
    world.meta['credits'][ENEMY] += AI_INCOME * dt


# ── AI state machine ──────────────────────────────────────────────────────────
def _tick_ai(world, eid, ai, team_id, dt):
    # Deploy MCV first if we have one and no base
    if not _has_building(world, team_id, 'base'):
        mcv = _find_mcv(world, team_id)
        if mcv is not None:
            pos = world.get(mcv, Position)
            if pos:
                _, bw, bh = BDAT['base']
                ent.spawn_building(world, pos.x - bw // 2, pos.y - bh // 2,
                                   team_id, 'base', complete=False)
                world.kill(mcv)
            return
        return  # no MCV, no base — nothing to do

    # Build essential structures if missing
    ai.build_t += dt
    if ai.build_t >= 2.0:  # check every 2s
        ai.build_t = 0.0
        _ai_build_structure(world, team_id)

    if ai.state == 'building':
        ai.raid_t  += dt
        if ai.raid_t >= AI_BUILD_DT:
            ai.raid_t = 0.0
            _build_unit(world, team_id)
        if _count_army(world, team_id) >= AI_RAID_N:
            ai.state   = 'gathering'
            ai.rally_x, ai.rally_y = _midpoint(world, team_id, ENEMY)

    elif ai.state == 'gathering':
        _rally(world, team_id, ai.rally_x, ai.rally_y)
        if _army_at_rally(world, team_id, ai.rally_x, ai.rally_y):
            ai.state = 'raiding'

    elif ai.state == 'raiding':
        target = _player_base(world)
        if target is None:
            ai.state = 'building'
            return
        tpos = world.get(target, Position)
        if tpos is None:
            ai.state = 'building'
            return
        _send_army(world, team_id, tpos.x, tpos.y)
        if _count_army(world, team_id) == 0:
            ai.state = 'building'


def _find_mcv(world, team_id):
    for eid, ud, team in world.q(UnitData, Team):
        if team.id == team_id and ud.kind == 'mcv':
            return eid
    return None


def _has_building(world, team_id, kind):
    for eid, bd, team in world.q(BuildingData, Team):
        if team.id == team_id and bd.kind == kind:
            return True
    return False


def _ai_build_structure(world, team_id):
    """AI auto-builds essential structures when it can afford them."""
    credits = world.meta['credits']
    # Only build if base is complete
    if not _base_complete(world, team_id):
        return
    # Priority order of structures to build
    needs = [
        ('refinery',    'refinery'),
        ('barracks',    'barracks'),
        ('power_plant', 'power_plant'),
        ('factory',     'factory'),
    ]
    for kind, _ in needs:
        if _has_complete_or_constructing(world, team_id, kind):
            continue
        cost = BUILD_COST[kind]
        if credits[team_id] < cost:
            continue
        base_pos = _base_pos(world, team_id)
        if base_pos is None:
            continue
        bx, by = base_pos
        offsets = [(-120, 80), (80, 80), (-100, -60), (100, -60),
                   (-120, -120), (120, 0)]
        for ox, oy in offsets:
            px, py = bx + ox, by + oy
            if not _has_building_near(world, px, py, 40):
                credits[team_id] -= cost
                _, bw, bh = BDAT[kind]
                ent.spawn_building(world, px - bw // 2, py - bh // 2,
                                   team_id, kind, complete=False)
                return
        break  # couldn't place, try next tick


def _base_complete(world, team_id):
    for eid, bd, team in world.q(BuildingData, Team):
        if team.id == team_id and bd.kind == 'base':
            if not world.get(eid, UnderConstruction):
                return True
    return False


def _has_complete_or_constructing(world, team_id, kind):
    for eid, bd, team in world.q(BuildingData, Team):
        if team.id == team_id and bd.kind == kind:
            return True
    return False


def _has_building_near(world, x, y, radius):
    for eid, pos, bd in world.q(Position, BuildingData):
        if math.hypot(pos.x - x, pos.y - y) < radius:
            return True
    return False


# ── Helpers ───────────────────────────────────────────────────────────────────
def _build_unit(world, team_id):
    """Pick a unit and add to a production building queue."""
    credits = world.meta['credits']
    # Pick unit – prefer advanced tanks when rich, mix for variety
    heavy = ['rocket_tank', 'tesla_tank', 'laser_tank', 'flame_tank', 'tank']
    r = random.random()
    kind = None
    if r < 0.45 and credits[team_id] >= UDAT['tank'][6]:
        kind = random.choice(heavy)
        if credits[team_id] < UDAT[kind][6]:
            kind = 'tank'
    elif r < 0.70 and credits[team_id] >= UDAT['buggy'][6]:
        kind = 'buggy'
    elif credits[team_id] >= UDAT['infantry'][6]:
        kind = 'infantry'
    else:
        return
    if kind is None:
        return
    cost = UDAT[kind][6]
    # Find a suitable building
    for eid, bd, bteam in world.q(BuildingData, Team):
        if bteam.id != team_id:
            continue
        if kind in PROD_MENU.get(bd.kind, []):
            credits[team_id] -= cost
            bd.prod_queue.append([kind, PROD_TIME[kind]])
            return
    # No production building – spawn directly near base
    base_pos = _base_pos(world, team_id)
    if base_pos:
        bx, by = base_pos
        credits[team_id] -= cost
        ent.spawn_unit(world,
                       bx + random.uniform(-80, 80),
                       by + random.uniform(-80, 80),
                       team_id, kind)


def _count_army(world, team_id) -> int:
    return sum(1 for _eid, ud, team in world.q(UnitData, Team)
               if team.id == team_id and ud.kind not in ('harvester', 'mcv'))


def _rally(world, team_id, rx, ry):
    for eid, pos, ud, mv, team in world.q(Position, UnitData, Movement, Team):
        if team.id != team_id or ud.kind in ('harvester', 'mcv'):
            continue
        if mv.tx is None:
            offset = random.uniform(-30, 30)
            mv.tx  = rx + offset
            mv.ty  = ry + offset


def _army_at_rally(world, team_id, rx, ry) -> bool:
    units = [(pos.x, pos.y)
             for _eid, pos, ud, team in world.q(Position, UnitData, Team)
             if team.id == team_id and ud.kind != 'harvester']
    if len(units) < 2:
        return bool(units)
    return all(math.hypot(x - rx, y - ry) < 200 for x, y in units)


def _send_army(world, team_id, tx, ty):
    for eid, pos, ud, mv, cb, team in world.q(Position, UnitData, Movement, Combat, Team):
        if team.id != team_id or ud.kind in ('harvester', 'mcv'):
            continue
        if mv.tx is None:
            mv.tx = tx + random.uniform(-50, 50)
            mv.ty = ty + random.uniform(-50, 50)
            mv.attack_move = True


def _player_base(world):
    for eid, bd, team in world.q(BuildingData, Team):
        if team.id == PLAYER and bd.kind == 'base':
            return eid
    return None


def _base_pos(world, team_id):
    for eid, pos, bd, team in world.q(Position, BuildingData, Team):
        if team.id == team_id and bd.kind == 'base':
            return pos.x, pos.y
    return None


def _midpoint(world, team_a, team_b):
    pa = _base_pos(world, team_a)
    pb = _base_pos(world, team_b)
    if pa and pb:
        return (pa[0] + pb[0]) * 0.5, (pa[1] + pb[1]) * 0.5
    return pa or pb or (MAP_W * TILE // 2, MAP_H * TILE // 2)
