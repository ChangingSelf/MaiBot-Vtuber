"""
基础分析器类

所有具体分析器的父类，提供通用的配置管理和日志功能
"""

from typing import List, Dict, Any
from abc import ABC, abstractmethod
from src.utils.logger import get_logger


class BaseAnalyzer(ABC):
    """
    基础分析器抽象类

    提供通用的配置管理、日志功能和分析接口
    """

    def __init__(self, obs, config: Dict[str, Any] = None):
        """
        初始化基础分析器

        Args:
            obs: Mineland观察对象
            config: 配置字典
        """
        self.obs = obs
        self.config = config or {}
        self.logger = get_logger("MinecraftPlugin")

        # 获取该分析器的专门配置
        self.analyzer_config = self._get_analyzer_config()

    def _get_analyzer_config(self) -> Dict[str, Any]:
        """
        获取该分析器的专门配置

        Returns:
            Dict[str, Any]: 分析器配置
        """
        analyzer_name = self.__class__.__name__.lower().replace("analyzer", "")
        return self.config.get("state_analyzer", {}).get(analyzer_name, {})

    @abstractmethod
    def analyze(self) -> List[str]:
        """
        执行分析

        Returns:
            List[str]: 分析结果列表
        """
        pass

    def _safe_getattr(self, obj, attr_path: str, default=None):
        """
        安全地获取嵌套属性

        Args:
            obj: 对象
            attr_path: 属性路径，如 "location_stats.pos"
            default: 默认值

        Returns:
            属性值或默认值
        """
        try:
            attrs = attr_path.split(".")
            result = obj
            for attr in attrs:
                if hasattr(result, attr):
                    result = getattr(result, attr)
                elif isinstance(result, dict) and attr in result:
                    result = result[attr]
                else:
                    return default
            return result
        except (AttributeError, KeyError, TypeError):
            return default

    def _get_config_value(self, key: str, default_value):
        """
        获取配置值

        Args:
            key: 配置键
            default_value: 默认值

        Returns:
            配置值或默认值
        """
        return self.analyzer_config.get(key, default_value)
