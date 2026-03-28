# systems/rendering/buildings.py – building drawing functions
import math, random, pygame
from config import P
from systems.rendering import _cfg
from systems.rendering.helpers import _get_surf, _glow, _darker, _lighter, _OCT_OFFSETS

# ── Draw aliases ──
_rect = pygame.draw.rect
_line = pygame.draw.line
_circ = pygame.draw.circle
_elli = pygame.draw.ellipse
_arc  = pygame.draw.arc
_poly = pygame.draw.polygon
_lines = pygame.draw.lines
_ADD  = pygame.BLEND_ADD

# ── Micro-helpers ─────────────────────────────────────────────────────────────
def _shadow(surf, x, y, w, h, pad, alpha=38):
    sh = _get_surf(w + pad, h + pad)
    _elli(sh, (0, 0, 0, alpha), (0, 4, w + pad, h + pad - 4))
    surf.blit(sh, (x - pad // 2, y - 2))

def _foundation(surf, x, y, w, h, col=(55, 55, 50), pad=1, rad=2, border=None):
    _rect(surf, col, (x - pad, y - pad, w + pad*2, h + pad*2), 0, rad)
    if border:
        _rect(surf, border, (x - pad, y - pad, w + pad*2, h + pad*2), 1, rad)

def _bevel_tb(surf, x, y, w, h, hi, dk, dk_b=30, dk_r=0):
    _line(surf, hi, (x + 1, y), (x + w - 2, y), 2)
    _line(surf, _darker(dk, dk_b), (x + 1, y + h - 1), (x + w - 1, y + h - 1), 2)
    if dk_r:
        _line(surf, _darker(dk, dk_r), (x + w - 1, y + 1), (x + w - 1, y + h - 1), 1)

def _smoke_puffs(surf, sx, top, t, count=3, col=(110, 115, 110)):
    for i in range(count):
        sy = top - 6 - i * 7
        px = sx + int(math.sin(t * 1.2 + i * 1.8) * 4)
        r = 3 + i * 2; a = max(10, 60 - i * 20)
        ss = _get_surf(r * 2 + 4, r * 2 + 4)
        _circ(ss, (*col, a), (r + 2, r + 2), r)
        surf.blit(ss, (px - r - 2, sy - r - 2))

def _steam_puffs(surf, vx, y, t, i):
    for j in range(2):
        sy = y - 2 - j * 6 - i * 3
        sx = vx + int(math.sin(t * 1.5 + i * 2.0 + j * 1.3) * 3)
        r, a = 3 + j, max(10, 50 - j * 25)
        ss = _get_surf(r * 2 + 2, r * 2 + 2)
        _circ(ss, (160, 165, 160, a), (r + 1, r + 1), r)
        surf.blit(ss, (sx - r - 1, sy - r - 1))


# ── Building dispatcher ──────────────────────────────────────────────────────
_DRAW_MAP = {}  # populated after function defs

def _draw_building(surf, x, y, bd, team, hp_ratio, time, selected, uc_ratio=None):
    cx, cy = x + bd.w // 2, y + bd.h // 2
    c  = P['player'] if team == _cfg.PLAYER else P['enemy']
    dk = _darker(c, 60)
    if selected:
        _glow(surf, cx, cy, P['select'], max(bd.w, bd.h) // 2 + 12)

    fn = _DRAW_MAP.get(bd.kind)
    if fn:
        if bd.kind in ('base', 'factory', 'power_plant'):
            fn(surf, x, y, bd.w, bd.h, c, dk, time)
        elif bd.kind == 'turret':
            fn(surf, cx, cy, c, dk, time)
        else:
            fn(surf, x, y, bd.w, bd.h, c, dk)

    if uc_ratio is not None and uc_ratio < 1.0:
        ov = _get_surf(bd.w, bd.h); ov.fill((0, 0, 0, int(100 * (1 - uc_ratio))))
        surf.blit(ov, (x, y))
        pw = int(bd.w * uc_ratio)
        _rect(surf, (0, 0, 0), (x, y + bd.h + 2, bd.w, 5))
        _rect(surf, P['ui_hi'], (x, y + bd.h + 2, pw, 5))
        return
    _hp_bar(surf, cx, y - 8, bd.w, hp_ratio)


def _hp_bar(surf, cx, y, w, ratio):
    bw = max(24, w); bx = cx - bw // 2
    _rect(surf, (0, 0, 0), (bx, y, bw, 5))
    col = P['hp_hi'] if ratio > 0.6 else P['hp_mid'] if ratio > 0.3 else P['hp_lo']
    _rect(surf, col, (bx, y, int(bw * ratio), 5))
    _rect(surf, P['gray'], (bx, y, bw, 5), 1)


# ── Individual building renderers ─────────────────────────────────────────────

def _draw_base(surf, x, y, w, h, c, dk, t):
    cx, cy = x + w // 2, y + h // 2
    dk2, hi, hi2 = _darker(c, 30), _lighter(c, 40), _lighter(c, 70)

    _shadow(surf, x, y, w, h, 12, 40)
    _foundation(surf, x, y, w, h, (50, 50, 48), 2, 3, (65, 65, 60))

    # Outer armoured shell
    _rect(surf, dk, (x, y, w, h), 0, 2)
    _line(surf, hi, (x + 1, y), (x + w - 2, y), 2)
    _line(surf, hi, (x, y + 1), (x, y + h - 2), 1)
    _line(surf, _darker(dk, 30), (x + 1, y + h - 1), (x + w - 1, y + h - 1), 2)
    _line(surf, _darker(dk, 20), (x + w - 1, y + 1), (x + w - 1, y + h - 2), 1)

    # Armour panel lines
    m = 6
    _rect(surf, dk2, (x+m, y+m, w-m*2, h-m*2), 0, 2)
    _rect(surf, c, (x+m, y+m, w-m*2, h-m*2), 1, 2)
    dk15 = _darker(dk, 15)
    for py_ in range(y+m+12, y+h-m, 14):
        _line(surf, dk15, (x+m+2, py_), (x+w-m-2, py_), 1)
    for px_ in range(x+m+14, x+w-m, 16):
        _line(surf, dk15, (px_, y+m+2), (px_, y+h-m-2), 1)

    # Corner reinforcement plates
    for ox, oy in ((0, 0), (w-14, 0), (0, h-14), (w-14, h-14)):
        rx, ry = x+ox+2, y+oy+2
        _rect(surf, dk2, (rx, ry, 12, 12), 0, 2)
        _rect(surf, c, (rx, ry, 12, 12), 1, 2)
        for dx, dy in ((3,3),(9,3),(3,9),(9,9)):
            _circ(surf, hi, (rx+dx, ry+dy), 1)

    # Central command dome
    _elli(surf, _darker(dk, 20), (cx-18, cy-16, 36, 32))
    _elli(surf, dk2, (cx-16, cy-14, 32, 28))
    _elli(surf, c, (cx-16, cy-14, 32, 28), 2)
    _elli(surf, hi, (cx-10, cy-12, 16, 10))
    _elli(surf, hi2, (cx-6, cy-11, 8, 5))

    # Radar dish
    ra = t * 1.5
    rdx, rdy = int(cx + math.cos(ra)*10), int(cy - 6 + math.sin(ra)*5)
    _line(surf, hi, (cx, cy-6), (rdx, rdy), 2)
    _circ(surf, hi2, (rdx, rdy), 3); _circ(surf, c, (rdx, rdy), 3, 1)

    # Antenna towers
    ax_, ay_ = x + 14, y + 6
    _line(surf, (140,140,140), (ax_, ay_+20), (ax_, ay_), 2)
    _line(surf, (160,160,160), (ax_, ay_), (ax_, ay_-8), 1)
    blink = int(t * 2.5) % 2
    _circ(surf, (255,60,30) if blink else (180,30,15), (ax_, ay_-8), 2)
    if blink: _glow(surf, ax_, ay_-8, (255,60,30), 6, 60)

    ax2 = x + w - 14
    _line(surf, (140,140,140), (ax2, ay_+16), (ax2, ay_), 2)
    _line(surf, (160,160,160), (ax2, ay_), (ax2, ay_-5), 1)
    _circ(surf, P['fire_hi'] if (int(t*2.5)+1)%2 else dk2, (ax2, ay_-5), 2)

    # Corner defence turrets
    for ox, oy in ((6,6),(w-6,6),(6,h-6),(w-6,h-6)):
        tx_, ty_ = x+ox, y+oy
        _circ(surf, _darker(dk,20), (tx_,ty_), 7)
        _circ(surf, dk2, (tx_,ty_), 6); _circ(surf, c, (tx_,ty_), 6, 1)
        bd_ = math.atan2(ty_-cy, tx_-cx)
        _line(surf, (160,160,160), (tx_,ty_), (int(tx_+math.cos(bd_)*8), int(ty_+math.sin(bd_)*8)), 2)

    _glow(surf, cx, cy, c, 20, int(30 + 20*math.sin(t*2.0)))


def _draw_barracks(surf, x, y, w, h, c, dk):
    cx, cy = x + w//2, y + h//2
    dk2, hi = _darker(c, 30), _lighter(c, 35)

    _shadow(surf, x, y, w, h, 8, 35)
    _foundation(surf, x, y, w, h, (55,55,50), 1, 2)

    _rect(surf, dk, (x, y, w, h), 0, 1)
    _bevel_tb(surf, x, y, w, h, hi, dk, 25)

    # Roof
    rh = 10
    _rect(surf, _darker(dk,20), (x+2, y+2, w-4, rh), 0, 1)
    _line(surf, hi, (x+3, y+2), (x+w-3, y+2), 1)
    _line(surf, dk2, (x+3, y+rh+1), (x+w-3, y+rh+1), 1)
    dk10 = _darker(dk, 10)
    for rx in range(x+6, x+w-4, 5):
        _line(surf, dk10, (rx, y+3), (rx, y+rh), 1)

    # Wall panels
    py_ = y + rh + 4; ph = h - rh - 24
    _rect(surf, dk2, (x+4, py_, w-8, ph))
    _rect(surf, c, (x+4, py_, w-8, ph), 1)

    # Windows
    ww, wh, wy = 8, 7, py_ + 3
    for wx_ in (x+7, x+w-15):
        _rect(surf, (10,10,10), (wx_-1, wy-1, ww+2, wh+2))
        _rect(surf, _lighter(c,80), (wx_, wy, ww, wh))
        _line(surf, dk, (wx_+ww//2, wy), (wx_+ww//2, wy+wh), 1)
        _line(surf, dk, (wx_, wy+wh//2), (wx_+ww, wy+wh//2), 1)
        _rect(surf, c, (wx_, wy, ww, wh), 1)
        gs = _get_surf(ww+4, wh+4)
        _rect(gs, (*_lighter(c,100)[:3], 30), (0, 0, ww+4, wh+4))
        surf.blit(gs, (wx_-2, wy-2), special_flags=_ADD)

    # Door
    dw, dh_ = 14, 18
    dx_, dy_ = x + w//2 - dw//2, y + h - dh_
    _rect(surf, (3,3,3), (dx_-1, dy_-1, dw+2, dh_+1))
    _rect(surf, (25,25,25), (dx_, dy_, dw, dh_))
    _line(surf, (35,35,35), (dx_+dw//2, dy_), (dx_+dw//2, dy_+dh_), 1)
    _rect(surf, c, (dx_-1, dy_-1, dw+2, dh_+1), 1)
    _circ(surf, (140,140,140), (dx_+dw//2+3, dy_+dh_//2), 1)
    _rect(surf, (70,70,65), (dx_-2, y+h-2, dw+4, 2))

    # Sandbags
    for si, sy_ in enumerate(range(y+h-6, y+h-2, 3)):
        sw_ = 10 - si*2; sbx = x - 3 + si
        _elli(surf, (100,90,65), (sbx, sy_, sw_, 4))
        _elli(surf, (80,70,50), (sbx, sy_, sw_, 4), 1)

    # Insignia
    _circ(surf, c, (cx, py_+ph//2+1), 4, 1)
    _circ(surf, hi, (cx, py_+ph//2+1), 2)
    _rect(surf, c, (x, y, w, h), 2, 1)


def _draw_factory(surf, x, y, w, h, c, dk, t):
    cx, cy = x + w//2, y + h//2
    dk2, hi = _darker(c, 30), _lighter(c, 35)

    _shadow(surf, x, y, w, h, 10, 38)
    _foundation(surf, x, y, w, h, (55,55,50), 2, 2, (65,65,58))

    _rect(surf, dk, (x, y, w, h), 0, 2)
    _bevel_tb(surf, x, y, w, h, hi, dk, 30, 20)

    dk12 = _darker(dk, 12)
    for py_ in (y+14, y+h//2, y+h-14):
        _line(surf, dk12, (x+3, py_), (x+w-3, py_), 1)

    # Chimney
    sx, sw = x+5, 10; stop = y - 10
    _rect(surf, (60,60,55), (sx, stop, sw, y-stop+12))
    _rect(surf, (75,75,70), (sx, stop, sw, y-stop+12), 1)
    for by_ in (stop+3, stop+8):
        _line(surf, (90,90,85), (sx, by_), (sx+sw, by_), 1)
    _rect(surf, (80,80,75), (sx-1, stop-2, sw+2, 3))
    _smoke_puffs(surf, sx + sw//2, stop, t)

    # Assembly area
    ax_, ay_ = x+18, y+6; aw, ah_ = w-24, h-32
    _rect(surf, _darker(dk,15), (ax_, ay_, aw, ah_), 0, 1)
    _rect(surf, dk2, (ax_, ay_, aw, ah_), 1, 1)
    belt_off = int(t*40) % 8
    dk8 = _darker(dk, 8)
    for by_ in range(ay_+4+belt_off, ay_+ah_-2, 8):
        _line(surf, dk8, (ax_+3, by_), (ax_+aw-3, by_), 1)

    # Crane
    ry = ay_ + 2
    _line(surf, (100,100,95), (ax_+2, ry), (ax_+aw-2, ry), 2)
    crx = int(ax_ + 6 + (aw-12) * (0.5 + 0.5*math.sin(t*0.4)))
    _rect(surf, (120,120,115), (crx-4, ry-1, 8, 4))
    _line(surf, (90,90,90), (crx, ry+3), (crx, ry+ah_//2), 1)
    _circ(surf, (140,140,135), (crx, ry+ah_//2), 2, 1)

    # Vehicle bay door
    dw, dh = 28, 22
    dx_, dy_ = x+w//2-dw//2, y+h-dh
    _rect(surf, (8,8,8), (dx_-1, dy_-1, dw+2, dh+2))
    dp = math.sin(t*0.5)*0.5 + 0.5
    vh = int(dh * (1.0 - dp*0.6))
    if vh > 0:
        _rect(surf, (40,40,38), (dx_, dy_, dw, vh))
        for seg_y in range(dy_+3, dy_+vh-1, 4):
            _line(surf, (55,55,50), (dx_+1, seg_y), (dx_+dw-1, seg_y), 1)
    if vh < dh:
        _rect(surf, (5,5,5), (dx_, dy_+vh, dw, dh-vh))
    _rect(surf, c, (dx_-1, dy_-1, dw+2, dh+2), 1)
    for si in range(0, dh, 6):
        sc = (200,180,0) if (si//3)%2==0 else (30,30,30)
        h_ = min(3, dh-si)
        _rect(surf, sc, (dx_-3, dy_+si, 2, h_))
        _rect(surf, sc, (dx_+dw+1, dy_+si, 2, h_))

    lc = (0,200,60) if dp > 0.3 else (200,60,0)
    _circ(surf, lc, (dx_+dw+5, dy_-3), 2)
    if dp > 0.3: _glow(surf, dx_+dw+5, dy_-3, lc, 5, 40)
    _rect(surf, c, (x, y, w, h), 2, 2)


def _draw_refinery(surf, x, y, w, h, c, dk):
    cx, cy = x + w//2, y + h//2
    dk2, hi = _darker(c, 30), _lighter(c, 35)

    _shadow(surf, x, y, w, h, 8, 35)
    _foundation(surf, x, y, w, h, (52,52,48), 1, 3)

    _rect(surf, dk, (x, y, w, h), 0, 4)
    _line(surf, hi, (x+2, y), (x+w-3, y), 2)
    _line(surf, _darker(dk,25), (x+2, y+h-1), (x+w-3, y+h-1), 2)

    # Processing module
    px_, py_ = x+4, y+4; pw, ph = w//2-4, h-8
    _rect(surf, dk2, (px_, py_, pw, ph), 0, 2)
    _rect(surf, c, (px_, py_, pw, ph), 1, 2)
    dk15 = _darker(dk, 15)
    for gy in range(py_+4, py_+ph-2, 5):
        _line(surf, dk15, (px_+3, gy), (px_+pw-3, gy), 1)
    hy = py_ + ph - 12
    _rect(surf, (20,80,30), (px_+2, hy, pw-4, 10), 0, 1)
    _rect(surf, P['tib'], (px_+2, hy, pw-4, 10), 1, 1)
    gs = _get_surf(pw, 14)
    _rect(gs, (*P['tib'][:3], 40), (0, 0, pw, 14))
    surf.blit(gs, (px_, hy-2), special_flags=_ADD)

    # Storage tank
    tcx, tcy, tr = x+w-18, cy, 15
    _elli(surf, _darker(dk,30), (tcx-tr-1, tcy-tr-1, tr*2+2, tr*2+2))
    _circ(surf, _darker(c,40), (tcx, tcy), tr)
    _circ(surf, dk2, (tcx, tcy), tr-2)
    _arc(surf, hi, (tcx-tr+2, tcy-tr+2, tr*2-4, tr*2-4), math.radians(200), math.radians(340), 2)
    _circ(surf, P['tib'], (tcx, tcy), tr-5)
    _circ(surf, P['tib_hi'], (tcx, tcy), tr-9)
    _circ(surf, _lighter(P['tib_hi'],40), (tcx-3, tcy-4), 3)
    _circ(surf, c, (tcx, tcy), tr, 2)
    for mi in range(-tr+4, tr-3, 5):
        _line(surf, c, (tcx+tr-2, tcy+mi), (tcx+tr+1, tcy+mi), 1)

    # Pipes
    py1, py2 = cy-5, cy+5
    psx, pex = px_+pw, tcx-tr
    for py in (py1, py2):
        _line(surf, (90,90,85), (psx, py), (pex, py), 3)
        _line(surf, (110,110,105), (psx, py-1), (pex, py-1), 1)
    for jx in (psx+2, pex-2):
        for py in (py1, py2):
            _circ(surf, (100,100,95), (jx, py), 3)
            _circ(surf, (75,75,70), (jx, py), 3, 1)
    vx = (psx + pex) // 2
    _circ(surf, (120,40,40), (vx, py1), 3); _circ(surf, (150,60,60), (vx, py1), 3, 1)

    # Unloading bay
    bx_, by_ = x+8, y+h-6
    _rect(surf, (40,40,38), (bx_, by_, 20, 6), 0, 1)
    _rect(surf, c, (bx_, by_, 20, 6), 1, 1)
    for lx in (bx_+3, bx_+15):
        _rect(surf, (200,180,0), (lx, by_+1, 3, 4))
    _rect(surf, c, (x, y, w, h), 2, 4)


def _draw_turret(surf, cx, cy, c, dk, t):
    dk2, hi, hi2 = _darker(c, 30), _lighter(c, 35), _lighter(c, 60)

    sh = _get_surf(40, 20)
    _elli(sh, (0,0,0,40), (0, 6, 40, 16))
    surf.blit(sh, (cx-20, cy-6))

    # Octagonal base
    pts = [(cx+_OCT_OFFSETS[i][0], cy+_OCT_OFFSETS[i][1]) for i in range(8)]
    _poly(surf, (55,55,50), pts); _poly(surf, (70,70,65), pts, 2)

    # Platform
    _rect(surf, dk, (cx-14, cy-14, 28, 28), 0, 3)
    _line(surf, hi, (cx-13, cy-14), (cx+13, cy-14), 2)
    _line(surf, _darker(dk,20), (cx-13, cy+13), (cx+13, cy+13), 2)
    _rect(surf, c, (cx-14, cy-14, 28, 28), 2, 3)

    # Ring + dome
    _circ(surf, _darker(dk,15), (cx,cy), 12)
    _circ(surf, dk2, (cx,cy), 11); _circ(surf, c, (cx,cy), 11, 2)
    _circ(surf, dk2, (cx,cy), 9); _circ(surf, c, (cx,cy), 8)
    _circ(surf, hi, (cx-2, cy-3), 4); _circ(surf, hi2, (cx-2, cy-3), 2)

    # Barrel
    a = t * 0.8; bl = 20
    bx, by = int(cx+math.cos(a)*bl), int(cy+math.sin(a)*bl)
    _line(surf, (30,30,30), (cx, cy+2), (int(cx+math.cos(a)*(bl+2)), int(cy+math.sin(a)*(bl+2))+2), 4)
    for w_, c_ in ((5,(120,120,115)),(3,(160,160,155)),(1,(180,180,175))):
        _line(surf, c_, (cx,cy), (bx,by), w_)
    # Muzzle brake
    mx, my = int(cx+math.cos(a)*(bl-2)), int(cy+math.sin(a)*(bl-2))
    perp = a + math.pi/2
    for s in (-1, 1):
        _line(surf, (140,140,135), (mx,my), (int(mx+math.cos(perp)*4*s), int(my+math.sin(perp)*4*s)), 2)

    for ox, oy in ((-11,-11),(11,-11),(-11,11),(11,11)):
        _circ(surf, hi, (cx+ox, cy+oy), 1)


def _draw_wall(surf, x, y, w, h, c, dk):
    S, SD, SH, SM = (95,95,88), (58,58,54), (125,123,116), (78,78,72)

    sh = _get_surf(w+4, h+6)
    _rect(sh, (0,0,0,45), (2, 3, w+2, h+2))
    surf.blit(sh, (x-1, y))
    _rect(surf, SD, (x, y, w, h))

    bh = h // 4
    for ri in range(4):
        ry = y + ri * bh
        off = (w//3) if ri % 2 else 0
        for bx_ in range(-off, w, w//2):
            rbx, rex = x + max(0, bx_), x + min(w, bx_ + w//2)
            if rex <= rbx: continue
            shade = ((ri*7 + bx_*3) % 12) - 6
            bc = tuple(max(0, min(255, v)) for v in (S[0]+shade, S[1]+shade, S[2]+shade-2))
            _rect(surf, bc, (rbx+1, ry+1, rex-rbx-1, bh-1))

    for ri in range(1, 4):
        _line(surf, SD, (x+1, y+ri*bh), (x+w-1, y+ri*bh), 1)
    for ri in range(4):
        ry = y + ri*bh; off = (w//3) if ri%2 else 0
        for bx_ in range(-off, w, w//2):
            vx = x + bx_ + w//2
            if x < vx < x+w:
                _line(surf, SD, (vx, ry+1), (vx, ry+bh-1), 1)

    _line(surf, SH, (x, y), (x+w-1, y), 2)
    _line(surf, SM, (x, y), (x, y+h-1), 1)
    _line(surf, _darker(SD,15), (x, y+h-1), (x+w-1, y+h-1), 1)
    _line(surf, _darker(SD,10), (x+w-1, y), (x+w-1, y+h-1), 1)
    _line(surf, _darker(SD,8), (x+5, y+4), (x+w-8, y+h-5), 1)
    _rect(surf, SD, (x, y, w, h), 1)


def _draw_power_plant(surf, x, y, w, h, c, dk, t):
    cx, cy = x + w//2, y + h//2
    dk2, hi, hi2 = _darker(c, 30), _lighter(c, 35), _lighter(c, 60)

    _shadow(surf, x, y, w, h, 10, 38)
    _foundation(surf, x, y, w, h, (52,52,48), 1, 2)

    _rect(surf, dk, (x, y, w, h), 0, 2)
    _line(surf, hi, (x+1, y), (x+w-2, y), 2)
    _line(surf, _darker(dk,25), (x+1, y+h-1), (x+w-2, y+h-1), 2)
    _line(surf, hi, (x, y+1), (x, y+h-2), 1)
    _line(surf, _darker(dk,15), (x+w-1, y+1), (x+w-1, y+h-2), 1)

    dk10 = _darker(dk, 10)
    for py_ in range(y+12, y+h-6, 14):
        _line(surf, dk10, (x+3, py_), (x+w-3, py_), 1)

    # Cooling tower
    tcx, tcy, tr = x+16, cy+2, 13
    _elli(surf, _darker(dk,25), (tcx-tr-1, tcy-tr-1, tr*2+2, tr*2+2))
    _circ(surf, _darker(c,45), (tcx, tcy), tr)
    _circ(surf, _darker(c,25), (tcx, tcy), tr-2)
    _arc(surf, hi, (tcx-tr+2, tcy-tr+2, tr*2-4, tr*2-4), math.radians(200), math.radians(330), 2)
    _circ(surf, c, (tcx, tcy), tr, 2)
    _circ(surf, _darker(dk,40), (tcx, tcy), tr-5)
    for br in (tr-3, tr-7):
        _circ(surf, dk2, (tcx, tcy), br, 1)

    # Steam vents
    for i, vx in enumerate((tcx-5, tcx+3)):
        _steam_puffs(surf, vx, y, t, i)
        _circ(surf, (140,140,135), (vx, y+3), 4)
        _circ(surf, (100,100,95), (vx, y+3), 4, 1)

    # Reactor core
    ccx, ccy = cx+12, cy
    _rect(surf, _darker(dk,15), (ccx-10, ccy-12, 20, 24), 0, 3)
    _rect(surf, c, (ccx-10, ccy-12, 20, 24), 1, 3)

    pulse = math.sin(t * 3.0)
    pr = int(6 + 2*pulse); ca = int(120 + 80*pulse)
    _glow(surf, ccx, ccy, (255,255,100), 14, int(40+30*pulse))
    cs = _get_surf(pr*2+8, pr*2+8)
    _circ(cs, (255,255,80,ca), (pr+4, pr+4), pr+2)
    _circ(cs, (255,255,180, min(255,ca+40)), (pr+4, pr+4), pr)
    surf.blit(cs, (ccx-pr-4, ccy-pr-4), special_flags=_ADD)
    _circ(surf, (255,255,200), (ccx, ccy), 3)

    # Bolt symbol
    bx_, by_ = ccx-2, ccy-9
    bp = [(bx_+2,by_),(bx_-1,by_+6),(bx_+3,by_+6),(bx_,by_+13)]
    _lines(surf, (255,230,0), False, bp, 2)
    _lines(surf, (255,255,150), False, bp, 1)

    # Conduit pipe
    pipe_y = cy + 8
    _line(surf, (90,90,85), (tcx+tr, pipe_y), (ccx-10, pipe_y), 3)
    _line(surf, (110,110,105), (tcx+tr, pipe_y-1), (ccx-10, pipe_y-1), 1)

    # Energy arcs
    ap = math.sin(t * 5.0)
    if ap > 0.7:
        aa_ = int((ap - 0.7) / 0.3 * 120)
        for _ in range(2):
            a_ = random.uniform(0, math.tau); r_ = random.uniform(8, 16)
            ex, ey = int(ccx+math.cos(a_)*r_), int(ccy+math.sin(a_)*r_)
            as_ = _get_surf(4, 4)
            _line(as_, (200,240,255,aa_), (0,0), (3,3), 1)
            surf.blit(as_, (min(ex,ccx)-1, min(ey,ccy)-1), special_flags=_ADD)
            _line(surf, (180,220,255), (ccx,ccy), (ex,ey), 1)

    for i, lx in enumerate((x+4, x+10)):
        _circ(surf, (0,200,60) if (int(t*1.5)+i)%3!=0 else (200,60,0), (lx, y+h-5), 2)
    _rect(surf, c, (x, y, w, h), 2, 2)


# ── Populate dispatch map ─────────────────────────────────────────────────────
_DRAW_MAP = {
    'base': _draw_base, 'barracks': _draw_barracks, 'factory': _draw_factory,
    'refinery': _draw_refinery, 'turret': _draw_turret, 'wall': _draw_wall,
    'power_plant': _draw_power_plant,
}
