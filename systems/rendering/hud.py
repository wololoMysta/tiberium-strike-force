# systems/rendering/hud.py – HUD, minimap, game over, ghost preview
import math, pygame
from ecs import World
from config import (
    P, W, H, HUD_H, TILE, MAP_W, MAP_H, MINI,
    HUD_TABS, HUD_TAB_X, HUD_TAB_W, HUD_TAB_H,
    HUD_TAB_ITEMS, HUD_BTN_W, HUD_BTN_H, HUD_BTN_GAP,
    BUILD_COST, UDAT, PROD_TIME, BDAT, HARVEST_CARRY,
)
from components import (
    UnitData, BuildingData, Health, Team, Selectable,
    UnderConstruction, Harvester, Position, Resource,
)
from systems.rendering import _cfg
from systems.rendering.helpers import (
    _get_surf, _glow, _darker, _lighter, _wall_line_centers, _in_influence,
)
from systems.rendering.units import _DRAWERS


# ── HUD helpers ───────────────────────────────────────────────────────────────
def _has_complete_bldg(world, kind: str) -> bool:
    for eid, bd, t in world.q(BuildingData, Team):
        if t.id == _cfg.PLAYER and bd.kind == kind:
            if not world.get(eid, UnderConstruction):
                return True
    return False


def _draw_lock_icon(surf, x: int, y: int) -> None:
    pygame.draw.arc(surf, P['gray'], (x, y, 9, 8), 0, math.pi, 2)
    pygame.draw.rect(surf, P['gray'], (x, y + 5, 9, 7), 0, 1)


