from abc import abstractmethod
from typing import Dict, Any, Optional, List, Callable
import logging
import time
import asyncio

from src.core.synaptic_network import SynapticNetwork
from src.signals.neural_signal import NeuralSignal, SignalType
from src.neurons.neuron import Neuron

logger = logging.getLogger(__name__)


class Sensor(Neuron):
    """感觉神经元 - 负责感知外部刺激并转换为内部神经信号"""

    def __init__(self, synaptic_network: SynapticNetwork, name: Optional[str] = None):
        super().__init__(synaptic_network, name)
        self.input_queue = asyncio.Queue()
        self.input_task = None
        self.input_processors = []
        # 扩展统计信息
        self.stats.update({"inputs_processed": 0, "last_input_time": None})

    async def _initialize(self, config: Dict[str, Any]) -> None:
        """初始化感觉神经元

        Args:
            config: 神经元配置
        """
        # 由子类实现特定的初始化逻辑
        pass

    async def _activate(self) -> None:
        """激活感觉神经元，开始处理输入"""
        self.input_task = asyncio.create_task(self._process_input_queue())
        logger.info(f"感觉神经元已激活: {self.name}")

    async def _deactivate(self) -> None:
        """停用感觉神经元，停止处理输入"""
        if self.input_task:
            self.input_task.cancel()
            try:
                await self.input_task
            except asyncio.CancelledError:
                pass
            self.input_task = None
        logger.info(f"感觉神经元已停用: {self.name}")

    async def _register_receptors(self) -> None:
        """感觉神经元通常不需要注册接收器，因为它们只负责输入"""
        pass

    async def process_input(self, input_data: Any) -> None:
        """处理输入数据

        Args:
            input_data: 外部输入数据
        """
        if not self.is_active:
            logger.warning(f"尝试处理输入但感觉神经元未激活: {self.name}")
            return

        await self.input_queue.put(input_data)

    async def _process_input_queue(self) -> None:
        """处理输入队列的后台任务"""
        while self.is_active:
            try:
                input_data = await self.input_queue.get()
                await self._handle_input(input_data)
                self.input_queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"处理输入队列时出错: {self.name}, 错误: {e}")
                self.stats["errors"] += 1

    async def _handle_input(self, input_data: Any) -> None:
        """处理单个输入数据项

        Args:
            input_data: 外部输入数据
        """
        try:
            self.stats["inputs_processed"] += 1
            self.stats["last_input_time"] = time.time()
            self.stats["last_active"] = time.time()

            # 调用具体实现的处理方法
            signals = await self._process_raw_input(input_data)

            # 如果处理方法返回了信号，将它们传入神经网络
            if signals:
                for signal in signals:
                    await self.transmit_signal(signal)
        except Exception as e:
            logger.error(f"处理输入数据时出错: {self.name}, 错误: {e}")
            self.stats["errors"] += 1

    @abstractmethod
    async def _process_raw_input(self, input_data: Any) -> List[NeuralSignal]:
        """处理原始输入数据并生成神经信号

        Args:
            input_data: 原始输入数据

        Returns:
            生成的神经信号列表
        """
        pass

    def register_input_processor(self, processor: Callable[[Any], Any]) -> None:
        """注册输入处理器，用于预处理输入数据

        Args:
            processor: 输入处理器函数
        """
        self.input_processors.append(processor)

    async def _preprocess_input(self, input_data: Any) -> Any:
        """通过所有已注册的输入处理器对输入数据进行预处理

        Args:
            input_data: 原始输入数据

        Returns:
            预处理后的输入数据
        """
        processed_data = input_data
        for processor in self.input_processors:
            try:
                processed_data = processor(processed_data)
            except Exception as e:
                logger.error(f"输入预处理时出错: {self.name}, 处理器: {processor.__name__}, 错误: {e}")
                self.stats["errors"] += 1

        return processed_data
