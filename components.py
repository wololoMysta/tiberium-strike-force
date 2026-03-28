# components.py – pure data, no logic
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Position:
    x: float
    y: float


@dataclass
class Velocity:
    vx: float = 0.0
    vy: float = 0.0


@dataclass
class Health:
    hp:     float
    max_hp: float

    @property
    def ratio(self) -> float:
        return max(0.0, self.hp / self.max_hp)

    @property
    def dead(self) -> bool:
        return self.hp <= 0


@dataclass
class Team:
    id: int   # PLAYER or ENEMY


@dataclass
class UnitData:
    kind:   str    # 'infantry' | 'buggy' | 'tank' | 'harvester'
    speed:  float
    damage: float
    rng:    float
    rate:   float  # attacks per second
    radius: int
    cost:   int
    facing: float = 0.0   # radians, used for drawing
    turret: float = 0.0   # turret facing (tanks)


@dataclass
class BuildingData:
    kind:  str
    w:     int
    h:     int
    name:  str
    prod_queue: list = field(default_factory=list)   # [(unit_kind, timer_left)]
    rally_x: float = 0.0
    rally_y: float = 0.0


@dataclass
class Selectable:
    selected: bool = False


@dataclass
class Combat:
    target:    Optional[int] = None   # entity ID
    cooldown:  float = 0.0


@dataclass
class Movement:
    tx: Optional[float] = None   # target world x
    ty: Optional[float] = None   # target world y
    attack_move: bool = False     # move and attack anything in range


@dataclass
class Harvester:
    state:      str = 'idle'    # idle|to_resource|harvesting|to_base
    res_eid:    Optional[int] = None
    carry:      float = 0.0
    h_timer:    float = 0.0     # harvest tick timer


@dataclass
class Resource:
    amount:     float
    max_amount: float


@dataclass
class Vision:
    radius: float


@dataclass
class AIController:
    state:      str   = 'building'   # building|gathering|raiding
    build_t:    float = 0.0
    raid_t:     float = 0.0
    rally_x:    float = 0.0
    rally_y:    float = 0.0


@dataclass
class Projectile:
    tx:    float
    ty:    float
    speed: float
    dmg:   float
    team:  int
    weapon: str = 'bullet'   # bullet|rocket|tesla|laser|flame


@dataclass
class HomingProjectile:
    """Attached alongside Projectile – tracks a living target entity."""
    target_eid: int
    turn_rate:  float = 4.0   # radians / sec
    heading:    float = 0.0


@dataclass
class Wall:
    pass   # marker; movement collision handled by move_sys


@dataclass
class PowerConsumer:
    demand: int   # power units required


@dataclass
class PowerPlant:
    output: int = 100   # power units produced


@dataclass
class UnderConstruction:
    total:    float
    elapsed:  float = 0.0

    @property
    def ratio(self) -> float:
        return min(1.0, self.elapsed / self.total)

    @property
    def done(self) -> bool:
        return self.elapsed >= self.total
