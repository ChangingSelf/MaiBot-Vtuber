from abc import ABC, abstractmethod
from enum import Enum, auto
from typing import Any, Dict, Optional
import uuid
import time
from datetime import datetime


class SignalPriority(Enum):
    """信号优先级枚举"""

    LOW = auto()
    NORMAL = auto()
    HIGH = auto()
    URGENT = auto()


class SignalType(Enum):
    """信号类型枚举"""

    SENSORY = auto()  # 感觉信号（输入）
    CORE = auto()  # 核心信号（内部处理）
    MOTOR = auto()  # 运动信号（输出）
    SYSTEM = auto()  # 系统信号（管理和控制）


class NeuralSignal(ABC):
    """神经信号基类 - 系统内传递的信息单元"""

    def __init__(
        self,
        signal_type: SignalType,
        source: str,
        data: Dict[str, Any],
        priority: SignalPriority = SignalPriority.NORMAL,
        target: Optional[str] = None,
    ):
        self.id = str(uuid.uuid4())
        self.timestamp = datetime.now()
        self.created_at = time.time()
        self.signal_type = signal_type
        self.source = source
        self.target = target
        self.data = data
        self.priority = priority
        self.processed = False
        self.processing_history = []

    def mark_processed(self, processor_id: str) -> None:
        """标记信号为已处理状态"""
        self.processed = True
        self.processing_history.append({"processor": processor_id, "time": time.time()})

    def add_processing_note(self, processor_id: str, note: str) -> None:
        """添加处理记录"""
        self.processing_history.append({"processor": processor_id, "time": time.time(), "note": note})

    def get_transit_time(self) -> float:
        """获取信号在系统中传递的时间（秒）"""
        return time.time() - self.created_at

    def to_dict(self) -> Dict[str, Any]:
        """将信号转换为字典格式"""
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat(),
            "signal_type": self.signal_type.name,
            "source": self.source,
            "target": self.target,
            "data": self.data,
            "priority": self.priority.name,
            "processed": self.processed,
            "processing_history": self.processing_history,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "NeuralSignal":
        """从字典创建信号（需要由子类实现）"""
        raise NotImplementedError("Subclasses must implement this method")