def _draw_btn_icon(surf, cx: int, cy: int, kind: str) -> None:
    """~44 × 26 programmatic icon centred at (cx, cy)."""
    cu = (120, 185, 120)
    cb = (110, 150, 200)
    if kind == 'infantry':
        pygame.draw.circle(surf, cu, (cx, cy - 9), 5)
        pygame.draw.rect(surf, cu, (cx - 4, cy - 4, 8, 9))
        pygame.draw.line(surf, (200, 200, 200), (cx + 3, cy - 6), (cx + 12, cy - 9), 2)
    elif kind == 'buggy':
        pygame.draw.rect(surf, cu, (cx - 14, cy - 5, 28, 10), 0, 2)
        for wx in (cx - 9, cx + 9):
            pygame.draw.circle(surf, (45, 45, 45),    (wx, cy + 6), 5)
            pygame.draw.circle(surf, (100, 100, 100), (wx, cy + 6), 5, 1)
        pygame.draw.line(surf, (200, 200, 200), (cx, cy - 1), (cx + 16, cy - 3), 2)
    elif kind == 'tank':
        pygame.draw.rect(surf, cu, (cx - 16, cy - 5, 32, 12), 0, 2)
        pygame.draw.circle(surf, _lighter(cu, 30), (cx, cy - 1), 7)
        pygame.draw.line(surf, (200, 200, 200), (cx, cy - 1), (cx + 18, cy - 4), 3)
    elif kind == 'harvester':
        pygame.draw.rect(surf, cu, (cx - 14, cy - 6, 28, 12), 0, 2)
        pygame.draw.circle(surf, P['tib'],    (cx + 15, cy), 6)
        pygame.draw.circle(surf, P['tib_hi'], (cx + 15, cy), 4)
    elif kind == 'barracks':
        pygame.draw.rect(surf, cb, (cx - 13, cy - 1, 26, 12), 0, 2)
        pygame.draw.polygon(surf, _darker(cb, 25),
                            [(cx - 15, cy - 1), (cx, cy - 11), (cx + 15, cy - 1)])
        pygame.draw.rect(surf, (5, 5, 5), (cx - 4, cy + 5, 8, 6))
    elif kind == 'factory':
        pygame.draw.rect(surf, cb, (cx - 15, cy - 8, 30, 19), 0, 2)
        pygame.draw.rect(surf, _darker(cb, 30), (cx - 12, cy - 8, 5, 16))
        pygame.draw.rect(surf, (5, 5, 5), (cx - 7, cy + 4, 14, 7))
    elif kind == 'refinery':
        pygame.draw.rect(surf, cb, (cx - 13, cy - 5, 20, 14), 0, 2)
        pygame.draw.circle(surf, P['tib'],    (cx + 11, cy), 8)
        pygame.draw.circle(surf, P['tib_hi'], (cx + 11, cy), 5)
    elif kind == 'turret':
        pygame.draw.rect(surf, cb, (cx - 9, cy - 7, 18, 16), 0, 3)
        pygame.draw.circle(surf, _lighter(cb, 20), (cx, cy - 1), 6)
        pygame.draw.line(surf, (200, 200, 200), (cx, cy - 1), (cx + 15, cy - 5), 3)
    elif kind == 'wall':
        pygame.draw.rect(surf, (80, 80, 75), (cx - 12, cy - 10, 24, 20), 0, 2)
        pygame.draw.rect(surf, (110, 108, 100), (cx - 12, cy - 10, 24, 20), 2, 2)
    elif kind == 'power_plant':
        pygame.draw.rect(surf, cb, (cx - 13, cy - 5, 20, 14), 0, 2)
        pygame.draw.circle(surf, (60, 60, 70), (cx - 3, cy), 7)
        bx2, by2 = cx + 8, cy - 8
        pts = [(bx2, by2), (bx2 - 3, by2 + 6), (bx2 + 1, by2 + 6), (bx2 - 2, by2 + 13)]
        pygame.draw.lines(surf, (255, 220, 0), False, pts, 2)
    elif kind == 'rocket_tank':
        pygame.draw.rect(surf, cu, (cx - 16, cy - 5, 32, 12), 0, 2)
        pygame.draw.circle(surf, _lighter(cu, 30), (cx - 2, cy - 1), 7)
        # twin rocket tubes
        for dy in (-3, 3):
            pygame.draw.line(surf, (180, 180, 180), (cx + 2, cy + dy - 1), (cx + 18, cy + dy - 1), 2)
            pygame.draw.circle(surf, P['rocket'], (cx + 18, cy + dy - 1), 2)
    elif kind == 'tesla_tank':
        pygame.draw.rect(surf, cu, (cx - 16, cy - 5, 32, 12), 0, 2)
        pygame.draw.circle(surf, _lighter(cu, 30), (cx - 2, cy - 1), 7)
        # tesla coil
        pygame.draw.circle(surf, P['tesla'], (cx + 4, cy - 8), 5)
        pygame.draw.circle(surf, P['tesla_hi'], (cx + 4, cy - 8), 3)
        pygame.draw.line(surf, P['tesla_hi'], (cx + 4, cy - 3), (cx + 4, cy - 8), 2)
    elif kind == 'laser_tank':
        pygame.draw.rect(surf, cu, (cx - 16, cy - 5, 32, 12), 0, 2)
        pygame.draw.circle(surf, _lighter(cu, 30), (cx - 2, cy - 1), 7)
        # laser barrel with red tip
        pygame.draw.line(surf, (200, 200, 200), (cx, cy - 1), (cx + 18, cy - 3), 3)
        pygame.draw.circle(surf, P['laser_r'], (cx + 18, cy - 3), 3)
    elif kind == 'flame_tank':
        pygame.draw.rect(surf, cu, (cx - 16, cy - 5, 34, 14), 0, 2)
        pygame.draw.circle(surf, _lighter(cu, 30), (cx - 2, cy), 7)
        # flame nozzle + fire
        pygame.draw.line(surf, (160, 160, 160), (cx + 2, cy), (cx + 14, cy), 3)
        pygame.draw.circle(surf, P['flame'], (cx + 17, cy), 4)
        pygame.draw.circle(surf, P['flame_hi'], (cx + 17, cy), 2)
    elif kind == 'mcv':
        pygame.draw.rect(surf, cu, (cx - 18, cy - 7, 36, 16), 0, 2)
        pygame.draw.circle(surf, _lighter(cu, 30), (cx - 2, cy - 1), 8)
        pygame.draw.line(surf, (200, 200, 200), (cx, cy - 1), (cx + 14, cy - 6), 3)
        pygame.draw.circle(surf, (255, 220, 60), (cx + 14, cy - 6), 3)


