from typing import Any, Dict, Optional
from datetime import datetime
import time

from src.signals.neural_signal import NeuralSignal, SignalType, SignalPriority


class SensorySignal(NeuralSignal):
    """感觉信号 - 从外部环境感知到的信息"""

    def __init__(
        self,
        source: str,
        data: Dict[str, Any],
        priority: SignalPriority = SignalPriority.NORMAL,
        target: Optional[str] = None,
    ):
        super().__init__(signal_type=SignalType.SENSORY, source=source, data=data, priority=priority, target=target)
        # 添加感觉信号特有的属性
        self.sensory_type = data.get("sensory_type", "unknown")
        self.raw_input = data.get("raw_input", None)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SensorySignal":
        """从字典创建感觉信号"""
        source = data.get("source", "unknown")
        signal_data = data.get("data", {})
        priority_name = data.get("priority", "NORMAL")
        priority = SignalPriority[priority_name] if isinstance(priority_name, str) else SignalPriority.NORMAL
        target = data.get("target")

        signal = cls(source=source, data=signal_data, priority=priority, target=target)

        # 恢复其他属性
        if "id" in data:
            signal.id = data["id"]
        if "timestamp" in data:
            signal.timestamp = datetime.fromisoformat(data["timestamp"])
        if "processed" in data:
            signal.processed = data["processed"]
        if "processing_history" in data:
            signal.processing_history = data["processing_history"]

        return signal


class DanmakuSignal(SensorySignal):
    """弹幕信号 - 从直播平台接收到的弹幕消息"""

    def __init__(
        self,
        source: str,
        platform: str,
        user: str,
        content: str,
        priority: SignalPriority = SignalPriority.NORMAL,
        target: Optional[str] = None,
        **extra_data,
    ):
        data = {
            "sensory_type": "danmaku",
            "platform": platform,
            "user": user,
            "content": content,
            "raw_input": extra_data.get("raw_input"),
            **extra_data,
        }
        super().__init__(source=source, data=data, priority=priority, target=target)


class CommandSignal(SensorySignal):
    """命令信号 - 从用户接收到的命令消息"""

    def __init__(
        self,
        source: str,
        command: str,
        args: Dict[str, Any],
        user: str,
        priority: SignalPriority = SignalPriority.HIGH,  # 命令默认高优先级
        target: Optional[str] = None,
        **extra_data,
    ):
        data = {
            "sensory_type": "command",
            "command": command,
            "args": args,
            "user": user,
            "raw_input": extra_data.get("raw_input"),
            **extra_data,
        }
        super().__init__(source=source, data=data, priority=priority, target=target)
