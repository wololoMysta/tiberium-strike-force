# systems/rendering/fx.py – particles, movement dust, building ambient FX
import math, random, pygame
from config import P
from systems.rendering.helpers import _get_surf, _glow


# ── Movement dust ─────────────────────────────────────────────────────────────
_move_dust_accum: dict = {}  # eid → accumulated time

def _spawn_move_dust(fx: list, pos, ud) -> None:
    """Every ~0.08s while moving, emit a small ground-coloured puff."""
    eid_hash = id(pos)  # unique per entity position component
    acc = _move_dust_accum.get(eid_hash, 0) + 0.017  # ~approx dt at 60fps
    if acc >= 0.08:
        acc = 0.0
        # Heavy units make bigger dust
        sz = 2.5 if ud.kind in ('tank', 'harvester', 'mcv') else 1.5
        fx.append({
            'kind': 'move_dust',
            'x': pos.x + random.uniform(-4, 4),
            'y': pos.y + random.uniform(2, 8),
            'vx': random.uniform(-8, 8),
            'vy': random.uniform(-12, -2),
            't': random.uniform(0.3, 0.7),
            'mt': 0.7,
            'sz': sz,
        })
    _move_dust_accum[eid_hash] = acc


# ── Building ambient FX ──────────────────────────────────────────────────────
_bldg_fx_accum: dict = {}

def _building_ambient(fx: list, pos, bd, t) -> None:
    """Factories smoke, refineries glow, bases blink – all on cheap timers."""
    key = id(bd)
    acc = _bldg_fx_accum.get(key, 0) + 0.017
    fire = False
    if bd.kind == 'factory' and acc >= 0.6:
        acc = 0.0
        fire = True
        fx.append({
            'kind': 'smoke', 'x': pos.x + 10, 'y': pos.y + 4,
            'vx': random.uniform(-4, 4), 'vy': random.uniform(-18, -8),
            't': random.uniform(1.0, 2.0), 'mt': 2.0,
            'color': P['smoke'], 'sz': random.uniform(3, 6),
        })
    elif bd.kind == 'refinery' and acc >= 0.9:
        acc = 0.0
        fire = True
        fx.append({
            'kind': 'particle',
            'x': pos.x + bd.w - 18, 'y': pos.y + bd.h // 2,
            'vx': 0, 'vy': -10,
            't': 0.4, 'mt': 0.4,
            'color': P['tib_hi'], 'sz': 3.0,
        })
    elif bd.kind == 'base' and acc >= 1.5:
        acc = 0.0
        fire = True
        # Radar ping
        fx.append({
            'kind': 'shockwave',
            'x': pos.x + bd.w // 2, 'y': pos.y + bd.h // 2,
            'max_r': 30, 't': 0.8, 'mt': 0.8,
            'color': P['select'] if t % 6 < 3 else P['player'],
        })
    if not fire:
        _bldg_fx_accum[key] = acc
    else:
        _bldg_fx_accum[key] = 0.0


