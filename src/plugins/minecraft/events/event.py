from typing import Optional, Dict, Any
import time
from mineland import Event


class MinecraftEvent(Event):
    """Minecraft游戏事件类

    继承mineland.Event并扩展我们需要的字段
    """

    def __init__(self, type: str = "", message: str = "", tick: int = 0, **kwargs):
        # 调用父类构造函数
        super().__init__(type=type, message=message, tick=tick)

        # 扩展字段（从MineLand事件数据中获取）
        self.only_message = kwargs.get("only_message", "")
        self.username = kwargs.get("username", "")

        # 额外的属性（用于事件管理）
        self.timestamp: float = time.time()
        self.step_num: int = 0

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MinecraftEvent":
        """从字典创建事件对象"""
        return cls(
            type=data.get("type", ""),
            message=data.get("message", ""),
            tick=data.get("tick", 0),
            only_message=data.get("only_message", ""),
            username=data.get("username", ""),
        )

    @classmethod
    def from_mineland_event(cls, event: Event, **kwargs) -> "MinecraftEvent":
        """从mineland.Event对象创建"""
        return cls(type=event.type, message=event.message, tick=event.tick, **kwargs)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "type": self.type,
            "message": self.message,
            "only_message": self.only_message,
            "username": self.username,
            "tick": self.tick,
        }

    def __str__(self) -> str:
        return f"MinecraftEvent(type='{self.type}', message='{self.message}', tick={self.tick})"

    def __repr__(self) -> str:
        return self.__str__()
