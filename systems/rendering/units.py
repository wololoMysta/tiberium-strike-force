# systems/rendering/units.py – unit drawing functions
import math, random, pygame
from config import P
from systems.rendering import _cfg
from systems.rendering.helpers import (
    _get_surf, _glow, _rot_rect, _darker, _lighter,
)


# ── Unit drawing ──────────────────────────────────────────────────────────────
def _draw_infantry(surf, x, y, team, facing, selected, pulse):
    c   = P['player'] if team == _cfg.PLAYER else P['enemy']
    dk  = _darker(c, 50)
    # Idle bob
    bob = math.sin(pulse * 3.5) * 1.2
    y2 = int(y + bob)
    # Shadow (alpha-blended)
    sh = _get_surf(20, 10)
    pygame.draw.ellipse(sh, (0, 0, 0, 55), (0, 0, 20, 10))
    surf.blit(sh, (x - 10, y + 3))
    if selected:
        _glow(surf, x, y2, P['select'], 18, int(80 + 40 * math.sin(pulse * 6)))
        pygame.draw.circle(surf, P['select'], (x, y2), 12, 2)
    # Body
    pygame.draw.circle(surf, dk, (x, y2), 9)
    pygame.draw.circle(surf, c,  (x, y2), 8)
    # Head direction
    hx = int(x + math.cos(facing) * 4)
    hy = int(y2 + math.sin(facing) * 4)
    pygame.draw.circle(surf, _lighter(c, 30), (hx, hy), 4)
    # Weapon
    gx = int(x + math.cos(facing) * 13)
    gy = int(y2 + math.sin(facing) * 13)
    pygame.draw.line(surf, (160, 160, 160), (hx, hy), (gx, gy), 2)


def _draw_buggy(surf, x, y, team, facing, selected, pulse):
    c  = P['player'] if team == _cfg.PLAYER else P['enemy']
    dk = _darker(c, 60)
    # Shadow (alpha)
    sh = _get_surf(30, 12)
    pygame.draw.ellipse(sh, (0, 0, 0, 50), (0, 0, 30, 12))
    surf.blit(sh, (x - 15, y + 6))
    if selected:
        _glow(surf, x, y, P['select'], 22, int(80 + 40 * math.sin(pulse * 6)))
        pygame.draw.circle(surf, P['select'], (x, y), 16, 2)
    hull = _rot_rect(x, y, 24, 14, facing)
    pygame.draw.polygon(surf, dk,  hull)
    pygame.draw.polygon(surf, c,   hull, 1)
    # Wheels
    for sign in (-1, 1):
        wx = int(x + math.cos(facing + math.pi / 2) * 8 * sign)
        wy = int(y + math.sin(facing + math.pi / 2) * 8 * sign)
        pygame.draw.circle(surf, (40, 40, 40), (wx, wy), 5)
        pygame.draw.circle(surf, (80, 80, 80), (wx, wy), 5, 1)
    # Gun
    gx = int(x + math.cos(facing) * 18)
    gy = int(y + math.sin(facing) * 18)
    pygame.draw.line(surf, (180, 180, 180), (x, y), (gx, gy), 3)


def _draw_tank(surf, x, y, team, facing, turret, selected, pulse):
    c   = P['player'] if team == _cfg.PLAYER else P['enemy']
    dk  = _darker(c, 70)
    dk2 = _darker(c, 40)
    # Shadow (alpha)
    sh = _get_surf(38, 14)
    pygame.draw.ellipse(sh, (0, 0, 0, 55), (0, 0, 38, 14))
    surf.blit(sh, (x - 19, y + 8))
    if selected:
        _glow(surf, x, y, P['select'], 28, int(80 + 40 * math.sin(pulse * 6)))
        pygame.draw.circle(surf, P['select'], (x, y), 20, 2)
    # Treads
    for sign in (-1, 1):
        ox = math.cos(facing + math.pi / 2) * 12 * sign
        oy = math.sin(facing + math.pi / 2) * 12 * sign
        tread = _rot_rect(x + ox, y + oy, 28, 8, facing)
        pygame.draw.polygon(surf, (35, 35, 35),  tread)
        pygame.draw.polygon(surf, (60, 60, 60),  tread, 1)
    # Hull
    hull = _rot_rect(x, y, 26, 18, facing)
    pygame.draw.polygon(surf, dk,  hull)
    pygame.draw.polygon(surf, dk2, hull, 1)
    # Turret ring
    pygame.draw.circle(surf, dk2, (x, y), 10)
    pygame.draw.circle(surf, c,   (x, y), 9)
    # Barrel
    bx = int(x + math.cos(turret) * 20)
    by = int(y + math.sin(turret) * 20)
    pygame.draw.line(surf, (180, 180, 180), (x, y), (bx, by), 4)
    pygame.draw.line(surf, (220, 220, 220), (x, y), (bx, by), 2)


