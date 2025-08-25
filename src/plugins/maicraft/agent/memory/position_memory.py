import math

class FurnacePoint:
    def __init__(self, position: tuple[int, int, int], description: str = ""):
        self.accurate_position: tuple[int, int, int] = position
        self.position_description: str = description
        
    def get_distance(self, position: tuple[int, int, int]) -> float:
        return min(
            [
                math.sqrt(
                    (position[0] - p[0]) ** 2 + (position[1] - p[1]) ** 2 + (position[2] - p[2]) ** 2
                )
                for p in self.accurate_position
            ]
        )
        

class FurnaceMemory:
    def __init__(self):
        self.furnace_points: list[FurnacePoint] = []
        
    def add_furnace_point(self, position: tuple[int, int, int], description: str = ""):
        self.furnace_points.append(FurnacePoint(position, description))
        
    def remove_furnace_point(self, position: tuple[int, int, int]):
        self.furnace_points = [p for p in self.furnace_points if p.get_distance(position) > 1]
        
    def get_nearest_furnace_point(self, position: tuple[int, int, int]) -> FurnacePoint:
        return min(self.furnace_points, key=lambda x: x.get_distance(position))






class CraftingTablePoint:
    def __init__(self, position: tuple[int, int, int], description: str = ""):
        self.accurate_position: tuple[int, int, int] = position
        self.position_description: str = description
        
    def get_distance(self, position: tuple[int, int, int]) -> float:
        return min(
            [
                math.sqrt(
                    (position[0] - p[0]) ** 2 + (position[1] - p[1]) ** 2 + (position[2] - p[2]) ** 2
                )
                for p in self.accurate_position
            ]
        )
        
        
class CraftingTableMemory:
    def __init__(self):
        self.crafting_table_points: list[CraftingTablePoint] = []
        
    def add_crafting_table_point(self, position: tuple[int, int, int], description: str = ""):
        self.crafting_table_points.append(CraftingTablePoint(position, description))
        
    def remove_crafting_table_point(self, position: tuple[int, int, int]):
        self.crafting_table_points = [p for p in self.crafting_table_points if p.get_distance(position) > 1]
        
    def get_nearest_crafting_table_point(self, position: tuple[int, int, int]) -> CraftingTablePoint:
        return min(self.crafting_table_points, key=lambda x: x.get_distance(position))


# 全局的工作台位置记忆实例，供工具后处理等模块直接引用
crafting_table_memory = CraftingTableMemory()
furnace_memory = FurnaceMemory()