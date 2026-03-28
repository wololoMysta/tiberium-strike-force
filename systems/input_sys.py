# systems/input_sys.py – player mouse + keyboard input
import math
import pygame
from ecs import World, System
from components import *
from config import *
import entities as ent


# ── Shared helpers (also used by render_sys) ──────────────────────────────────
def _wall_line_centers(x0: float, y0: float, x1: float, y1: float,
                       step: int = TILE) -> list[tuple[float, float]]:
    """Return grid-snapped wall centre positions along the line from (x0,y0) to (x1,y1)."""
    sx = round(x0 / step) * step
    sy = round(y0 / step) * step
    ex = round(x1 / step) * step
    ey = round(y1 / step) * step
    dx, dy = ex - sx, ey - sy
    n = max(abs(dx), abs(dy)) // step
    if n == 0:
        return [(sx, sy)]
    out: list = []
    seen: set = set()
    for i in range(n + 1):
        t = i / n
        cx = round(sx + dx * t)
        cy = round(sy + dy * t)
        cx = round(cx / step) * step
        cy = round(cy / step) * step
        if (cx, cy) not in seen:
            seen.add((cx, cy))
            out.append((cx, cy))
    return out


def _in_influence(world: World, wx: float, wy: float, team_id: int) -> bool:
    """Return True if (wx, wy) is within any friendly building's influence radius."""
    for _eid, pos, team, bd in world.q(Position, Team, BuildingData):
        if team.id != team_id:
            continue
        bx = pos.x + bd.w / 2
        by = pos.y + bd.h / 2
        r  = INFLUENCE_RADIUS.get(bd.kind, 200)
        if math.hypot(bx - wx, by - wy) <= r:
            return True
    return False


# Double-click timing
_DCLICK_THRESHOLD = 0.35  # seconds


