# systems/combat_sys.py – auto-attack, damage, death cleanup
import math
import random
from ecs import World, System
from components import *
from config import *
import entities as ent


class CombatSys(System):
    def update(self, world: World, dt: float) -> None:
        _turret_acquire(world)
        _unit_acquire(world)
        _cooldown(world, dt)
        _attack(world, dt)
        _reap_dead(world)


# ── Auto-targeting ────────────────────────────────────────────────────────────
def _turret_acquire(world: World) -> None:
    """Turrets scan for enemies automatically."""
    for eid, pos, cb, bd, team in world.q(Position, Combat, BuildingData, Team):
        if cb.target is not None and world.has(cb.target, Health):
            continue
        cb.target = _nearest_enemy(world, pos.x, pos.y, TURRET_RNG, team.id)


def _unit_acquire(world: World) -> None:
    """Units with no explicit target find the nearest enemy in range."""
    for eid, pos, ud, cb, team in world.q(Position, UnitData, Combat, Team):
        if ud.damage <= 0:
            continue   # harvesters don't fight
        if cb.target is not None:
            # validate target still alive and in range
            tpos = world.get(cb.target, Position)
            if tpos is None:
                cb.target = None
                continue
            rng = ud.rng if world.has(eid, UnitData) else TURRET_RNG
            if math.hypot(tpos.x - pos.x, tpos.y - pos.y) > rng * 1.5:
                cb.target = None  # chased too far
        if cb.target is None:
            rng = ud.rng
            cb.target = _nearest_enemy(world, pos.x, pos.y, rng, team.id)


def _nearest_enemy(world: World, x: float, y: float,
                   rng: float, my_team: int):
    best, best_d = None, rng
    for eid, pos, team in world.q(Position, Team):
        if team.id == my_team:
            continue
        # skip dead-but-not-reaped, skip tiberium
        if not world.has(eid, Health):
            continue
        d = math.hypot(pos.x - x, pos.y - y)
        if d < best_d:
            best, best_d = eid, d
    return best


# ── Cooldown ──────────────────────────────────────────────────────────────────
def _cooldown(world: World, dt: float) -> None:
    for _eid, cb in world.q(Combat):
        if cb.cooldown > 0:
            cb.cooldown -= dt


# ── Fire ──────────────────────────────────────────────────────────────────────
def _attack(world: World, dt: float) -> None:
    for eid, pos, cb, team in world.q(Position, Combat, Team):
        if cb.target is None or cb.cooldown > 0:
            continue
        tpos = world.get(cb.target, Position)
        if tpos is None:
            cb.target = None
            continue

        ud = world.get(eid, UnitData)
        bd = world.get(eid, BuildingData)
        if ud:
            dmg, rng, rate = ud.damage, ud.rng, ud.rate
            # Rotate turret toward target for tank variants
            dx, dy = tpos.x - pos.x, tpos.y - pos.y
            if ud.kind in ('tank', 'rocket_tank', 'tesla_tank',
                           'laser_tank', 'flame_tank'):
                ud.turret = math.atan2(dy, dx)
            else:
                ud.facing = math.atan2(dy, dx)
        elif bd:
            team_id = world.get(eid, Team)
            pr = world.meta.get(f'power_ratio_{team_id.id if team_id else 0}', 1.0)
            dmg, rng, rate = TURRET_DMG, TURRET_RNG, TURRET_RATE * pr
        else:
            continue

        dist = math.hypot(tpos.x - pos.x, tpos.y - pos.y)
        if dist > rng:
            # Move toward target if it's a unit
            mv = world.get(eid, Movement)
            if mv and ud:
                mv.tx = tpos.x
                mv.ty = tpos.y
            continue

        # Fire!
        cb.cooldown = 1.0 / max(0.01, rate)
        fx = world.meta['fx']
        aim = math.atan2(tpos.y - pos.y, tpos.x - pos.x)
        kind = ud.kind if ud else 'turret'

        if kind == 'rocket_tank':
            _fire_rocket(world, pos, tpos, dmg, team.id, cb.target, fx, aim)
        elif kind == 'tesla_tank':
            _fire_tesla(world, pos, tpos, dmg, team.id, fx, aim)
        elif kind == 'laser_tank':
            _fire_laser(world, pos, tpos, dmg, team.id, fx, aim)
        elif kind == 'flame_tank':
            _fire_flame(world, pos, tpos, dmg, team.id, fx, aim)
        else:
            ent.spawn_projectile(world, pos.x, pos.y, tpos.x, tpos.y,
                                 dmg, team.id)
            _spawn_muzzle_fx(fx, pos.x, pos.y, aim, dmg, team.id)



