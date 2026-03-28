# systems/effects_sys.py – projectiles, particles, fog-of-war
import math
import numpy as np
from ecs import World, System
from components import *
from config import *


class EffectsSys(System):
    def update(self, world: World, dt: float) -> None:
        _move_projectiles(world, dt)
        _age_fx(world, dt)
        _update_fog(world)


# ── Projectiles ───────────────────────────────────────────────────────────────
def _move_projectiles(world: World, dt: float) -> None:
    import random as rnd
    dead = []
    for eid, pos, proj in world.q(Position, Projectile):
        # ── Homing rockets: steer toward living target ────────
        homing = world.get(eid, HomingProjectile)
        if homing:
            tgt_pos = world.get(homing.target_eid, Position)
            if tgt_pos and world.has(homing.target_eid, Health):
                # Update target coordinates
                proj.tx = tgt_pos.x
                proj.ty = tgt_pos.y
            # Steer heading toward target
            desired = math.atan2(proj.ty - pos.y, proj.tx - pos.x)
            diff = (desired - homing.heading + math.pi) % math.tau - math.pi
            max_turn = homing.turn_rate * dt
            homing.heading += max(-max_turn, min(max_turn, diff))
            # Move along heading (not straight to target)
            step = proj.speed * dt
            pos.x += math.cos(homing.heading) * step
            pos.y += math.sin(homing.heading) * step
            # Check arrival
            d = math.hypot(proj.tx - pos.x, proj.ty - pos.y)
            if d < step + 8:
                _deal_splash(world, pos.x, pos.y, proj.dmg, proj.team)
                _spawn_rocket_impact(world.meta, pos.x, pos.y)
                dead.append(eid)
            else:
                # Rocket trail: hot exhaust + smoke
                fx = world.meta['fx']
                tail_a = homing.heading + math.pi
                fx.append({'kind': 'particle', 'x': pos.x, 'y': pos.y,
                           'vx': math.cos(tail_a) * 60 + rnd.uniform(-20, 20),
                           'vy': math.sin(tail_a) * 60 + rnd.uniform(-20, 20),
                           't': 0.2, 'mt': 0.2,
                           'color': rnd.choice([P['rocket'], P['rocket_hi'],
                                                P['flame_hi']]),
                           'sz': rnd.uniform(2.5, 5)})
                fx.append({'kind': 'smoke', 'x': pos.x, 'y': pos.y,
                           'vx': rnd.uniform(-10, 10),
                           'vy': rnd.uniform(-10, 10),
                           't': rnd.uniform(0.3, 0.6), 'mt': 0.6,
                           'color': P['smoke'], 'sz': rnd.uniform(3, 5)})
            continue

        # ── Normal projectile movement ────────────────────────
        dx = proj.tx - pos.x
        dy = proj.ty - pos.y
        d  = math.hypot(dx, dy)
        if d < proj.speed * dt + 4:
            # Impact
            _deal_splash(world, proj.tx, proj.ty, proj.dmg, proj.team)
            _spawn_impact_fx(world.meta, proj.tx, proj.ty, proj.dmg)
            dead.append(eid)
        else:
            step = proj.speed * dt
            pos.x += (dx / d) * step
            pos.y += (dy / d) * step
            # ── Projectile trail particles ────────────────────────
            tc = P['proj_p'] if proj.team == PLAYER else P['proj_e']
            fx = world.meta['fx']
            # glowing trail every frame
            fx.append({
                'kind': 'particle', 'x': pos.x, 'y': pos.y,
                'vx': rnd.uniform(-15, 15),
                'vy': rnd.uniform(-15, 15),
                't': 0.15, 'mt': 0.15, 'color': tc,
                'sz': rnd.uniform(1.5, 3.0),
            })
            # occasional spark
            if rnd.random() < 0.3:
                fx.append({
                    'kind': 'particle', 'x': pos.x, 'y': pos.y,
                    'vx': rnd.uniform(-60, 60),
                    'vy': rnd.uniform(-60, 60),
                    't': 0.1, 'mt': 0.1,
                    'color': P['nova'],
                    'sz': 1.5,
                })
    for eid in dead:
        world.kill(eid)


