from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
import logging

from src.core.synaptic_network import SynapticNetwork
from src.signals.neural_signal import NeuralSignal

logger = logging.getLogger(__name__)


class Neuron(ABC):
    """神经元 - 系统中所有神经组件的基类"""

    def __init__(self, synaptic_network: SynapticNetwork, name: Optional[str] = None):
        self.synaptic_network = synaptic_network
        self.name = name or self.__class__.__name__
        self.is_active = False
        self.receptor_ids = []  # 存储注册的接收器ID
        self.stats = {"signals_processed": 0, "signals_transmitted": 0, "errors": 0, "last_active": None}
        logger.debug(f"神经元创建: {self.name}")

    async def initialize(self, config: Dict[str, Any]) -> None:
        """初始化神经元

        Args:
            config: 神经元配置
        """
        logger.info(f"初始化神经元: {self.name}")
        try:
            await self._initialize(config)
        except Exception as e:
            logger.error(f"初始化神经元时出错: {self.name}, 错误: {e}")
            self.stats["errors"] += 1
            raise

    @abstractmethod
    async def _initialize(self, config: Dict[str, Any]) -> None:
        """供子类实现的初始化方法"""
        pass

    async def activate(self) -> None:
        """激活神经元"""
        if self.is_active:
            logger.warning(f"神经元已经处于活动状态: {self.name}")
            return

        logger.info(f"激活神经元: {self.name}")
        try:
            await self._register_receptors()
            await self._activate()
            self.is_active = True
            logger.info(f"神经元已激活: {self.name}")
        except Exception as e:
            logger.error(f"激活神经元时出错: {self.name}, 错误: {e}")
            self.stats["errors"] += 1
            raise

    @abstractmethod
    async def _activate(self) -> None:
        """供子类实现的激活方法"""
        pass

    @abstractmethod
    async def _register_receptors(self) -> None:
        """供子类实现的接收器注册方法"""
        pass

    async def deactivate(self) -> None:
        """停用神经元"""
        if not self.is_active:
            logger.warning(f"神经元已经处于非活动状态: {self.name}")
            return

        logger.info(f"停用神经元: {self.name}")
        try:
            # 取消注册所有接收器
            for receptor_id in self.receptor_ids:
                self.synaptic_network.unregister_receptor(receptor_id)
            self.receptor_ids.clear()

            await self._deactivate()
            self.is_active = False
            logger.info(f"神经元已停用: {self.name}")
        except Exception as e:
            logger.error(f"停用神经元时出错: {self.name}, 错误: {e}")
            self.stats["errors"] += 1
            raise

    @abstractmethod
    async def _deactivate(self) -> None:
        """供子类实现的停用方法"""
        pass

    async def transmit_signal(self, signal: NeuralSignal) -> None:
        """发送神经信号到神经网络

        Args:
            signal: 要发送的神经信号
        """
        if not self.is_active:
            logger.warning(f"尝试从非活动神经元发送信号: {self.name}")
            return

        try:
            await self.synaptic_network.transmit(signal)
            self.stats["signals_transmitted"] += 1
        except Exception as e:
            logger.error(f"神经元发送信号时出错: {self.name}, 错误: {e}")
            self.stats["errors"] += 1
            raise

    def get_stats(self) -> Dict[str, Any]:
        """获取神经元的统计信息"""
        return dict(self.stats)