class InputSys(System):
    _last_click_time: float = 0.0
    _last_click_eid: int | None = None

    def update(self, world: World, dt: float) -> None:
        meta  = world.meta
        m     = meta
        tiles = m['tiles']
        cam   = m['cam']          # [x, y]
        keys  = pygame.key.get_pressed()

        # ── Camera scroll ─────────────────────────────────────────────────────
        spd = 320.0
        mx, my = pygame.mouse.get_pos()
        edge = 20
        if keys[pygame.K_LEFT]  or mx < edge:            cam[0] -= spd * dt
        if keys[pygame.K_RIGHT] or mx >= W - edge:       cam[0] += spd * dt
        if keys[pygame.K_UP]    or my < edge:            cam[1] -= spd * dt
        if keys[pygame.K_DOWN]  or (HUD_H > 0 and my >= H - HUD_H - edge and my < H - HUD_H):
            cam[1] += spd * dt
        zoom = m.get('zoom', 1.0)
        vw = W / zoom
        vh = (H - HUD_H) / zoom
        cam[0] = max(0, min(MAP_W * TILE - vw, cam[0]))
        cam[1] = max(0, min(MAP_H * TILE - vh, cam[1]))

        for event in m.get('events', []):
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    m['mode']            = 'normal'
                    m['place_type']      = None
                    m['sel_bldg']        = None
                    m['wall_drag_start'] = None
                if event.key == pygame.K_DELETE:
                    _kill_selected(world)
                # Tab switching: Q / W / E
                if event.key == pygame.K_q:
                    m['hud_tab'] = 0
                if event.key == pygame.K_w:
                    if _has_complete_bldg(world, 'barracks'): m['hud_tab'] = 1
                if event.key == pygame.K_e:
                    if _has_complete_bldg(world, 'factory'):  m['hud_tab'] = 2
                # Hotkeys 1–4 within active tab
                _hotkey_produce(world, m, event.key)

            elif event.type == pygame.MOUSEBUTTONDOWN:
                self._on_mouse_down(world, m, event)

            elif event.type == pygame.MOUSEBUTTONUP:
                self._on_mouse_up(world, m, event)

            elif event.type == pygame.MOUSEWHEEL:
                _handle_zoom(m, event)

    # ── Mouse down ────────────────────────────────────────────────────────────
    def _on_mouse_down(self, world: World, m: dict, event: pygame.event.Event) -> None:
        mx, my = event.pos
        zoom = m.get('zoom', 1.0)
        wx = mx / zoom + m['cam'][0]
        wy = my / zoom + m['cam'][1]

        # Clicks inside HUD are handled by render/UI layer
        if my >= H - HUD_H:
            _handle_hud_click(world, m, mx, my)
            return

        if event.button == 1:
            if m['mode'] == 'place_building':
                kind = m['place_type']
                if kind == 'wall':
                    # Start drag — snap start point to tile grid
                    snap = TILE
                    m['wall_drag_start'] = (
                        round(wx / snap) * snap,
                        round(wy / snap) * snap,
                    )
                else:
                    _try_place_building(world, m, wx, wy)
                return
            # Start selection box
            m['sel_start'] = (mx, my)
            m['sel_box']   = None

        elif event.button == 3:
            m['mode'] = 'normal'
            m['place_type'] = None
            _right_click(world, m, wx, wy)

    # ── Mouse up (finalise box-select) ────────────────────────────────────────
    def _on_mouse_up(self, world: World, m: dict, event: pygame.event.Event) -> None:
        if event.button != 1:
            return

        zoom = m.get('zoom', 1.0)

        # ── Wall drag: place the whole line then stay in wall-mode ────────────
        drag = m['wall_drag_start']
        m['wall_drag_start'] = None
        if drag is not None:
            mx, my = event.pos
            wx = mx / zoom + m['cam'][0]
            wy = my / zoom + m['cam'][1]
            for cx, cy in _wall_line_centers(drag[0], drag[1], wx, wy):
                _try_place_building(world, m, cx, cy)
            return

        mx, my = event.pos
        start  = m.pop('sel_start', None)
        if start is None:
            return
        sx, sy  = start
        dx, dy  = abs(mx - sx), abs(my - sy)
        cam     = m['cam']

        if dx < 4 and dy < 4:
            # Single click – select one unit at world pos
            wx = mx / zoom + cam[0]
            wy = my / zoom + cam[1]
            clicked = _unit_at(world, wx, wy)
            now = pygame.time.get_ticks() / 1000.0

            # Double-click on MCV → deploy
            if (clicked is not None
                    and clicked == self._last_click_eid
                    and now - self._last_click_time < _DCLICK_THRESHOLD):
                ud = world.get(clicked, UnitData)
                if ud and ud.kind == 'mcv':
                    m['selected'] = {clicked}
                    _deploy_mcv(world, m)
                    self._last_click_eid = None
                    return

            self._last_click_time = now
            self._last_click_eid = clicked

            mods = pygame.key.get_mods()
            if not (mods & pygame.KMOD_SHIFT):
                _deselect_all(world, m)
            if clicked is not None:
                sel = world.get(clicked, Selectable)
                if sel:
                    sel.selected = True
                    m['selected'].add(clicked)
                bd = world.get(clicked, BuildingData)
                m['sel_bldg'] = clicked if bd else None
            else:
                m['sel_bldg'] = None
        else:
            # Box select
            x1 = min(sx, mx) / zoom + cam[0]
            y1 = min(sy, my) / zoom + cam[1]
            x2 = max(sx, mx) / zoom + cam[0]
            y2 = max(sy, my) / zoom + cam[1]
            mods = pygame.key.get_mods()
            if not (mods & pygame.KMOD_SHIFT):
                _deselect_all(world, m)
            _box_select(world, m, x1, y1, x2, y2)

        m['sel_box'] = None


# ── Helpers ───────────────────────────────────────────────────────────────────
def _world_to_screen(wx: float, wy: float, cam: list) -> tuple:
    return wx - cam[0], wy - cam[1]

def _handle_zoom(m: dict, event: pygame.event.Event) -> None:
    """Zoom toward/away from mouse cursor position."""
    old_zoom = m.get('zoom', 1.0)
    new_zoom = max(ZOOM_MIN, min(ZOOM_MAX, old_zoom + event.y * ZOOM_STEP))
    if new_zoom == old_zoom:
        return
    # Keep the world point under the mouse fixed
    mx, my = pygame.mouse.get_pos()
    cam = m['cam']
    wx = mx / old_zoom + cam[0]
    wy = my / old_zoom + cam[1]
    cam[0] = wx - mx / new_zoom
    cam[1] = wy - my / new_zoom
    m['zoom'] = new_zoom
    # Clamp camera
    vw = W / new_zoom
    vh = (H - HUD_H) / new_zoom
    cam[0] = max(0, min(MAP_W * TILE - vw, cam[0]))
    cam[1] = max(0, min(MAP_H * TILE - vh, cam[1]))

