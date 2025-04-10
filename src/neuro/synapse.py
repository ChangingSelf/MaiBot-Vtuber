import asyncio
from typing import Callable, List, Optional
from maim_message.message_base import GroupInfo, UserInfo
from ..utils.logger import logger


class Neurotransmitter:
    """
    神经递质(Neurotransmitter)是神经元之间传递信息的化学物质。在这里，我们用它来表示传感器和执行器之间传递的消息。
    """

    def __init__(
        self,
        raw_message: str,
        user_info: Optional[UserInfo] = None,
        group_info: Optional[GroupInfo] = None,
    ):
        self.raw_message = raw_message
        self.user_info = user_info
        self.group_info = group_info


class Synapse:
    """
    突触(Synapse)是神经元之间传递信息的结构。在这里，我们用它来表示传感器和执行器之间的连接。
    """

    def __init__(self):
        """
        初始化突触
        """
        self.input_queue = asyncio.Queue()  # 输入队列
        self.output_handlers: List[Callable] = []  # 输出处理器列表

    async def publish_input(self, neurotransmitter: Neurotransmitter):
        """
        发布输入神经递质
        """
        await self.input_queue.put(neurotransmitter)

    async def consume_input(self) -> Neurotransmitter:
        """
        消费输入神经递质
        """
        return await self.input_queue.get()

    async def publish_output(self, neurotransmitter: Neurotransmitter):
        """
        发布输出神经递质
        """
        for handler in self.output_handlers:
            try:
                await handler(neurotransmitter)
            except Exception as e:
                logger.error(f"处理输出神经递质时出错: {e}", exc_info=True)

    async def subscribe_output(self, handler: Callable):
        """
        订阅输出神经递质
        """
        if handler not in self.output_handlers:
            self.output_handlers.append(handler)
            logger.debug(f"已添加输出处理器: {handler.__name__}")

    async def unsubscribe_output(self, handler: Callable):
        """
        取消订阅输出神经递质
        """
        if handler in self.output_handlers:
            self.output_handlers.remove(handler)
            logger.debug(f"已移除输出处理器: {handler.__name__}")


# 创建全局突触实例
synapse = Synapse()