# ── Reap dead entities ────────────────────────────────────────────────────────
def _reap_dead(world: World) -> None:
    meta = world.meta
    for eid, hp in world.q(Health):
        if hp.dead:
            pos = world.get(eid, Position)
            if pos:
                size = 1.5
                ud   = world.get(eid, UnitData)
                bd   = world.get(eid, BuildingData)
                if bd:
                    size = 3.0
                    # Check win/lose
                    team = world.get(eid, Team)
                    if bd.kind == 'base' and team:
                        if team.id == ENEMY:
                            meta['game_over'] = 'win'
                        else:
                            meta['game_over'] = 'lose'
                _spawn_explosion(meta, pos.x, pos.y, size)
            world.kill(eid)
            # Remove from selection
            meta['selected'].discard(eid)
            if meta.get('sel_bldg') == eid:
                meta['sel_bldg'] = None


def _spawn_muzzle_fx(fx: list, x: float, y: float, aim: float,
                     dmg: float, team: int) -> None:
    """Crazy over-the-top muzzle blast with sparks and arcs."""
    import random as rnd
    # Big flash
    fx.append({'kind': 'flash', 'x': x, 'y': y, 't': 0.18})
    # Directional muzzle flare (cone of sparks)
    n_sparks = 6 if dmg < 60 else 14
    for _ in range(n_sparks):
        spread = rnd.uniform(-0.4, 0.4)
        spd = rnd.uniform(120, 350)
        a = aim + spread
        l = rnd.uniform(0.08, 0.28)
        c = rnd.choice([P['fire_hi'], P['nova'], P['elec_hi'],
                        (255, 255, 255), P['bang']])
        fx.append({'kind': 'particle', 'x': x, 'y': y,
                   'vx': math.cos(a) * spd, 'vy': math.sin(a) * spd,
                   't': l, 'mt': l, 'color': c,
                   'sz': rnd.uniform(1.5, 4.0)})
    # Electric arcs (short-lived lightning segments near muzzle)
    if dmg >= 40:
        for _ in range(3):
            fx.append({
                'kind': 'arc',
                'x': x, 'y': y,
                'aim': aim,
                'len': rnd.uniform(15, 40),
                'segs': rnd.randint(3, 6),
                't': rnd.uniform(0.06, 0.14),
                'mt': 0.14,
                'color': P['elec'] if team == PLAYER else P['laser_e'],
            })
    # Ground ring flash for heavy weapons
    if dmg >= 60:
        fx.append({
            'kind': 'shockwave',
            'x': x, 'y': y,
            'max_r': 24,
            't': 0.2, 'mt': 0.2,
            'color': P['nova'],
        })