def _draw_harvester(surf, x, y, team, facing, selected, pulse):
    c  = P['player'] if team == _cfg.PLAYER else P['enemy']
    dk = _darker(c, 50)
    # Shadow (alpha)
    sh = _get_surf(36, 14)
    pygame.draw.ellipse(sh, (0, 0, 0, 50), (0, 0, 36, 14))
    surf.blit(sh, (x - 18, y + 7))
    if selected:
        _glow(surf, x, y, P['select'], 25, int(80 + 40 * math.sin(pulse * 6)))
        pygame.draw.circle(surf, P['select'], (x, y), 18, 2)
    hull = _rot_rect(x, y, 28, 18, facing)
    pygame.draw.polygon(surf, dk, hull)
    pygame.draw.polygon(surf, c,  hull, 1)
    # Scoop at front
    fx = int(x + math.cos(facing) * 16)
    fy = int(y + math.sin(facing) * 16)
    pygame.draw.circle(surf, (80, 200, 80), (fx, fy), 6)
    pygame.draw.circle(surf, P['tib_hi'],   (fx, fy), 4)


# ── MCV (Mobile Construction Vehicle) ────────────────────────────────────────
def _draw_mcv(surf, x, y, team, facing, selected, pulse):
    c  = P['player'] if team == _cfg.PLAYER else P['enemy']
    dk = _darker(c, 50)
    lt = _lighter(c, 40)
    # Shadow
    sh = _get_surf(48, 16)
    pygame.draw.ellipse(sh, (0, 0, 0, 55), (0, 0, 48, 16))
    surf.blit(sh, (x - 24, y + 10))
    if selected:
        _glow(surf, x, y, P['select'], 30, int(80 + 40 * math.sin(pulse * 6)))
        pygame.draw.circle(surf, P['select'], (x, y), 24, 2)
    # Treads
    for sign in (-1, 1):
        ox = math.cos(facing + math.pi / 2) * 14 * sign
        oy = math.sin(facing + math.pi / 2) * 14 * sign
        tread = _rot_rect(x + ox, y + oy, 34, 10, facing)
        pygame.draw.polygon(surf, (35, 35, 35), tread)
        pygame.draw.polygon(surf, (60, 60, 60), tread, 1)
    # Large hull
    hull = _rot_rect(x, y, 32, 24, facing)
    pygame.draw.polygon(surf, dk, hull)
    pygame.draw.polygon(surf, lt, hull, 1)
    # Crane/arm on top
    pygame.draw.circle(surf, _darker(c, 30), (x, y), 10)
    pygame.draw.circle(surf, c, (x, y), 8)
    ax = int(x + math.cos(facing) * 14)
    ay = int(y + math.sin(facing) * 14)
    pygame.draw.line(surf, (180, 180, 180), (x, y), (ax, ay), 3)
    pygame.draw.circle(surf, (200, 200, 100), (ax, ay), 4)
    pygame.draw.circle(surf, (255, 220, 60), (ax, ay), 2)
    # Double-click deploy hint when selected
    if selected:
        # Two small overlapping circles to indicate double-click
        pygame.draw.circle(surf, P['ui_hi'], (x - 4, y - 28), 5, 1)
        pygame.draw.circle(surf, P['ui_hi'], (x + 4, y - 28), 5, 1)


