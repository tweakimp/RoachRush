import sc2
from sc2.position import Point2, Point3


def terrain_to_z_height(h):
    # return round(-100 + 200 * h / 255)
    return round(16 * h / 255, 2)


class test_bot(sc2.BotAI):
    def __init__(self):
        self.all_points = None

    async def on_step(self, iteration):
        if iteration == 0:
            self.all_points = [
                Point2((x, y))
                for x in range(self._game_info.pathing_grid.width)
                for y in range(self._game_info.pathing_grid.height)
            ]
            # for structure in self.units.structure:
            #     print(structure.position3d)
        # if iteration % 10 == 0:
        #     for structure in self.units.structure:
        #         print(structure.position3d)

        await self.draw_map()
        pass

    async def draw_map(self):
        for point in self.all_points:
            if self.state.visibility[point] != 0:
                red = Point3((255, 20, 20))
                green = Point3((20, 255, 20))
                height = terrain_to_z_height(self.get_terrain_height(point))
                # height = self.get_terrain_height(point)
                # visibility = self.state.visibility[point]
                pathable = self._game_info.pathing_grid[point]
                self._client.debug_text_world(
                    # f"{point.x},{point.y}\n{height}\n{pathable}",
                    f"{height}",
                    Point3((point.x, point.y, 12)),
                    color=green,
                    size=8,
                )
            # self._client.debug_text_world(f"{height}", Point3((point.x, point.y, 15)), color=color, size=8)
            # location3d1 = Point3((point.x - 0.1, point.y - 0.1, 0))
            # location3d2 = Point3((point.x + 0.1, point.y + 0.1, 15)
            # self._client.debug_box_out(location3d1, location3d2, color)
        await self._client.send_debug()


def main():
    bot = sc2.player.Bot(sc2.Race.Terran, test_bot())
    builtin_bot = sc2.player.Computer(sc2.Race.Zerg, sc2.Difficulty.VeryEasy, sc2.AIBuild.Air)
    sc2.run_game(sc2.maps.get("StasisLE"), [bot, builtin_bot], realtime=False)


main()
