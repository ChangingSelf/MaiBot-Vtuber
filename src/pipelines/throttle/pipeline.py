import time
import asyncio
from typing import Dict, Optional
from collections import defaultdict, deque

from maim_message import MessageBase
from src.core.pipeline_manager import MessagePipeline
from src.utils.logger import logger


class ThrottlePipeline(MessagePipeline):
    """
    限流管道，基于滑动时间窗口算法限制消息发送频率。

    功能：
    1. 全局消息频率限制 - 控制整个系统每分钟处理的消息总量
    2. 用户级别频率限制 - 控制单个用户每分钟可发送的消息数量
    """

    priority = 100  # 设置默认优先级

    def __init__(
        self,
        global_rate_limit: int = 100,  # 全局每分钟最大消息数
        user_rate_limit: int = 10,  # 每个用户每分钟最大消息数
        window_size: int = 60,  # 时间窗口大小（秒）
    ):
        """
        初始化限流管道。

        Args:
            global_rate_limit: 全局每分钟最大消息数量
            user_rate_limit: 每个用户每分钟最大消息数量
            window_size: 滑动窗口大小（秒）
        """
        self._global_rate_limit = global_rate_limit
        self._user_rate_limit = user_rate_limit
        self._window_size = window_size

        # 存储时间戳的数据结构
        self._global_timestamps = deque()  # 全局消息时间戳队列
        self._user_timestamps = defaultdict(deque)  # 用户级别消息时间戳队列

        # 并发控制
        self._cleanup_lock = asyncio.Lock()

        # 统计数据
        self._throttled_count = 0

        logger.info(
            f"限流管道初始化: 全局限制={global_rate_limit}/分钟, 用户限制={user_rate_limit}/分钟, 窗口={window_size}秒"
        )

    async def on_connect(self) -> None:
        """
        连接建立时重置状态。

        当 AmaidesuCore 成功连接到 MaiCore 时调用。
        重置所有计数器和时间戳队列，为新会话做准备。
        """
        async with self._cleanup_lock:
            # 清空所有时间戳队列
            self._global_timestamps.clear()
            self._user_timestamps.clear()

            # 重置统计数据
            self._throttled_count = 0

            logger.info("限流管道已重置状态（连接建立）")

    async def on_disconnect(self) -> None:
        """
        连接断开时进行清理。

        当 AmaidesuCore 与 MaiCore 断开连接时调用。
        记录最终统计数据并释放资源。
        """
        async with self._cleanup_lock:
            logger.info(f"限流管道会话结束统计: 共限流消息 {self._throttled_count} 条")

            # 清空所有队列释放内存
            self._global_timestamps.clear()
            self._user_timestamps.clear()

            logger.info("限流管道已清理资源（连接断开）")

    async def _clean_expired_timestamps(self, current_time: float) -> None:
        """
        清理过期的时间戳记录，保持滑动窗口更新。

        Args:
            current_time: 当前时间戳
        """
        async with self._cleanup_lock:
            # 计算截止时间点
            cutoff_time = current_time - self._window_size

            # 清理全局队列中的过期时间戳
            while self._global_timestamps and self._global_timestamps[0] < cutoff_time:
                self._global_timestamps.popleft()

            # 清理各用户队列中的过期时间戳
            for user_id, timestamps in list(self._user_timestamps.items()):
                while timestamps and timestamps[0] < cutoff_time:
                    timestamps.popleft()

                # 优化内存: 如果用户队列为空，则从字典中移除
                if not timestamps:
                    del self._user_timestamps[user_id]

    def _is_throttled(self, user_id: str) -> bool:
        """
        检查指定用户的消息是否应该被限流。

        Args:
            user_id: 用户ID

        Returns:
            如果应该限流返回True，否则返回False
        """
        # 检查全局限流
        global_count = len(self._global_timestamps)
        if global_count >= self._global_rate_limit:
            logger.warning(
                f"全局消息限流触发: 当前速率 {global_count}/{self._window_size}秒 "
                f"超过限制 {self._global_rate_limit}/{self._window_size}秒"
            )
            return True

        # 检查用户级别限流
        user_timestamps = self._user_timestamps.get(user_id)
        if user_timestamps and len(user_timestamps) >= self._user_rate_limit:
            logger.warning(
                f"用户 {user_id} 消息限流触发: 当前速率 {len(user_timestamps)}/{self._window_size}秒 "
                f"超过限制 {self._user_rate_limit}/{self._window_size}秒"
            )
            return True

        return False

    def _record_message(self, user_id: str, current_time: float) -> None:
        """
        记录消息的发送时间到对应队列。

        Args:
            user_id: 用户ID
            current_time: 当前时间戳
        """
        self._global_timestamps.append(current_time)
        self._user_timestamps[user_id].append(current_time)

    async def process_message(self, message: MessageBase) -> Optional[MessageBase]:
        """
        处理消息，根据限流规则决定是否允许该消息继续传递。

        Args:
            message: 要处理的消息对象

        Returns:
            如果允许继续传递则返回消息对象，否则返回None（丢弃消息）
        """

        user_id = (
            getattr(message.message_info.user_info, "user_id", "unknown_user")
            if message.message_info
            else "unknown_user"
        )

        current_time = time.time()

        # 清理过期记录
        await self._clean_expired_timestamps(current_time)

        # 检查是否应该限流
        if self._is_throttled(user_id):
            self._throttled_count += 1

            # 获取消息内容（用于日志）
            if hasattr(message, "message_segment"):
                if message.message_segment.type == "text":
                    content = f"内容={message.message_segment.data}"
                else:
                    content = f"类型={message.message_segment.type}"
            else:
                content = "未知内容"

            logger.info(f"消息限流: 用户={user_id}, {content}, 累计限流={self._throttled_count}")
            return None  # 丢弃该消息

        # 记录通过的消息
        self._record_message(user_id, current_time)

        # 返回原始消息，允许继续处理
        return message
