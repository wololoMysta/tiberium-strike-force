# client.py – multiplayer pygame client (connects to server via websocket)
import sys
import asyncio
import threading
import queue
import math
import json
import time
import logging

import pygame
import numpy as np

from ecs import World
from config import *
import terrain as ter
from components import (
    Position, Health, Team, UnitData, BuildingData, Selectable,
    Combat, Movement, Harvester, Resource, Vision, Projectile,
    HomingProjectile, UnderConstruction, Wall,
    PowerConsumer, PowerPlant,
)
from systems.render_sys import RenderSys
from systems.rendering import _cfg
import protocol as proto

try:
    import websockets
except ImportError:
    raise SystemExit("Install websockets:  pip install websockets")

logging.basicConfig(level=logging.INFO, format='%(asctime)s [CLIENT] %(message)s')
log = logging.getLogger('client')

# ── Defaults ──────────────────────────────────────────────────────────────────
DEFAULT_HOST = 'localhost'
DEFAULT_PORT = 9876

# ── Client-side interpolation state ───────────────────────────────────────────
_prev_positions: dict[int, tuple[float, float]] = {}   # eid → (x, y) from previous snapshot
_curr_positions: dict[int, tuple[float, float]] = {}   # eid → (x, y) from latest snapshot
_snap_time: float = 0.0       # time.monotonic() when last snapshot arrived
_snap_interval: float = 0.05  # estimated interval between snapshots (adapts)


# ── Network thread ────────────────────────────────────────────────────────────
class NetThread(threading.Thread):
    """Runs an asyncio event loop in a background thread for websocket I/O."""

    def __init__(self, host: str, port: int):
        super().__init__(daemon=True)
        self.host = host
        self.port = port
        self.inbox: queue.Queue = queue.Queue()     # server → client
        self.outbox: queue.Queue = queue.Queue()    # client → server
        self.connected = threading.Event()
        self.stopped = False
        self._ws = None
        self._loop = None

    def run(self):
        asyncio.run(self._ws_loop())

    def request_stop(self):
        """Signal clean shutdown from the main thread."""
        self.stopped = True
        if self._ws and self._loop and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(self._ws.close(), self._loop)

    async def _ws_loop(self):
        uri = f"ws://{self.host}:{self.port}"
        log.info(f"Connecting to {uri} ...")
        try:
            async with websockets.connect(uri, max_size=2**22,
                                           ping_interval=30,
                                           ping_timeout=60,
                                           close_timeout=5) as ws:
                self._ws = ws
                self._loop = asyncio.get_event_loop()
                self.connected.set()
                log.info("Connected!")
                recv_task = asyncio.create_task(self._recv(ws))
                send_task = asyncio.create_task(self._send(ws))
                done, pending = await asyncio.wait(
                    [recv_task, send_task],
                    return_when=asyncio.FIRST_EXCEPTION,
                )
                for task in done:
                    exc = task.exception()
                    if exc:
                        log.error(f"Network task failed: {type(exc).__name__}: {exc}")
                for task in pending:
                    task.cancel()
        except websockets.ConnectionClosed as e:
            log.warning(f"Server closed connection: code={e.code} reason='{e.reason}'")
        except ConnectionRefusedError:
            log.error(f"Connection refused – is the server running at {uri}?")
        except OSError as e:
            log.error(f"Network error: {e}")
        except Exception as e:
            log.error(f"Unexpected connection error: {type(e).__name__}: {e}", exc_info=True)
        finally:
            self.stopped = True
            log.info("Network thread stopped.")

    async def _recv(self, ws):
        try:
            async for raw in ws:
                try:
                    msg = proto.decode(raw)
                    self.inbox.put(msg)
                except (json.JSONDecodeError, KeyError) as e:
                    log.warning(f"Received malformed message from server: {e}")
        except websockets.ConnectionClosed as e:
            log.warning(f"Recv: server closed connection: code={e.code} reason='{e.reason}'")
            self.stopped = True
        except Exception as e:
            log.error(f"Recv: unexpected error: {type(e).__name__}: {e}")
            self.stopped = True

    async def _send(self, ws):
        while not self.stopped:
            try:
                msg = self.outbox.get_nowait()
                await ws.send(proto.encode(msg))
            except queue.Empty:
                await asyncio.sleep(0.001)
            except websockets.ConnectionClosed as e:
                log.warning(f"Send: server closed connection: code={e.code} reason='{e.reason}'")
                self.stopped = True
                break
            except Exception as e:
                log.error(f"Send: unexpected error: {type(e).__name__}: {e}")
                self.stopped = True
                break

    def send(self, msg: dict):
        self.outbox.put(msg)


