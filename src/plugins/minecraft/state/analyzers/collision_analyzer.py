"""
碰撞检测分析器

负责分析周围方块分布情况，判断碰撞风险和移动空间
"""

from typing import List
from .base_analyzer import BaseAnalyzer


class CollisionAnalyzer(BaseAnalyzer):
    """碰撞检测分析器"""

    def __init__(self, obs, config=None):
        super().__init__(obs, config)

        # 加载配置参数
        collision_config = self.config.get("state_analyzer", {}).get("collision", {})
        self.collision_check_radius = collision_config.get("check_radius", 1)
        self.wall_block_threshold = collision_config.get("wall_block_threshold", 2)

    def analyze(self) -> List[str]:
        """
        分析周围方块分布情况，判断是否可能撞墙

        Returns:
            List[str]: 碰撞检测分析提示列表
        """
        collision_prompts = []

        try:
            voxels = self._safe_getattr(self.obs, "voxels")
            if not voxels:
                return collision_prompts

            block_names = self._safe_getattr(voxels, "block_name")
            is_collidable = self._safe_getattr(voxels, "is_collidable")

            if not block_names or len(block_names) < 3:
                return collision_prompts

            # 检查各个方向的碰撞风险
            collision_directions = []

            # 检查四个方向的碰撞
            directions = {"前方": (0, 1, 1), "后方": (2, 1, 1), "左侧": (1, 1, 0), "右侧": (1, 1, 2)}

            for direction_name, (x, y, z) in directions.items():
                try:
                    if x < len(block_names) and y < len(block_names[x]) and z < len(block_names[x][y]):
                        block_name = block_names[x][y][z]
                        if block_name and block_name != "air":
                            if self._is_block_collidable(is_collidable, x, y, z):
                                collision_directions.append(direction_name)
                except IndexError:
                    continue

            # 根据碰撞方向给出提示
            if len(collision_directions) >= 3:
                collision_prompts.append("警告：你几乎被方块包围，移动空间非常有限")
            elif len(collision_directions) >= 2:
                collision_prompts.append(f"注意：你的{', '.join(collision_directions)}有方块阻挡，移动时需要小心")
            elif len(collision_directions) == 1:
                collision_prompts.append(f"你的{collision_directions[0]}有方块，移动时注意避开")

            # 检查空间狭窄程度
            air_count = 0
            solid_count = 0

            for x in range(len(block_names)):
                for y in range(len(block_names[x])):
                    for z in range(len(block_names[x][y])):
                        block_name = block_names[x][y][z]
                        if block_name == "air":
                            air_count += 1
                        elif block_name and block_name != "null":
                            if self._is_block_collidable(is_collidable, x, y, z):
                                solid_count += 1

            # 判断空间类型
            if air_count <= 8:  # 在27个方块中，空气方块太少
                collision_prompts.append("你处于非常狭窄的空间中")
            elif air_count <= 15:
                collision_prompts.append("你处于相对狭窄的空间中")

        except Exception as e:
            self.logger.warning(f"分析碰撞检测数据时出错: {e}")

        return collision_prompts

    def _is_block_collidable(self, is_collidable, x: int, y: int, z: int) -> bool:
        """
        检查指定位置的方块是否可碰撞

        Args:
            is_collidable: 碰撞数据数组
            x, y, z: 方块位置坐标

        Returns:
            bool: 是否可碰撞
        """
        try:
            if is_collidable and x < len(is_collidable) and y < len(is_collidable[x]) and z < len(is_collidable[x][y]):
                return is_collidable[x][y][z]
        except (IndexError, TypeError):
            pass

        # 如果无法获取碰撞信息，默认认为非空气方块都可碰撞
        return True
