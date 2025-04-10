from abc import ABC, abstractmethod


class Sensor(ABC):
    @abstractmethod
    async def connect(self):
        """
        开始进行感知，处理感知器感知到的信息
        """
        pass
