import logging
import asyncio
import time
from typing import Dict, Any, List, Optional

from src.sensors.base_sensor import Sensor
from src.signals.sensory_signals import SensorySignal
from src.signals.neural_signal import SignalType, SignalFilter, SignalPriority


class DemoSensor(Sensor):
    """
    示例感知神经元 - 一个用于演示插件系统的简单传感器

    这个传感器会定期发送测试消息，用于演示神经可塑性系统的功能。
    """

    def __init__(self, synaptic_network):
        """初始化DemoSensor

        Args:
            synaptic_network: 神经突触网络
        """
        super().__init__(synaptic_network, name="示例感知神经元")
        self.logger = logging.getLogger(f"plugin.demo_sensor")
        self._task = None
        self.interval = 5  # 默认5秒
        self.message = "这是一个测试消息"

    async def _initialize(self, config: Dict[str, Any]) -> None:
        """初始化插件

        Args:
            config: 插件配置
        """
        self.logger.info(f"初始化 {self.name}")

        # 从配置中获取参数
        self.enabled = config.get("enabled", True)
        self.interval = config.get("interval", 5)
        self.message = config.get("message", "这是一个测试消息")

        self.logger.info(f'配置: 消息间隔={self.interval}秒, 消息内容="{self.message}"')

    async def _activate(self) -> None:
        """激活传感器"""
        self.logger.info(f"{self.name} 已激活")

        # 启动一个后台任务定期发送测试消息
        self._task = asyncio.create_task(self._send_periodic_messages())

    async def _deactivate(self) -> None:
        """停用传感器"""
        # 取消后台任务
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

        self.logger.info(f"{self.name} 已停用")

    async def _register_receptors(self) -> None:
        """注册信号接收器"""
        # 这个简单传感器不需要接收任何信号
        pass

    async def _send_periodic_messages(self) -> None:
        """定期发送测试消息"""
        try:
            message_count = 0
            while True:
                message_count += 1

                # 创建感知信号
                signal = SensorySignal(
                    source=self.name,
                    data={"message": self.message, "count": message_count, "type": "demo_message"},
                    timestamp=time.time(),
                    priority=SignalPriority.NORMAL,
                )

                # 传输信号
                self.logger.debug(f"发送测试消息 #{message_count}: {self.message}")
                await self.transmit_signal(signal)

                # 等待指定的间隔时间
                await asyncio.sleep(self.interval)
        except asyncio.CancelledError:
            # 正常取消
            self.logger.info("定期消息任务已取消")
        except Exception as e:
            self.logger.error(f"发送周期性消息时出错: {e}")

    @classmethod
    def get_plugin_metadata(cls):
        """获取插件元数据

        Returns:
            包含插件元数据的字典
        """
        return {
            "id": "demo_sensor",
            "name": "示例感知神经元",
            "version": "0.1.0",
            "description": "这是一个示例感知神经元插件，用于演示插件系统的使用方法",
            "author": "MaiBot",
            "neuron_type": "sensor",
            "entry_point": "demo_sensor.py",
            "dependencies": {},
            "enabled": True,
        }