def _unit_at(world: World, wx: float, wy: float):
    """Return entity ID of the topmost player-owned unit/building at position."""
    best, best_d = None, 9999.0
    for eid, pos, team, sel in world.q(Position, Team, Selectable):
        if team.id != PLAYER:
            continue
        bd = world.get(eid, BuildingData)
        if bd:
            # Rectangle hit-test for buildings
            if pos.x <= wx <= pos.x + bd.w and pos.y <= wy <= pos.y + bd.h:
                d = math.hypot(pos.x + bd.w / 2 - wx, pos.y + bd.h / 2 - wy)
                if d < best_d:
                    best, best_d = eid, d
        else:
            ud = world.get(eid, UnitData)
            r  = ud.radius if ud else 20
            d  = math.hypot(pos.x - wx, pos.y - wy)
            if d < r + 4 and d < best_d:
                best, best_d = eid, d
    return best


def _deselect_all(world: World, m: dict) -> None:
    for eid in list(m['selected']):
        sel = world.get(eid, Selectable)
        if sel:
            sel.selected = False
    m['selected'].clear()
    m['sel_bldg'] = None


def _box_select(world: World, m: dict,
                x1: float, y1: float, x2: float, y2: float) -> None:
    for eid, pos, team, sel, ud in world.q(Position, Team, Selectable, UnitData):
        if team.id != PLAYER:
            continue
        if x1 <= pos.x <= x2 and y1 <= pos.y <= y2:
            sel.selected = True
            m['selected'].add(eid)


def _right_click(world: World, m: dict, wx: float, wy: float) -> None:
    """Move or attack-order for selected units."""
    if not m['selected']:
        return
    # Check if clicking on an enemy
    target_eid = _enemy_at(world, wx, wy)
    units = list(m['selected'])
    # Spread units in a formation around target
    n = len(units)
    for i, eid in enumerate(units):
        mv = world.get(eid, Movement)
        cb = world.get(eid, Combat)
        if mv is None:
            continue
        # Formation offset
        row = i // 4
        col = i % 4
        ox  = (col - 1.5) * 28
        oy  = row * 28
        mv.tx = wx + ox
        mv.ty = wy + oy
        mv.attack_move = target_eid is not None
        if cb and target_eid is not None:
            cb.target = target_eid
    # Click ripple effect
    m['fx'].append({'kind': 'click', 'x': wx, 'y': wy, 't': 0.5})


