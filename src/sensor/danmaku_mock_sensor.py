from maim_message.message_base import UserInfo

from src.neuro.synapse import Neurotransmitter, Synapse, synapse
from .sensor import Sensor
from ..utils.logger import logger
import asyncio
import random
from ..utils.config import global_config


class DanmakuMockSensor(Sensor):
    def __init__(self, synapse: Synapse):
        super().__init__(synapse)
        self.running = False
        # 模拟用户数据
        self.users = [
            {"id": 1001, "nickname": "快乐的小猫咪", "cardname": "快乐的小猫咪"},
            {"id": 1002, "nickname": "游戏达人", "cardname": "游戏达人"},
            {"id": 1003, "nickname": "音乐爱好者", "cardname": "音乐爱好者"},
            {"id": 1004, "nickname": "动漫迷", "cardname": "动漫迷"},
            {"id": 1005, "nickname": "科技控", "cardname": "科技控"},
            {"id": 1006, "nickname": "美食家", "cardname": "美食家"},
            {"id": 1007, "nickname": "旅行者", "cardname": "旅行者"},
            {"id": 1008, "nickname": "摄影师", "cardname": "摄影师"},
            {"id": 1009, "nickname": "读书人", "cardname": "读书人"},
            {"id": 1010, "nickname": "运动健将", "cardname": "运动健将"},
        ]
        # 模拟消息内容
        self.messages = [
            "主播好厉害！",
            "这个游戏我也玩过，太难了",
            "主播的声音真好听",
            "666666",
            "主播玩得真溜",
            "这个操作太秀了",
            "主播今天状态不错啊",
            "这个游戏叫什么名字？",
            "主播玩得真开心",
            "主播好可爱啊",
            "这个游戏我也想玩",
            "主播玩得真快",
            "主播玩得真稳",
            "主播玩得真准",
            "主播玩得真狠",
            "主播玩得真猛",
            "主播玩得真强",
            "主播玩得真棒",
            "主播玩得真好",
            "主播玩得真绝",
        ]

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

            await self.synapse.publish_input(
                Neurotransmitter(raw_message=message, user_info=user_info, group_info=None)
            )
            await asyncio.sleep(10)


danmaku_mock_sensor = DanmakuMockSensor(synapse)
