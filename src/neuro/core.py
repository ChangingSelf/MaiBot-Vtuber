from maim_message import Router, RouteConfig, TargetConfig
from maim_message.message_base import BaseMessageInfo, FormatInfo, GroupInfo, MessageBase, Seg, TemplateInfo, UserInfo
from ..utils.config import global_config
from ..utils.logger import logger
import asyncio
import time
from .synapse import Synapse, synapse, Neurotransmitter
from ..actuator.subtitle_actuator import SubtitleActuator
from ..actuator.vts_client import VtubeStudioClient
import json


class NeuroCore:
    """
    神经中枢(Core)是神经系统的核心，负责处理和整合来自传感器的信息，并生成输出信号。它协调神经元之间的信息传递，确保神经系统正常运作。
    """

    def __init__(self, synapse: Synapse):
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
        self.synapse = synapse
        self.subtitle_actuator = SubtitleActuator(synapse, show_history=False)

    async def connect(self, response_handler=None):
        """
        连接麦麦核心
        """
        logger.info("正在释放神经递质...")
        await self.register_handler(response_handler)

        # 连接字幕执行器
        await self.subtitle_actuator.connect()

        # 创建VTS管理器实例
        self.vts_client = VtubeStudioClient(
            plugin_name=global_config.plugin_name,
            developer=global_config.developer,
        )

        # 连接到VTS
        connected = await self.vts_client.connect()
        if not connected:
            logger.error("无法连接到VTS，程序退出")
            return

        await self.router.run()

    async def disconnect(self):
        """
        断开麦麦核心的连接
        """
        logger.info("正在切断与核心的连接...")
        await self.router.stop()

        # 断开字幕执行器
        await self.subtitle_actuator.disconnect()

    async def send_message(self, raw_message: str, user_info: UserInfo, group_info: GroupInfo = None):
        """
        发送消息
        """

        time_stamp = int(time.time())

        format_info = FormatInfo(
            # 消息内容中包含的Seg的type列表
            content_format=["text"],
            # 消息发出后，期望最终的消息中包含的消息类型，可以帮助某些plugin判断是否向消息中添加某些消息类型
            accept_format=[
                "text",
                "emoji",  # 表情包可以保存下来用vts的load_item显示在场景中，不过暂未实现
            ],
        )

        # 自定义提示词模板
        template_info_custom = await self.init_vts_prompt()

        # 消息信息
        message_info: BaseMessageInfo = BaseMessageInfo(
            platform=global_config.platform,
            message_id=time_stamp,
            time=time_stamp,
            user_info=user_info,
            group_info=group_info,
            template_info=template_info_custom,
            format_info=format_info,
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
        logger.info(f"大脑信息反馈至神经中枢: {raw_message_base_str[:200]}...")
        raw_message_base: MessageBase = MessageBase.from_dict(raw_message_base_str)
        message_info: BaseMessageInfo = raw_message_base.message_info
        message_segment: Seg = raw_message_base.message_segment
        group_info: GroupInfo = message_info.group_info
        user_info: UserInfo = message_info.user_info
        user_info.user_nickname = "麦麦"

        if message_segment.type == "text":
            message_text = message_segment.data
            process_message = False
            hotkey = ""

            # 尝试将整个消息解析为JSON对象
            try:
                # 解析消息内容
                response_json = json.loads(message_text)

                # 提取回复文本和热键
                if isinstance(response_json, dict):
                    if "reply" in response_json:
                        message_text = response_json["reply"]
                        process_message = True
                    else:
                        logger.warning("JSON中缺少'reply'字段，丢弃消息")
                        return

                    if "hotkey" in response_json and isinstance(response_json["hotkey"], str):
                        hotkey = response_json["hotkey"]
                        if hotkey:
                            # 使用ensure_ascii=False确保中文正确显示
                            logger.info(f"检测到热键: {hotkey}")
                        else:
                            logger.info("热键为空字符串")
                    else:
                        logger.info("JSON中无热键或热键格式不正确")
                else:
                    logger.warning("解析的JSON不是字典格式，丢弃消息")
                    return
            except json.JSONDecodeError:
                # 不是合法的JSON，丢弃
                logger.info("消息不是JSON格式，丢弃")
                return
            except Exception as e:
                logger.error(f"解析消息JSON失败: {e}")
                return

            if not process_message:
                logger.warning("消息处理失败，丢弃")
                return

            logger.info(f"【麦麦】: {message_text}")

            # 发布神经递质到突触
            try:
                await self.synapse.publish_output(
                    Neurotransmitter(
                        raw_message=message_text,
                        user_info=user_info,
                        group_info=group_info,
                    )
                )
            except Exception as e:
                logger.error(f"发布消息到神经突触失败: {e}")

            # 触发热键（如果不为空）
            if hotkey:
                try:
                    # 确保热键名称正确显示
                    logger.info(f"触发热键: {hotkey}")
                    await self.vts_client.trigger_hotkey(hotkey)
                except Exception as e:
                    logger.error(f"触发热键'{hotkey}'失败: {e}")
        else:
            logger.info(f"收到[{message_segment.type}]类型的消息")

    async def process_input(self):
        """后台任务，处理来自传感器的输入消息"""
        logger.info("启动消息队列处理器...")
        while True:
            try:
                # 等待从队列中获取消息 (user_input, user_info)
                neurotransmitter = await self.synapse.consume_input()
                logger.debug(f"从队列接收到输入: {neurotransmitter.raw_message[:20]}...")
                # 处理消息
                logger.info(
                    f"正在处理来自 {neurotransmitter.user_info.user_nickname} 的输入: {neurotransmitter.raw_message}"
                )
                await self.send_message(neurotransmitter.raw_message, neurotransmitter.user_info, None)

            except asyncio.CancelledError:
                logger.info("消息队列处理器被取消。")
                break
            except Exception as e:
                logger.error(f"处理队列消息时出错: {e}", exc_info=True)

    async def init_vts_prompt(self):
        """初始化vts提示词"""

        hotkey_list = await self.vts_client.get_hotkey_list()

        main_prompt = (
            """
            {relation_prompt_all}
            {memory_prompt}
            {prompt_info}
            {schedule_prompt}
            {chat_target}
            {chat_talking_prompt}
            你是一个AI主播，正在bilibili直播间直播，现在弹幕中用户[{sender_name}]说的「{message_txt}」引起了你的注意，请你根据当前的直播内容{chat_target_2},以及之前的弹幕记录，给出日常且口语化的、适合主播回复观众的回复，说中文，不要刻意突出自身学科背景，尽量不要说你说过的话。你的Live2D皮套有如下热键：
            """
            + json.dumps(hotkey_list, ensure_ascii=False)
            + """。必须以标准json格式返回一个json对象，不允许返回其他任何内容，示例如下：
            \{
                "reply": "回复内容",
                "hotkey": "热键名称"
            \}
            
            注意事项：
            1. 必须只使用上面提供的热键列表中的热键，不要发明不存在的热键
            2. 如果没有合适的热键，返回空字符串
            3. 不要用markdown代码块包裹
            """
        )

        return TemplateInfo(
            template_items={
                "reasoning_prompt_main": main_prompt,
                "heart_flow_prompt_normal": main_prompt,
            },
            template_name="qq123_default",
            template_default=False,
        )


core = NeuroCore(synapse)