# ── Rocket Tank ───────────────────────────────────────────────────────────────
def _draw_rocket_tank(surf, x, y, team, facing, turret, selected, pulse):
    c   = P['player'] if team == _cfg.PLAYER else P['enemy']
    dk  = _darker(c, 70)
    dk2 = _darker(c, 40)
    # Shadow
    sh = _get_surf(40, 14)
    pygame.draw.ellipse(sh, (0, 0, 0, 55), (0, 0, 40, 14))
    surf.blit(sh, (x - 20, y + 8))
    if selected:
        _glow(surf, x, y, P['select'], 28, int(80 + 40 * math.sin(pulse * 6)))
        pygame.draw.circle(surf, P['select'], (x, y), 20, 2)
    # Treads
    for sign in (-1, 1):
        ox = math.cos(facing + math.pi / 2) * 12 * sign
        oy = math.sin(facing + math.pi / 2) * 12 * sign
        tread = _rot_rect(x + ox, y + oy, 28, 8, facing)
        pygame.draw.polygon(surf, (35, 35, 35), tread)
        pygame.draw.polygon(surf, (60, 60, 60), tread, 1)
    # Hull
    hull = _rot_rect(x, y, 26, 20, facing)
    pygame.draw.polygon(surf, dk, hull)
    pygame.draw.polygon(surf, dk2, hull, 1)
    # Rocket launcher pod (twin tubes)
    pygame.draw.circle(surf, dk2, (x, y), 10)
    pygame.draw.circle(surf, c, (x, y), 8)
    for sign in (-1, 1):
        bx = x + math.cos(turret) * 18 + math.cos(turret + math.pi/2) * 3 * sign
        by = y + math.sin(turret) * 18 + math.sin(turret + math.pi/2) * 3 * sign
        pygame.draw.line(surf, (120, 120, 120), (x, y), (int(bx), int(by)), 3)
    # Orange tip marking
    tx = int(x + math.cos(turret) * 19)
    ty = int(y + math.sin(turret) * 19)
    pygame.draw.circle(surf, P['rocket'], (tx, ty), 3)


# ── Tesla Tank ────────────────────────────────────────────────────────────────
def _draw_tesla_tank(surf, x, y, team, facing, turret, selected, pulse):
    c   = P['player'] if team == _cfg.PLAYER else P['enemy']
    dk  = _darker(c, 70)
    dk2 = _darker(c, 40)
    # Shadow
    sh = _get_surf(38, 14)
    pygame.draw.ellipse(sh, (0, 0, 0, 55), (0, 0, 38, 14))
    surf.blit(sh, (x - 19, y + 8))
    if selected:
        _glow(surf, x, y, P['select'], 28, int(80 + 40 * math.sin(pulse * 6)))
        pygame.draw.circle(surf, P['select'], (x, y), 20, 2)
    # Treads
    for sign in (-1, 1):
        ox = math.cos(facing + math.pi / 2) * 12 * sign
        oy = math.sin(facing + math.pi / 2) * 12 * sign
        tread = _rot_rect(x + ox, y + oy, 28, 8, facing)
        pygame.draw.polygon(surf, (35, 35, 35), tread)
        pygame.draw.polygon(surf, (60, 60, 60), tread, 1)
    # Hull
    hull = _rot_rect(x, y, 26, 18, facing)
    pygame.draw.polygon(surf, dk, hull)
    pygame.draw.polygon(surf, dk2, hull, 1)
    # Tesla coil dome
    pygame.draw.circle(surf, dk2, (x, y), 11)
    pygame.draw.circle(surf, P['tesla'], (x, y), 9)
    # Crackling arc antenna
    bx = int(x + math.cos(turret) * 16)
    by = int(y + math.sin(turret) * 16)
    pygame.draw.line(surf, (180, 200, 240), (x, y), (bx, by), 4)
    # Spark at tip (animated)
    spark_a = int(120 + 80 * math.sin(pulse * 12))
    ss = _get_surf(12, 12)
    pygame.draw.circle(ss, (*P['tesla_hi'][:3], spark_a), (6, 6), 5)
    surf.blit(ss, (bx - 6, by - 6), special_flags=pygame.BLEND_ADD)
    # Ambient mini-arcs around the dome
    for _ in range(2):
        aa = random.uniform(0, math.tau)
        ar = random.uniform(8, 14)
        ax = int(x + math.cos(aa) * ar)
        ay = int(y + math.sin(aa) * ar)
        pygame.draw.line(surf, P['tesla_hi'], (x, y), (ax, ay), 1)


