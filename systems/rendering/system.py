# systems/rendering/system.py – RenderSys class (main render pipeline)
import random, pygame

from ecs import World, System
from components import (Position, Resource, BuildingData, Health, Team,
                        UnderConstruction, Selectable, UnitData, Movement,
                        Projectile)
from config import W, H, HUD_H, TILE, MAP_W, MAP_H, P

from systems.rendering.helpers import (
    _get_surf, _ensure_surfaces, _spos,
)
from systems.rendering.units import _DRAWERS
from systems.rendering.buildings import _draw_building, _hp_bar
from systems.rendering.environment import (
    _draw_tiberium, _draw_projectile, _draw_fog,
    _draw_water_shimmer, _draw_day_night_tint, _draw_influence_overlay,
)
from systems.rendering.hud import (
    _draw_hud, _draw_minimap, _draw_game_over,
    _draw_ghost, _draw_wall_drag_line,
)
from systems.rendering.fx import _spawn_move_dust, _building_ambient, draw_fx


class RenderSys(System):
    def __init__(self, screen, terrain_surf, font, small_font, big_font, clock=None):
        self.screen       = screen
        self.terrain_surf = terrain_surf
        self.font         = font
        self.small_font   = small_font
        self.big_font     = big_font
        self._clock       = clock
        self._time        = 0.0
        # Ambient dust pool (spawn once, recycle)
        self._dust: list[dict] = []
        self._dust_timer = 0.0
        self._game_surf  = None
        self._game_surf_sz = (0, 0)

    def _get_game_surf(self, vw: int, vh: int) -> pygame.Surface:
        if self._game_surf_sz != (vw, vh):
            self._game_surf = pygame.Surface((vw, vh))
            self._game_surf_sz = (vw, vh)
        return self._game_surf

    def update(self, world: World, dt: float) -> None:
        self._time += dt
        t   = self._time
        cam = list(world.meta['cam'])  # copy so we can shake it
        fog = world.meta['fog']
        tiles = world.meta['tiles']
        zoom = world.meta.get('zoom', 1.0)

        # Virtual viewport dimensions (world-space pixels)
        vw = int(W / zoom)
        vh = int((H - HUD_H) / zoom)

        # Game surface at virtual viewport size
        scr = self._get_game_surf(vw, vh)

        # ── 1. Terrain ───────────────────────────────────────────────────────
        src = pygame.Rect(int(cam[0]), int(cam[1]), vw, vh)
        scr.blit(self.terrain_surf, (0, 0), src)

        # ── 1b. Water shimmer overlay ─────────────────────────────────────
        _ensure_surfaces()
        _draw_water_shimmer(scr, tiles, cam, t)

        # ── 1c. Ambient dust particles ────────────────────────────────────
        self._dust_timer += dt
        if self._dust_timer >= 0.12 and len(self._dust) < 40:
            self._dust_timer = 0.0
            wx = cam[0] + random.uniform(0, vw)
            wy = cam[1] + random.uniform(0, vh)
            self._dust.append({
                'x': wx, 'y': wy,
                'vx': random.uniform(8, 25), 'vy': random.uniform(-6, 6),
                't': random.uniform(2.0, 5.0),
                'mt': 5.0,
                'sz': random.uniform(1.0, 2.5),
            })
        live_dust = []
        for d in self._dust:
            d['t'] -= dt
            if d['t'] > 0:
                d['x'] += d['vx'] * dt
                d['y'] += d['vy'] * dt
                dsx = int(d['x'] - cam[0])
                dsy = int(d['y'] - cam[1])
                if 0 <= dsx < vw and 0 <= dsy < vh:
                    alpha = min(50, int(50 * d['t'] / d['mt']))
                    if alpha > 5:
                        sz = max(1, int(d['sz']))
                        ds = _get_surf(sz * 2, sz * 2)
                        pygame.draw.circle(ds, (180, 175, 160, alpha), (sz, sz), sz)
                        scr.blit(ds, (dsx - sz, dsy - sz))
                live_dust.append(d)
        self._dust = live_dust

        # ── 1d. Influence overlay ───────────────────────────────────
        if not world.meta.get('game_over'):
            _draw_influence_overlay(scr, world, cam)

        # ── 2. Tiberium fields ───────────────────────────────────────────────
        for _eid, pos, res in world.q(Position, Resource):
            if res.amount <= 0:
                continue
            sx = int(pos.x - cam[0])
            sy = int(pos.y - cam[1])
            if -30 < sx < vw + 30 and -30 < sy < vh + 30:
                _draw_tiberium(scr, sx, sy, res.amount / res.max_amount, t)

        # ── 3. Buildings (below units for z-order) ───────────────────────────
        for eid, pos, bd, hp, team in world.q(Position, BuildingData, Health, Team):
            sx = int(pos.x - cam[0])
            sy = int(pos.y - cam[1])
            if not (-bd.w < sx < vw + bd.w and -bd.h < sy < vh + bd.h):
                continue
            tx = int(pos.x // TILE)
            ty2 = int(pos.y // TILE)
            if 0 <= tx < MAP_W and 0 <= ty2 < MAP_H and fog[ty2, tx] == 0:
                continue
            uc  = world.get(eid, UnderConstruction)
            sel = world.get(eid, Selectable)
            _draw_building(scr, sx, sy, bd, team.id, hp.ratio, t,
                           sel and sel.selected,
                           uc.ratio if uc else None)
            # ── Active building ambient FX ────────────────────
            if uc is None:
                _building_ambient(world.meta['fx'], pos, bd, t)

        # ── 4. Units ─────────────────────────────────────────────────────────
        for eid, pos, ud, hp, team in world.q(Position, UnitData, Health, Team):
            sx = int(pos.x - cam[0])
            sy = int(pos.y - cam[1])
            if not (-30 < sx < vw + 30 and -30 < sy < vh + 30):
                continue
            tx3 = int(pos.x // TILE)
            ty3 = int(pos.y // TILE)
            if 0 <= tx3 < MAP_W and 0 <= ty3 < MAP_H and fog[ty3, tx3] == 0:
                continue
            sel = world.get(eid, Selectable)
            mv = world.get(eid, Movement)
            fn  = _DRAWERS.get(ud.kind)
            if fn:
                if ud.kind in ('tank', 'rocket_tank', 'tesla_tank',
                               'laser_tank', 'flame_tank'):
                    fn(scr, sx, sy, team.id, ud.facing, ud.turret,
                       sel and sel.selected, t)
                else:
                    fn(scr, sx, sy, team.id, ud.facing,
                       sel and sel.selected, t)
            _hp_bar(scr, sx, sy - ud.radius - 8, 28, hp.ratio)
            # ── movement dust trail ───────────────────────────
            if mv and mv.tx is not None:
                _spawn_move_dust(world.meta['fx'], pos, ud)

        # ── 5. Projectiles ───────────────────────────────────────────────────
        for _eid, pos, proj in world.q(Position, Projectile):
            sx = int(pos.x - cam[0])
            sy = int(pos.y - cam[1])
            if -10 < sx < vw + 10 and -10 < sy < vh + 10:
                _spos.x = sx; _spos.y = sy
                _draw_projectile(scr, _spos, proj)

        # ── 6. Particles / FX ────────────────────────────────────────────────
        draw_fx(scr, world.meta['fx'], cam, self.small_font)

        # ── 7. Selection drag box ─────────────────────────────────────────────
        sel_st = world.meta.get('sel_start')
        if sel_st is not None:
            mx, my = pygame.mouse.get_pos()
            sx2, sy2 = sel_st
            # Convert to virtual-viewport coordinates for drawing
            vrx = min(sx2, mx) / zoom
            vry = min(sy2, my) / zoom
            vrw = abs(mx - sx2) / zoom
            vrh = abs(my - sy2) / zoom
            if vrw > 4 or vrh > 4:
                bw2 = max(1, int(vrw))
                bh2 = max(1, int(vrh))
                box_surf = pygame.Surface((bw2, bh2), pygame.SRCALPHA)
                box_surf.fill((*P['select'], 25))
                pygame.draw.rect(box_surf, (*P['select'], 180), (0, 0, bw2, bh2), 1)
                scr.blit(box_surf, (int(vrx), int(vry)))

        # ── 8. Fog of war ────────────────────────────────────────────────────
        _draw_fog(scr, fog, cam[0], cam[1])

        # ── 8b. Day/night tint ────────────────────────────────────────────────
        _draw_day_night_tint(scr, t)

        # ── 9. Ghost building / wall drag preview ────────────────────────────
        if world.meta.get('mode') == 'place_building':
            kind = world.meta['place_type']
            drag = world.meta.get('wall_drag_start')
            if kind == 'wall' and drag is not None:
                _draw_wall_drag_line(scr, cam, world, drag)
            else:
                _draw_ghost(scr, cam, kind, world)

        # ── Scale game surface to screen ──────────────────────────────────────
        real_scr = self.screen
        if zoom != 1.0:
            pygame.transform.scale(scr, (W, H - HUD_H), real_scr)
        else:
            real_scr.blit(scr, (0, 0))

        # ── 10. Minimap (upper-left) ──────────────────────────────────────────
        _draw_minimap(real_scr, world, 6)

        # ── 11. HUD ───────────────────────────────────────────────────────────
        _draw_hud(real_scr, world, self.font, self.small_font, t)

        # ── 10b. FPS counter ─────────────────────────────────────────────────
        if self._clock:
            fps = self._clock.get_fps()
            fps_col = P['hp_hi'] if fps >= 50 else P['hp_mid'] if fps >= 30 else P['hp_lo']
            fps_txt = self.small_font.render(f"FPS: {int(fps)}", True, fps_col)
            real_scr.blit(fps_txt, (W - fps_txt.get_width() - 6, 4))

        # ── 12. Game-over ─────────────────────────────────────────────────────
        go = world.meta.get('game_over')
        if go:
            _draw_game_over(real_scr, go, self.big_font, self.font)

        pygame.display.flip()
