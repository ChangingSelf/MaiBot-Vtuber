from typing import Any, Dict, Optional, Union, Type, List
import json
import logging

from src.signals.neural_signal import NeuralSignal, SignalType, SignalPriority
from src.signals.sensory_signals import SensorySignal, DanmakuSignal, CommandSignal
from src.signals.motor_signals import MotorSignal, SubtitleSignal, Live2DSignal

logger = logging.getLogger(__name__)


class SignalAdapter:
    """信号适配器 - 负责转换内部神经信号和外部消息格式"""

    @staticmethod
    def to_neural_signal(message: Dict[str, Any]) -> Optional[NeuralSignal]:
        """将外部消息转换为神经信号"""
        try:
            # 解析消息类型
            msg_type = message.get("type", "unknown")

            # 根据消息类型创建对应的神经信号
            if msg_type == "danmaku":
                return DanmakuSignal(
                    source="external",
                    platform=message.get("platform", "unknown"),
                    user=message.get("user", "anonymous"),
                    content=message.get("content", ""),
                    raw_input=message,
                )
            elif msg_type == "command":
                return CommandSignal(
                    source="external",
                    command=message.get("command", ""),
                    args=message.get("args", {}),
                    user=message.get("user", "admin"),
                    raw_input=message,
                )
            elif msg_type == "subtitle":
                return SubtitleSignal(
                    source="external",
                    text=message.get("text", ""),
                    duration=message.get("duration", 5.0),
                    style=message.get("style", {}),
                )
            elif msg_type == "live2d":
                return Live2DSignal(
                    source="external",
                    expression=message.get("expression"),
                    motion=message.get("motion"),
                    parameters=message.get("parameters", {}),
                    duration=message.get("duration", 3.0),
                )
            else:
                # 如果是未知类型，尝试根据消息内容推断
                if "content" in message and "user" in message:
                    return DanmakuSignal(
                        source="external",
                        platform="unknown",
                        user=message.get("user", "anonymous"),
                        content=message.get("content", ""),
                        raw_input=message,
                    )

                logger.warning(f"未知消息类型: {msg_type}, 消息内容: {message}")
                return None

        except Exception as e:
            logger.error(f"转换消息到神经信号时出错: {e}")
            logger.debug(f"问题消息: {message}")
            return None

    @staticmethod
    def to_maim_message(signal: NeuralSignal) -> Dict[str, Any]:
        """将神经信号转换为外部消息格式"""
        try:
            base_msg = {"id": signal.id, "timestamp": signal.timestamp.isoformat(), "source": signal.source}

            # 根据信号类型生成对应的消息
            if isinstance(signal, DanmakuSignal):
                return {
                    **base_msg,
                    "type": "danmaku",
                    "platform": signal.data.get("platform", "unknown"),
                    "user": signal.data.get("user", "anonymous"),
                    "content": signal.data.get("content", ""),
                }
            elif isinstance(signal, CommandSignal):
                return {
                    **base_msg,
                    "type": "command",
                    "command": signal.data.get("command", ""),
                    "args": signal.data.get("args", {}),
                    "user": signal.data.get("user", "admin"),
                }
            elif isinstance(signal, SubtitleSignal):
                return {
                    **base_msg,
                    "type": "subtitle",
                    "text": signal.data.get("text", ""),
                    "duration": signal.data.get("duration", 5.0),
                    "style": signal.data.get("style", {}),
                }
            elif isinstance(signal, Live2DSignal):
                return {
                    **base_msg,
                    "type": "live2d",
                    "expression": signal.data.get("expression"),
                    "motion": signal.data.get("motion"),
                    "parameters": signal.data.get("parameters", {}),
                    "duration": signal.data.get("duration", 3.0),
                }
            else:
                # 通用转换
                return {**base_msg, "type": signal.signal_type.name.lower(), "data": signal.data}

        except Exception as e:
            logger.error(f"转换神经信号到消息时出错: {e}")
            logger.debug(f"问题信号: {signal.to_dict() if hasattr(signal, 'to_dict') else signal}")
            return {"type": "error", "error": str(e), "source": getattr(signal, "source", "unknown")}