# ── Laser Tank ────────────────────────────────────────────────────────────────
def _draw_laser_tank(surf, x, y, team, facing, turret, selected, pulse):
    c   = P['player'] if team == _cfg.PLAYER else P['enemy']
    dk  = _darker(c, 70)
    dk2 = _darker(c, 40)
    # Shadow
    sh = _get_surf(38, 14)
    pygame.draw.ellipse(sh, (0, 0, 0, 55), (0, 0, 38, 14))
    surf.blit(sh, (x - 19, y + 8))
    if selected:
        _glow(surf, x, y, P['select'], 28, int(80 + 40 * math.sin(pulse * 6)))
        pygame.draw.circle(surf, P['select'], (x, y), 20, 2)
    # Treads
    for sign in (-1, 1):
        ox = math.cos(facing + math.pi / 2) * 12 * sign
        oy = math.sin(facing + math.pi / 2) * 12 * sign
        tread = _rot_rect(x + ox, y + oy, 28, 8, facing)
        pygame.draw.polygon(surf, (35, 35, 35), tread)
        pygame.draw.polygon(surf, (60, 60, 60), tread, 1)
    # Sleek hull
    hull = _rot_rect(x, y, 28, 16, facing)
    pygame.draw.polygon(surf, dk, hull)
    pygame.draw.polygon(surf, dk2, hull, 1)
    # Laser emitter turret
    laser_c = P['laser_r'] if team == _cfg.PLAYER else P['laser_g']
    pygame.draw.circle(surf, dk2, (x, y), 9)
    pygame.draw.circle(surf, laser_c, (x, y), 6)
    # Barrel (thinner, more precise looking)
    bx = int(x + math.cos(turret) * 22)
    by = int(y + math.sin(turret) * 22)
    pygame.draw.line(surf, (200, 200, 200), (x, y), (bx, by), 3)
    pygame.draw.line(surf, laser_c, (x, y), (bx, by), 1)
    # Glow at barrel tip
    tip_a = int(100 + 60 * math.sin(pulse * 8))
    ts = _get_surf(10, 10)
    pygame.draw.circle(ts, (*laser_c[:3], tip_a), (5, 5), 4)
    surf.blit(ts, (bx - 5, by - 5), special_flags=pygame.BLEND_ADD)


# ── Flame Tank ────────────────────────────────────────────────────────────────
def _draw_flame_tank(surf, x, y, team, facing, turret, selected, pulse):
    c   = P['player'] if team == _cfg.PLAYER else P['enemy']
    dk  = _darker(c, 70)
    dk2 = _darker(c, 40)
    # Shadow
    sh = _get_surf(40, 16)
    pygame.draw.ellipse(sh, (0, 0, 0, 55), (0, 0, 40, 16))
    surf.blit(sh, (x - 20, y + 8))
    if selected:
        _glow(surf, x, y, P['select'], 28, int(80 + 40 * math.sin(pulse * 6)))
        pygame.draw.circle(surf, P['select'], (x, y), 20, 2)
    # Treads (wider)
    for sign in (-1, 1):
        ox = math.cos(facing + math.pi / 2) * 13 * sign
        oy = math.sin(facing + math.pi / 2) * 13 * sign
        tread = _rot_rect(x + ox, y + oy, 30, 9, facing)
        pygame.draw.polygon(surf, (35, 35, 35), tread)
        pygame.draw.polygon(surf, (60, 60, 60), tread, 1)
    # Chunky hull
    hull = _rot_rect(x, y, 28, 20, facing)
    pygame.draw.polygon(surf, dk, hull)
    pygame.draw.polygon(surf, dk2, hull, 1)
    # Fuel tank on back
    bk = facing + math.pi
    ftx = int(x + math.cos(bk) * 10)
    fty = int(y + math.sin(bk) * 10)
    pygame.draw.circle(surf, (80, 60, 30), (ftx, fty), 6)
    pygame.draw.circle(surf, (100, 80, 40), (ftx, fty), 6, 1)
    # Flamer nozzle (wide)
    pygame.draw.circle(surf, dk2, (x, y), 8)
    pygame.draw.circle(surf, P['flame'], (x, y), 5)
    bx = int(x + math.cos(turret) * 18)
    by = int(y + math.sin(turret) * 18)
    pygame.draw.line(surf, (160, 140, 100), (x, y), (bx, by), 5)
    pygame.draw.line(surf, (200, 160, 80), (x, y), (bx, by), 3)
    # Flame tip pilot light
    fx2 = int(x + math.cos(turret) * 20)
    fy2 = int(y + math.sin(turret) * 20)
    flicker = int(180 + 75 * math.sin(pulse * 15))
    fs = _get_surf(10, 10)
    pygame.draw.circle(fs, (*P['flame_hi'][:3], flicker), (5, 5), 4)
    surf.blit(fs, (fx2 - 5, fy2 - 5), special_flags=pygame.BLEND_ADD)


# ── Drawer dispatch table ────────────────────────────────────────────────────
_DRAWERS = {
    'infantry':     _draw_infantry,
    'buggy':        _draw_buggy,
    'tank':         _draw_tank,
    'rocket_tank':  _draw_rocket_tank,
    'tesla_tank':   _draw_tesla_tank,
    'laser_tank':   _draw_laser_tank,
    'flame_tank':   _draw_flame_tank,
    'harvester':    _draw_harvester,
    'mcv':          _draw_mcv,
}