def _spawn_explosion(meta: dict, x: float, y: float, size: float = 1.0) -> None:
    """CRAZY fire + smoke + shockwave + debris + screen-shake explosion."""
    import random as rnd
    fx = meta['fx']
    # ── shockwave ring ────────────────────────────────────────
    fx.append({
        'kind': 'shockwave',
        'x': x, 'y': y,
        'max_r': int(55 * size),
        't': 0.45, 'mt': 0.45,
        'color': P['nova'],
    })
    if size >= 2.0:
        # second slower shockwave for buildings
        fx.append({
            'kind': 'shockwave',
            'x': x, 'y': y,
            'max_r': int(90 * size),
            't': 0.7, 'mt': 0.7,
            'color': P['bang'],
        })
    # ── fire particles (more, faster, bigger) ─────────────────
    for _ in range(int(28 * size)):
        a = rnd.uniform(0, math.tau)
        s = rnd.uniform(50, 220) * size
        l = rnd.uniform(0.25, 1.0)
        c = rnd.choice([P['fire_hi'], P['fire_lo'], P['bang'],
                        (220, 120, 0), P['nova'], (255, 255, 100)])
        fx.append({'kind': 'particle', 'x': x, 'y': y,
                   'vx': math.cos(a) * s, 'vy': math.sin(a) * s,
                   't': l, 'mt': l, 'color': c,
                   'sz': rnd.uniform(2.5, 7) * size})
    # ── hot core flash ────────────────────────────────────────
    fx.append({
        'kind': 'nova',
        'x': x, 'y': y,
        'max_r': int(30 * size),
        't': 0.3, 'mt': 0.3,
    })
    # ── smoke (more dramatic) ─────────────────────────────────
    for _ in range(int(12 * size)):
        a  = rnd.uniform(0, math.tau)
        s  = rnd.uniform(10, 65)
        l  = rnd.uniform(0.6, 2.2)
        sz = rnd.uniform(5, 16) * size
        fx.append({'kind': 'smoke', 'x': x, 'y': y,
                   'vx': math.cos(a) * s, 'vy': math.sin(a) * s - 30,
                   't': l, 'mt': l, 'color': P['smoke'], 'sz': sz})
    # ── flying debris chunks ──────────────────────────────────
    for _ in range(int(8 * size)):
        a = rnd.uniform(0, math.tau)
        s = rnd.uniform(80, 250) * size
        l = rnd.uniform(0.3, 0.8)
        fx.append({'kind': 'debris', 'x': x, 'y': y,
                   'vx': math.cos(a) * s,
                   'vy': math.sin(a) * s - rnd.uniform(40, 120),
                   't': l, 'mt': l,
                   'color': rnd.choice([(100, 100, 100), (60, 55, 40),
                                        (140, 80, 20)]),
                   'sz': rnd.uniform(2, 5)})


# ── Special weapon fire functions ─────────────────────────────────────────────

def _fire_rocket(world, pos, tpos, dmg, team_id, target_eid, fx, aim):
    """Launch a homing rocket that tracks the target."""
    import random as rnd
    # Offset launch from barrel tip
    ox = pos.x + math.cos(aim) * 22
    oy = pos.y + math.sin(aim) * 22
    ent.spawn_homing_rocket(world, ox, oy, tpos.x, tpos.y,
                            dmg, team_id, target_eid, speed=260.0)
    # Launch smoke puff
    for _ in range(6):
        a = aim + math.pi + rnd.uniform(-0.6, 0.6)
        s = rnd.uniform(40, 120)
        fx.append({'kind': 'smoke', 'x': ox, 'y': oy,
                   'vx': math.cos(a) * s, 'vy': math.sin(a) * s,
                   't': rnd.uniform(0.3, 0.7), 'mt': 0.7,
                   'color': P['smoke'], 'sz': rnd.uniform(3, 6)})
    fx.append({'kind': 'flash', 'x': ox, 'y': oy, 't': 0.12})


