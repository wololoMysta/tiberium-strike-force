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
        # Pre-allocated buffer for zoomed terrain (avoids per-frame Surface allocation
        # and fixes a ValueError raised by pygame when the dest surface height is H
        # but the requested scale height is H-HUD_H).
        self._terrain_buf = pygame.Surface((W, H - HUD_H))

    def update(self, world: World, dt: float) -> None:
        self._time += dt
        t   = self._time
        scr = self.screen               # always screen-sized
        cam = list(world.meta['cam'])    # copy so we can shake it
        fog = world.meta['fog']
        tiles = world.meta['tiles']
        zoom = world.meta.get('zoom', 1.0)

        # World-space viewport size
        vw = W / zoom
        vh = (H - HUD_H) / zoom
        screen_w = W
        screen_h = H - HUD_H
        nz = (zoom != 1.0)  # need zoom?

        # World→screen helpers
        def w2s_x(wx):
            return int((wx - cam[0]) * zoom)
        def w2s_y(wy):
            return int((wy - cam[1]) * zoom)

        # ── 1. Terrain ───────────────────────────────────────────────────────
        src = pygame.Rect(int(cam[0]), int(cam[1]),
                          int(vw) + 1, int(vh) + 1)
        src = src.clip(self.terrain_surf.get_rect())
        if src.width > 0 and src.height > 0:
            chunk = self.terrain_surf.subsurface(src)
            if nz:
                pygame.transform.scale(chunk, (screen_w, screen_h), self._terrain_buf)
                scr.blit(self._terrain_buf, (0, 0))
            else:
                scr.blit(chunk, (0, 0))

        # ── 1b. Water shimmer overlay ─────────────────────────────────────
        _ensure_surfaces()
        _draw_water_shimmer(scr, tiles, cam, t, zoom)

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
                dsx = w2s_x(d['x'])
                dsy = w2s_y(d['y'])
                if 0 <= dsx < screen_w and 0 <= dsy < screen_h:
                    alpha = min(50, int(50 * d['t'] / d['mt']))
                    if alpha > 5:
                        sz = max(1, int(d['sz'] * zoom))
                        ds = _get_surf(sz * 2, sz * 2)
                        pygame.draw.circle(ds, (180, 175, 160, alpha), (sz, sz), sz)
                        scr.blit(ds, (dsx - sz, dsy - sz))
                live_dust.append(d)
        self._dust = live_dust

        # ── 1d. Influence overlay ───────────────────────────────────
        if not world.meta.get('game_over'):
            _draw_influence_overlay(scr, world, cam, zoom)

        # ── 2. Tiberium fields ───────────────────────────────────────────────
        _tib_pad = 30
        for _eid, pos, res in world.q(Position, Resource):
            if res.amount <= 0:
                continue
            sx = w2s_x(pos.x)
            sy = w2s_y(pos.y)
            margin = int(30 * zoom)
            if -margin < sx < screen_w + margin and -margin < sy < screen_h + margin:
                if nz:
                    buf = _get_surf(_tib_pad * 2, _tib_pad * 2)
                    _draw_tiberium(buf, _tib_pad, _tib_pad,
                                   res.amount / res.max_amount, t)
                    s_sz = max(1, int(_tib_pad * 2 * zoom))
                    scaled = pygame.transform.scale(buf, (s_sz, s_sz))
                    scr.blit(scaled, (sx - s_sz // 2, sy - s_sz // 2))
                else:
                    _draw_tiberium(scr, sx, sy,
                                   res.amount / res.max_amount, t)

        # ── 3. Buildings (below units for z-order) ───────────────────────────
        for eid, pos, bd, hp, team in world.q(Position, BuildingData, Health, Team):
            sx = w2s_x(pos.x)
            sy = w2s_y(pos.y)
            bw_s = int(bd.w * zoom)
            bh_s = int(bd.h * zoom)
            if not (-bw_s < sx < screen_w + bw_s and
                    -bh_s < sy < screen_h + bh_s):
                continue
            tx = int(pos.x // TILE)
            ty2 = int(pos.y // TILE)
            if 0 <= tx < MAP_W and 0 <= ty2 < MAP_H and fog[ty2, tx] == 0:
                continue
            uc  = world.get(eid, UnderConstruction)
            sel = world.get(eid, Selectable)
            if nz:
                bpad = 12
                raw_w = bd.w + bpad * 2
                raw_h = bd.h + bpad * 2
                buf = pygame.Surface((raw_w, raw_h), pygame.SRCALPHA)
                _draw_building(buf, bpad, bpad, bd, team.id, hp.ratio, t,
                               sel and sel.selected,
                               uc.ratio if uc else None)
                sw2 = max(1, int(raw_w * zoom))
                sh2 = max(1, int(raw_h * zoom))
                buf = pygame.transform.scale(buf, (sw2, sh2))
                scr.blit(buf, (sx - int(bpad * zoom),
                               sy - int(bpad * zoom)))
                _hp_bar(scr, sx + bw_s // 2, sy - int(4 * zoom),
                        max(8, int(28 * zoom)), hp.ratio)
            else:
                _draw_building(scr, sx, sy, bd, team.id, hp.ratio, t,
                               sel and sel.selected,
                               uc.ratio if uc else None)
                _hp_bar(scr, sx + bd.w // 2, sy - 4, 28, hp.ratio)
            # ── Active building ambient FX ────────────────────
            if uc is None:
                _building_ambient(world.meta['fx'], pos, bd, t)

        # ── 4. Units ─────────────────────────────────────────────────────────
        for eid, pos, ud, hp, team in world.q(Position, UnitData, Health, Team):
            sx = w2s_x(pos.x)
            sy = w2s_y(pos.y)
            margin = int(30 * zoom)
            if not (-margin < sx < screen_w + margin and
                    -margin < sy < screen_h + margin):
                continue
            tx3 = int(pos.x // TILE)
            ty3 = int(pos.y // TILE)
            if 0 <= tx3 < MAP_W and 0 <= ty3 < MAP_H and fog[ty3, tx3] == 0:
                continue
            sel = world.get(eid, Selectable)
            mv = world.get(eid, Movement)
            fn  = _DRAWERS.get(ud.kind)
            if nz:
                upad = 20
                buf_sz = (ud.radius + upad) * 2
                buf = pygame.Surface((buf_sz, buf_sz), pygame.SRCALPHA)
                cx2, cy2 = buf_sz // 2, buf_sz // 2
                if fn:
                    if ud.kind in ('tank', 'rocket_tank', 'tesla_tank',
                                   'laser_tank', 'flame_tank'):
                        fn(buf, cx2, cy2, team.id, ud.facing, ud.turret,
                           sel and sel.selected, t)
                    else:
                        fn(buf, cx2, cy2, team.id, ud.facing,
                           sel and sel.selected, t)
                s_sz = max(1, int(buf_sz * zoom))
                buf = pygame.transform.scale(buf, (s_sz, s_sz))
                scr.blit(buf, (sx - s_sz // 2, sy - s_sz // 2))
                _hp_bar(scr, sx, sy - int((ud.radius + 8) * zoom),
                        max(8, int(28 * zoom)), hp.ratio)
            else:
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
            sx = w2s_x(pos.x)
            sy = w2s_y(pos.y)
            if -10 < sx < screen_w + 10 and -10 < sy < screen_h + 10:
                _spos.x = sx; _spos.y = sy
                _draw_projectile(scr, _spos, proj)

        # ── 6. Particles / FX ────────────────────────────────────────────────
        draw_fx(scr, world.meta['fx'], cam, self.small_font, zoom)

        # ── 7. Selection drag box ─────────────────────────────────────────────
        sel_st = world.meta.get('sel_start')
        if sel_st is not None:
            mx, my = pygame.mouse.get_pos()
            sx2, sy2 = sel_st
            rx, ry   = min(sx2, mx), min(sy2, my)
            rw, rh   = abs(mx - sx2), abs(my - sy2)
            if rw > 4 or rh > 4:
                box_surf = pygame.Surface((rw, rh), pygame.SRCALPHA)
                box_surf.fill((*P['select'], 25))
                pygame.draw.rect(box_surf, (*P['select'], 180),
                                 (0, 0, rw, rh), 1)
                scr.blit(box_surf, (rx, ry))

        # ── 8. Fog of war ────────────────────────────────────────────────────
        _draw_fog(scr, fog, cam[0], cam[1], zoom)

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

        # ── 10. Minimap (upper-left) ──────────────────────────────────────────
        _draw_minimap(scr, world, 6)

        # ── 11. HUD ───────────────────────────────────────────────────────────
        _draw_hud(scr, world, self.font, self.small_font, t)

        # ── 10b. FPS counter ─────────────────────────────────────────────────
        if self._clock:
            fps = self._clock.get_fps()
            fps_col = P['hp_hi'] if fps >= 50 else P['hp_mid'] if fps >= 30 else P['hp_lo']
            fps_txt = self.small_font.render(f"FPS: {int(fps)}", True, fps_col)
            scr.blit(fps_txt, (W - fps_txt.get_width() - 6, 4))

        # ── 12. Game-over ─────────────────────────────────────────────────────
        go = world.meta.get('game_over')
        if go:
            _draw_game_over(scr, go, self.big_font, self.font)

        pygame.display.flip()