# ── FX aging (client-local) ──────────────────────────────────────────────────
def _age_fx(world: World, dt: float) -> None:
    fx = world.meta.get('fx', [])
    live = []
    for item in fx:
        item['t'] -= dt
        if item['t'] > 0:
            if 'x' in item:
                item['x'] += item.get('vx', 0) * dt
                item['y'] += item.get('vy', 0) * dt
            live.append(item)
    world.meta['fx'] = live


# ── Input processing (client-local, sends commands to server) ─────────────────
class ClientInput:
    def __init__(self, net: NetThread, my_team: int):
        self.net = net
        self.my_team = my_team
        self._last_click_time: float = 0.0
        self._last_click_eid: int | None = None

    def update(self, world: World, dt: float) -> None:
        meta  = world.meta
        cam   = meta['cam']
        keys  = pygame.key.get_pressed()

        # Camera scroll
        spd = 320.0
        mx, my = pygame.mouse.get_pos()
        edge = 20
        if keys[pygame.K_LEFT]  or mx < edge:            cam[0] -= spd * dt
        if keys[pygame.K_RIGHT] or mx >= W - edge:       cam[0] += spd * dt
        if keys[pygame.K_UP]    or my < edge:            cam[1] -= spd * dt
        if keys[pygame.K_DOWN]  or (HUD_H > 0 and my >= H - HUD_H - edge and my < H - HUD_H):
            cam[1] += spd * dt
        zoom = meta.get('zoom', 1.0)
        vw = W / zoom
        vh = (H - HUD_H) / zoom
        cam[0] = max(0, min(MAP_W * TILE - vw, cam[0]))
        cam[1] = max(0, min(MAP_H * TILE - vh, cam[1]))

        for event in meta.get('events', []):
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    meta['mode']             = 'normal'
                    meta['place_type']       = None
                    meta['sel_bldg']         = None
                    meta['wall_drag_start']  = None
                if event.key == pygame.K_q:
                    meta['hud_tab'] = 0
                if event.key == pygame.K_w:
                    if _has_complete_bldg(world, 'barracks', self.my_team):
                        meta['hud_tab'] = 1
                if event.key == pygame.K_e:
                    if _has_complete_bldg(world, 'factory', self.my_team):
                        meta['hud_tab'] = 2
                self._hotkey_produce(world, meta, event.key)

            elif event.type == pygame.MOUSEBUTTONDOWN:
                self._on_mouse_down(world, meta, event)

            elif event.type == pygame.MOUSEBUTTONUP:
                self._on_mouse_up(world, meta, event)

            elif event.type == pygame.MOUSEWHEEL:
                self._handle_zoom(meta, event)

    def _handle_zoom(self, m: dict, event):
        old_zoom = m.get('zoom', 1.0)
        new_zoom = max(ZOOM_MIN, min(ZOOM_MAX, old_zoom + event.y * ZOOM_STEP))
        if new_zoom == old_zoom:
            return
        mx, my = pygame.mouse.get_pos()
        cam = m['cam']
        wx = mx / old_zoom + cam[0]
        wy = my / old_zoom + cam[1]
        cam[0] = wx - mx / new_zoom
        cam[1] = wy - my / new_zoom
        m['zoom'] = new_zoom
        vw = W / new_zoom
        vh = (H - HUD_H) / new_zoom
        cam[0] = max(0, min(MAP_W * TILE - vw, cam[0]))
        cam[1] = max(0, min(MAP_H * TILE - vh, cam[1]))

    def _on_mouse_down(self, world: World, m: dict, event):
        mx, my = event.pos
        zoom = m.get('zoom', 1.0)
        wx = mx / zoom + m['cam'][0]
        wy = my / zoom + m['cam'][1]

        if my >= H - HUD_H:
            self._handle_hud_click(world, m, mx, my)
            return

        if event.button == 1:
            if m['mode'] == 'place_building':
                kind = m['place_type']
                if kind == 'wall':
                    snap = TILE
                    m['wall_drag_start'] = (
                        round(wx / snap) * snap,
                        round(wy / snap) * snap,
                    )
                else:
                    self._try_place_building(world, m, wx, wy)
                return
            m['sel_start'] = (mx, my)
            m['sel_box']   = None

        elif event.button == 3:
            m['mode'] = 'normal'
            m['place_type'] = None
            self._right_click(world, m, wx, wy)

    def _on_mouse_up(self, world: World, m: dict, event):
        if event.button != 1:
            return
        zoom = m.get('zoom', 1.0)
        # ── Wall drag: place the whole line ──────────────────────────────
        drag = m['wall_drag_start']
        m['wall_drag_start'] = None
        if drag is not None:
            mx, my = event.pos
            wx = mx / zoom + m['cam'][0]
            wy = my / zoom + m['cam'][1]
            for cx, cy in _wall_line_centers(drag[0], drag[1], wx, wy):
                self._try_place_building(world, m, cx, cy)
            return
        mx, my = event.pos
        start  = m.pop('sel_start', None)
        if start is None:
            return
        sx, sy  = start
        dx, dy  = abs(mx - sx), abs(my - sy)
        cam     = m['cam']

        if dx < 4 and dy < 4:
            wx = mx / zoom + cam[0]
            wy = my / zoom + cam[1]
            clicked = _unit_at(world, wx, wy, self.my_team)
            now = pygame.time.get_ticks() / 1000.0

            # Double-click on MCV → deploy
            if (clicked is not None
                    and clicked == self._last_click_eid
                    and now - self._last_click_time < 0.35):
                ud = world.get(clicked, UnitData)
                if ud and ud.kind == 'mcv':
                    m['selected'] = {clicked}
                    self._deploy_mcv(world, m)
                    self._last_click_eid = None
                    return

            self._last_click_time = now
            self._last_click_eid = clicked

            mods = pygame.key.get_mods()
            if not (mods & pygame.KMOD_SHIFT):
                _deselect_all(world, m)
            if clicked is not None:
                sel = world.get(clicked, Selectable)
                if sel is None:
                    world.add(clicked, Selectable(True))
                else:
                    sel.selected = True
                m['selected'].add(clicked)
                bd = world.get(clicked, BuildingData)
                m['sel_bldg'] = clicked if bd else None
            else:
                m['sel_bldg'] = None
        else:
            x1 = min(sx, mx) / zoom + cam[0]
            y1 = min(sy, my) / zoom + cam[1]
            x2 = max(sx, mx) / zoom + cam[0]
            y2 = max(sy, my) / zoom + cam[1]
            mods = pygame.key.get_mods()
            if not (mods & pygame.KMOD_SHIFT):
                _deselect_all(world, m)
            _box_select(world, m, x1, y1, x2, y2, self.my_team)

        m['sel_box'] = None

    def _right_click(self, world: World, m: dict, wx: float, wy: float):
        if not m['selected']:
            return
        target_eid = _enemy_at(world, wx, wy, self.my_team)
        units = list(m['selected'])

        if target_eid is not None:
            self.net.send(proto.make_cmd('attack_move',
                                         eids=units, tx=wx, ty=wy,
                                         target=target_eid))
        else:
            self.net.send(proto.make_cmd('move', eids=units, tx=wx, ty=wy))

        m['fx'].append({'kind': 'click', 'x': wx, 'y': wy, 't': 0.5})

    def _try_place_building(self, world: World, m: dict, wx: float, wy: float):
        kind = m['place_type']
        if kind is None:
            return
        # Client-side influence check (server enforces authoritatively)
        if not _in_influence(world, wx, wy, self.my_team):
            return
        self.net.send(proto.make_cmd('place_building', kind=kind, x=wx, y=wy))
        if kind != 'wall':
            m['mode']       = 'normal'
            m['place_type'] = None

    def _deploy_mcv(self, world: World, m: dict):
        """Send deploy command for a selected MCV."""
        for eid in list(m.get('selected', set())):
            ud = world.get(eid, UnitData)
            team = world.get(eid, Team)
            if ud and team and ud.kind == 'mcv' and team.id == self.my_team:
                self.net.send(proto.make_cmd('deploy_mcv', eid=eid))
                m['selected'].discard(eid)
                m['sel_bldg'] = None
                break

    def _handle_hud_click(self, world: World, m: dict, mx: int, my: int):
        panel_y = H - HUD_H
        credits = m['credits']

        # Minimap click (upper-left corner)
        mini_x = 6
        mini_y = 6
        if mini_x <= mx <= mini_x + MINI and mini_y <= my <= mini_y + MINI:
            rx = (mx - mini_x) / MINI
            ry = (my - mini_y) / MINI
            cam = m['cam']
            zoom = m.get('zoom', 1.0)
            cvw = W / zoom
            cvh = (H - HUD_H) / zoom
            cam[0] = max(0, min(MAP_W * TILE - cvw, rx * MAP_W * TILE - cvw / 2))
            cam[1] = max(0, min(MAP_H * TILE - cvh,
                                ry * MAP_H * TILE - cvh / 2))
            return

        # Tab header clicks
        for i, (label, req) in enumerate(HUD_TABS):
            tx = HUD_TAB_X + i * HUD_TAB_W
            ty = panel_y + 4
            tw, th = HUD_TAB_W - 2, HUD_TAB_H
            if tx <= mx <= tx + tw and ty <= my <= ty + th:
                avail_i = (req is None) or _has_complete_bldg(world, req,
                                                               self.my_team)
                if avail_i:
                    m['hud_tab'] = i
                return

        # Content button clicks
        tab = m.get('hud_tab', 0)
        req = HUD_TABS[tab][1]
        if req is not None and not _has_complete_bldg(world, req, self.my_team):
            return

        cy0  = panel_y + 4 + HUD_TAB_H
        bx0  = HUD_TAB_X + 4
        by   = cy0 + 3
        items = HUD_TAB_ITEMS[tab]
        for j, kind in enumerate(items):
            bx = bx0 + j * (HUD_BTN_W + HUD_BTN_GAP)
            if bx <= mx <= bx + HUD_BTN_W and by <= my <= by + HUD_BTN_H:
                if tab == 0:
                    cost = BUILD_COST[kind]
                    if credits[self.my_team] >= cost:
                        m['mode']       = 'place_building'
                        m['place_type'] = kind
                else:
                    self._queue_unit(world, m, kind)
                return

    def _queue_unit(self, world: World, m: dict, unit_kind: str):
        self.net.send(proto.make_cmd('queue_unit', kind=unit_kind))

    def _hotkey_produce(self, world: World, m: dict, key: int):
        tab   = m.get('hud_tab', 0)
        req   = HUD_TABS[tab][1]
        avail = (req is None) or _has_complete_bldg(world, req, self.my_team)
        if not avail:
            return
        items = HUD_TAB_ITEMS[tab]
        idx   = {pygame.K_1: 0, pygame.K_2: 1, pygame.K_3: 2,
                 pygame.K_4: 3}.get(key)
        if idx is None or idx >= len(items):
            return
        kind = items[idx]
        credits = m['credits']
        if tab == 0:
            cost = BUILD_COST[kind]
            if credits[self.my_team] >= cost:
                m['mode']       = 'place_building'
                m['place_type'] = kind
        else:
            self._queue_unit(world, m, kind)


