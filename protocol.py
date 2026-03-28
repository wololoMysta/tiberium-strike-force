# protocol.py – network message serialisation for multiplayer
import json
import zlib
import math
import numpy as np

from ecs import World
from components import (
    Position, Health, Team, UnitData, BuildingData, Selectable,
    Combat, Movement, Harvester, Resource, Vision, Projectile,
    HomingProjectile, UnderConstruction, AIController, Wall,
    PowerConsumer, PowerPlant,
)
from config import MAP_W, MAP_H, TILE, PLAYER

# ── Component registry (name ↔ class) ────────────────────────────────────────
_COMP_CLASSES = {
    'Position': Position,
    'Health': Health,
    'Team': Team,
    'UnitData': UnitData,
    'BuildingData': BuildingData,
    'Combat': Combat,
    'Movement': Movement,
    'Harvester': Harvester,
    'Resource': Resource,
    'Vision': Vision,
    'Projectile': Projectile,
    'HomingProjectile': HomingProjectile,
    'UnderConstruction': UnderConstruction,
    'Wall': Wall,
    'PowerConsumer': PowerConsumer,
    'PowerPlant': PowerPlant,
}

# Components we serialise for network (skip AIController, Selectable)
_NET_COMPONENTS = list(_COMP_CLASSES.values())


# ── Serialise a single component → dict ──────────────────────────────────────
def _comp_to_dict(comp) -> dict:
    d = {}
    for f in comp.__dataclass_fields__:
        v = getattr(comp, f)
        if isinstance(v, float):
            d[f] = round(v, 2)
        elif isinstance(v, list):
            d[f] = [round(item, 2) if isinstance(item, float) else
                    list(item) if isinstance(item, list) else item
                    for item in v]
        else:
            d[f] = v
    return d


def _dict_to_comp(cls, d: dict):
    return cls(**d)


# ── Fog encoding (zlib compressed) ────────────────────────────────────────────
def encode_fog(fog: np.ndarray) -> str:
    """Compress fog array with zlib, then latin-1 escape for JSON embedding."""
    compressed = zlib.compress(fog.tobytes(), level=1)
    # Use base85 which is more compact than base64 and JSON-safe
    import base64
    return base64.b85encode(compressed).decode('ascii')


def decode_fog(data: str) -> np.ndarray:
    import base64
    compressed = base64.b85decode(data.encode('ascii'))
    raw = zlib.decompress(compressed)
    return np.frombuffer(raw, dtype=np.uint8).reshape((MAP_H, MAP_W)).copy()


# ── Snapshot: server → client ─────────────────────────────────────────────────

# Per-team caches for delta snapshots
_last_snap_data: dict[int, dict] = {}   # team → {eid_str: {comp_name: comp_dict}}
_last_snap_eids: dict[int, set]  = {}   # team → set of eid strings

def reset_snap_cache(team: int) -> None:
    """Clear delta cache for a team (call on disconnect)."""
    _last_snap_data.pop(team, None)
    _last_snap_eids.pop(team, None)


