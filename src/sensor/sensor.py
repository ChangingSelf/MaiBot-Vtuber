from abc import ABC, abstractmethod
import asyncio
from ..neuro.synapse import Synapse, synapse
from ..actuator.subtitle_actuator import SubtitleActuator


class Sensor(ABC):
    def __init__(self, synapse: Synapse):
        self.synapse = synapse
        self.subtitle_actuator = None

    @abstractmethod
    async def connect(self):
        """
        与需要对接的平台进行连接，开始接收对面传来的消息，并放入消息队列
        """
        pass

    def set_subtitle_actuator(self, subtitle_actuator: SubtitleActuator):
        """
        设置字幕执行器

        参数:
            subtitle_actuator: 字幕执行器实例
        """
        self.subtitle_actuator = subtitle_actuator

    def add_input_to_subtitle(self, text: str, user: str):
        """
        添加输入消息到字幕

        参数:
            text: 消息文本
            user: 用户名
        """
        # 不再显示输入消息
        pass
