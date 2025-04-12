from abc import abstractmethod
from typing import Dict, Any, Optional, List
import logging
import asyncio
import time

from src.core.synaptic_network import SynapticNetwork, SignalFilter
from src.signals.neural_signal import NeuralSignal, SignalType
from src.neurons.neuron import Neuron

logger = logging.getLogger(__name__)


class Actuator(Neuron):
    """运动神经元 - 负责将内部神经信号转换为外部行为"""

    def __init__(
        self,
        synaptic_network: SynapticNetwork,
        name: Optional[str] = None,
        accepted_signal_types: Optional[List[SignalType]] = None,
    ):
        super().__init__(synaptic_network, name)
        # 可接收的信号类型，默认接收运动信号
        self.accepted_signal_types = accepted_signal_types or [SignalType.MOTOR]
        # 扩展统计信息
        self.stats.update({"actions_performed": 0, "last_action_time": None, "pending_actions": 0})
        # 任务队列
        self.action_queue = asyncio.Queue()
        self.action_task = None

    async def _initialize(self, config: Dict[str, Any]) -> None:
        """初始化运动神经元

        Args:
            config: 神经元配置
        """
        # 由子类实现特定的初始化逻辑
        pass

    async def _activate(self) -> None:
        """激活运动神经元，开始处理动作"""
        self.action_task = asyncio.create_task(self._process_action_queue())
        logger.info(f"运动神经元已激活: {self.name}")

    async def _deactivate(self) -> None:
        """停用运动神经元，停止处理动作"""
        if self.action_task:
            self.action_task.cancel()
            try:
                await self.action_task
            except asyncio.CancelledError:
                pass
            self.action_task = None
        logger.info(f"运动神经元已停用: {self.name}")

    async def _register_receptors(self) -> None:
        """注册信号接收器"""
        signal_filter = SignalFilter(signal_types=self.accepted_signal_types)
        receptor_id = self.synaptic_network.register_receptor(
            callback=self._handle_signal, signal_filter=signal_filter, is_async=True
        )
        self.receptor_ids.append(receptor_id)

    async def _handle_signal(self, signal: NeuralSignal) -> None:
        """处理接收到的神经信号

        Args:
            signal: 接收到的神经信号
        """
        if not self.is_active:
            return

        self.stats["signals_processed"] += 1
        self.stats["last_active"] = time.time()

        try:
            # 将信号转换为动作并放入队列
            action = await self._convert_signal_to_action(signal)
            if action:
                await self.action_queue.put(action)
                self.stats["pending_actions"] = self.action_queue.qsize()
        except Exception as e:
            logger.error(f"转换信号为动作时出错: {self.name}, 错误: {e}")
            self.stats["errors"] += 1

    @abstractmethod
    async def _convert_signal_to_action(self, signal: NeuralSignal) -> Optional[Dict[str, Any]]:
        """将神经信号转换为动作

        Args:
            signal: 要转换的神经信号

        Returns:
            表示动作的字典，如果不需要执行动作则返回None
        """
        pass

    async def _process_action_queue(self) -> None:
        """处理动作队列的后台任务"""
        while self.is_active:
            try:
                action = await self.action_queue.get()
                await self._execute_action(action)
                self.action_queue.task_done()
                self.stats["pending_actions"] = self.action_queue.qsize()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"处理动作队列时出错: {self.name}, 错误: {e}")
                self.stats["errors"] += 1

    async def _execute_action(self, action: Dict[str, Any]) -> None:
        """执行动作

        Args:
            action: 要执行的动作
        """
        try:
            # 执行动作
            await self._perform_action(action)

            self.stats["actions_performed"] += 1
            self.stats["last_action_time"] = time.time()

            # 如果动作需要反馈，生成反馈信号
            if "needs_feedback" in action and action["needs_feedback"]:
                await self._generate_feedback(action)
        except Exception as e:
            logger.error(f"执行动作时出错: {self.name}, 错误: {e}")
            self.stats["errors"] += 1

    @abstractmethod
    async def _perform_action(self, action: Dict[str, Any]) -> None:
        """执行具体的动作

        Args:
            action: 要执行的动作
        """
        pass

    async def _generate_feedback(self, action: Dict[str, Any]) -> None:
        """生成动作执行反馈

        Args:
            action: 执行的动作
        """
        # 由子类实现，生成特定类型的反馈信号
        pass
