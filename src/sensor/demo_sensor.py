import asyncio
import time
import random
from src.sensor.sensor import Sensor
from src.neuro.synapse import Neurotransmitter
from src.utils.logger import logger
from maim_message.message_base import UserInfo


class DemoSensor(Sensor):
    """
    示例传感器，用于演示字幕功能
    """

    def __init__(self, synapse):
        super().__init__(synapse)
        self.running = False
        self.demo_users = ["用户A", "用户B", "用户C", "用户D", "用户E"]
        self.demo_messages = [
            "你好，麦麦！",
            "今天天气真不错",
            "你能帮我做些什么？",
            "讲个笑话吧",
            "我想听一首歌",
            "你最近怎么样？",
            "有什么有趣的事情吗？",
            "谢谢你的帮助",
            "再见，下次见！",
            "我很喜欢和你聊天",
        ]

    async def connect(self):
        """
        连接示例传感器
        """
        logger.info("示例传感器正在连接...")
        self.running = True

        # 启动消息生成循环
        asyncio.create_task(self._generate_messages())

        logger.info("示例传感器已连接")

    async def disconnect(self):
        """
        断开示例传感器
        """
        logger.info("示例传感器正在断开连接...")
        self.running = False
        logger.info("示例传感器已断开连接")

    async def _generate_messages(self):
        """
        生成示例消息
        """
        while self.running:
            try:
                # 随机等待1-5秒
                await asyncio.sleep(random.uniform(1, 5))

                # 随机选择用户和消息
                user_name = random.choice(self.demo_users)
                message = random.choice(self.demo_messages)

                # 创建用户信息
                user_info = UserInfo(user_id=f"demo_{int(time.time())}", user_nickname=user_name, user_avatar=None)

                # 发布神经递质
                await self.synapse.publish_input(
                    Neurotransmitter(raw_message=message, user_info=user_info, group_info=None)
                )

                # 添加到字幕
                self.add_input_to_subtitle(message, user_name)

                logger.info(f"示例传感器发送消息: {user_name}: {message}")

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"生成示例消息时出错: {e}", exc_info=True)

    async def run(self):
        """
        运行示例传感器
        """
        await self.connect()

        try:
            # 保持运行
            while self.running:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass
        finally:
            await self.disconnect()
