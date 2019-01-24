import sc2
from sc2 import Race, Difficulty
from sc2.constants import *
from sc2.player import Bot, Computer
from sc2.position import Point2


class RoachRush(sc2.BotAI):
    def __init__(self):
        # list of actions we do at each step
        self.actions = []
        # list of things that come from a larva
        self.from_larva = {DRONE, OVERLORD, ZERGLING, ROACH}
        # list of things that come from a drone
        self.from_drone = {SPAWNINGPOOL, EXTRACTOR, ROACHWARREN}
        # buildorder
        self.bo = [DRONE, DRONE, SPAWNINGPOOL, DRONE, OVERLORD, DRONE, EXTRACTOR, QUEEN, ROACHWARREN, "END"]
        # current step of the buildorder
        self.bo_step = 0

    async def on_step(self, iteration):
        if iteration == 0:
            # only do on_step every nth step, 8 is standard
            self._client.game_step = 8
        # only try to build something if you have 50 minerals, otherwise you dont have enough anyway
        if self.minerals >= 50:
            await self.do_buildorder()
        await self.inject()
        # buildorder completed, start second phase of the bot
        if self.bo[self.bo_step] == "END":
            self.build_army()
            self.send_idle_army()
            self.control_fighting_army()
            self.additional_overlords()
        # do list of actions of the current step
        await self.do_actions(self.actions)
        # empty list to be ready for new actions in the next frame
        self.actions = []

    async def on_building_construction_complete(self, unit):
        # fill extractor with 3 drones once it is done
        if unit.type_id == EXTRACTOR:
            for n in range(3):
                drone = self.units(DRONE)[n]
                self.actions.append(drone.gather(unit))

    async def do_buildorder(self):
        current_step = self.bo[self.bo_step]
        # do nothing if we are done already or dont have enough resources for current step of build order
        if current_step is "END" or not self.can_afford(current_step):
            return
        # check if current step needs larva
        if current_step in self.from_larva and self.units(LARVA):
            self.actions.append(self.units(LARVA).first.train(current_step))
            self.bo_step += 1
            print(f"STEP {self.bo_step} {current_step.name}")
        # check if current step needs drone
        elif current_step in self.from_drone:
            if current_step == EXTRACTOR:
                # get geysers that dont have extractor on them
                geysers = self.state.vespene_geyser.filter(
                    lambda g: all(g.position != e.position for e in self.units(EXTRACTOR))
                )
                # pick closest
                position = geysers.closest_to(self.start_location)
            else:
                if current_step == ROACHWARREN:
                    # check tech requirement
                    if not self.units(SPAWNINGPOOL).ready:
                        return
                # pick position towards ramp to avoid building between hatchery and resources
                buildings_around = self.units(HATCHERY).first.position.towards(self.main_base_ramp.depot_in_middle, 7)
                position = await self.find_placement(building=current_step, near=buildings_around, placement_step=5)
            # got building position, pick worker that will get there the fastest
            worker = self.workers.closest_to(position)
            self.actions.append(worker.build(current_step, position))
            print(f"STEP {self.bo_step} {current_step.name}")
            self.bo_step += 1
        elif current_step == QUEEN:
            # tech requirement check
            if not self.units(SPAWNINGPOOL).ready:
                return
            hatch = self.units(HATCHERY).first
            self.actions.append(hatch.train(QUEEN))
            print(f"STEP {self.bo_step} {current_step.name}")
            self.bo_step += 1

    async def inject(self):
        for queen in self.units(QUEEN).idle:
            abilities = await self.get_available_abilities(queen)
            # check if queen can inject
            # you could also use queen.energy >= 25 to save the async call
            if AbilityId.EFFECT_INJECTLARVA in abilities:
                hatch = self.units(HATCHERY).first
                self.actions.append(queen(EFFECT_INJECTLARVA, hatch))

    def build_army(self):
        # rebuild lost queen
        if self.units(SPAWNINGPOOL).ready and not self.units(QUEEN) and self.units(HATCHERY).idle:
            if self.can_afford(QUEEN):
                hatch = self.units(HATCHERY).first
                self.actions.append(hatch.train(QUEEN))
            return
        if self.units(ROACHWARREN) and self.units(ROACHWARREN).ready and self.units(LARVA):
            if self.can_afford(ROACH):
                # note that this only builds one unit per step
                self.actions.append(self.units(LARVA).first.train(ROACH))
            # only build zergling if you cant build roach soon
            elif self.minerals >= 50 and self.vespene <= 10:
                self.actions.append(self.units(LARVA).first.train(ZERGLING))

    def send_idle_army(self):
        army = (self.units(ROACH) | self.units(ZERGLING)).idle
        # wait with first attack until we have 5 units
        if army.amount >= 5:
            for unit in army:
                # we dont see anything, go to enemy start location (only works on 2 player maps)
                if not self.known_enemy_units:
                    self.actions.append(unit.attack(self.enemy_start_locations[0]))
                # otherwise, attack closest unit
                else:
                    closest_enemy = self.known_enemy_units.closest_to(unit)
                    self.actions.append(unit.attack(closest_enemy))

    def control_fighting_army(self):
        # no need to do anything here if we dont see anything
        if not self.known_enemy_units:
            return
        army = self.units(ROACH) | self.units(ZERGLING)
        # create selection of dangerous enemy units.
        # bunker and uprooted spine dont have weapon, but should be in that selection
        # also add spinecrawler and cannon if they are not ready yet and have no weapon
        enemy_fighters = self.known_enemy_units.filter(
            lambda u: u.can_attack or u.type_id in {BUNKER, SPINECRAWLERUPROOTED, SPINECRAWLER, PHOTONCANNON}
        )
        for unit in army:
            if enemy_fighters:
                # select enemies in range
                in_range_enemies = enemy_fighters.in_attack_range_of(unit)
                if in_range_enemies:
                    # attack enemy with lowest hp of the ones in range
                    lowest_hp = min(in_range_enemies, key=lambda e: e.health + e.shield)
                    self.actions.append(unit.attack(lowest_hp))
                else:
                    # no unit in range, go to closest
                    self.actions.append(unit.move(enemy_fighters.closest_to(unit)))
            else:
                # no dangerous enemy at all, attack closest of everything
                self.actions.append(unit.attack(self.known_enemy_units.closest_to(unit)))

    def additional_overlords(self):
        # build more overlords after buildorder
        # you need larva and enough minerals
        # prevent overlords if you have reached the cap already
        # calculate if you need more supply
        if (
            self.can_afford(OVERLORD)
            and self.units(LARVA)
            and self.supply_cap != 200
            and self.supply_left + ((self.units(OVERLORD).not_ready.amount + self.already_pending(OVERLORD)) * 8)
            < 3 + self.supply_used // 7
        ):
            self.actions.append(self.units(LARVA).first.train(OVERLORD))


def main():
    sc2.run_game(
        sc2.maps.get("BlueshiftLE"),
        [Bot(Race.Zerg, RoachRush()), Computer(Race.Random, Difficulty.Hard)],
        realtime=False,
    )


if __name__ == "__main__":
    main()
