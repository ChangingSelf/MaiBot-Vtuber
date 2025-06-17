"""
主状态分析器

重构后的主分析器，组合使用各个专门的分析器来提供完整的状态分析
"""

from typing import List, Dict, Any
from .base_analyzer import BaseAnalyzer
from .life_stats_analyzer import LifeStatsAnalyzer
from .motion_analyzer import MotionAnalyzer
from .equipment_analyzer import EquipmentAnalyzer
from .inventory_analyzer import InventoryAnalyzer
from .voxel_analyzer import VoxelAnalyzer
from .environment_analyzer import EnvironmentAnalyzer
from .collision_analyzer import CollisionAnalyzer


class StateAnalyzer(BaseAnalyzer):
    """
    主状态分析器

    组合使用多个专门的分析器来提供完整的游戏状态分析
    """

    def __init__(self, obs, config: Dict[str, Any] = None):
        """
        初始化主状态分析器

        Args:
            obs: Mineland观察对象
            config: 配置字典
        """
        super().__init__(obs, config)

        # 初始化各个专门的分析器
        self.life_stats_analyzer = LifeStatsAnalyzer(obs, config)
        self.motion_analyzer = MotionAnalyzer(obs, config)
        self.equipment_analyzer = EquipmentAnalyzer(obs, config)
        self.inventory_analyzer = InventoryAnalyzer(obs, config)
        self.voxel_analyzer = VoxelAnalyzer(obs, config)
        self.environment_analyzer = EnvironmentAnalyzer(obs, config)
        self.collision_analyzer = CollisionAnalyzer(obs, config)

    def set_observation(self, obs):
        """更新观察对象，并级联更新所有子分析器"""
        self.obs = obs
        self.life_stats_analyzer.obs = obs
        self.motion_analyzer.obs = obs
        self.equipment_analyzer.obs = obs
        self.inventory_analyzer.obs = obs
        self.voxel_analyzer.obs = obs
        self.environment_analyzer.obs = obs
        self.collision_analyzer.obs = obs

    def analyze(self) -> List[str]:
        """
        执行完整的状态分析

        Returns:
            List[str]: 完整的状态提示列表
        """
        return self.analyze_all()

    def analyze_all(self) -> List[str]:
        """
        分析所有游戏状态

        Returns:
            List[str]: 完整的状态提示列表
        """
        status_prompts = []

        try:
            # 按重要性顺序分析各项状态
            status_prompts.extend(self.life_stats_analyzer.analyze())
            status_prompts.extend(self.motion_analyzer.analyze())
            status_prompts.extend(self.equipment_analyzer.analyze())
            status_prompts.extend(self.inventory_analyzer.analyze())
            status_prompts.extend(self.analyze_environment())
            status_prompts.extend(self.collision_analyzer.analyze())
            status_prompts.extend(self.collision_analyzer.analyze_facing_direction_wall())
            status_prompts.extend(self.environment_analyzer.analyze())

        except Exception as e:
            self.logger.warning(f"执行完整状态分析时出错: {e}")

        return status_prompts

    def analyze_environment(self) -> List[str]:
        """
        分析环境相关状态（主要是voxel分析）

        Returns:
            List[str]: 环境状态提示列表
        """
        # 如果有voxels数据，使用体素分析器
        if hasattr(self.obs, "voxels") and self.obs.voxels:
            return self.voxel_analyzer.analyze()
        return []
