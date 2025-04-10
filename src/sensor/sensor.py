from abc import ABC, abstractmethod
import asyncio
from src.neuro.synapse import Synapse, synapse


class Sensor(ABC):
    def __init__(self, synapse: Synapse):
        self.synapse = synapse

    @abstractmethod
    async def connect(self):
        """
        与需要对接的平台进行连接，开始接收对面传来的消息，并放入消息队列
        """
        pass
