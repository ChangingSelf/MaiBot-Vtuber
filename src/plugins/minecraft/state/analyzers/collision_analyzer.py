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

    def analyze_facing_direction_wall(self) -> List[str]:
        """
        分析玩家面朝方向是否有墙

        Returns:
            List[str]: 面朝方向墙体检测结果
        """
        facing_prompts = []

        try:
            # 获取玩家朝向信息
            location_stats = self._safe_getattr(self.obs, "location_stats")
            if not location_stats:
                return facing_prompts

            yaw = self._safe_getattr(location_stats, "yaw")
            if yaw is None:
                return facing_prompts

            # 获取voxel数据
            voxels = self._safe_getattr(self.obs, "voxels")
            if not voxels:
                return facing_prompts

            block_names = self._safe_getattr(voxels, "block_name")
            is_collidable = self._safe_getattr(voxels, "is_collidable")

            if not block_names or len(block_names) < 3:
                return facing_prompts

            # 标准化yaw角度到[0, 360)范围
            normalized_yaw = yaw % 360

            # 根据yaw角度确定玩家面朝的基本方向和对应的voxel坐标
            # voxel坐标系：x=0是北方，x=2是南方，z=0是西方，z=2是东方
            facing_coords = self._get_facing_voxel_coords(normalized_yaw)

            if facing_coords:
                x, z = facing_coords
                y = 1  # 眼部高度，检查同一水平面

                # 检查面朝方向是否有可碰撞的方块
                if x < len(block_names) and y < len(block_names[x]) and z < len(block_names[x][y]):
                    block_name = block_names[x][y][z]

                    if block_name and block_name != "air":
                        if self._is_block_collidable(is_collidable, x, y, z):
                            direction_name = self._get_direction_name(normalized_yaw)
                            facing_prompts.append(f"警告：你面朝{direction_name}方向有墙体阻挡（{block_name}方块）")

                            # 检查是否还有更远的方块
                            self._check_extended_wall(block_names, is_collidable, facing_coords, facing_prompts)
                        else:
                            facing_prompts.append(f"你面朝方向有方块但可以通过（{block_name}）")
                    else:
                        facing_prompts.append("你面朝方向畅通无阻")

        except Exception as e:
            self.logger.warning(f"分析面朝方向墙体时出错: {e}")

        return facing_prompts

    def _get_facing_voxel_coords(self, yaw: float) -> tuple:
        """
        根据yaw角度获取面朝方向在voxel中的坐标

        Args:
            yaw: 标准化后的偏航角(0-360度)

        Returns:
            tuple: (x, z) 坐标，如果无法确定则返回None
        """
        # 根据yaw角度映射到voxel坐标系
        # 游戏中：北=0°, 东=90°, 南=180°, 西=270°
        # voxel中：x=0是北方，x=2是南方，z=0是西方，z=2是东方

        if 315 <= yaw or yaw < 45:  # 北方
            return (0, 1)
        elif 45 <= yaw < 135:  # 东方
            return (1, 2)
        elif 135 <= yaw < 225:  # 南方
            return (2, 1)
        elif 225 <= yaw < 315:  # 西方
            return (1, 0)

        return None

    def _get_direction_name(self, yaw: float) -> str:
        """
        根据yaw角度获取方向名称

        Args:
            yaw: 标准化后的偏航角(0-360度)

        Returns:
            str: 方向名称
        """
        if 315 <= yaw or yaw < 45:
            return "北"
        elif 45 <= yaw < 135:
            return "东"
        elif 135 <= yaw < 225:
            return "南"
        elif 225 <= yaw < 315:
            return "西"
        return "未知"

    def _check_extended_wall(self, block_names, is_collidable, facing_coords, prompts: List[str]):
        """
        检查面朝方向是否有延伸的墙体

        Args:
            block_names: 方块名称数组
            is_collidable: 碰撞数据数组
            facing_coords: 面朝方向的坐标
            prompts: 提示列表，会直接修改
        """
        try:
            x, z = facing_coords

            # 检查垂直方向的墙体延伸
            wall_height = 0
            for y in range(3):  # 检查下方、同层、上方
                if x < len(block_names) and y < len(block_names[x]) and z < len(block_names[x][y]):
                    block_name = block_names[x][y][z]
                    if block_name and block_name != "air":
                        if self._is_block_collidable(is_collidable, x, y, z):
                            wall_height += 1

            if wall_height >= 2:
                prompts.append("前方墙体较高，需要绕行")
            elif wall_height == 1:
                prompts.append("前方有单层障碍，可以跳跃通过或绕行")

        except Exception as e:
            self.logger.warning(f"检查延伸墙体时出错: {e}")

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
