from maim_message.message_base import GroupInfo, UserInfo
from ..neuro.synapse import Neurotransmitter, Synapse, synapse
from .sensor import Sensor
from ..utils.logger import logger
import asyncio
import random
from ..utils.config import global_config
from ..data.mock_danmaku_data import MOCK_USERS, MOCK_MESSAGES, MOCK_GROUP_INFO


class DanmakuMockSensor(Sensor):
    def __init__(self, synapse: Synapse):
        super().__init__(synapse)
        self.running = False
        # 从外部文件导入模拟数据
        self.users = MOCK_USERS
        self.messages = MOCK_MESSAGES
        self.group_info = MOCK_GROUP_INFO

    async def connect(self):
        """制造模拟消息放入队列"""

        await asyncio.sleep(2)  # 等待核心连接
        self.running = True
        while self.running:
            # 随机选择一个用户和消息
            user = random.choice(self.users)
            message = random.choice(self.messages)

            logger.info(f"Mock 传感器已启动，将模拟消息发送至核心: {user['nickname']} 说: {message}")

            # 构造用户信息
            user_info = UserInfo(
                platform=global_config.platform,
                user_id=user["id"],
                user_nickname=user["nickname"],
                user_cardname=user["cardname"],
            )

            group_info = GroupInfo(
                platform=global_config.platform,
                group_id=self.group_info["group_id"],
                group_name=self.group_info["group_name"],
            )

            await self.synapse.publish_input(
                Neurotransmitter(raw_message=message, user_info=user_info, group_info=group_info)
            )
            await asyncio.sleep(10)


danmaku_mock_sensor = DanmakuMockSensor(synapse)
