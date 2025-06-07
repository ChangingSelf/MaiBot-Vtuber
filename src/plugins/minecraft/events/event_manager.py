from typing import List, Any, Dict
import time
from .event import MinecraftEvent


class MinecraftEventManager:
    """Minecraft事件管理器"""

    def __init__(self, max_event_history: int = 20, config: Dict[str, Any] = None):
        self.max_event_history = max_event_history
        self.event_history: List[MinecraftEvent] = []

        # 从配置中读取参数
        self.config = config or {}
        event_manager_config = self.config.get("event_manager", {})

        # 配置化的阈值参数
        self.duplicate_event_time_window = event_manager_config.get("duplicate_event_time_window", 2.0)
        self.recent_events_range = event_manager_config.get("recent_events_range", 5)
        self.chat_similarity_time_window = event_manager_config.get("chat_similarity_time_window", 10.0)
        self.short_message_threshold = event_manager_config.get("short_message_threshold", 10)
        self.long_message_threshold = event_manager_config.get("long_message_threshold", 15)
        self.similarity_threshold = event_manager_config.get("similarity_threshold", 0.7)

    def update_event_history(self, agent_events: List[MinecraftEvent], current_step_num: int):
        """更新事件历史记录，去重并保留最近的记录"""
        if not agent_events:
            return

        current_timestamp = time.time()

        for event in agent_events:
            if not event or not event.message:
                continue

            # 创建增强的事件对象（复制原事件并添加时间戳信息）
            enhanced_event = MinecraftEvent(
                type=event.type,
                message=event.message,
                only_message=getattr(event, "only_message", ""),
                username=getattr(event, "username", ""),
                tick=getattr(event, "tick", 0),
            )
            # 添加额外的属性
            enhanced_event.timestamp = current_timestamp
            enhanced_event.step_num = current_step_num

            # 去重检查
            if not self._is_duplicate_event(enhanced_event, current_timestamp):
                self.event_history.append(enhanced_event)

        # 保持历史记录数量在限制范围内
        if len(self.event_history) > self.max_event_history:
            self.event_history = self.event_history[-self.max_event_history :]

    def _is_duplicate_event(self, event: MinecraftEvent, current_timestamp: float) -> bool:
        """检查是否为重复事件"""
        if not self.event_history:
            return False

        # 检查最近几条事件是否有完全相同的内容
        recent_events = self.event_history[-self.recent_events_range :]
        for recent_event in recent_events:
            # 只有在短时间内且内容完全相同时才认为是重复
            time_diff = current_timestamp - getattr(recent_event, "timestamp", 0)
            if (
                time_diff <= self.duplicate_event_time_window
                and recent_event.type == event.type
                and recent_event.message == event.message
            ):
                return True

            # 对于聊天消息，进行相似度检测
            if self._is_similar_chat_event(event, recent_event, time_diff):
                return True

        return False

    def _is_similar_chat_event(
        self, current_event: MinecraftEvent, recent_event: MinecraftEvent, time_diff: float
    ) -> bool:
        """检查聊天事件是否相似"""
        if current_event.type != "chat" or recent_event.type != "chat" or time_diff > self.chat_similarity_time_window:
            return False

        current_msg = current_event.message
        recent_msg = recent_event.message

        if len(current_msg) <= self.short_message_threshold or len(recent_msg) <= self.short_message_threshold:
            return False

        # 提取实际聊天内容
        current_content = self._extract_chat_content(current_msg)
        recent_content = self._extract_chat_content(recent_msg)
        # 检查内容相似性
        return (
            len(current_content) > self.long_message_threshold
            and len(recent_content) > self.long_message_threshold
            and (
                current_content in recent_content
                or recent_content in current_content
                or self._calculate_similarity(current_content, recent_content) > self.similarity_threshold
            )
        )

    def _extract_chat_content(self, message: str) -> str:
        """提取聊天消息的实际内容"""
        return message.split(">", 1)[-1].strip() if ">" in message else message

    def _calculate_similarity(self, text1: str, text2: str) -> float:
        """计算两个文本的相似度"""
        if not text1 or not text2:
            return 0.0

        text1 = text1.lower().replace(" ", "")
        text2 = text2.lower().replace(" ", "")

        if text1 == text2:
            return 1.0

        max_len = max(len(text1), len(text2))
        if max_len == 0:
            return 0.0

        common_chars = sum(min(text1.count(char), text2.count(char)) for char in set(text1))
        return common_chars / max_len

    def get_recent_events_text(self, agent_name: str = "Mai", max_count: int = None) -> List[str]:
        """获取最近事件的文本描述"""
        if not self.event_history:
            return []

        # 如果没有提供max_count，则使用配置中的值
        if max_count is None:
            prompt_config = self.config.get("prompt", {})
            max_count = prompt_config.get("max_event_display_count", 10)

        recent_events = self.event_history[-max_count:]
        event_messages = []

        for event in recent_events:
            if event.message:
                clean_message = event.message.replace(agent_name, "你")
                event_messages.append(f"[{event.type}] {clean_message}")

        return event_messages

    def get_current_events_text(self, current_events: List[MinecraftEvent], agent_name: str = "Mai") -> List[str]:
        """获取当前事件的文本描述"""
        event_messages = []
        if current_events:
            for event in current_events:
                if hasattr(event, "type") and hasattr(event, "message"):
                    clean_message = event.message.replace(agent_name, "你")
                    event_messages.append(f"[{event.type}] {clean_message}")
        return event_messages