def _draw_queue_strip(surf, world, small_font, tab: int, avail: list,
                      panel_y: int) -> None:
    qy = panel_y + 4 + HUD_TAB_H + HUD_BTN_H + 8
    qx = HUD_TAB_X
    qw = len(HUD_TABS) * HUD_TAB_W - 2

    if tab == 0:
        bldgs = [(bd, uc) for eid, bd, uc, t
                 in world.q(BuildingData, UnderConstruction, Team)
                 if t.id == _cfg.PLAYER]
        if not bldgs:
            idle = small_font.render("No buildings under construction", True, (45, 65, 45))
            surf.blit(idle, (qx + 4, qy + 1))
            return
        slot = (qw - 4) // max(1, len(bldgs))
        for k, (bd, uc) in enumerate(bldgs[:4]):
            ix  = qx + 2 + k * slot
            iw  = slot - 4
            bpw = max(0, int(iw * uc.ratio))
            pygame.draw.rect(surf, (0, 0, 0),    (ix, qy, iw, 14))
            pygame.draw.rect(surf, P['ui_hi'],   (ix, qy, bpw, 14))
            pygame.draw.rect(surf, (30, 60, 30), (ix, qy, iw, 14), 1)
            lbl = small_font.render(f"{bd.kind[:7]}  {int(uc.ratio * 100)}%",
                                    True, P['white'])
            surf.blit(lbl, (ix + 3, qy + 1))
        return

    req = HUD_TABS[tab][1]
    if not avail[tab]:
        return

    # Gather per-building queues for this tab's building type
    bld_queues: list = []
    for eid, bd, t in world.q(BuildingData, Team):
        if t.id == _cfg.PLAYER and bd.kind == req and not world.get(eid, UnderConstruction):
            if bd.prod_queue:
                bld_queues.append(bd.prod_queue)

    if not bld_queues:
        idle = small_font.render("Queue empty  ·  click buttons above to train",
                                 True, (50, 80, 50))
        surf.blit(idle, (qx + 4, qy + 1))
        return

    # Show progress bar for each building producing simultaneously
    slot_w = min(180, (qw - 4) // max(1, len(bld_queues)))
    for i, pq in enumerate(bld_queues[:4]):
        ix = qx + i * (slot_w + 4)
        qkind, qt = pq[0]
        ratio = 1.0 - qt / PROD_TIME[qkind]
        pygame.draw.rect(surf, (0, 0, 0),    (ix, qy, slot_w, 14))
        pygame.draw.rect(surf, P['ui_hi'],   (ix, qy, int(slot_w * ratio), 14))
        pygame.draw.rect(surf, (30, 60, 30), (ix, qy, slot_w, 14), 1)
        extra = len(pq) - 1
        txt = f"{qkind[:6].upper()}" + (f" +{extra}" if extra else "")
        lbl = small_font.render(txt, True, P['white'])
        surf.blit(lbl, (ix + 3, qy + 1))


# ── HUD ───────────────────────────────────────────────────────────────────────
def _draw_hud(surf: pygame.Surface, world: World, font, small_font, time: float):
    meta    = world.meta
    credits = meta['credits']
    tab     = meta.get('hud_tab', 0)
    panel_y = H - HUD_H

    # Panel background + top border
    pygame.draw.rect(surf, P['ui_bg'], (0, panel_y, W, HUD_H))
    pygame.draw.line(surf, P['ui_brd'], (0, panel_y), (W, panel_y), 2)

    # ── Left info column ──────────────────────────────────────────────────────
    surf.blit(font.render(f"${int(credits[_cfg.PLAYER]):,}", True, P['gold']),
              (8, panel_y + 8))
    pu = sum(1 for _, ud, t in world.q(UnitData, Team) if t.id == _cfg.PLAYER)
    eu = sum(1 for _, ud, t in world.q(UnitData, Team) if t.id == _cfg.ENEMY)
    surf.blit(small_font.render(f"\u25b2 {pu} units", True, P['player']), (8, panel_y + 32))
    surf.blit(small_font.render(f"\u25bc {eu} enemy", True, P['enemy']),  (8, panel_y + 52))

    # ── Power bar ─────────────────────────────────────────────────────────────
    pwr_supply = meta.get('power_supply_0', 0)
    pwr_demand = meta.get('power_demand_0', 0)
    pwr_ratio  = meta.get('power_ratio_0', 1.0)
    pwr_col    = P['hp_hi'] if pwr_ratio >= 1.0 else (P['hp_mid'] if pwr_ratio >= 0.5 else P['hp_lo'])
    bar_x, bar_y, bar_w, bar_h = 8, panel_y + 66, 130, 8
    pygame.draw.rect(surf, (20, 30, 20), (bar_x, bar_y, bar_w, bar_h))
    pygame.draw.rect(surf, pwr_col, (bar_x, bar_y, int(bar_w * pwr_ratio), bar_h))
    pygame.draw.rect(surf, P['ui_brd'], (bar_x, bar_y, bar_w, bar_h), 1)
    lbl = small_font.render(f"\u26a1 {pwr_supply}/{pwr_demand}", True, pwr_col)
    surf.blit(lbl, (bar_x + bar_w + 4, bar_y - 1))

    # ── Selection info (right of left-info column) ───────────────────────────
    sel_set = meta.get('selected', set())
    sel_x = 148   # right side of left info column
    if len(sel_set) == 1:
        seid = next(iter(sel_set))
        sud = world.get(seid, UnitData)
        shp = world.get(seid, Health)
        sbd = world.get(seid, BuildingData)
        if sud and shp:
            # Draw mini icon of the unit
            fn = _DRAWERS.get(sud.kind)
            if fn:
                icon_x, icon_y = sel_x + 10, panel_y + 18
                if sud.kind in ('tank', 'rocket_tank', 'tesla_tank',
                                'laser_tank', 'flame_tank'):
                    fn(surf, icon_x, icon_y, _cfg.PLAYER, 0.0, 0.0, False, time)
                else:
                    fn(surf, icon_x, icon_y, _cfg.PLAYER, 0.0, False, time)
            surf.blit(small_font.render(f"{sud.kind.upper()}", True, P['white']),
                      (sel_x + 28, panel_y + 8))
            surf.blit(small_font.render(f"HP {int(shp.hp)}/{int(shp.max_hp)}"
                                        f"  DMG {int(sud.damage)}  RNG {int(sud.rng)}",
                                        True, P['gray']),
                      (sel_x + 28, panel_y + 22))
            harv = world.get(seid, Harvester)
            if harv:
                surf.blit(small_font.render(f"Carry: {int(harv.carry)}/{int(HARVEST_CARRY)}  [{harv.state}]",
                                            True, P['tib_hi']),
                          (sel_x, panel_y + 38))
            if sud.kind == 'mcv':
                surf.blit(small_font.render("Press [D] to DEPLOY base",
                                            True, P['build_ok']),
                          (sel_x, panel_y + 38))
        elif sbd and shp:
            surf.blit(small_font.render(f"{sbd.name}", True, P['white']),
                      (sel_x, panel_y + 8))
            surf.blit(small_font.render(f"HP {int(shp.hp)}/{int(shp.max_hp)}",
                                        True, P['gray']),
                      (sel_x, panel_y + 22))
    elif len(sel_set) > 1:
        # Group selected units by kind and show icon + count for each type
        kind_counts: dict[str, int] = {}
        for seid in sel_set:
            sud = world.get(seid, UnitData)
            if sud:
                kind_counts[sud.kind] = kind_counts.get(sud.kind, 0) + 1
        ix = sel_x
        iy = panel_y + 10
        for kind, count in kind_counts.items():
            fn = _DRAWERS.get(kind)
            if fn:
                icon_x = ix + 10
                icon_y = iy + 4
                if kind in ('tank', 'rocket_tank', 'tesla_tank',
                            'laser_tank', 'flame_tank'):
                    fn(surf, icon_x, icon_y, _cfg.PLAYER, 0.0, 0.0, False, time)
                else:
                    fn(surf, icon_x, icon_y, _cfg.PLAYER, 0.0, False, time)
            # Count badge
            cnt_txt = small_font.render(str(count), True, P['white'])
            surf.blit(cnt_txt, (ix + 22, iy + 14))
            ix += 38
            if ix > HUD_TAB_X - 46:
                break
        # Total count
        surf.blit(small_font.render(f"{len(sel_set)} selected", True, P['white']),
                  (sel_x, panel_y + 38))

    pygame.draw.line(surf, P['ui_brd'],
                     (HUD_TAB_X - 8, panel_y + 6),
                     (HUD_TAB_X - 8, panel_y + HUD_H - 6), 1)

    # ── Tab availability ──────────────────────────────────────────────────────
    avail = [_has_complete_bldg(world, 'base'),
             _has_complete_bldg(world, 'barracks'),
             _has_complete_bldg(world, 'factory')]

    # ── Tab headers ───────────────────────────────────────────────────────────
    for i, (label, _req) in enumerate(HUD_TABS):
        tx, ty = HUD_TAB_X + i * HUD_TAB_W, panel_y + 4
        tw, th = HUD_TAB_W - 2, HUD_TAB_H
        active, locked = (i == tab), not avail[i]

        if active:
            pygame.draw.rect(surf, P['ui_brd'], (tx, ty, tw, th), 0, 3)
            pygame.draw.line(surf, P['ui_hi'],
                             (tx + 1, ty + th - 1), (tx + tw - 2, ty + th - 1))
            tcol = P['ui_bg']
        elif locked:
            pygame.draw.rect(surf, (12, 20, 12), (tx, ty, tw, th), 0, 3)
            pygame.draw.rect(surf, (40, 55, 40), (tx, ty, tw, th), 1, 3)
            tcol = (50, 70, 50)
        else:
            pygame.draw.rect(surf, (10, 20, 10), (tx, ty, tw, th), 0, 3)
            pygame.draw.rect(surf, P['ui_hi'],   (tx, ty, tw, th), 1, 3)
            tcol = P['ui_hi']

        lbl = small_font.render(label, True, tcol)
        surf.blit(lbl, (tx + (tw - lbl.get_width()) // 2,
                        ty + (th - lbl.get_height()) // 2))
        if locked:
            _draw_lock_icon(surf, tx + tw - 14, ty + 5)

    # ── Content area ──────────────────────────────────────────────────────────
    cx0 = HUD_TAB_X
    cy0 = panel_y + 4 + HUD_TAB_H     # 634
    cw  = len(HUD_TABS) * HUD_TAB_W - 2
    ch  = HUD_BTN_H + 6
    pygame.draw.rect(surf, (8, 16, 8),   (cx0, cy0, cw, ch))
    pygame.draw.rect(surf, (25, 55, 25), (cx0, cy0, cw, ch), 1)

    items  = HUD_TAB_ITEMS[tab]
    locked = not avail[tab]

    if locked:
        req_name = {'base':      'COMMAND CENTER',
                    'barracks': 'BARRACKS',
                    'factory':  'WAR FACTORY'}[HUD_TABS[tab][1]]
        msg = font.render(f"BUILD A {req_name} FIRST", True, (55, 85, 55))
        surf.blit(msg, (cx0 + cw // 2 - msg.get_width() // 2,
                        cy0 + ch // 2 - msg.get_height() // 2))
    else:
        bx0 = cx0 + 4
        by  = cy0 + 3
        for j, kind in enumerate(items):
            bx   = bx0 + j * (HUD_BTN_W + HUD_BTN_GAP)
            cost = BUILD_COST[kind] if tab == 0 else UDAT[kind][6]
            can  = credits[_cfg.PLAYER] >= cost
            bcol = P['ui_hi'] if can else (45, 70, 45)
            bg   = (14, 28, 14) if can else (8, 14, 8)

            pygame.draw.rect(surf, bg,   (bx, by, HUD_BTN_W, HUD_BTN_H), 0, 4)
            pygame.draw.rect(surf, bcol, (bx, by, HUD_BTN_W, HUD_BTN_H), 2, 4)

            # Hotkey tag
            hk = small_font.render(f"[{j + 1}]",
                                   True, _darker(bcol, 20) if can else (40, 60, 40))
            surf.blit(hk, (bx + 3, by + 3))

            # Programmatic icon (centred in upper portion of button)
            _draw_btn_icon(surf, bx + HUD_BTN_W // 2, by + 22, kind)

            # Name
            nl = small_font.render(kind, True, bcol)
            surf.blit(nl, (bx + HUD_BTN_W // 2 - nl.get_width() // 2,
                           by + HUD_BTN_H - 24))
            # Cost
            cl = small_font.render(f"${cost}",
                                   True, P['gold'] if can else (70, 55, 15))
            surf.blit(cl, (bx + HUD_BTN_W // 2 - cl.get_width() // 2,
                           by + HUD_BTN_H - 12))

    # ── Bottom strip: placing hint  OR  queue/progress ────────────────────────
    if meta.get('mode') == 'place_building':
        hint = small_font.render(
            f"Click map to place  {meta.get('place_type', '')}  \u00b7  RMB cancel",
            True, P['build_ok'])
        surf.blit(hint, (cx0 + 4,
                         panel_y + 4 + HUD_TAB_H + HUD_BTN_H + 10))
    else:
        _draw_queue_strip(surf, world, small_font, tab, avail, panel_y)

    # ── Right: unit counts ────────────────────────────────────────────────────
    stats_x = W - 140
    surf.blit(font.render(f"Units: {pu}", True, P['player']), (stats_x, panel_y + 8))
    surf.blit(font.render(f"Enemy: {eu}", True, P['enemy']),  (stats_x, panel_y + 32))


# ── Minimap ───────────────────────────────────────────────────────────────────
_mini_fog_surf = None
_mini_fog_frame = 0

def _draw_minimap(surf, world, top_y):
    global _mini_fog_surf, _mini_fog_frame
    mx = 6
    pygame.draw.rect(surf, (0, 0, 0),   (mx - 2, top_y - 2, MINI + 4, MINI + 4))
    pygame.draw.rect(surf, P['ui_brd'], (mx - 2, top_y - 2, MINI + 4, MINI + 4), 2)

    # Pre-rendered terrain minimap
    mini_surf = world.meta.get('mini_surf')
    if mini_surf:
        surf.blit(mini_surf, (mx, top_y))
    else:
        pygame.draw.rect(surf, (20, 35, 15), (mx, top_y, MINI, MINI))

    # Fog overlay on minimap (rebuild every 6 frames)
    fog = world.meta['fog']
    scale_x = MINI / MAP_W
    scale_y = MINI / MAP_H
    _mini_fog_frame += 1
    if _mini_fog_surf is None or _mini_fog_frame % 6 == 0:
        step = 4
        if _mini_fog_surf is None:
            _mini_fog_surf = pygame.Surface((MINI, MINI), pygame.SRCALPHA)
        _mini_fog_surf.fill((0, 0, 0, 0))
        for fy in range(0, MAP_H, step):
            for fx in range(0, MAP_W, step):
                f = fog[fy, fx]
                if f == 0:
                    bx = int(fx * scale_x)
                    by = int(fy * scale_y)
                    bw = max(1, int(step * scale_x) + 1)
                    bh = max(1, int(step * scale_y) + 1)
                    pygame.draw.rect(_mini_fog_surf, (0, 0, 0, 210), (bx, by, bw, bh))
                elif f == 1:
                    bx = int(fx * scale_x)
                    by = int(fy * scale_y)
                    bw = max(1, int(step * scale_x) + 1)
                    bh = max(1, int(step * scale_y) + 1)
                    pygame.draw.rect(_mini_fog_surf, (0, 0, 0, 120), (bx, by, bw, bh))
    surf.blit(_mini_fog_surf, (mx, top_y))

    # Entities
    for eid, pos, team in world.q(Position, Team):
        ex = int(pos.x / (MAP_W * TILE) * MINI)
        ey = int(pos.y / (MAP_H * TILE) * MINI)
        c  = P['player'] if team.id == _cfg.PLAYER else P['enemy']
        # Only show enemy units in visible fog
        if team.id == _cfg.ENEMY:
            ftx = int(pos.x // TILE)
            fty = int(pos.y // TILE)
            if 0 <= ftx < MAP_W and 0 <= fty < MAP_H and fog[fty, ftx] < 2:
                continue
        ud = world.get(eid, UnitData)
        bd = world.get(eid, BuildingData)
        r  = 1 if ud else 3
        pygame.draw.circle(surf, c, (mx + ex, top_y + ey), r)

    # Resources (only in explored/visible areas)
    for eid, pos, res in world.q(Position, Resource):
        if res.amount <= 0:
            continue
        ftx = int(pos.x // TILE)
        fty = int(pos.y // TILE)
        if 0 <= ftx < MAP_W and 0 <= fty < MAP_H and fog[fty, ftx] == 0:
            continue
        ex = int(pos.x / (MAP_W * TILE) * MINI)
        ey = int(pos.y / (MAP_H * TILE) * MINI)
        pygame.draw.circle(surf, P['tib'], (mx + ex, top_y + ey), 2)

    # Camera viewport box
    cam = world.meta['cam']
    zoom = world.meta.get('zoom', 1.0)
    vx  = int(cam[0] / (MAP_W * TILE) * MINI)
    vy  = int(cam[1] / (MAP_H * TILE) * MINI)
    vw  = int((W / zoom) / (MAP_W * TILE) * MINI)
    vh  = int(((H-HUD_H) / zoom) / (MAP_H * TILE) * MINI)
    pygame.draw.rect(surf, P['white'], (mx + vx, top_y + vy, vw, vh), 1)


# ── Game-over overlay ─────────────────────────────────────────────────────────
def _draw_game_over(surf, result: str, big_font, font):
    overlay = _get_surf(W, H)
    overlay.fill((0, 0, 0, 160))
    surf.blit(overlay, (0, 0))
    if result == 'win':
        msg, col = "MISSION ACCOMPLISHED", P['ui_hi']
    else:
        msg, col = "BASE DESTROYED", P['enemy']
    t = big_font.render(msg, True, col)
    sub = font.render("Press R to restart or ESC to quit", True, P['white'])
    surf.blit(t,   (W // 2 - t.get_width() // 2,   H // 2 - 50))
    surf.blit(sub, (W // 2 - sub.get_width() // 2, H // 2 + 20))


# ── Ghost building preview ────────────────────────────────────────────────────
def _draw_ghost(surf, cam, kind, world):
    mx, my = pygame.mouse.get_pos()
    if my >= H - HUD_H:
        return
    zoom = world.meta.get('zoom', 1.0)
    _, bw, bh = BDAT[kind]
    raw_wx = mx / zoom + cam[0]
    raw_wy = my / zoom + cam[1]
    if kind == 'wall':
        raw_wx = round(raw_wx / TILE) * TILE
        raw_wy = round(raw_wy / TILE) * TILE
    from terrain import can_place_building
    tiles = world.meta['tiles']
    placeable = (can_place_building(world, tiles, raw_wx, raw_wy, kind, _cfg.PLAYER)
                 and _in_influence(world, raw_wx, raw_wy, _cfg.PLAYER))
    color = P['build_ok'] if placeable else P['build_no']
    # Screen-space position and size
    sx    = int((raw_wx - cam[0]) * zoom - bw * zoom / 2)
    sy    = int((raw_wy - cam[1]) * zoom - bh * zoom / 2)
    sw    = max(1, int(bw * zoom))
    sh    = max(1, int(bh * zoom))
    ghost = _get_surf(sw, sh)
    ghost.fill((*color, 80))
    surf.blit(ghost, (sx, sy))
    pygame.draw.rect(surf, color, (sx, sy, sw, sh), 2)


def _draw_wall_drag_line(surf, cam, world, drag_start):
    """Preview all wall ghosts along the drag line."""
    mx, my = pygame.mouse.get_pos()
    if my >= H - HUD_H:
        return
    zoom = world.meta.get('zoom', 1.0)
    wx1 = mx / zoom + cam[0]
    wy1 = my / zoom + cam[1]
    positions = _wall_line_centers(drag_start[0], drag_start[1], wx1, wy1)
    bw = bh = TILE
    from terrain import can_place_building
    tiles = world.meta['tiles']
    for cx, cy in positions:
        placeable = (can_place_building(world, tiles, cx, cy, 'wall', _cfg.PLAYER)
                     and _in_influence(world, cx, cy, _cfg.PLAYER))
        color = P['build_ok'] if placeable else P['build_no']
        sx    = int((cx - cam[0]) * zoom - bw * zoom / 2)
        sy    = int((cy - cam[1]) * zoom - bh * zoom / 2)
        sw    = max(1, int(bw * zoom))
        sh    = max(1, int(bh * zoom))
        ghost = _get_surf(sw, sh)
        ghost.fill((*color, 80))
        surf.blit(ghost, (sx, sy))
        pygame.draw.rect(surf, color, (sx, sy, sw, sh), 2)