def _deal_splash(world: World, x: float, y: float,
                 dmg: float, attacker_team: int) -> None:
    import random as rnd
    for eid, pos, hp, team in world.q(Position, Health, Team):
        if team.id == attacker_team:
            continue
        ud = world.get(eid, UnitData)
        bd = world.get(eid, BuildingData)
        r  = ud.radius if ud else (max(bd.w, bd.h) // 2 if bd else 20)
        if math.hypot(pos.x - x, pos.y - y) < r + 4:
            hp.hp -= dmg
            # ── hit flash (white strobe on damaged unit) ──────
            world.meta['fx'].append({
                'kind': 'hit_flash',
                'x': pos.x, 'y': pos.y,
                'r': r + 6,
                't': 0.1, 'mt': 0.1,
            })
            # ── floating damage number ────────────────────────
            world.meta['fx'].append({
                'kind': 'dmg_num',
                'x': pos.x + rnd.uniform(-6, 6),
                'y': pos.y - r - 10,
                'vx': rnd.uniform(-15, 15),
                'vy': -60,
                't': 0.8, 'mt': 0.8,
                'val': int(dmg),
            })
            # ── blood/spark spray ─────────────────────────────
            import random as rnd
            for _ in range(4):
                a = rnd.uniform(0, math.tau)
                s = rnd.uniform(40, 120)
                world.meta['fx'].append({
                    'kind': 'particle', 'x': pos.x, 'y': pos.y,
                    'vx': math.cos(a) * s, 'vy': math.sin(a) * s,
                    't': 0.18, 'mt': 0.18,
                    'color': rnd.choice([P['fire_hi'], P['nova'], (255, 255, 255)]),
                    'sz': rnd.uniform(1.5, 3.0),
                })


def _spawn_impact_fx(meta: dict, x: float, y: float, dmg: float) -> None:
    import random as rnd
    fx = meta['fx']
    # ── shockwave ring at impact ──────────────────────────────
    fx.append({
        'kind': 'shockwave',
        'x': x, 'y': y,
        'max_r': 18 + int(dmg * 0.3),
        't': 0.3, 'mt': 0.3,
        'color': P['nova'],
    })
    # ── impact sparks (more than before) ──────────────────────
    for _ in range(10):
        a = rnd.uniform(0, math.tau)
        s = rnd.uniform(40, 160)
        l = rnd.uniform(0.1, 0.3)
        c = rnd.choice([P['bang'], P['fire_hi'], P['nova'],
                        (255, 255, 255), P['elec_hi']])
        fx.append({
            'kind': 'particle', 'x': x, 'y': y,
            'vx': math.cos(a) * s, 'vy': math.sin(a) * s,
            't': l, 'mt': l, 'color': c, 'sz': rnd.uniform(2, 4),
        })
    # ── ground scorch glow ────────────────────────────────────
    fx.append({
        'kind': 'nova',
        'x': x, 'y': y,
        'max_r': 12 + int(dmg * 0.15),
        't': 0.2, 'mt': 0.2,
    })



def _spawn_rocket_impact(meta: dict, x: float, y: float) -> None:
    """Big fiery rocket explosion."""
    import random as rnd
    fx = meta['fx']
    fx.append({'kind': 'shockwave', 'x': x, 'y': y,
               'max_r': 40, 't': 0.35, 'mt': 0.35, 'color': P['rocket']})
    fx.append({'kind': 'nova', 'x': x, 'y': y,
               'max_r': 25, 't': 0.25, 'mt': 0.25})
    for _ in range(16):
        a = rnd.uniform(0, math.tau)
        s = rnd.uniform(50, 180)
        l = rnd.uniform(0.2, 0.6)
        c = rnd.choice([P['rocket'], P['rocket_hi'], P['fire_hi'],
                        P['flame'], P['flame_hi']])
        fx.append({'kind': 'particle', 'x': x, 'y': y,
                   'vx': math.cos(a) * s, 'vy': math.sin(a) * s,
                   't': l, 'mt': l, 'color': c, 'sz': rnd.uniform(2.5, 5)})
    for _ in range(6):
        a = rnd.uniform(0, math.tau)
        s = rnd.uniform(10, 40)
        fx.append({'kind': 'smoke', 'x': x, 'y': y,
                   'vx': math.cos(a) * s, 'vy': math.sin(a) * s - 25,
                   't': rnd.uniform(0.5, 1.2), 'mt': 1.2,
                   'color': P['smoke'], 'sz': rnd.uniform(4, 8)})


# ── Particle / FX ageing ──────────────────────────────────────────────────────
def _age_fx(world: World, dt: float) -> None:
    fx = world.meta['fx']
    live = []
    for item in fx:
        item['t'] -= dt
        if item['t'] > 0:
            if 'x' in item:
                item['x'] += item.get('vx', 0) * dt
                item['y'] += item.get('vy', 0) * dt
            live.append(item)
    world.meta['fx'] = live




# ── Fog of war ────────────────────────────────────────────────────────────────
def _update_fog(world: World) -> None:
    fog = world.meta['fog']           # numpy uint8 (MAP_H, MAP_W)
    # Visible → explored
    fog[fog == 2] = 1
    # Mark visible tiles for each player entity with Vision
    for _eid, pos, vis, team in world.q(Position, Vision, Team):
        if team.id != PLAYER:
            continue
        tx  = int(pos.x // TILE)
        ty  = int(pos.y // TILE)
        tr  = int(vis.radius // TILE) + 1
        tr2 = tr * tr
        y0  = max(0, ty - tr)
        y1  = min(MAP_H, ty + tr + 1)
        x0  = max(0, tx - tr)
        x1  = min(MAP_W, tx + tr + 1)
        for gy in range(y0, y1):
            for gx in range(x0, x1):
                if (gx - tx) ** 2 + (gy - ty) ** 2 <= tr2:
                    fog[gy, gx] = 2
