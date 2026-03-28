# systems/power_sys.py – power grid balance
from ecs import World, System
from components import PowerPlant, PowerConsumer, BuildingData, Team, UnderConstruction
from config import PLAYER, ENEMY, POWER_DEMAND, POWER_OUTPUT


class PowerSys(System):
    def update(self, world: World, dt: float) -> None:
        for team_id in (PLAYER, ENEMY):
            supply = 0
            demand = 0
            for _eid, pp, team in world.q(PowerPlant, Team):
                if team.id == team_id:
                    supply += pp.output
            for _eid, pc, team in world.q(PowerConsumer, Team):
                if team.id == team_id:
                    demand += pc.demand
            ratio = min(1.0, supply / max(1, demand))
            world.meta[f'power_ratio_{team_id}'] = ratio
            world.meta[f'power_supply_{team_id}'] = supply
            world.meta[f'power_demand_{team_id}'] = demand
