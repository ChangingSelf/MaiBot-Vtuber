from abc import abstractmethod
from typing import Any, Optional, List
import logging
import time

from src.core.synaptic_network import SynapticNetwork, SignalFilter
from src.signals.neural_signal import NeuralSignal, SignalType
from src.neurons.neuron import Neuron

logger = logging.getLogger(__name__)


class BiDirectionalNeuron(Neuron):
    """双向神经元 - 同时具有感知和执行能力的神经元"""

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
        self.stats.update({"inputs_received": 0, "outputs_sent": 0, "last_input_time": None, "last_output_time": None})

    @abstractmethod
    async def sense(self, input_data: Any) -> None:
        """感知外部输入（类似Sensor功能）

        Args:
            input_data: 外部输入数据
        """
        pass

    @abstractmethod
    async def respond(self, signal: NeuralSignal) -> None:
        """响应神经信号（类似Actuator功能）

        Args:
            signal: 接收到的神经信号
        """
        pass

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
            await self.respond(signal)
            self.stats["outputs_sent"] += 1
            self.stats["last_output_time"] = time.time()
        except Exception as e:
            logger.error(f"双向神经元响应信号时出错: {self.name}, 错误: {e}")
            self.stats["errors"] += 1

    async def _transmit_signal(self, signal: NeuralSignal) -> None:
        """将感知到的信号传递到神经网络

        Args:
            signal: 要传递的神经信号
        """
        await self.transmit_signal(signal)
        self.stats["inputs_received"] += 1
        self.stats["last_input_time"] = time.time()
