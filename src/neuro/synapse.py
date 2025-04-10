import asyncio
from maim_message.message_base import GroupInfo, UserInfo


class Neurotransmitter:
    """
    神经递质(Neurotransmitter)

    神经递质是化学信号分子，携带特定信息（如兴奋或抑制）通过突触间隙，作用于目标细胞的受体，触发后续反应。
    """

    def __init__(self, raw_message: str, user_info: UserInfo, group_info: GroupInfo):
        self.raw_message = raw_message
        self.user_info = user_info
        self.group_info = group_info


class Synapse:
    """
    突触(Synapse)是神经元之间的连接结构，负责将信号（由神经递质携带）从一个神经元传递到另一个神经元或效应器细胞。它是信息传递的中间媒介，确保信号的定向传递和整合。
    """

    def __init__(self):
        self.input_queue = asyncio.Queue()  # 输入消息队列，生产者是需适配的平台，消费者是麦麦核心
        self.output_queue = asyncio.Queue()  # 输出消息队列，生产者是麦麦核心，消费者是执行器

    async def publish_input(self, neurotransmitter: Neurotransmitter):
        """发布神经递质到突触"""
        await self.input_queue.put(neurotransmitter)

    async def consume_input(self) -> Neurotransmitter:
        """神经元从突触中获取神经递质"""
        return await self.input_queue.get()

    async def publish_output(self, neurotransmitter: Neurotransmitter):
        """发布神经递质到突触"""
        await self.output_queue.put(neurotransmitter)

    async def consume_output(self) -> Neurotransmitter:
        """神经元从突触中获取神经递质"""
        return await self.output_queue.get()


synapse = Synapse()
