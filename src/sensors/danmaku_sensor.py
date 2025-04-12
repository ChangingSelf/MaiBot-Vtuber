from typing import Dict, Any, Optional, List
import logging

from src.core.synaptic_network import SynapticNetwork
from src.signals.neural_signal import NeuralSignal, SignalPriority
from src.signals.sensory_signals import DanmakuSignal
from src.sensors.base_sensor import Sensor

logger = logging.getLogger(__name__)


class DanmakuSensor(Sensor):
    """弹幕传感器 - 处理来自直播平台的弹幕消息"""

    def __init__(self, synaptic_network: SynapticNetwork, name: Optional[str] = None):
        super().__init__(synaptic_network, name or "弹幕传感器")
        self.platform = None
        self.filters = []  # 弹幕过滤器列表
        self.user_whitelist = set()  # 用户白名单
        self.user_blacklist = set()  # 用户黑名单
        self.keyword_blacklist = []  # 关键词黑名单

    async def _initialize(self, config: Dict[str, Any]) -> None:
        """初始化弹幕传感器

        Args:
            config: 配置信息
        """
        self.platform = config.get("platform", "unknown")

        # 设置过滤器
        if "filters" in config:
            self.filters = config["filters"]

        # 设置用户白名单和黑名单
        if "user_whitelist" in config:
            self.user_whitelist = set(config["user_whitelist"])
        if "user_blacklist" in config:
            self.user_blacklist = set(config["user_blacklist"])

        # 设置关键词黑名单
        if "keyword_blacklist" in config:
            self.keyword_blacklist = config["keyword_blacklist"]

        # 注册内置的输入处理器
        self.register_input_processor(self._filter_by_user)
        self.register_input_processor(self._filter_by_keyword)

        logger.info(f"弹幕传感器初始化完成: {self.name}, 平台: {self.platform}")

    async def _process_raw_input(self, input_data: Dict[str, Any]) -> List[NeuralSignal]:
        """处理原始弹幕数据

        Args:
            input_data: 原始弹幕数据

        Returns:
            处理后的神经信号列表
        """
        # 预处理输入数据
        processed_data = await self._preprocess_input(input_data)

        # 如果输入被过滤掉，返回空列表
        if processed_data is None:
            return []

        # 提取弹幕信息
        user = processed_data.get("user", "anonymous")
        content = processed_data.get("content", "")

        # 如果输入中有platform，使用它，否则使用传感器的platform
        platform = processed_data.get("platform", self.platform)

        # 创建不包含platform的extra_data字典
        extra_data = {k: v for k, v in processed_data.items() if k not in ["user", "content", "platform"]}

        # 创建弹幕信号
        priority = self._determine_priority(user, content)
        signal = DanmakuSignal(
            source=f"{self.name}_{self.platform}",
            platform=platform,
            user=user,
            content=content,
            priority=priority,
            **extra_data,
        )

        logger.debug(f"生成弹幕信号: 用户={user}, 内容={content}, 优先级={priority.name}")
        return [signal]

    def _determine_priority(self, user: str, content: str) -> SignalPriority:
        """根据用户和内容确定信号优先级

        Args:
            user: 用户名
            content: 弹幕内容

        Returns:
            信号优先级
        """
        # VIP用户或管理员弹幕给高优先级
        if user in self.user_whitelist:
            return SignalPriority.HIGH

        # 包含@或问号的弹幕可能是提问，给予较高优先级
        if "@" in content or "?" in content or "？" in content:
            return SignalPriority.HIGH

        # 默认优先级
        return SignalPriority.NORMAL

    def _filter_by_user(self, input_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """根据用户过滤弹幕

        Args:
            input_data: 输入数据

        Returns:
            过滤后的数据，如果应该丢弃则返回None
        """
        user = input_data.get("user", "")

        # 如果设置了白名单且用户不在白名单中，过滤掉
        if self.user_whitelist and user not in self.user_whitelist:
            logger.debug(f"用户不在白名单中，过滤弹幕: {user}")
            return None

        # 如果用户在黑名单中，过滤掉
        if user in self.user_blacklist:
            logger.debug(f"用户在黑名单中，过滤弹幕: {user}")
            return None

        return input_data

    def _filter_by_keyword(self, input_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """根据关键词过滤弹幕

        Args:
            input_data: 输入数据

        Returns:
            过滤后的数据，如果应该丢弃则返回None
        """
        if input_data is None:
            return None

        content = input_data.get("content", "")

        # 检查是否包含黑名单关键词
        for keyword in self.keyword_blacklist:
            if keyword in content:
                logger.debug(f"弹幕包含黑名单关键词，过滤弹幕: {keyword}")
                return None

        return input_data