# ── FX particle rendering ────────────────────────────────────────────────────
def draw_fx(scr, world_fx, cam, small_font, zoom=1.0):
    """Render all active FX particles. Called from RenderSys.update()."""
    for item in world_fx:
        # Line-based effects use midpoint for culling
        if 'x' in item:
            sx = int((item['x'] - cam[0]) * zoom)
            sy = int((item['y'] - cam[1]) * zoom)
        else:
            sx = int(((item.get('sx', 0) + item.get('ex', 0)) / 2 - cam[0]) * zoom)
            sy = int(((item.get('sy', 0) + item.get('ey', 0)) / 2 - cam[1]) * zoom)

        from config import W, H, HUD_H
        sw = W
        sh = H - HUD_H
        if not (-60 < sx < sw + 60 and -60 < sy < sh + 60):
            continue

        if item['kind'] == 'flash':
            a = int(255 * item['t'] / 0.18)
            a = min(255, a)
            pygame.draw.circle(scr, (*P['fire_hi'][:3], min(255, a)),
                               (sx, sy), 10)
            _glow(scr, sx, sy, P['fire_hi'], 20, min(180, a))
            _glow(scr, sx, sy, P['nova'], 12, min(140, a))

        elif item['kind'] == 'shockwave':
            ratio = 1.0 - (item['t'] / item['mt'])
            r = max(1, int(ratio * item['max_r']))
            alpha = int(200 * (1.0 - ratio))
            c = item['color']
            if r > 1 and alpha > 0:
                sw = _get_surf(r * 2 + 6, r * 2 + 6)
                cx2, cy2 = r + 3, r + 3
                pygame.draw.circle(sw, (*c[:3], min(255, alpha)),
                                   (cx2, cy2), r, max(2, r // 6))
                ir = max(1, r - 3)
                pygame.draw.circle(sw, (*P['nova'][:3], min(255, alpha // 2)),
                                   (cx2, cy2), ir, 1)
                scr.blit(sw, (sx - r - 3, sy - r - 3),
                         special_flags=pygame.BLEND_ADD)

        elif item['kind'] == 'nova':
            ratio = item['t'] / item['mt']
            r = max(1, int(item['max_r'] * (1.0 - ratio * 0.3)))
            alpha = int(255 * ratio)
            if alpha > 0:
                _glow(scr, sx, sy, P['nova'], r, min(220, alpha))
                _glow(scr, sx, sy, P['fire_hi'], r // 2, min(180, alpha))

        elif item['kind'] == 'arc':
            ratio = item['t'] / item['mt']
            alpha = int(240 * ratio)
            aim = item['aim']
            length = item['len']
            segs = item['segs']
            c = item['color']
            pts = [(sx, sy)]
            for i in range(1, segs + 1):
                frac = i / segs
                bx = sx + math.cos(aim) * length * frac
                by = sy + math.sin(aim) * length * frac
                bx += random.uniform(-8, 8)
                by += random.uniform(-8, 8)
                pts.append((int(bx), int(by)))
            if len(pts) >= 2 and alpha > 10:
                for i in range(len(pts) - 1):
                    pygame.draw.line(scr, c, pts[i], pts[i + 1], 3)
                for i in range(len(pts) - 1):
                    pygame.draw.line(scr, P['elec_hi'],
                                     pts[i], pts[i + 1], 1)

        elif item['kind'] == 'hit_flash':
            ratio = item['t'] / item['mt']
            r = item['r']
            alpha = int(200 * ratio)
            if alpha > 0:
                hs = _get_surf(r * 2, r * 2)
                pygame.draw.circle(hs, (255, 255, 255, min(255, alpha)),
                                   (r, r), r)
                scr.blit(hs, (sx - r, sy - r),
                         special_flags=pygame.BLEND_ADD)

        elif item['kind'] == 'debris':
            ratio = item['t'] / item['mt']
            sz = max(1, int(item['sz'] * ratio))
            c = item['color']
            pygame.draw.rect(scr, c, (sx - sz, sy - sz, sz * 2, sz * 2))
            # tiny ember trail
            if sz >= 2:
                pygame.draw.circle(scr, P['bang'], (sx, sy + sz + 1), 1)

        elif item['kind'] == 'move_dust':
            ratio = item['t'] / item['mt']
            alpha = int(40 * ratio)
            sz = max(1, int(item['sz'] * (1.2 - ratio * 0.4)))
            if alpha > 2:
                ds2 = _get_surf(sz * 2, sz * 2)
                pygame.draw.circle(ds2, (140, 130, 100, alpha), (sz, sz), sz)
                scr.blit(ds2, (sx - sz, sy - sz),
                         special_flags=pygame.BLEND_ADD)

        elif item['kind'] == 'dmg_num':
            ratio = item['t'] / item['mt']
            alpha = int(255 * min(1.0, ratio * 2.0))
            if alpha > 10:
                val = item['val']
                # Big hits get brighter colour
                if val >= 60:
                    c = P['fire_hi']
                elif val >= 30:
                    c = P['bang']
                else:
                    c = (220, 220, 220)
                dtxt = small_font.render(str(val), True, c)
                dtxt.set_alpha(alpha)
                scr.blit(dtxt, (sx - dtxt.get_width() // 2,
                               sy - dtxt.get_height() // 2))

        elif item['kind'] in ('particle', 'smoke'):
            ratio = item['t'] / item['mt']
            alpha = int(220 * ratio)
            sz    = max(1, int(item['sz'] * ratio))
            c     = item['color']
            if item['kind'] == 'smoke':
                sc = _get_surf(sz * 2, sz * 2)
                pygame.draw.circle(sc, (*c, alpha), (sz, sz), sz)
                scr.blit(sc, (sx - sz, sy - sz),
                         special_flags=pygame.BLEND_ADD)
            else:
                pygame.draw.circle(scr, c, (sx, sy), sz)
                if sz >= 2:
                    _glow(scr, sx, sy, c, sz + 3, min(80, alpha))

        elif item['kind'] == 'click':
            ratio = 1.0 - (item['t'] / 0.5)
            r     = int(ratio * 22)
            a     = int(200 * (1 - ratio))
            if r > 0:
                cs = _get_surf(r * 2 + 4, r * 2 + 4)
                pygame.draw.circle(cs, (*P['select'][:3], a), (r + 2, r + 2), r, 2)
                scr.blit(cs, (sx - r - 2, sy - r - 2),
                         special_flags=pygame.BLEND_ADD)

        elif item['kind'] == 'tesla_bolt':
            ratio = item['t'] / item['mt']
            alpha = int(255 * ratio)
            sx1 = int((item['sx'] - cam[0]) * zoom)
            sy1 = int((item['sy'] - cam[1]) * zoom)
            ex1 = int((item['ex'] - cam[0]) * zoom)
            ey1 = int((item['ey'] - cam[1]) * zoom)
            segs = item['segs']
            jitter = item['jitter']
            # Build jagged lightning path
            pts = [(sx1, sy1)]
            for i in range(1, segs):
                frac = i / segs
                mx2 = sx1 + (ex1 - sx1) * frac + random.uniform(-jitter, jitter)
                my2 = sy1 + (ey1 - sy1) * frac + random.uniform(-jitter, jitter)
                pts.append((int(mx2), int(my2)))
            pts.append((ex1, ey1))
            if len(pts) >= 2 and alpha > 10:
                # Thick glow layer
                for i in range(len(pts) - 1):
                    pygame.draw.line(scr, P['tesla_bg'], pts[i], pts[i+1], 5)
                # Core bolt
                for i in range(len(pts) - 1):
                    pygame.draw.line(scr, P['tesla'], pts[i], pts[i+1], 3)
                # Bright inner core
                for i in range(len(pts) - 1):
                    pygame.draw.line(scr, P['tesla_hi'], pts[i], pts[i+1], 1)

        elif item['kind'] == 'laser_beam':
            ratio = item['t'] / item['mt']
            alpha = int(255 * ratio)
            sx1 = int((item['sx'] - cam[0]) * zoom)
            sy1 = int((item['sy'] - cam[1]) * zoom)
            ex1 = int((item['ex'] - cam[0]) * zoom)
            ey1 = int((item['ey'] - cam[1]) * zoom)
            from systems.rendering import _cfg
            team_id = item['team']
            lc = P['laser_r'] if team_id == _cfg.PLAYER else P['laser_g']
            if alpha > 10:
                # Wide glow via thick line on temp surface
                lw = abs(ex1 - sx1) + 20
                lh = abs(ey1 - sy1) + 20
                lox = min(sx1, ex1) - 10
                loy = min(sy1, ey1) - 10
                gs = _get_surf(lw, lh)
                pygame.draw.line(gs, (*lc[:3], min(255, alpha // 2)),
                                 (sx1 - lox, sy1 - loy), (ex1 - lox, ey1 - loy), 7)
                scr.blit(gs, (lox, loy), special_flags=pygame.BLEND_ADD)
                # Core beam
                pygame.draw.line(scr, lc, (sx1, sy1), (ex1, ey1), 3)
                # White-hot center
                pygame.draw.line(scr, (255, 255, 255),
                                 (sx1, sy1), (ex1, ey1), 1)