# ── Helpers ───────────────────────────────────────────────────────────────────
def _unit_at(world: World, wx: float, wy: float, my_team: int):
    best, best_d = None, 9999.0
    for eid, pos, team in world.q(Position, Team):
        if team.id != my_team:
            continue
        bd = world.get(eid, BuildingData)
        if bd:
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


def _deselect_all(world: World, m: dict):
    for eid in list(m['selected']):
        sel = world.get(eid, Selectable)
        if sel:
            sel.selected = False
    m['selected'].clear()
    m['sel_bldg'] = None


def _box_select(world: World, m: dict,
                x1: float, y1: float, x2: float, y2: float,
                my_team: int):
    for eid, pos, team in world.q(Position, Team):
        if team.id != my_team:
            continue
        ud = world.get(eid, UnitData)
        if ud is None:
            continue
        if x1 <= pos.x <= x2 and y1 <= pos.y <= y2:
            sel = world.get(eid, Selectable)
            if sel is None:
                world.add(eid, Selectable(True))
            else:
                sel.selected = True
            m['selected'].add(eid)


def _enemy_at(world: World, wx: float, wy: float, my_team: int):
    best, best_d = None, 9999.0
    for eid, pos, team in world.q(Position, Team):
        if team.id == my_team:
            continue
        ud = world.get(eid, UnitData)
        bd = world.get(eid, BuildingData)
        r  = ud.radius if ud else (max(bd.w, bd.h) // 2 if bd else 20)
        d  = math.hypot(pos.x - wx, pos.y - wy)
        if d < r + 6 and d < best_d:
            best, best_d = eid, d
    return best


def _has_complete_bldg(world: World, kind: str, my_team: int) -> bool:
    for eid, bd, t in world.q(BuildingData, Team):
        if t.id == my_team and bd.kind == kind:
            if not world.get(eid, UnderConstruction):
                return True
    return False


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
    """Return True if (wx, wy) is inside any friendly building's influence radius."""
    for _eid, pos, team, bd in world.q(Position, Team, BuildingData):
        if team.id != team_id:
            continue
        bx = pos.x + bd.w / 2
        by = pos.y + bd.h / 2
        r  = INFLUENCE_RADIUS.get(bd.kind, 200)
        if math.hypot(bx - wx, by - wy) <= r:
            return True
    return False


# ── Main client ───────────────────────────────────────────────────────────────
def main(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> None:
    pygame.init()
    screen = pygame.display.set_mode((W, H))
    pygame.display.set_caption(f"{TITLE}  ·  Multiplayer")
    clock  = pygame.time.Clock()

    font       = pygame.font.SysFont('consolas', 16, bold=True)
    small_font = pygame.font.SysFont('consolas', 13)
    big_font   = pygame.font.SysFont('consolas', 48, bold=True)

    # ── Show "connecting" screen ──────────────────────────────────────────────
    screen.fill((4, 8, 4))
    msg = font.render(f"Connecting to {host}:{port} ...", True, (0, 220, 60))
    screen.blit(msg, (W // 2 - msg.get_width() // 2, H // 2))
    pygame.display.flip()

    # Start network thread
    net = NetThread(host, port)
    net.start()
    net.connected.wait(timeout=10)
    if not net.connected.is_set():
        log.error("Could not connect to server")
        pygame.quit()
        sys.exit(1)

    # Wait for init message
    my_team = 0
    tiles = None
    while tiles is None:
        try:
            msg = net.inbox.get(timeout=5)
            if msg['type'] == 'init':
                my_team = msg['team']
                tiles   = msg['tiles']
                log.info(f"Assigned team {my_team}")
        except queue.Empty:
            log.error("No init message from server")
            pygame.quit()
            sys.exit(1)

    # Patch render_sys to treat our team as the "player" colour
    _cfg.PLAYER = my_team
    _cfg.ENEMY  = 1 - my_team

    # Build client-side world for rendering
    _, height = ter.generate(42)
    tsurf = ter.build_surface(tiles, height)
    mini_surf = ter.build_minimap_surf(tiles, height)

    world = World()
    cam_start = [0.0, 0.0]
    if my_team == 0:
        cam_start = [max(0, 480 - W // 2), max(0, 420 - (H - HUD_H) // 2)]
    else:
        ex = MAP_W * TILE - 600
        ey = MAP_H * TILE - 600
        cam_start = [max(0, ex + 40 - W // 2), max(0, ey + 40 - (H - HUD_H) // 2)]

    world.meta = {
        'tiles':        tiles,
        'credits':      [CREDITS_START, CREDITS_START],
        'cam':          cam_start,
        'selected':     set(),
        'sel_bldg':     None,
        'sel_start':    None,
        'sel_box':      None,
        'mode':         'normal',
        'place_type':   None,
        'wall_drag_start': None,
        'power_ratio_0': 1.0,
        'power_demand_0': 0,
        'power_supply_0': 0,
        'fog':          np.zeros((MAP_H, MAP_W), dtype=np.uint8),
        'fx':           [],
        'events':       [],
        'game_over':    None,
        'time':         0.0,
        'hud_tab':      0,
        'zoom':         1.0,
        'terrain_surf': tsurf,
        'mini_surf':    mini_surf,
    }

    # Patch render_sys to use our team for HUD display
    # The render system reads PLAYER constant for team coloring.
    # We'll use a wrapper to temporarily set PLAYER = my_team
    render   = RenderSys(screen, tsurf, font, small_font, big_font, clock)
    client_input = ClientInput(net, my_team)

    # Wait for the first snapshot so the world is populated before rendering
    log.info("Waiting for first snapshot...")
    first_snap = None
    deadline = time.monotonic() + 10
    while first_snap is None and time.monotonic() < deadline:
        try:
            msg = net.inbox.get(timeout=0.5)
            if msg['type'] == 'snapshot':
                first_snap = msg
        except queue.Empty:
            pass
        # Keep processing pygame events so the window stays responsive
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                net.request_stop(); pygame.quit(); sys.exit()
    if first_snap is not None:
        _apply_snapshot_preserve_local(world, first_snap, my_team)
    else:
        log.warning("No snapshot received within timeout")

    log.info("Entering game loop")

    while True:
        try:
            dt     = clock.tick(FPS) / 1000.0
            dt     = min(dt, 0.05)
            events = pygame.event.get()
            world.meta['events'] = events

            for ev in events:
                if ev.type == pygame.QUIT:
                    net.request_stop(); pygame.quit(); sys.exit()
                if ev.type == pygame.KEYDOWN:
                    if ev.key == pygame.K_ESCAPE and world.meta.get('game_over'):
                        net.request_stop(); pygame.quit(); sys.exit()

            # Drain network inbox → apply only the latest snapshot (skip stale ones)
            latest_snap = None
            while not net.inbox.empty():
                try:
                    msg = net.inbox.get_nowait()
                    if msg['type'] == 'snapshot':
                        latest_snap = msg   # keep overwriting; only latest matters
                except queue.Empty:
                    break

            if latest_snap is not None:
                _apply_snapshot_preserve_local(world, latest_snap, my_team)

            if net.stopped:
                log.error("Lost connection to server – shutting down client.")
                screen.fill((4, 8, 4))
                dc = font.render("Disconnected from server", True, (255, 60, 30))
                screen.blit(dc, (W // 2 - dc.get_width() // 2, H // 2))
                pygame.display.flip()
                pygame.time.wait(3000)
                net.request_stop(); pygame.quit(); sys.exit()

            # Client-local input
            client_input.update(world, dt)

            # Age local FX
            _age_fx(world, dt)

            # Interpolate entity positions between snapshots for smooth rendering
            _interpolate_positions(world)

            # Render
            render.update(world, dt)

            # Restore authoritative positions so next snapshot diff is correct
            _restore_positions(world)
        except Exception:
            log.exception("CRASH in game loop")
            import traceback; traceback.print_exc()
            input("Press ENTER to close...")
            pygame.quit(); sys.exit(1)


def _interpolate_positions(world: World) -> None:
    """Lerp entity positions between prev/curr snapshot for smooth rendering."""
    global _prev_positions, _curr_positions, _snap_time, _snap_interval
    if not _curr_positions:
        return
    elapsed = time.monotonic() - _snap_time
    t = min(1.0, elapsed / _snap_interval) if _snap_interval > 0 else 1.0
    for eid, (cx, cy) in _curr_positions.items():
        pos = world.get(eid, Position)
        if pos is None:
            continue
        prev = _prev_positions.get(eid)
        if prev is None:
            continue
        px, py = prev
        # Don't interpolate if the jump is huge (respawn / teleport)
        if abs(cx - px) > 200 or abs(cy - py) > 200:
            continue
        pos.x = px + (cx - px) * t
        pos.y = py + (cy - py) * t


def _restore_positions(world: World) -> None:
    """Restore authoritative (latest snapshot) positions after rendering."""
    for eid, (cx, cy) in _curr_positions.items():
        pos = world.get(eid, Position)
        if pos is not None:
            pos.x = cx
            pos.y = cy


def _apply_snapshot_preserve_local(world: World, snap: dict, my_team: int):
    """Apply server snapshot but preserve client-local state (cam, selection, etc.)."""
    global _prev_positions, _curr_positions, _snap_time, _snap_interval

    sel_backup  = world.meta.get('selected', set()).copy()
    sel_bldg    = world.meta.get('sel_bldg')

    # Capture previous positions before overwriting
    _prev_positions = _curr_positions.copy()

    proto.apply_snapshot(world, snap, my_team)

    # Capture new authoritative positions
    new_pos: dict[int, tuple[float, float]] = {}
    for eid in world._live:
        pos = world.get(eid, Position)
        if pos is not None:
            new_pos[eid] = (pos.x, pos.y)
    _curr_positions = new_pos

    # Update snapshot timing for interpolation
    now = time.monotonic()
    if _snap_time > 0:
        dt = now - _snap_time
        if 0.01 < dt < 0.5:
            _snap_interval = _snap_interval * 0.7 + dt * 0.3  # smooth adaptation
    _snap_time = now

    # Restore client-local state
    world.meta['selected'] = sel_backup
    if world.meta.get('sel_bldg') is None:
        world.meta['sel_bldg'] = sel_bldg

    # Re-apply Selectable markers from local selection
    for eid in sel_backup:
        sel = world.get(eid, Selectable)
        if sel is None:
            if eid in world._live:
                world.add(eid, Selectable(True))
        else:
            sel.selected = True

    # Purge dead eids from selection
    world.meta['selected'] = {e for e in world.meta['selected'] if e in world._live}


if __name__ == '__main__':
    import argparse, traceback
    parser = argparse.ArgumentParser(description='Tiberium Strike Force – MP Client')
    parser.add_argument('--host', default=DEFAULT_HOST, help='Server host')
    parser.add_argument('--port', type=int, default=DEFAULT_PORT, help='Server port')
    args = parser.parse_args()
    try:
        main(args.host, args.port)
    except Exception:
        traceback.print_exc()
        input("Press ENTER to close...")
