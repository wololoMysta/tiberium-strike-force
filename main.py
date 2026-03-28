# main.py – game initialisation, world setup, loop
import sys
import math
import random
import pygame
import numpy as np

from ecs import World
from config import *
import terrain as ter
import entities as ent
from components import AIController, Team
from systems.input_sys   import InputSys
from systems.move_sys    import MoveSys
from systems.combat_sys  import CombatSys
from systems.harvest_sys import HarvestSys
from systems.ai_sys      import AISys
from systems.effects_sys import EffectsSys
from systems.tib_sys     import TibSys
from systems.power_sys   import PowerSys
from systems.render_sys  import RenderSys


# ── World bootstrap ───────────────────────────────────────────────────────────
def build_world(seed: int = 42) -> World:
    world = World()
    rng   = random.Random(seed)

    # Terrain
    tiles, height = ter.generate(seed)
    tsurf         = ter.build_surface(tiles, height)

    # Fog of war
    fog = np.zeros((MAP_H, MAP_W), dtype=np.uint8)

    # Camera starts above player base
    world.meta = {
        'tiles':    tiles,
        'credits':  [CREDITS_START, CREDITS_START],
        'cam':      [0.0, 0.0],
        'selected': set(),
        'sel_bldg': None,
        'sel_start': None,
        'sel_box':  None,
        'mode':     'normal',
        'place_type': None,
        'wall_drag_start': None,
        'fog':      fog,
        'fx':       [],
        'events':   [],
        'game_over': None,
        'time':     0.0,
        'hud_tab':  0,
        'zoom':     1.0,
        'power_ratio_0': 1.0,
        'power_demand_0': 0,
        'power_supply_0': 0,
    }

    # ── Player start (NW quadrant) ────────────────────────────────────────────
    ent.spawn_unit(world, 480, 420, PLAYER, 'mcv')
    _cam_on(world, 480, 420)

    # Tiberium fields near player
    for cx, cy in ((800, 560), (950, 480), (700, 320)):
        ent.place_tiberium_field(world, cx, cy, count=14, radius=90,
                                 seed=rng.randint(0, 999))

    # ── Enemy start (SE quadrant) ─────────────────────────────────────────────
    ex = MAP_W * TILE - 600
    ey = MAP_H * TILE - 600
    ent.spawn_unit(world, ex + 40, ey + 40, ENEMY, 'mcv')

    # Tiberium near enemy
    for cx, cy in ((ex - 200, ey - 180), (ex + 100, ey - 250)):
        ent.place_tiberium_field(world, cx, cy, count=12, radius=80,
                                 seed=rng.randint(0, 999))

    # Mid-map tiberium
    mid = MAP_W * TILE // 2
    for cx, cy in ((mid, mid - 200), (mid - 300, mid + 100), (mid + 280, mid)):
        ent.place_tiberium_field(world, cx, cy, count=10, radius=80,
                                 seed=rng.randint(0, 999))

    # ── AI controller singleton ───────────────────────────────────────────────
    world.spawn(AIController(), Team(ENEMY))

    # ── Attach terrain surface to meta for render ─────────────────────────────
    world.meta['terrain_surf'] = tsurf
    world.meta['mini_surf']    = ter.build_minimap_surf(tiles, height)

    return world


def _cam_on(world: World, wx: float, wy: float) -> None:
    world.meta['cam'][0] = max(0, wx - W // 2)
    world.meta['cam'][1] = max(0, wy - (H - HUD_H) // 2)


# ── Main loop ─────────────────────────────────────────────────────────────────
def main() -> None:
    pygame.init()
    screen = pygame.display.set_mode((W, H))
    pygame.display.set_caption(TITLE)
    clock  = pygame.time.Clock()

    font       = pygame.font.SysFont('consolas', 16, bold=True)
    small_font = pygame.font.SysFont('consolas', 13)
    big_font   = pygame.font.SysFont('consolas', 48, bold=True)

    world = build_world()
    tsurf = world.meta['terrain_surf']

    render = RenderSys(screen, tsurf, font, small_font, big_font, clock)

    world.systems = [
        InputSys(),
        MoveSys(),
        CombatSys(),
        HarvestSys(),
        AISys(),
        EffectsSys(),
        TibSys(),
        PowerSys(),
        render,
    ]

    while True:
        dt     = clock.tick(FPS) / 1000.0
        dt     = min(dt, 0.05)   # cap delta for slow frames
        events = pygame.event.get()
        world.meta['events'] = events
        world.meta['time']  += dt

        for ev in events:
            if ev.type == pygame.QUIT:
                pygame.quit(); sys.exit()
            if ev.type == pygame.KEYDOWN:
                if ev.key == pygame.K_ESCAPE and world.meta.get('game_over'):
                    pygame.quit(); sys.exit()
                if ev.key == pygame.K_r and world.meta.get('game_over'):
                    world  = build_world()
                    tsurf  = world.meta['terrain_surf']
                    render.terrain_surf = tsurf
                    render._clock = clock
                    world.systems = [
                        InputSys(), MoveSys(), CombatSys(),
                        HarvestSys(), AISys(), EffectsSys(), TibSys(), PowerSys(), render,
                    ]

        if not world.meta.get('game_over'):
            world.tick(dt)
        else:
            # Still run render even on game over
            render.update(world, dt)


if __name__ == '__main__':
    main()
