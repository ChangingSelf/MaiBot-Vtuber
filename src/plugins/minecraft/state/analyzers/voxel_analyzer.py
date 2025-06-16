"""
体素分析器

负责分析玩家周围的3x3x3方块环境，包括墙壁检测、洞穴分析、地面稳定性等
"""

from typing import List, Dict
from .base_analyzer import BaseAnalyzer


class VoxelAnalyzer(BaseAnalyzer):
    """体素分析器"""

    def __init__(self, obs, config=None):
        super().__init__(obs, config)

        # 加载配置参数
        self.significant_block_count_threshold = self._get_config_value("significant_block_count_threshold", 3)
        self.voxel_analysis_size = self._get_config_value("voxel_analysis_size", 3)

    def analyze(self) -> List[str]:
        """
        分析周围方块环境

        Returns:
            List[str]: 周围环境分析提示列表
        """
        voxel_prompts = []

        try:
            voxels = self._safe_getattr(self.obs, "voxels")
            if not voxels:
                return voxel_prompts

            # 获取方块数据
            block_names = self._safe_getattr(voxels, "block_name")
            if not block_names:
                return voxel_prompts

            is_collidable = self._safe_getattr(voxels, "is_collidable")
            is_liquid = self._safe_getattr(voxels, "is_liquid")
            is_solid = self._safe_getattr(voxels, "is_solid")

            # 基础方块分析
            voxel_prompts.extend(self._analyze_basic_blocks(block_names, is_liquid, is_solid))

            # 详细的方块分布分析
            voxel_prompts.extend(self._analyze_block_distribution(block_names, is_collidable, is_solid))

        except Exception as e:
            self.logger.warning(f"分析voxels数据时出错: {e}")

        return voxel_prompts

    def _analyze_basic_blocks(self, block_names, is_liquid, is_solid) -> List[str]:
        """基础方块分析"""
        prompts = []

        # 收集所有方块类型
        block_counts = {}
        air_blocks = 0

        for x in range(len(block_names)):
            for y in range(len(block_names[x])):
                for z in range(len(block_names[x][y])):
                    block_name = block_names[x][y][z]

                    if block_name == "air":
                        air_blocks += 1
                    elif block_name and block_name != "null":
                        block_counts[block_name] = block_counts.get(block_name, 0) + 1

        # 生成方块概览
        if block_counts:
            sorted_blocks = sorted(block_counts.items(), key=lambda x: x[1], reverse=True)
            block_list = []
            for block_name, count in sorted_blocks:
                if count >= self.significant_block_count_threshold:
                    block_list.append(f"{block_name}({count}个)")
                else:
                    block_list.append(block_name)
            prompts.append(f"附近方块: {', '.join(block_list)}")

        # 分析特殊位置的方块
        center_size = len(block_names) // 2

        # 脚下方块
        if len(block_names) > center_size and len(block_names[center_size]) > 0:
            ground_block = block_names[center_size][0][center_size]
            if ground_block and ground_block != "air":
                prompts.append(f"你脚下是{ground_block}方块")

        # 头顶方块
        if len(block_names) > center_size and len(block_names[center_size]) > 2:
            overhead_block = block_names[center_size][2][center_size]
            if overhead_block and overhead_block != "air":
                prompts.append(f"你头顶有{overhead_block}方块，可能需要挖掘才能向上移动")

        # 空间分析
        if air_blocks >= 20:
            prompts.append("你处于开阔区域")
        elif air_blocks <= 5:
            prompts.append("你处于封闭或狭窄的空间")

        return prompts

    def _analyze_block_distribution(self, block_names, is_collidable, is_solid) -> List[str]:
        """详细的方块分布分析"""
        distribution_prompts = []

        if not block_names or len(block_names) < 3:
            return distribution_prompts

        try:
            # 墙壁分析
            wall_analysis = self._analyze_walls(block_names, is_collidable)
            if wall_analysis:
                distribution_prompts.extend(wall_analysis)

            # 洞穴和开口分析
            cave_analysis = self._analyze_caves_and_openings(block_names)
            if cave_analysis:
                distribution_prompts.extend(cave_analysis)

            # 头顶遮挡分析
            ceiling_analysis = self._analyze_ceiling_coverage(block_names, is_solid)
            if ceiling_analysis:
                distribution_prompts.extend(ceiling_analysis)

            # 地面稳定性分析
            ground_analysis = self._analyze_ground_stability(block_names, is_solid)
            if ground_analysis:
                distribution_prompts.extend(ground_analysis)

            # 环境类型分析
            environment_type = self._analyze_environment_type(block_names, is_solid)
            if environment_type:
                distribution_prompts.extend(environment_type)

        except Exception as e:
            self.logger.warning(f"分析方块分布时出错: {e}")

        return distribution_prompts

    def _analyze_walls(self, block_names, is_collidable) -> List[str]:
        """分析墙壁情况"""
        wall_prompts = []

        # 四个水平方向检测
        directions = {"北": (0, 1, 1), "南": (2, 1, 1), "西": (1, 1, 0), "东": (1, 1, 2)}

        wall_directions = []
        partial_wall_directions = []

        for direction_name, (x, y, z) in directions.items():
            try:
                if x < len(block_names) and y < len(block_names[x]) and z < len(block_names[x][y]):
                    if self._is_wall_in_direction(block_names, is_collidable, x, y, z):
                        wall_directions.append(direction_name)
                    elif self._is_partial_wall_in_direction(block_names, x, y, z):
                        partial_wall_directions.append(direction_name)
            except IndexError:
                continue

        # 生成墙壁分析提示
        if len(wall_directions) >= 3:
            wall_prompts.append("你被墙壁围绕，可能在房间或狭窄的通道中")
        elif len(wall_directions) >= 2:
            wall_prompts.append(f"你的{' '.join(wall_directions)}有墙壁")
        elif len(wall_directions) == 1:
            wall_prompts.append(f"你的{wall_directions[0]}方向有墙壁")

        if partial_wall_directions:
            wall_prompts.append(f"你的{' '.join(partial_wall_directions)}方向有部分遮挡")

        return wall_prompts

    def _analyze_caves_and_openings(self, block_names) -> List[str]:
        """分析洞穴和开口情况"""
        opening_prompts = []

        # 统计各层空气方块数量
        air_counts_by_level = {}

        for y in range(len(block_names[0])):
            air_count = 0
            for x in range(len(block_names)):
                for z in range(len(block_names[x][y])):
                    if block_names[x][y][z] == "air":
                        air_count += 1
            air_counts_by_level[y] = air_count

        # 分析空间开阔程度
        current_level_air = air_counts_by_level.get(1, 0)

        if current_level_air >= 7:
            opening_prompts.append("你周围空间很开阔，有大片空地")
        elif current_level_air >= 5:
            opening_prompts.append("你周围有较多的开放空间")
        elif current_level_air <= 2:
            opening_prompts.append("你周围空间狭窄，被方块密集包围")

        # 检查是否在隧道中
        if self._is_in_tunnel(block_names):
            opening_prompts.append("你似乎在隧道或走廊中")

        return opening_prompts

    def _analyze_ceiling_coverage(self, block_names, is_solid) -> List[str]:
        """分析头顶遮挡情况"""
        ceiling_prompts = []

        if len(block_names[0]) < 3:
            return ceiling_prompts

        try:
            # 检查上层方块情况
            solid_blocks_above = 0
            air_blocks_above = 0

            for x in range(len(block_names)):
                for z in range(len(block_names[x][2])):
                    block_name = block_names[x][2][z]
                    if block_name == "air":
                        air_blocks_above += 1
                    elif block_name and block_name != "null":
                        solid_blocks_above += 1

            # 分析遮挡程度
            total_above = solid_blocks_above + air_blocks_above
            if total_above > 0:
                coverage_ratio = solid_blocks_above / total_above

                if coverage_ratio >= 0.8:
                    ceiling_prompts.append("你的头顶几乎完全被遮住，处于室内或洞穴中")
                elif coverage_ratio >= 0.5:
                    ceiling_prompts.append("你的头顶大部分被遮挡")
                elif coverage_ratio >= 0.2:
                    ceiling_prompts.append("你的头顶有部分遮挡")
                else:
                    ceiling_prompts.append("你的头顶很开阔，可以看到天空")

        except Exception as e:
            self.logger.warning(f"分析头顶遮挡时出错: {e}")

        return ceiling_prompts

    def _analyze_ground_stability(self, block_names, is_solid) -> List[str]:
        """分析地面稳定性"""
        ground_prompts = []

        if not block_names or len(block_names[0]) < 1:
            return ground_prompts

        try:
            # 检查下层方块情况
            solid_ground = 0
            air_holes = 0
            ground_types = []

            for x in range(len(block_names)):
                for z in range(len(block_names[x][0])):
                    block_name = block_names[x][0][z]
                    if block_name == "air":
                        air_holes += 1
                    elif block_name and block_name != "null":
                        solid_ground += 1
                        ground_types.append(block_name)

            # 分析稳定性
            total_ground = solid_ground + air_holes
            if total_ground > 0:
                stability_ratio = solid_ground / total_ground

                if stability_ratio >= 0.9:
                    ground_prompts.append("你脚下的地面很稳固")
                elif stability_ratio >= 0.7:
                    ground_prompts.append("你脚下的地面大部分稳固")
                elif stability_ratio >= 0.4:
                    ground_prompts.append("你脚下的地面有一些空洞，需要小心")
                else:
                    ground_prompts.append("警告：你脚下有很多空洞，地面不稳定！")

                # 分析地面类型
                if ground_types:
                    unique_ground_types = list(set(ground_types))
                    if len(unique_ground_types) == 1:
                        ground_prompts.append(f"地面主要由{unique_ground_types[0]}构成")

        except Exception as e:
            self.logger.warning(f"分析地面稳定性时出错: {e}")

        return ground_prompts

    def _analyze_environment_type(self, block_names, is_solid) -> List[str]:
        """分析环境类型"""
        env_prompts = []

        try:
            # 统计各层的固体方块密度
            layer_densities = []
            for y in range(len(block_names[0])):
                solid_count = 0
                total_count = 0
                for x in range(len(block_names)):
                    for z in range(len(block_names[x][y])):
                        total_count += 1
                        block_name = block_names[x][y][z]
                        if block_name != "air" and block_name and block_name != "null":
                            solid_count += 1

                if total_count > 0:
                    layer_densities.append(solid_count / total_count)
                else:
                    layer_densities.append(0)

            # 基于密度模式判断环境类型
            if len(layer_densities) >= 3:
                upper_density = layer_densities[2]
                middle_density = layer_densities[1]
                lower_density = layer_densities[0]

                if upper_density > 0.6 and lower_density > 0.6 and middle_density < 0.4:
                    env_prompts.append("你可能在地下洞穴或隧道中")
                elif upper_density > 0.5 and middle_density < 0.3 and lower_density > 0.7:
                    env_prompts.append("你可能在建筑物内部")
                elif upper_density < 0.3 and lower_density > 0.6:
                    env_prompts.append("你在开阔的地面上")
                elif all(density > 0.6 for density in layer_densities):
                    env_prompts.append("你在完全封闭的空间中，可能在地下深处")
                elif lower_density < 0.3:
                    env_prompts.append("你可能在高处或悬空的位置")

        except Exception as e:
            self.logger.warning(f"分析环境类型时出错: {e}")

        return env_prompts

    # 辅助方法
    def _is_wall_in_direction(self, block_names, is_collidable, x, y, z) -> bool:
        """检查指定方向是否有完整的墙壁"""
        try:
            block_name = block_names[x][y][z]
            if block_name == "air" or not block_name or block_name == "null":
                return False

            # 检查垂直连续性
            wall_height = 0
            for check_y in range(len(block_names[x])):
                if (
                    z < len(block_names[x][check_y])
                    and block_names[x][check_y][z] != "air"
                    and block_names[x][check_y][z]
                    and block_names[x][check_y][z] != "null"
                ):
                    wall_height += 1

            return wall_height >= 2

        except IndexError:
            return False

    def _is_partial_wall_in_direction(self, block_names, x, y, z) -> bool:
        """检查指定方向是否有部分墙壁/遮挡"""
        try:
            block_name = block_names[x][y][z]
            return block_name != "air" and block_name and block_name != "null"
        except IndexError:
            return False

    def _is_in_tunnel(self, block_names) -> bool:
        """检查是否在隧道中"""
        try:
            # 隧道特征：两侧有墙，前后相对开阔，或前后有墙，左右开阔
            left_blocked = block_names[1][1][0] not in ["air", "null", None]
            right_blocked = block_names[1][1][2] not in ["air", "null", None]
            front_open = block_names[0][1][1] in ["air", "null", None]
            back_open = block_names[2][1][1] in ["air", "null", None]

            front_blocked = block_names[0][1][1] not in ["air", "null", None]
            back_blocked = block_names[2][1][1] not in ["air", "null", None]
            left_open = block_names[1][1][0] in ["air", "null", None]
            right_open = block_names[1][1][2] in ["air", "null", None]

            return (left_blocked and right_blocked and (front_open or back_open)) or (
                front_blocked and back_blocked and (left_open or right_open)
            )

        except IndexError:
            return False
