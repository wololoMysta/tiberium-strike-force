# server.py – authoritative multiplayer game server (websocket)
import asyncio
import time
import json
import logging
import numpy as np

from ecs import World
from config import *
import terrain as ter
import entities as ent
from components import (
    AIController, Team, Position, UnitData, Movement, Combat,
    BuildingData, UnderConstruction, Health, Vision, Harvester,
    Selectable, Resource,
)
from systems.move_sys    import MoveSys
from systems.combat_sys  import CombatSys
from systems.harvest_sys import HarvestSys
from systems.effects_sys import EffectsSys
from systems.tib_sys     import TibSys
from systems.power_sys   import PowerSys
import protocol as proto


def _in_influence(world: World, wx: float, wy: float, team_id: int) -> bool:
    """Return True if (wx, wy) is within any building of team_id's influence."""
    import math
    for _eid, pos, team, bd in world.q(Position, Team, BuildingData):
        if team.id != team_id:
            continue
        bx = pos.x + bd.w / 2
        by = pos.y + bd.h / 2
        r  = INFLUENCE_RADIUS.get(bd.kind, 200)
        if math.hypot(bx - wx, by - wy) <= r:
            return True
    return False

try:
    import websockets
    from websockets.asyncio.server import serve
except ImportError:
    raise SystemExit("Install websockets:  pip install websockets")

logging.basicConfig(level=logging.INFO, format='%(asctime)s [SERVER] %(message)s')
log = logging.getLogger('server')

# ── Network config ────────────────────────────────────────────────────────────
HOST = '0.0.0.0'
PORT = 9876
MAX_PLAYERS   = 2
SNAPSHOT_RATE = 30          # snapshots per second (was 20)
TICK_RATE     = 60          # simulation ticks per second


