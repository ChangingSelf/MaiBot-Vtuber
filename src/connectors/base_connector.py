from abc import abstractmethod
from typing import Dict, Any, Optional, List
import logging
import asyncio
import time

from src.neurons.bidirectional_neuron import BiDirectionalNeuron
from src.core.synaptic_network import SynapticNetwork
from src.signals.neural_signal import NeuralSignal, SignalType

logger = logging.getLogger(__name__)


class Connector(BiDirectionalNeuron):
    """连接器基类 - 负责与外部系统通信的双向神经元"""

    def __init__(
        self,
        synaptic_network: SynapticNetwork,
        name: Optional[str] = None,
        input_signal_types: Optional[List[SignalType]] = None,
        output_signal_types: Optional[List[SignalType]] = None,
    ):
        # 设置默认信号类型
        if input_signal_types is None:
            input_signal_types = [SignalType.CORE]
        if output_signal_types is None:
            output_signal_types = [SignalType.SENSORY, SignalType.MOTOR]

        super().__init__(synaptic_network, name, input_signal_types)

        self.output_signal_types = output_signal_types
        self.connection_state = "disconnected"
        self.last_connected = None
        self.reconnect_task = None
        self.reconnect_interval = 5.0  # 重连间隔（秒）
        self.max_reconnect_attempts = 10  # 最大重连尝试次数
        self.reconnect_attempts = 0

        # 扩展统计信息
        self.stats.update(
            {
                "messages_received": 0,
                "messages_sent": 0,
                "connection_uptime": 0,
                "reconnect_attempts": 0,
                "connection_failures": 0,
            }
        )

    async def _initialize(self, config: Dict[str, Any]) -> None:
        """初始化连接器

        Args:
            config: 连接器配置
        """
        # 设置重连参数
        if "reconnect_interval" in config:
            self.reconnect_interval = config["reconnect_interval"]
        if "max_reconnect_attempts" in config:
            self.max_reconnect_attempts = config["max_reconnect_attempts"]

        # 调用子类特定的初始化
        await self._init_connection(config)

        logger.info(f"连接器初始化完成: {self.name}")

    @abstractmethod
    async def _init_connection(self, config: Dict[str, Any]) -> None:
        """初始化连接配置，由子类实现

        Args:
            config: 连接配置
        """
        pass

    async def _activate(self) -> None:
        """激活连接器"""
        # 尝试建立连接
        await self._connect()

        # 如果连接失败且启用了自动重连，启动重连任务
        if self.connection_state != "connected" and self.max_reconnect_attempts > 0:
            self.reconnect_task = asyncio.create_task(self._reconnect_loop())

        logger.info(f"连接器已激活: {self.name}, 状态: {self.connection_state}")

    async def _deactivate(self) -> None:
        """停用连接器"""
        # 停止重连任务
        if self.reconnect_task:
            self.reconnect_task.cancel()
            try:
                await self.reconnect_task
            except asyncio.CancelledError:
                pass
            self.reconnect_task = None

        # 断开连接
        await self._disconnect()

        logger.info(f"连接器已停用: {self.name}")

    @abstractmethod
    async def _connect(self) -> bool:
        """建立与外部系统的连接，由子类实现

        Returns:
            连接是否成功
        """
        pass

    @abstractmethod
    async def _disconnect(self) -> None:
        """断开与外部系统的连接，由子类实现"""
        pass

    async def _reconnect_loop(self) -> None:
        """自动重连循环"""
        self.reconnect_attempts = 0

        while self.is_active and self.connection_state != "connected":
            try:
                if self.reconnect_attempts >= self.max_reconnect_attempts:
                    logger.error(f"达到最大重连尝试次数，停止重连: {self.name}")
                    break

                self.reconnect_attempts += 1
                self.stats["reconnect_attempts"] += 1
                logger.info(f"尝试重新连接 ({self.reconnect_attempts}/{self.max_reconnect_attempts}): {self.name}")

                if await self._connect():
                    logger.info(f"重连成功: {self.name}")
                    self.reconnect_attempts = 0
                    break
                else:
                    logger.warning(f"重连失败: {self.name}")
                    await asyncio.sleep(self.reconnect_interval)
            except asyncio.CancelledError:
                logger.info(f"重连任务被取消: {self.name}")
                break
            except Exception as e:
                logger.error(f"重连过程中出错: {self.name}, 错误: {e}")
                self.stats["errors"] += 1
                self.stats["connection_failures"] += 1
                await asyncio.sleep(self.reconnect_interval)

    @abstractmethod
    async def sense(self, input_data: Any) -> None:
        """处理从外部系统接收到的数据

        Args:
            input_data: 外部输入数据
        """
        pass

    @abstractmethod
    async def respond(self, signal: NeuralSignal) -> None:
        """响应神经信号，发送数据到外部系统

        Args:
            signal: 接收到的神经信号
        """
        pass

    def _update_connection_state(self, new_state: str) -> None:
        """更新连接状态

        Args:
            new_state: 新状态，可以是 "connected", "disconnected", "connecting", "error"
        """
        old_state = self.connection_state
        self.connection_state = new_state

        if new_state == "connected" and old_state != "connected":
            # 记录连接时间
            self.last_connected = time.time()
            logger.info(f"连接器状态变更: {old_state} -> {new_state}, {self.name}")
        elif old_state == "connected" and new_state != "connected":
            # 记录连接失败
            self.stats["connection_failures"] += 1
            logger.warning(f"连接器状态变更: {old_state} -> {new_state}, {self.name}")

            # 如果启用了自动重连且没有正在进行的重连任务，启动重连
            if self.is_active and self.max_reconnect_attempts > 0 and not self.reconnect_task:
                self.reconnect_task = asyncio.create_task(self._reconnect_loop())
        else:
            logger.debug(f"连接器状态变更: {old_state} -> {new_state}, {self.name}")

    def get_connection_stats(self) -> Dict[str, Any]:
        """获取连接统计信息

        Returns:
            连接统计信息
        """
        stats = {"state": self.connection_state, "uptime": 0, **self.stats}

        # 计算连接时长
        if self.connection_state == "connected" and self.last_connected:
            stats["uptime"] = time.time() - self.last_connected

        return stats
