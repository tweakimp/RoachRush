import itertools
import random

import sc2
from sc2.ids.ability_id import AbilityId as AbilID
from sc2.ids.unit_typeid import UnitTypeId as UnitID


class RoachRush(sc2.BotAI):
    def __init__(self):
        # list of actions we do at each step
        self.actions = []
        # set of things that come from a larva
        self.from_larva = {UnitID.DRONE, UnitID.OVERLORD, UnitID.ZERGLING, UnitID.ROACH}
        # set of things that come from a drone
        self.from_drone = {UnitID.SPAWNINGPOOL, UnitID.EXTRACTOR, UnitID.ROACHWARREN}
        # buildorder
        self.buildorder = [
            UnitID.DRONE,
            UnitID.SPAWNINGPOOL,
            UnitID.DRONE,
            UnitID.DRONE,
            UnitID.OVERLORD,
            UnitID.EXTRACTOR,
            UnitID.ROACHWARREN,
            UnitID.QUEEN,
            UnitID.DRONE,
            UnitID.DRONE,
            UnitID.DRONE,
            UnitID.OVERLORD,
            "END",
        ]
        # current step of the buildorder
        self.buildorder_step = 0
        # expansion we need to clear next, changed in 'send_idle_army'
        self.army_target = None
        # generator we need to cycle through expansions, created in 'send_idle_army'
        self.clear_map = None
        # unit groups, created in 'set_unit_groups'
        self.drones = None
        self.larvae = None
        self.queens = None
        self.army = None
        # flag we wave in case we want to give up
        self.surrendered: bool = False
        # expansions ordered by distance from starting location
        self.ordered_expansions = None

    async def on_step(self, iteration):
        # dont do anything if we surrendered already
        if self.surrendered:
            return
        # create selections one time for the whole frame
        # so that we dont have to filter the same units multiple times
        self.set_unit_groups()
        # things to only do in the first step
        if iteration == 0:
            await self.start_step()
        # give up if no drones are left
        if not self.drones:
            # surrender phrase for ladder manager
            await self.chat_send("(pineapple)")
            self.surrendered = True
            return
        await self.do_buildorder()
        await self.inject()
        self.fill_extractors()
        # buildorder completed, start second phase of the bot
        if self.buildorder[self.buildorder_step] == "END":
            self.build_army()
            self.build_additional_overlords()
            self.set_army_target()
            self.control_army()
        # do list of actions of the current step
        await self.do_actions(self.actions)
        # empty list to be ready for new actions in the next frame
        self.actions = []

    def set_unit_groups(self):
        self.drones = self.units(UnitID.DRONE)
        self.larvae = self.units(UnitID.LARVA)
        self.queens = self.units(UnitID.QUEEN)
        self.army = self.units.filter(lambda unit: unit.type_id in {UnitID.ROACH, UnitID.ZERGLING})

    async def start_step(self):
        # send a welcome message
        await self.chat_send("(kappa)")
        # split workers
        for drone in self.drones:
            # find closest mineral patch
            closest_mineral_patch = self.state.mineral_field.closest_to(drone)
            self.actions.append(drone.gather(closest_mineral_patch))
        # prepare ordered expansions, sort by distance to start location
        self.ordered_expansions = sorted(
            self.expansion_locations.keys(), key=lambda expansion: expansion.distance_to(self.start_location)
        )
        # only do on_step every nth step, 8 is standard
        self._client.game_step = 8

    def fill_extractors(self):
        for extractor in self.units(UnitID.EXTRACTOR):
            # returns negative value if not enough workers
            if extractor.surplus_harvesters < 0:
                drones_with_no_minerals = self.drones.filter(lambda unit: not unit.is_carrying_minerals)
                if drones_with_no_minerals:
                    # surplus_harvesters is negative when workers are missing
                    for n in range(-extractor.surplus_harvesters):
                        # prevent crash by only taking the minimum
                        drone = drones_with_no_minerals[min(n, drones_with_no_minerals.amount) - 1]
                        self.actions.append(drone.gather(extractor))

    async def do_buildorder(self):
        # only try to build something if you have 25 minerals, otherwise you dont have enough anyway
        if self.minerals < 25:
            return
        current_step = self.buildorder[self.buildorder_step]
        # do nothing if we are done already or dont have enough resources for current step of build order
        if current_step == "END" or not self.can_afford(current_step):
            return
        # check if current step needs larva
        if current_step in self.from_larva and self.larvae:
            self.actions.append(self.larvae.first.train(current_step))
            print(f"{self.time_formatted} STEP {self.buildorder_step} {current_step.name} ")
            self.buildorder_step += 1
        # check if current step needs drone
        elif current_step in self.from_drone:
            if current_step == UnitID.EXTRACTOR:
                # get geysers that dont have extractor on them
                geysers = self.state.vespene_geyser.filter(
                    lambda g: all(g.position != e.position for e in self.units(UnitID.EXTRACTOR))
                )
                # pick closest
                position = geysers.closest_to(self.start_location)
            else:
                if current_step == UnitID.ROACHWARREN:
                    # check tech requirement
                    if not self.units(UnitID.SPAWNINGPOOL).ready:
                        return
                # pick position towards ramp to avoid building between hatchery and resources
                buildings_around = self.units(UnitID.HATCHERY).first.position.towards(
                    self.main_base_ramp.depot_in_middle, 7
                )
                position = await self.find_placement(building=current_step, near=buildings_around, placement_step=4)
            # got building position, pick worker that will get there the fastest
            worker = self.workers.closest_to(position)
            self.actions.append(worker.build(current_step, position))
            print(f"{self.time_formatted} STEP {self.buildorder_step} {current_step.name}")
            self.buildorder_step += 1
        elif current_step == UnitID.QUEEN:
            # tech requirement check
            if not self.units(UnitID.SPAWNINGPOOL).ready:
                return
            hatch = self.units(UnitID.HATCHERY).first
            self.actions.append(hatch.train(UnitID.QUEEN))
            print(f"{self.time_formatted} STEP {self.buildorder_step} {current_step.name}")
            self.buildorder_step += 1

    async def inject(self):
        if not self.queens:
            return
        for queen in self.queens.idle:
            abilities = await self.get_available_abilities(queen)
            # check if queen can inject
            # you could also use queen.energy >= 25 to save the async call
            if AbilID.EFFECT_INJECTLARVA in abilities:
                hatch = self.units(UnitID.HATCHERY).first
                self.actions.append(queen(AbilID.EFFECT_INJECTLARVA, hatch))

    def build_army(self):
        # we cant build any army unit with less than 50 minerals
        if self.minerals < 50:
            return
        # rebuild lost workers
        if self.larvae and self.supply_workers + self.already_pending(UnitID.DRONE) < 15:
            self.actions.append(self.larvae.first.train(UnitID.DRONE))
        # rebuild lost queen
        if self.units(UnitID.SPAWNINGPOOL).ready and not self.queens and self.units(UnitID.HATCHERY).idle:
            if self.can_afford(UnitID.QUEEN):
                hatch = self.units(UnitID.HATCHERY).first
                self.actions.append(hatch.train(UnitID.QUEEN))
            return
        if self.larvae and self.units(UnitID.ROACHWARREN) and self.units(UnitID.ROACHWARREN).ready:
            if self.can_afford(UnitID.ROACH):
                # note that this only builds one unit per step
                self.actions.append(self.larvae.first.train(UnitID.ROACH))
            # only build zergling if you cant build roach soon
            elif self.minerals >= 50 and self.vespene <= 8:
                self.actions.append(self.larvae.first.train(UnitID.ZERGLING))

    def set_army_target(self):
        # sets the next waypoint for the army in case there is nothing on the map
        # if we didnt start to clear the map already
        if not self.clear_map:
            # start with enemy starting location, then cycle through all expansions
            self.clear_map = itertools.cycle(reversed(self.ordered_expansions))
            self.army_target = next(self.clear_map)
        # we can see the expansion but there seems to be nothing there, get next
        if self.units.closer_than(6, self.army_target):
            self.army_target = next(self.clear_map)

    def control_army(self):
        # calculate actions for the army units
        army = self.units.filter(lambda unit: unit.type_id in {UnitID.ROACH, UnitID.ZERGLING})
        # dont do anything if we dont have an army
        if not army:
            return
        # we can only fight ground units and we dont want to fight larvae
        ground_enemies = self.known_enemy_units.filter(lambda unit: not unit.is_flying and unit.type_id != UnitID.LARVA)
        # we dont see anything so start to clear the map
        if not ground_enemies:
            for unit in army:
                self.actions.append(unit.attack(self.army_target))
            return
        # calculate army size and center for grouping
        army_size = len(army)
        army_center = army.center
        # create selection of dangerous enemy units.
        # bunker and uprooted spine dont have weapon, but should be in that selection
        # also add uprooted spinecrawler and bunker because they have no weapon and pylon to unpower protoss structures
        enemy_fighters = ground_enemies.filter(
            lambda u: u.can_attack
            or u.type_id in {UnitID.BUNKER, UnitID.SPINECRAWLERUPROOTED, UnitID.SPINECRAWLER, UnitID.PYLON}
        )
        for unit in army:
            if enemy_fighters:
                # select enemies in range
                in_range_enemies = enemy_fighters.in_attack_range_of(unit)
                if in_range_enemies:
                    # prioritize units if in range that are dangerous or repair
                    # workers = in_range_enemies({UnitID.DRONE, UnitID.SCV, UnitID.PROBE})
                    priority = in_range_enemies({UnitID.SCV, UnitID.IMMORTAL})
                    if priority:
                        in_range_enemies = priority
                    # special micro for ranged units
                    if unit.ground_range > 1:
                        # attack if weapon not on cooldown
                        if unit.weapon_cooldown == 0:
                            # attack enemy with lowest hp of the ones in range
                            lowest_hp = min(in_range_enemies, key=lambda e: e.health + e.shield)
                            self.actions.append(unit.attack(lowest_hp))
                        else:
                            closest_enemy = in_range_enemies.closest_to(unit)
                            # micro awy from closest unit, distance one shorter than range
                            # to let other friendly units get close enough as well and not block
                            self.actions.append(unit.move(closest_enemy.position.towards(unit, unit.ground_range - 1)))
                    else:
                        # target fire with melee units
                        lowest_hp = min(in_range_enemies, key=lambda e: e.health + e.shield)
                        self.actions.append(unit.attack(lowest_hp))
                else:
                    self.actions.append(unit.move(enemy_fighters.closest_to(unit)))
                    # # no unit in range, go to closest enemy if unit near army center
                    # # depending on the army size
                    # if unit.distance_to(army_center) < army_size ** 1.5 - army_size ** 1.2:
                    #     self.actions.append(unit.move(enemy_fighters.closest_to(unit)))
                    # # no unit in range, and unit is not near army center, group up
                    # else:
                    #     self.actions.append(unit.move(army_center))
            # no dangerous enemy at all, attack closest anyhting
            else:
                self.actions.append(unit.attack(ground_enemies.closest_to(unit)))

    def build_additional_overlords(self):
        # build more overlords after buildorder
        # you need larva and enough minerals
        # prevent overlords if you have reached the cap already
        # calculate if you need more supply
        if (
            self.can_afford(UnitID.OVERLORD)
            and self.larvae
            and self.supply_cap != 200
            and self.supply_left + self.already_pending(UnitID.OVERLORD) * 8 < 3 + self.supply_used // 7
        ):
            self.actions.append(self.larvae.first.train(UnitID.OVERLORD))