# ── Server-side fog update (supports any team) ────────────────────────────────
def _update_fog_for_team(world: World, fog: np.ndarray, team_id: int) -> None:
    fog[fog == 2] = 1
    for _eid, pos, vis, team in world.q(Position, Vision, Team):
        if team.id != team_id:
            continue
        tx  = int(pos.x // TILE)
        ty  = int(pos.y // TILE)
        tr  = int(vis.radius // TILE) + 1
        tr2 = tr * tr
        y0  = max(0, ty - tr)
        y1  = min(MAP_H, ty + tr + 1)
        x0  = max(0, tx - tr)
        x1  = min(MAP_W, tx + tr + 1)
        for gy in range(y0, y1):
            for gx in range(x0, x1):
                if (gx - tx) ** 2 + (gy - ty) ** 2 <= tr2:
                    fog[gy, gx] = 2


# ── World bootstrap (2-player, no AI) ────────────────────────────────────────
def build_mp_world(seed: int = 42) -> World:
    import random
    world = World()
    rng   = random.Random(seed)

    tiles, height = ter.generate(seed)
    # No terrain surface needed on server (headless)

    world.meta = {
        'tiles':     tiles,
        'credits':   [CREDITS_START, CREDITS_START],
        'time':      0.0,
        'game_over': None,
        'fx':        [],
        '_new_fx':   [],      # accumulated per snapshot interval
        'events':    [],      # unused on server
        'selected':  set(),   # needed by _reap_dead in combat_sys
        'sel_bldg':  None,
        'power_ratio_0': 1.0, 'power_demand_0': 0, 'power_supply_0': 0,
        'power_ratio_1': 1.0, 'power_demand_1': 0, 'power_supply_1': 0,
    }

    # ── Player 0 start (NW) ──────────────────────────────────────────────────
    ent.spawn_unit(world, 480, 420, 0, 'mcv')
    for cx, cy in ((800, 560), (950, 480), (700, 320)):
        ent.place_tiberium_field(world, cx, cy, count=14, radius=90,
                                 seed=rng.randint(0, 999))

    # ── Player 1 start (SE) ──────────────────────────────────────────────────
    ex = MAP_W * TILE - 600
    ey = MAP_H * TILE - 600
    ent.spawn_unit(world, ex + 40, ey + 40, 1, 'mcv')
    for cx, cy in ((ex - 200, ey - 180), (ex + 100, ey - 250)):
        ent.place_tiberium_field(world, cx, cy, count=12, radius=80,
                                 seed=rng.randint(0, 999))

    # ── Mid-map tiberium ──────────────────────────────────────────────────────
    mid = MAP_W * TILE // 2
    for cx, cy in ((mid, mid - 200), (mid - 300, mid + 100), (mid + 280, mid)):
        ent.place_tiberium_field(world, cx, cy, count=10, radius=80,
                                 seed=rng.randint(0, 999))

    return world


# ── Command processing ────────────────────────────────────────────────────────
def _process_cmd(world: World, team_id: int, msg: dict) -> None:
    cmd = msg.get('cmd', '')

    if cmd == 'move':
        eids = msg.get('eids', [])
        tx, ty = msg.get('tx', 0), msg.get('ty', 0)
        for i, eid in enumerate(eids):
            team_c = world.get(eid, Team)
            if team_c is None or team_c.id != team_id:
                continue
            mv = world.get(eid, Movement)
            cb = world.get(eid, Combat)
            if mv is None:
                continue
            row = i // 4
            col = i % 4
            ox  = (col - 1.5) * 28
            oy  = row * 28
            mv.tx = tx + ox
            mv.ty = ty + oy
            mv.attack_move = False
            if cb:
                cb.target = None

    elif cmd == 'attack_move':
        eids = msg.get('eids', [])
        tx, ty = msg.get('tx', 0), msg.get('ty', 0)
        target = msg.get('target')
        for i, eid in enumerate(eids):
            team_c = world.get(eid, Team)
            if team_c is None or team_c.id != team_id:
                continue
            mv = world.get(eid, Movement)
            cb = world.get(eid, Combat)
            if mv is None:
                continue
            row = i // 4
            col = i % 4
            ox  = (col - 1.5) * 28
            oy  = row * 28
            mv.tx = tx + ox
            mv.ty = ty + oy
            mv.attack_move = True
            if cb and target is not None:
                cb.target = target

    elif cmd == 'queue_unit':
        kind = msg.get('kind', '')
        if kind not in UDAT:
            return
        cost = UDAT[kind][6]
        credits = world.meta['credits']
        if credits[team_id] < cost:
            return
        req = None
        for bk, ulist in PROD_MENU.items():
            if kind in ulist:
                req = bk
                break
        if req is None:
            return
        # Find least-busy matching building
        best, best_qlen = None, 999
        for eid, bd, t in world.q(BuildingData, Team):
            if t.id != team_id or bd.kind != req:
                continue
            if world.get(eid, UnderConstruction):
                continue
            if len(bd.prod_queue) < best_qlen:
                best, best_qlen = eid, len(bd.prod_queue)
        if best is None:
            return
        credits[team_id] -= cost
        world.get(best, BuildingData).prod_queue.append(
            [kind, PROD_TIME[kind]])

    elif cmd == 'place_building':
        kind = msg.get('kind', '')
        wx, wy = msg.get('x', 0), msg.get('y', 0)
        if kind not in BUILD_COST:
            return
        cost = BUILD_COST[kind]
        credits = world.meta['credits']
        if credits[team_id] < cost:
            return
        _, bw, bh = BDAT[kind]
        cx = wx - bw // 2
        cy = wy - bh // 2
        if not ter.can_place_building(world, world.meta['tiles'], wx, wy, kind, team_id):
            return
        if not _in_influence(world, wx, wy, team_id):
            return
        credits[team_id] -= cost
        ent.spawn_building(world, cx, cy, team_id, kind, complete=False)

    elif cmd == 'deploy_mcv':
        eid = msg.get('eid')
        if eid is None:
            return
        team_c = world.get(eid, Team)
        ud = world.get(eid, UnitData)
        pos = world.get(eid, Position)
        if not (team_c and ud and pos and team_c.id == team_id and ud.kind == 'mcv'):
            return
        _, bw, bh = BDAT['base']
        cx = pos.x - bw // 2
        cy = pos.y - bh // 2
        ent.spawn_building(world, cx, cy, team_id, 'base', complete=False)
        world.kill(eid)


# ── FX tracker (captures new appends to the fx list) ─────────────────────────
class _FxTracker(list):
    def __init__(self, initial):
        super().__init__(initial)
        self.new_items: list = []

    def append(self, item):
        super().append(item)
        self.new_items.append(item)


# ── Server class ──────────────────────────────────────────────────────────────
class GameServer:
    def __init__(self):
        self.world: World | None = None
        self.clients: dict[int, object] = {}   # team_id → websocket
        self.cmd_queue: list[tuple[int, dict]] = []
        self.fogs: dict[int, np.ndarray] = {}
        self.running = False

    async def handler(self, websocket):
        # Assign team
        team_id = len(self.clients)
        if team_id >= MAX_PLAYERS:
            await websocket.send(proto.encode({'type': 'error', 'msg': 'Server full'}))
            await websocket.close()
            return

        self.clients[team_id] = websocket
        log.info(f"Player {team_id} connected from {websocket.remote_address}")

        # Send init data
        init_msg = proto.build_init_msg(self.world, team_id)
        await websocket.send(proto.encode(init_msg))
        log.info(f"Sent init data to player {team_id}")

        try:
            async for raw in websocket:
                try:
                    msg = proto.decode(raw)
                    if msg.get('type') == 'cmd':
                        self.cmd_queue.append((team_id, msg))
                except (json.JSONDecodeError, KeyError) as e:
                    log.warning(f"Player {team_id}: malformed message – {e}")
        except websockets.ConnectionClosed as e:
            reason_text = {
                1000: 'normal close',
                1001: 'going away (client closed window)',
                1002: 'protocol error',
                1006: 'abnormal closure (no close frame)',
            }.get(e.code, 'unknown')
            log.warning(f"Player {team_id} disconnected: code={e.code} ({reason_text}) reason='{e.reason}'")
        except Exception as e:
            log.error(f"Player {team_id} handler crashed: {type(e).__name__}: {e}", exc_info=True)
        finally:
            log.info(f"Player {team_id} disconnected (cleaning up)")
            self.clients.pop(team_id, None)
            proto.reset_snap_cache(team_id)

    async def game_loop(self):
        world = self.world
        # Server systems: everything except Input and Render
        systems = [MoveSys(), CombatSys(), HarvestSys(), EffectsSys(), TibSys(), PowerSys()]

        tick_dt = 1.0 / TICK_RATE
        snap_interval = 1.0 / SNAPSHOT_RATE
        snap_accum = 0.0
        pending_fx: list = []   # new fx accumulated between snapshots

        log.info(f"Game loop started  tick={TICK_RATE}Hz  snapshot={SNAPSHOT_RATE}Hz")
        log.info(f"Waiting for players to connect on ws://{HOST}:{PORT} ...")

        while self.running:
            t0 = time.monotonic()

            # Process commands
            while self.cmd_queue:
                team_id, msg = self.cmd_queue.pop(0)
                _process_cmd(world, team_id, msg)

            # Install fx tracker to capture newly generated fx
            tracker = _FxTracker(world.meta.get('fx', []))
            world.meta['fx'] = tracker

            # Run simulation
            if not world.meta.get('game_over'):
                world.meta['time'] += tick_dt
                for sys in systems:
                    sys.update(world, tick_dt)

            # Collect new fx from this tick
            pending_fx.extend(tracker.new_items)

            # Update per-team fog
            for team_id in range(MAX_PLAYERS):
                if team_id not in self.fogs:
                    self.fogs[team_id] = np.zeros((MAP_H, MAP_W), dtype=np.uint8)
                _update_fog_for_team(world, self.fogs[team_id], team_id)

            # Send snapshots at SNAPSHOT_RATE
            snap_accum += tick_dt
            if snap_accum >= snap_interval and self.clients:
                snap_accum = 0.0
                world.meta['_new_fx'] = pending_fx

                # Build and send snapshots concurrently
                async def _send_snap(tid, ws):
                    try:
                        fog = self.fogs.get(tid,
                                            np.zeros((MAP_H, MAP_W), dtype=np.uint8))
                        snap = proto.build_snapshot(world, tid, fog)
                        await ws.send(proto.encode(snap))
                    except websockets.ConnectionClosed as e:
                        log.warning(f"Snapshot send failed – player {tid} connection closed: code={e.code}")
                        self.clients.pop(tid, None)
                        proto.reset_snap_cache(tid)
                    except Exception as e:
                        log.error(f"Snapshot send failed for player {tid}: {type(e).__name__}: {e}")

                tasks = [_send_snap(tid, ws) for tid, ws in list(self.clients.items())]
                if tasks:
                    await asyncio.gather(*tasks)
                pending_fx = []

            elapsed = time.monotonic() - t0
            await asyncio.sleep(max(0, tick_dt - elapsed))

    async def run(self):
        self.world = build_mp_world()
        self.running = True

        # Override _update_fog in EffectsSys to be a no-op (we handle it ourselves)
        import systems.effects_sys as efx
        efx._update_fog = lambda world: None

        async with serve(self.handler, HOST, PORT,
                         max_size=2**22,
                         ping_interval=30,
                         ping_timeout=60,
                         close_timeout=5):
            log.info(f"Listening on ws://{HOST}:{PORT}")
            await self.game_loop()


def main():
    server = GameServer()
    try:
        asyncio.run(server.run())
    except KeyboardInterrupt:
        log.info("Server stopped by KeyboardInterrupt.")
    except Exception as e:
        log.critical(f"Server crashed: {type(e).__name__}: {e}", exc_info=True)
        import traceback; traceback.print_exc()
        input("Press ENTER to close...")
        raise


if __name__ == '__main__':
    main()