def build_snapshot(world: World, for_team: int, fog: np.ndarray) -> dict:
    """Serialise only changed/new entities + removed eids as a delta snapshot."""
    prev_data = _last_snap_data.get(for_team, {})
    prev_eids = _last_snap_eids.get(for_team, set())

    current_entities = {}
    current_eids = set()

    for eid in list(world._live):
        pos = world.get(eid, Position)
        team = world.get(eid, Team)

        # Filter by fog visibility for enemy entities
        if pos and team and team.id != for_team:
            tx = int(pos.x // TILE)
            ty = int(pos.y // TILE)
            if 0 <= tx < MAP_W and 0 <= ty < MAP_H:
                if fog[ty, tx] < 2:
                    bd = world.get(eid, BuildingData)
                    if not bd or fog[ty, tx] == 0:
                        continue

        comps = {}
        for name, cls in _COMP_CLASSES.items():
            c = world.get(eid, cls)
            if c is not None:
                comps[name] = _comp_to_dict(c)
        if comps:
            eid_str = str(eid)
            current_eids.add(eid_str)
            current_entities[eid_str] = comps

    # Compute delta: only entities that are new or changed
    delta_entities = {}
    for eid_str, comps in current_entities.items():
        prev = prev_data.get(eid_str)
        if prev is None or prev != comps:
            delta_entities[eid_str] = comps

    # Compute removed eids
    removed = list(prev_eids - current_eids)

    # Cache for next delta
    _last_snap_data[for_team] = current_entities
    _last_snap_eids[for_team] = current_eids

    snap = {
        'type': 'snapshot',
        'delta': delta_entities,
        'removed': removed,
        'credits': list(world.meta['credits']),
        'time': round(world.meta['time'], 2),
        'fog': encode_fog(fog),
        'new_fx': world.meta.get('_new_fx', []),
        'power_ratio':  round(world.meta.get(f'power_ratio_{for_team}',  1.0), 3),
        'power_supply': world.meta.get(f'power_supply_{for_team}', 0),
        'power_demand': world.meta.get(f'power_demand_{for_team}', 0),
    }
    go = world.meta.get('game_over')
    if go:
        snap['game_over'] = go
    return snap


def apply_snapshot(world: World, snap: dict, local_team: int) -> None:
    """Update a client-side World from a delta server snapshot."""

    # Handle delta format
    delta_data = snap.get('delta', {})
    removed = snap.get('removed', [])

    # Handle legacy full-snapshot format (backwards compat)
    if 'entities' in snap:
        delta_data = snap['entities']
        removed = []  # full snapshot implies we rebuild everything
        # Remove entities not in full snapshot
        snap_eids = set(int(e) for e in delta_data.keys())
        stale = world._live - snap_eids
        for eid in stale:
            world.kill(eid)

    # Apply changed/new entities
    for eid_str, comps in delta_data.items():
        eid = int(eid_str)
        if eid not in world._live:
            world._live.add(eid)
            world._nxt = max(world._nxt, eid + 1)

        for name, data in comps.items():
            cls = _COMP_CLASSES.get(name)
            if cls is None:
                continue
            comp = _dict_to_comp(cls, data)
            world._store.setdefault(cls, {})[eid] = comp

        # Remove components the server no longer has for this entity
        for name, cls in _COMP_CLASSES.items():
            if name not in comps:
                store = world._store.get(cls)
                if store and eid in store:
                    del store[eid]

    # Remove deleted entities
    for eid_str in removed:
        eid = int(eid_str)
        if eid in world._live:
            world.kill(eid)

    # Update meta
    world.meta['credits'] = snap['credits']
    world.meta['time'] = snap['time']
    world.meta['game_over'] = snap.get('game_over')
    world.meta['fog'] = decode_fog(snap['fog'])
    world.meta['power_ratio_0']  = snap.get('power_ratio',  1.0)
    world.meta['power_supply_0'] = snap.get('power_supply', 0)
    world.meta['power_demand_0'] = snap.get('power_demand', 0)

    # Merge new fx into client's fx list
    new_fx = snap.get('new_fx', [])
    world.meta.setdefault('fx', []).extend(new_fx)


# ── Initial data: server → client (sent once) ────────────────────────────────
def build_init_msg(world: World, team: int) -> dict:
    return {
        'type': 'init',
        'team': team,
        'tiles': world.meta['tiles'],
        'seed': 42,
    }


# ── Command: client → server ─────────────────────────────────────────────────
def make_cmd(cmd: str, **kwargs) -> dict:
    return {'type': 'cmd', 'cmd': cmd, **kwargs}


# ── JSON encode / decode with safety limits ──────────────────────────────────
def encode(msg: dict) -> str:
    return json.dumps(msg, separators=(',', ':'))


def decode(data: str) -> dict:
    return json.loads(data)
