from typing import Any, Dict, Optional
from datetime import datetime

from src.signals.neural_signal import NeuralSignal, SignalType, SignalPriority


class MotorSignal(NeuralSignal):
    """运动信号 - 用于控制外部行为的信号"""

    def __init__(
        self,
        source: str,
        data: Dict[str, Any],
        priority: SignalPriority = SignalPriority.NORMAL,
        target: Optional[str] = None,
    ):
        super().__init__(signal_type=SignalType.MOTOR, source=source, data=data, priority=priority, target=target)
        # 添加运动信号特有的属性
        self.action_type = data.get("action_type", "unknown")

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MotorSignal":
        """从字典创建运动信号"""
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


class SubtitleSignal(MotorSignal):
    """字幕信号 - 控制字幕显示的信号"""

    def __init__(
        self,
        source: str,
        text: str,
        duration: float = 5.0,  # 默认持续5秒
        style: Optional[Dict[str, Any]] = None,
        priority: SignalPriority = SignalPriority.NORMAL,
        target: Optional[str] = None,
        **extra_data,
    ):
        style = style or {}
        data = {"action_type": "subtitle", "text": text, "duration": duration, "style": style, **extra_data}
        super().__init__(source=source, data=data, priority=priority, target=target)


class Live2DSignal(MotorSignal):
    """Live2D控制信号 - 控制Live2D模型表情和动作的信号"""

    def __init__(
        self,
        source: str,
        expression: Optional[str] = None,
        motion: Optional[str] = None,
        parameters: Optional[Dict[str, float]] = None,
        duration: float = 3.0,  # 默认持续3秒
        priority: SignalPriority = SignalPriority.NORMAL,
        target: Optional[str] = None,
        **extra_data,
    ):
        parameters = parameters or {}
        data = {
            "action_type": "live2d",
            "expression": expression,
            "motion": motion,
            "parameters": parameters,
            "duration": duration,
            **extra_data,
        }
        super().__init__(source=source, data=data, priority=priority, target=target)