def _fire_tesla(world, pos, tpos, dmg, team_id, fx, aim):
    """Instant-hit tesla bolt: no projectile, direct damage + insane arcs."""
    import random as rnd
    # Direct damage to anything near target
    from systems.effects_sys import _deal_splash
    _deal_splash(world, tpos.x, tpos.y, dmg, team_id)
    # The main tesla bolt: thick multi-segment arc from source to target
    dist = math.hypot(tpos.x - pos.x, tpos.y - pos.y)
    n_arcs = rnd.randint(3, 6)
    for _ in range(n_arcs):
        fx.append({
            'kind': 'tesla_bolt',
            'sx': pos.x, 'sy': pos.y,
            'ex': tpos.x, 'ey': tpos.y,
            'segs': max(4, int(dist / 20)),
            'jitter': rnd.uniform(12, 30),
            't': rnd.uniform(0.12, 0.25),
            'mt': 0.25,
            'team': team_id,
        })
    # Bright flash at both ends
    fx.append({'kind': 'flash', 'x': pos.x, 'y': pos.y, 't': 0.15})
    fx.append({'kind': 'nova', 'x': tpos.x, 'y': tpos.y,
               'max_r': 20, 't': 0.2, 'mt': 0.2})
    # Branching secondary arcs at target
    for _ in range(rnd.randint(2, 5)):
        ba = rnd.uniform(0, math.tau)
        bl = rnd.uniform(20, 60)
        bex = tpos.x + math.cos(ba) * bl
        bey = tpos.y + math.sin(ba) * bl
        fx.append({
            'kind': 'tesla_bolt',
            'sx': tpos.x, 'sy': tpos.y,
            'ex': bex, 'ey': bey,
            'segs': rnd.randint(3, 5),
            'jitter': rnd.uniform(8, 18),
            't': rnd.uniform(0.06, 0.15),
            'mt': 0.15,
            'team': team_id,
        })
    # Ground scorch particles
    for _ in range(8):
        a = rnd.uniform(0, math.tau)
        s = rnd.uniform(30, 100)
        fx.append({'kind': 'particle', 'x': tpos.x, 'y': tpos.y,
                   'vx': math.cos(a) * s, 'vy': math.sin(a) * s,
                   't': 0.2, 'mt': 0.2,
                   'color': P['tesla_hi'], 'sz': rnd.uniform(2, 4)})


def _fire_laser(world, pos, tpos, dmg, team_id, fx, aim):
    """Instant-hit laser beam: direct damage + sustained beam visual."""
    from systems.effects_sys import _deal_splash
    _deal_splash(world, tpos.x, tpos.y, dmg, team_id)
    # Beam FX (rendered as a line with glow)
    fx.append({
        'kind': 'laser_beam',
        'sx': pos.x + math.cos(aim) * 20,
        'sy': pos.y + math.sin(aim) * 20,
        'ex': tpos.x, 'ey': tpos.y,
        't': 0.15, 'mt': 0.15,
        'team': team_id,
    })
    # Small impact sparks
    import random as rnd
    for _ in range(4):
        a = rnd.uniform(0, math.tau)
        s = rnd.uniform(30, 80)
        fx.append({'kind': 'particle', 'x': tpos.x, 'y': tpos.y,
                   'vx': math.cos(a) * s, 'vy': math.sin(a) * s,
                   't': 0.12, 'mt': 0.12,
                   'color': P['laser_r'] if team_id == PLAYER else P['laser_g'],
                   'sz': rnd.uniform(1.5, 3)})


def _fire_flame(world, pos, tpos, dmg, team_id, fx, aim):
    """Short-range flamethrower burst: stream of fire particles + direct dmg."""
    import random as rnd
    from systems.effects_sys import _deal_splash
    _deal_splash(world, tpos.x, tpos.y, dmg, team_id)
    # Flame stream: many particles in a cone from barrel to target
    dist = math.hypot(tpos.x - pos.x, tpos.y - pos.y)
    ox = pos.x + math.cos(aim) * 18
    oy = pos.y + math.sin(aim) * 18
    for _ in range(12):
        spread = rnd.uniform(-0.25, 0.25)
        a = aim + spread
        s = rnd.uniform(150, 300)
        lifetime = max(0.15, dist / s * rnd.uniform(0.8, 1.3))
        c = rnd.choice([P['flame'], P['flame_hi'], P['flame_wh'],
                        P['fire_hi'], P['fire_lo']])
        fx.append({'kind': 'particle', 'x': ox, 'y': oy,
                   'vx': math.cos(a) * s, 'vy': math.sin(a) * s,
                   't': lifetime, 'mt': lifetime,
                   'color': c, 'sz': rnd.uniform(3, 7)})
    # Smoke behind the flames
    for _ in range(4):
        a = aim + rnd.uniform(-0.4, 0.4)
        s = rnd.uniform(30, 80)
        fx.append({'kind': 'smoke',
                   'x': tpos.x + rnd.uniform(-10, 10),
                   'y': tpos.y + rnd.uniform(-10, 10),
                   'vx': math.cos(a) * s, 'vy': -rnd.uniform(15, 40),
                   't': rnd.uniform(0.5, 1.2), 'mt': 1.2,
                   'color': P['smoke'], 'sz': rnd.uniform(4, 8)})
