# ecs.py – minimal, zero-dependency ECS core
from typing import Any, Generator, Type, TypeVar

T = TypeVar('T')


class World:
    """Sparse-set ECS world: entities are ints, components stored by type."""
    __slots__ = ('_nxt', '_live', '_store', 'systems', 'meta')

    def __init__(self) -> None:
        self._nxt   = 0
        self._live: set[int] = set()
        self._store: dict[type, dict[int, Any]] = {}
        self.systems: list = []
        self.meta:    dict = {}

    # ── Entity lifecycle ──────────────────────────────────────────────────────
    def spawn(self, *comps) -> int:
        eid = self._nxt; self._nxt += 1
        self._live.add(eid)
        for c in comps:
            self._store.setdefault(type(c), {})[eid] = c
        return eid

    def kill(self, eid: int) -> None:
        self._live.discard(eid)
        for s in self._store.values():
            s.pop(eid, None)

    # ── Component access ──────────────────────────────────────────────────────
    def add(self, eid: int, *comps) -> None:
        for c in comps:
            self._store.setdefault(type(c), {})[eid] = c

    def get(self, eid: int, ct: Type[T]) -> T | None:
        return self._store.get(ct, {}).get(eid)

    def has(self, eid: int, *cts: type) -> bool:
        return all(eid in self._store.get(ct, {}) for ct in cts)

    def rm(self, eid: int, ct: type) -> None:
        self._store.get(ct, {}).pop(eid, None)

    # ── Query (yields (eid, c0, c1, …)) ──────────────────────────────────────
    def q(self, *cts: type) -> Generator:
        if not cts:
            return
        stores = [self._store.get(ct, {}) for ct in cts]
        base   = min(stores, key=len)
        for eid in list(base):
            if eid in self._live and all(eid in s for s in stores):
                yield (eid, *[s[eid] for s in stores])

    # ── Tick ──────────────────────────────────────────────────────────────────
    def tick(self, dt: float) -> None:
        for sys in self.systems:
            sys.update(self, dt)


class System:
    """Base class – override update()."""
    def update(self, world: World, dt: float) -> None: ...
