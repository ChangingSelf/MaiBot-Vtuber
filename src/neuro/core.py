from maim_message import Router, RouteConfig, TargetConfig
from maim_message.message_base import BaseMessageInfo, GroupInfo, MessageBase, Seg, UserInfo
from ..utils.config import global_config
from ..utils.logger import logger
import asyncio
import time

message_queue = asyncio.Queue()  # 全局消息队列


class MaiMaiCore:
    def __init__(self):
        """
        初始化平台路由
        """
        route_config = RouteConfig(
            route_config={
                global_config.platform: TargetConfig(
                    url=f"ws://{global_config.core_host}:{global_config.core_port}/ws",
                    token=None,
                )
            }
        )
        self.router = Router(route_config)

    async def connect(self, response_handler=None):
        """
        连接麦麦核心
        """
        logger.info("正在释放神经递质...")
        await self.register_handler(response_handler)
        await self.router.run()

    async def disconnect(self):
        """
        断开麦麦核心的连接
        """
        logger.info("正在切断与核心的连接...")
        await self.router.stop()

    async def send_message(self, raw_message: str, user_info: UserInfo, group_info: GroupInfo = None):
        """
        发送消息
        """

        time_stamp = int(time.time())

        # 消息信息
        message_info: BaseMessageInfo = BaseMessageInfo(
            platform=global_config.platform,
            message_id=time_stamp,
            time=time_stamp,
            user_info=user_info,
            group_info=group_info,
            template_info=None,
            format_info=None,
            additional_config={
                "maimcore_reply_probability_gain": 1,  # 回复概率增益
            },
        )

        # 处理实际信息，如果消息内容为空，则不发送
        if raw_message is None or raw_message.strip() == "":
            logger.warning("消息内容为空")
            return None

        submit_seg: Seg = Seg(
            type="text",
            data=raw_message,
        )
        # MessageBase创建
        message_base: MessageBase = MessageBase(
            message_info=message_info,
            message_segment=submit_seg,
            raw_message=raw_message,
        )

        logger.info(f"发送消息：{raw_message}")
        await self.router.send_message(message_base)

    async def register_handler(self, handler):
        """
        注册消息处理器

        处理器处理的是麦麦核心返回的响应消息
        """
        if handler is None:
            logger.warning("未指定处理器，使用默认处理器")
            handler = self.default_handler

        self.router.register_class_handler(handler)

    async def default_handler(self, raw_message_base_str: str):
        """
        默认处理器

        处理麦麦核心返回的消息，只将文本类型的信息通过日志打印输出到控制台
        """

        logger.info(f"大脑信息反馈至神经中枢: {raw_message_base_str}")
        raw_message_base: MessageBase = MessageBase.from_dict(raw_message_base_str)
        message_info: BaseMessageInfo = raw_message_base.message_info
        message_segment: Seg = raw_message_base.message_segment
        group_info: GroupInfo = message_info.group_info
        user_info: UserInfo = message_info.user_info

        if message_segment.type == "text":
            logger.info(f"【麦麦】: {message_segment.data}")
        else:
            logger.info(f"收到[{message_segment.type}]类型的消息")

    async def process_message_queue(self):
        """后台任务，处理来自传感器的输入消息"""
        logger.info("启动消息队列处理器...")
        while True:
            try:
                # 等待从队列中获取消息 (user_input, user_info)
                user_input, user_info = await message_queue.get()
                logger.debug(f"从队列接收到输入: {user_input[:20]}...")

                # 在这里调用核心的消息处理逻辑
                # 例如，调用一个处理输入的函数，或者直接在这里实现
                logger.info(f"正在处理来自 {user_info.user_nickname} 的输入: {user_input}")
                await self.send_message(user_input, user_info, None)

                # 标记任务完成，以便队列可以跟踪处理进度 (如果需要的话)
                message_queue.task_done()

            except asyncio.CancelledError:
                logger.info("消息队列处理器被取消。")
                break
            except Exception as e:
                logger.error(f"处理队列消息时出错: {e}", exc_info=True)
                # 可以在这里添加重试逻辑或错误处理


core = MaiMaiCore()
