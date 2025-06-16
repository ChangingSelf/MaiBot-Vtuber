"""
环境分析器

负责分析游戏环境信息，包括时间、天气、游戏信息等
"""

from typing import List
from .base_analyzer import BaseAnalyzer


class EnvironmentAnalyzer(BaseAnalyzer):
    """环境分析器"""

    def __init__(self, obs, config=None):
        super().__init__(obs, config)

        # 时间分析配置
        self.night_time_start = self._get_config_value("night_time_start", 13000)
        self.night_time_end = self._get_config_value("night_time_end", 23000)
        self.dawn_time_start = self._get_config_value("dawn_time_start", 23000)
        self.dawn_time_end = self._get_config_value("dawn_time_end", 1000)
        self.day_time_start = self._get_config_value("day_time_start", 1000)
        self.day_time_end = self._get_config_value("day_time_end", 13000)
        self.ticks_per_second = self._get_config_value("ticks_per_second", 20)

        # 天气分析配置
        self.weather_detailed_info = self._get_config_value("detailed_info", True)

    def analyze(self) -> List[str]:
        """
        分析环境相关状态

        Returns:
            List[str]: 环境状态提示列表
        """
        environment_prompts = []

        environment_prompts.extend(self.analyze_time())
        environment_prompts.extend(self.analyze_weather())
        environment_prompts.extend(self.analyze_game_info())

        return environment_prompts

    def analyze_time(self) -> List[str]:
        """分析时间相关状态"""
        time_prompts = []

        try:
            game_time = self._safe_getattr(self.obs, "time", 0)
            day = self._safe_getattr(self.obs, "day", 0)

            # 详细的时间描述
            if self.dawn_time_start <= game_time or game_time <= self.dawn_time_end:
                time_prompts.append(f"现在是第{day + 1}天的黎明时分（游戏时间{game_time}），天即将亮起。")
            elif self.day_time_start <= game_time <= self.day_time_end:
                time_prompts.append(f"现在是第{day + 1}天的白天（游戏时间{game_time}），光线充足，适合户外活动。")
            elif self.night_time_start <= game_time <= self.night_time_end:
                time_prompts.append(f"现在是第{day + 1}天的夜晚（游戏时间{game_time}），小心可能出现的敌对生物。")
            else:
                time_prompts.append(f"现在是第{day + 1}天（游戏时间{game_time}）。")

        except Exception as e:
            self.logger.warning(f"分析时间数据时出错: {e}")

        return time_prompts

    def analyze_weather(self) -> List[str]:
        """分析天气状态"""
        weather_prompts = []

        try:
            location_stats = self._safe_getattr(self.obs, "location_stats")
            if not location_stats:
                return weather_prompts

            is_raining = self._safe_getattr(location_stats, "is_raining", False)
            rainfall = self._safe_getattr(location_stats, "rainfall")
            temperature = self._safe_getattr(location_stats, "temperature")
            can_see_sky = self._safe_getattr(location_stats, "can_see_sky")

            # 降雨状态
            if is_raining:
                weather_prompts.append("当前正在下雨")
                if self.weather_detailed_info:
                    weather_prompts.append("雨天可能影响视野，熄灭火把，并使某些生物更加活跃")
            else:
                weather_prompts.append("当前天气晴朗")

            # 降雨量详细信息
            if rainfall is not None and self.weather_detailed_info:
                weather_prompts.append(f"降雨量: {rainfall}")

            # 温度分析
            if temperature and temperature != "TODO" and self.weather_detailed_info:
                weather_prompts.append(f"当前温度: {temperature}")

            # 天空可见性
            if can_see_sky and can_see_sky != "TODO":
                if can_see_sky:
                    weather_prompts.append("你可以看到天空")
                else:
                    weather_prompts.append("你在室内或地下，无法看到天空")

        except Exception as e:
            self.logger.warning(f"分析天气数据时出错: {e}")

        return weather_prompts

    def analyze_game_info(self) -> List[str]:
        """分析游戏基本信息"""
        game_info_prompts = []

        try:
            # 游戏难度
            difficulty = self._safe_getattr(self.obs, "difficulty", "unknown")
            difficulty_names = {"peaceful": "和平模式", "easy": "简单模式", "normal": "普通模式", "hard": "困难模式"}
            difficulty_name = difficulty_names.get(difficulty, difficulty)
            game_info_prompts.append(f"当前游戏难度: {difficulty_name}")

            # 已上线时长
            tick = self._safe_getattr(self.obs, "tick", 0)
            seconds = tick // self.ticks_per_second
            minutes = seconds // 60
            hours = minutes // 60

            if hours > 0:
                game_info_prompts.append(f"已上线时长: {hours}小时{minutes % 60}分钟{seconds % 60}秒（{tick} tick）")
            elif minutes > 0:
                game_info_prompts.append(f"已上线时长: {minutes}分钟{seconds % 60}秒（{tick} tick）")
            else:
                game_info_prompts.append(f"已上线时长: {seconds}秒（{tick} tick）")

            # 世界年龄
            age = self._safe_getattr(self.obs, "age", 0)
            age_seconds = age // self.ticks_per_second
            age_minutes = age_seconds // 60
            age_hours = age_minutes // 60
            age_days = age_hours // 24

            if age_days > 0:
                game_info_prompts.append(f"世界已存在: {age_days}天{age_hours % 24}小时（{age} tick）")
            elif age_hours > 0:
                game_info_prompts.append(f"世界已存在: {age_hours}小时{age_minutes % 60}分钟（{age} tick）")
            else:
                game_info_prompts.append(f"世界已存在: {age_minutes}分钟（{age} tick）")

            # 玩家名称
            name = self._safe_getattr(self.obs, "name", "未知")
            game_info_prompts.append(f"你的玩家角色名称: {name}")

        except Exception as e:
            self.logger.warning(f"分析游戏信息时出错: {e}")

        return game_info_prompts