def main():
    # create bot instance
    bot = sc2.player.Bot(sc2.Race.Zerg, RoachRush())
    # fixed race seems to use different strats than sc2.Race.Random
    # choose a race for the opponent builtin bot
    race = random.choice([sc2.Race.Zerg, sc2.Race.Terran, sc2.Race.Protoss, sc2.Race.Random])
    # choose a strategy for the opponent builtin bot
    build = random.choice(
        [
            sc2.AIBuild.RandomBuild,
            sc2.AIBuild.Rush,
            sc2.AIBuild.Timing,
            sc2.AIBuild.Power,
            sc2.AIBuild.Macro,
            sc2.AIBuild.Air,
        ]
    )
    # create the opponent builtin bot instance
    builtin_bot = sc2.player.Computer(race, sc2.Difficulty.VeryHard, build)
    # choose a random map
    random_map = random.choice(
        [
            "Acropolis",
            # "AutomatonLE",
            # "BlueshiftLE",
            # "CeruleanFallLE",
            # "KairosJunctionLE",
            # "ParaSiteLE",
            # "PortAleksanderLE",
            # "StasisLE",
            # "DarknessSanctuaryLE",  # 4 player map, bot is ready for it but has to find enemy first
        ]
    )
    # start the game with both bots
    sc2.run_game(sc2.maps.get(random_map), [bot, builtin_bot], realtime=False)


if __name__ == "__main__":
    main()
