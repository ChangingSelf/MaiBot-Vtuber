from typing import Any, Dict, Optional
import logging
import time

from src.signals.neural_signal import NeuralSignal, SignalType
from src.signals.sensory_signals import DanmakuSignal, CommandSignal
from src.signals.motor_signals import SubtitleSignal, Live2DSignal

# 引入maim_message包中的类
from maim_message import (
    BaseMessageInfo,
    MessageBase,
    Seg,
    UserInfo,
    GroupInfo,
)

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
    def to_maim_message(signal: NeuralSignal) -> MessageBase:
        """将神经信号转换为MaiM消息格式，遵循MaimCore接口规范

        将NeuralSignal转换为符合MaimCore消息接口的格式，使用maim_message包中的类

        Args:
            signal: 神经信号对象

        Returns:
            符合MaimCore消息规范的MessageBase对象
        """
        try:
            # 获取当前时间戳
            time_stamp = int(time.time())
            platform = signal.data.get("platform", "unknown")

            # 创建用户信息
            user_info = UserInfo(
                platform=platform,
                user_id=signal.data.get("user_id", time_stamp),
                user_nickname=signal.data.get("user", "MaiBot"),
                user_cardname=signal.data.get("user_cardname", None),
            )

            # 创建群组信息（如果有）
            group_info = None
            if "group_id" in signal.data:
                group_info = GroupInfo(
                    platform=platform,
                    group_id=signal.data.get("group_id"),
                    group_name=signal.data.get("group_name", None),
                )

            # 基础消息信息
            message_info = BaseMessageInfo(
                platform=platform,
                message_id=signal.id,
                time=time_stamp,
                user_info=user_info,
                group_info=group_info,
                additional_config={"maimcore_reply_probability_gain": signal.data.get("reply_probability_gain", 1)},
            )

            # 处理消息段内容
            content = ""
            seg_type = "text"

            if isinstance(signal, DanmakuSignal):
                content = signal.data.get("content", "")
            elif isinstance(signal, SubtitleSignal):
                content = signal.data.get("text", "")
            else:
                # 如果是其他信号类型，尝试获取文本内容
                content = signal.data.get("text", signal.data.get("content", ""))
                # 如果是特殊类型，设置对应的段类型
                if signal.signal_type == SignalType.MOTOR:
                    action_type = signal.data.get("action_type")
                    if action_type == "image":
                        seg_type = "image"
                        content = signal.data.get("url", "")

            # 创建消息段
            message_segment = Seg(type=seg_type, data=content)

            # 创建完整消息
            message_base = MessageBase(message_info=message_info, message_segment=message_segment, raw_message=content)

            return message_base

        except Exception as e:
            logger.error(f"转换神经信号到MaiM消息时出错: {e}")
            logger.debug(f"问题信号: {signal.to_dict() if hasattr(signal, 'to_dict') else signal}")

            # 创建错误消息
            error_info = BaseMessageInfo(
                platform="error",
                message_id="error",
                time=int(time.time()),
                user_info=UserInfo(platform="error", user_nickname="System"),
            )
            error_seg = Seg(type="text", data=f"错误: {str(e)}")

            return MessageBase(message_info=error_info, message_segment=error_seg, raw_message=f"错误: {str(e)}")
