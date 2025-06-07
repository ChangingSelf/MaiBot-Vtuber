"""
生命统计分析器

负责分析玩家的生命值、饥饿值、氧气值等生命统计信息
"""

from typing import List
from .base_analyzer import BaseAnalyzer


class LifeStatsAnalyzer(BaseAnalyzer):
    """生命统计分析器"""

    def __init__(self, obs, config=None):
        super().__init__(obs, config)

        # 加载配置参数
        self.food_very_low_threshold = self._get_config_value("food_very_low_threshold", 6)
        self.food_low_threshold = self._get_config_value("food_low_threshold", 10)
        self.food_max_value = self._get_config_value("food_max_value", 20)
        self.health_critical_threshold = self._get_config_value("health_critical_threshold", 5)
        self.health_low_threshold = self._get_config_value("health_low_threshold", 10)
        self.health_max_value = self._get_config_value("health_max_value", 20)
        self.oxygen_max_value = self._get_config_value("oxygen_max_value", 20)

    def analyze(self) -> List[str]:
        """
        分析生命统计相关状态

        Returns:
            List[str]: 生命状态提示列表
        """
        life_prompts = []

        try:
            life_stats = self._safe_getattr(self.obs, "life_stats")
            if not life_stats:
                return life_prompts

            # 饥饿状态分析
            food_level = self._safe_getattr(life_stats, "food", self.food_max_value)
            if food_level <= self.food_very_low_threshold:
                life_prompts.append("你现在非常饥饿，需要尽快寻找食物。")
            elif food_level <= self.food_low_threshold:
                life_prompts.append("你的饥饿值较低，应该考虑寻找食物。")

            # 生命值分析
            health = self._safe_getattr(life_stats, "life", self.health_max_value)
            if health <= self.health_critical_threshold:
                life_prompts.append("警告：你的生命值极低，处于危险状态！")
            elif health <= self.health_low_threshold:
                life_prompts.append("你的生命值较低，需要小心行动。")

            # 氧气值分析
            oxygen = self._safe_getattr(life_stats, "oxygen", self.oxygen_max_value)
            if oxygen < self.oxygen_max_value:
                life_prompts.append(f"你的氧气值不足，当前只有{oxygen}/{self.oxygen_max_value}。")

        except Exception as e:
            self.logger.warning(f"分析生命统计数据时出错: {e}")

        return life_prompts
