# systems/harvest_sys.py – harvester state machine
import math
from ecs import World, System
from components import *
from config import *


class HarvestSys(System):
    def update(self, world: World, dt: float) -> None:
        for eid, pos, hv, team in world.q(Position, Harvester, Team):
            mv = world.get(eid, Movement)
            if mv is None:
                continue
            _tick(world, eid, pos, hv, mv, team.id, dt)


def _tick(world, eid, pos, hv, mv, team_id, dt):
    if hv.state == 'idle':
        r = _find_resource(world, pos.x, pos.y)
        if r is not None:
            hv.res_eid = r
            rp = world.get(r, Position)
            mv.tx, mv.ty = rp.x, rp.y
            hv.state = 'to_resource'

    elif hv.state == 'to_resource':
        if mv.tx is None:       # arrived
            res = world.get(hv.res_eid, Resource)
            if res is None or res.amount <= 0:
                hv.state = 'idle'
                return
            hv.state   = 'harvesting'
            hv.h_timer = 0.0

    elif hv.state == 'harvesting':
        res = world.get(hv.res_eid, Resource)
        if res is None or res.amount <= 0:
            if hv.carry > 0:
                hv.state = 'to_base'
                _set_target_refinery(world, eid, pos, mv, team_id)
            else:
                hv.state = 'idle'
            return
        hv.h_timer += dt
        # show harvest FX periodically
        if hv.h_timer >= 0.25:
            hv.h_timer = 0.0
            rp = world.get(hv.res_eid, Position)
            if rp:
                world.meta['fx'].append({
                    'kind': 'particle', 'x': rp.x, 'y': rp.y,
                    'vx': 0, 'vy': -30, 't': 0.4, 'mt': 0.4,
                    'color': P['tib_hi'], 'sz': 4.0,
                })
        take  = min(HARVEST_RATE * dt, res.amount, HARVEST_CARRY - hv.carry)
        res.amount -= take
        hv.carry   += take
        if hv.carry >= HARVEST_CARRY:
            hv.state = 'to_base'
            _set_target_refinery(world, eid, pos, mv, team_id)

    elif hv.state == 'to_base':
        if mv.tx is None:       # arrived at refinery
            world.meta['credits'][team_id] += int(hv.carry * TIB_VALUE)
            hv.carry  = 0.0
            hv.state  = 'idle'


def _find_resource(world, x: float, y: float):
    best, best_d = None, 1e9
    for eid, rpos, res in world.q(Position, Resource):
        if res.amount <= 0:
            continue
        d = math.hypot(rpos.x - x, rpos.y - y)
        if d < best_d:
            best, best_d = eid, d
    return best


def _set_target_refinery(world, eid, pos, mv, team_id):
    """Move harvester toward the nearest refinery of its team."""
    best, best_d = None, 1e9
    for bid, bpos, bd, bteam in world.q(Position, BuildingData, Team):
        if bteam.id != team_id:
            continue
        if bd.kind not in ('refinery', 'base'):
            continue
        d = math.hypot(bpos.x - pos.x, bpos.y - pos.y)
        if d < best_d:
            best, best_d = bid, d
            mv.tx = bpos.x + bd.w // 2
            mv.ty = bpos.y + bd.h // 2