def _enemy_at(world: World, wx: float, wy: float):
    best, best_d = None, 9999.0
    for eid, pos, team in world.q(Position, Team):
        if team.id != ENEMY:
            continue
        ud = world.get(eid, UnitData)
        bd = world.get(eid, BuildingData)
        r  = ud.radius if ud else (max(bd.w, bd.h) // 2 if bd else 20)
        d  = math.hypot(pos.x - wx, pos.y - wy)
        if d < r + 6 and d < best_d:
            best, best_d = eid, d
    return best


def _kill_selected(world: World) -> None:
    pass   # disabled in gameplay; keep for debug if desired


def _try_place_building(world: World, m: dict, wx: float, wy: float) -> None:
    kind  = m['place_type']
    if kind is None:
        return
    cost  = BUILD_COST[kind]
    if m['credits'][PLAYER] < cost:
        m['mode']       = 'normal'
        m['place_type'] = None
        return
    _, bw, bh = BDAT[kind]
    from terrain import can_place_building
    cx = wx - bw // 2
    cy = wy - bh // 2
    if not can_place_building(world, m['tiles'], wx, wy, kind, PLAYER):
        return
    if not _in_influence(world, wx, wy, PLAYER):
        return
    m['credits'][PLAYER] -= cost
    ent.spawn_building(world, cx, cy, PLAYER, kind, complete=False)
    if kind != 'wall':
        m['mode']       = 'normal'
        m['place_type'] = None


def _has_complete_bldg(world, kind: str) -> bool:
    for eid, bd, t in world.q(BuildingData, Team):
        if t.id == PLAYER and bd.kind == kind:
            if not world.get(eid, UnderConstruction):
                return True
    return False


def _deploy_mcv(world: World, m: dict) -> None:
    """Deploy a selected MCV into a base building (under construction)."""
    for eid in list(m['selected']):
        ud = world.get(eid, UnitData)
        if ud and ud.kind == 'mcv':
            pos = world.get(eid, Position)
            team = world.get(eid, Team)
            if pos and team and team.id == PLAYER:
                _, bw, bh = BDAT['base']
                cx = pos.x - bw // 2
                cy = pos.y - bh // 2
                ent.spawn_building(world, cx, cy, PLAYER, 'base', complete=False)
                world.kill(eid)
                m['selected'].discard(eid)
                m['sel_bldg'] = None
                break


def _queue_unit_global(world, m: dict, unit_kind: str) -> None:
    """Find the least-busy matching production building and queue the unit."""
    req  = next(k for k, us in PROD_MENU.items() if unit_kind in us)
    cost = UDAT[unit_kind][6]
    if m['credits'][PLAYER] < cost:
        return
    best, best_qlen = None, 999
    for eid, bd, t in world.q(BuildingData, Team):
        if t.id != PLAYER or bd.kind != req:
            continue
        if world.get(eid, UnderConstruction):
            continue
        if len(bd.prod_queue) < best_qlen:
            best, best_qlen = eid, len(bd.prod_queue)
    if best is None:
        return
    m['credits'][PLAYER] -= cost
    world.get(best, BuildingData).prod_queue.append([unit_kind, PROD_TIME[unit_kind]])


def _handle_hud_click(world: World, m: dict, mx: int, my: int) -> None:
    """Route clicks inside the HUD panel."""
    panel_y = H - HUD_H

    # ── Minimap click → move camera (upper-left corner) ───────────────────
    mini_x = 6
    mini_y = 6
    if mini_x <= mx <= mini_x + MINI and mini_y <= my <= mini_y + MINI:
        rx = (mx - mini_x) / MINI
        ry = (my - mini_y) / MINI
        cam = m['cam']
        zoom = m.get('zoom', 1.0)
        vw = W / zoom
        vh = (H - HUD_H) / zoom
        cam[0] = max(0, min(MAP_W * TILE - vw, rx * MAP_W * TILE - vw / 2))
        cam[1] = max(0, min(MAP_H * TILE - vh, ry * MAP_H * TILE - vh / 2))
        return

    # ── Tab header clicks ────────────────────────────────────────────────────
    for i, (label, req) in enumerate(HUD_TABS):
        tx = HUD_TAB_X + i * HUD_TAB_W
        ty = panel_y + 4
        tw, th = HUD_TAB_W - 2, HUD_TAB_H
        if tx <= mx <= tx + tw and ty <= my <= ty + th:
            avail_i = (req is None) or _has_complete_bldg(world, req)
            if avail_i:
                m['hud_tab'] = i
            return

    # ── Content button clicks ────────────────────────────────────────────────
    tab = m.get('hud_tab', 0)
    req = HUD_TABS[tab][1]
    if req is not None and not _has_complete_bldg(world, req):
        return   # tab is locked

    cy0  = panel_y + 4 + HUD_TAB_H
    bx0  = HUD_TAB_X + 4
    by   = cy0 + 3
    items = HUD_TAB_ITEMS[tab]
    for j, kind in enumerate(items):
        bx = bx0 + j * (HUD_BTN_W + HUD_BTN_GAP)
        if bx <= mx <= bx + HUD_BTN_W and by <= my <= by + HUD_BTN_H:
            if tab == 0:
                cost = BUILD_COST[kind]
                if m['credits'][PLAYER] >= cost:
                    m['mode']       = 'place_building'
                    m['place_type'] = kind
            else:
                _queue_unit_global(world, m, kind)
            return


def _hotkey_produce(world: World, m: dict, key: int) -> None:
    """1–4 hotkeys act on items in the currently active tab."""
    tab   = m.get('hud_tab', 0)
    req   = HUD_TABS[tab][1]
    avail = (req is None) or _has_complete_bldg(world, req)
    if not avail:
        return
    items = HUD_TAB_ITEMS[tab]
    idx   = {pygame.K_1: 0, pygame.K_2: 1, pygame.K_3: 2, pygame.K_4: 3}.get(key)
    if idx is None or idx >= len(items):
        return
    kind = items[idx]
    if tab == 0:
        cost = BUILD_COST[kind]
        if m['credits'][PLAYER] >= cost:
            m['mode']       = 'place_building'
            m['place_type'] = kind
    else:
        _queue_unit_global(world, m, kind)
