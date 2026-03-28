# entities.py – factory functions, no game logic
import math
from ecs import World
from components import *
from config import *


def spawn_unit(world: World, x: float, y: float, team: int, kind: str) -> int:
    hp, spd, dmg, rng, rate, radius, cost = UDAT[kind]
    comps: list = [
        Position(x, y),
        Team(team),
        Health(float(hp), float(hp)),
        UnitData(kind, float(spd), float(dmg), float(rng),
                 float(rate), radius, cost),
        Movement(),
        Combat(),
        Vision(max(rng * VISION_MULT, 200.0)),
        Selectable(),
    ]
    if kind == 'harvester':
        comps.append(Harvester())
    return world.spawn(*comps)


def spawn_building(world: World, x: float, y: float, team: int,
                   kind: str, complete: bool = True) -> int:
    hp, w, h = BDAT[kind]
    name     = {'base': 'Command Center', 'barracks': 'Barracks',
                'factory': 'War Factory', 'refinery': 'Tiberium Refinery',
                'turret': 'Guard Tower', 'wall': 'Wall',
                'power_plant': 'Power Plant'}[kind]
    bd = BuildingData(kind, w, h, name, rally_x=x + w + 40, rally_y=y + h // 2)
    comps: list = [
        Position(x, y),
        Team(team),
        Health(float(hp), float(hp)),
        bd,
        Selectable(),
    ]
    if kind != 'wall':
        comps.append(Vision(220.0))
    if kind == 'turret':
        comps.append(Combat())
    if kind == 'wall':
        comps.append(Wall())
    if kind in POWER_DEMAND:
        comps.append(PowerConsumer(POWER_DEMAND[kind]))
    if kind == 'power_plant':
        comps.append(PowerPlant(POWER_OUTPUT))
    if not complete:
        bt = BUILD_TIME.get(kind, 15.0)
        comps.append(UnderConstruction(bt))
    return world.spawn(*comps)


def spawn_tiberium(world: World, x: float, y: float,
                   amount: float = 800.0) -> int:
    return world.spawn(
        Position(x, y),
        Resource(amount, amount),
    )


def spawn_projectile(world: World,
                     sx: float, sy: float,
                     tx: float, ty: float,
                     dmg: float, team: int, speed: float = 400.0,
                     weapon: str = 'bullet') -> int:
    return world.spawn(
        Position(sx, sy),
        Projectile(tx, ty, speed, dmg, team, weapon),
    )


def spawn_homing_rocket(world: World,
                        sx: float, sy: float,
                        tx: float, ty: float,
                        dmg: float, team: int,
                        target_eid: int,
                        speed: float = 280.0) -> int:
    heading = math.atan2(ty - sy, tx - sx)
    eid = world.spawn(
        Position(sx, sy),
        Projectile(tx, ty, speed, dmg, team, 'rocket'),
        HomingProjectile(target_eid, turn_rate=3.5, heading=heading),
    )
    return eid


def place_tiberium_field(world: World, cx: float, cy: float,
                         count: int = 12, radius: float = 100.0,
                         seed: int = 0) -> list[int]:
    import random
    rng = random.Random(seed)
    eids = []
    for _ in range(count):
        angle  = rng.uniform(0, math.tau)
        dist   = rng.uniform(0, radius)
        amount = rng.uniform(400.0, 900.0)
        eids.append(spawn_tiberium(world,
                                   cx + math.cos(angle) * dist,
                                   cy + math.sin(angle) * dist,
                                   amount))
    return eids
