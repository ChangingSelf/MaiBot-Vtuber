import asyncio
from typing import Any, Dict, Optional, List
import time
import mineland
import os
import tomllib

from src.core.plugin_manager import BasePlugin
from src.core.amaidesu_core import AmaidesuCore
from maim_message import MessageBase, TemplateInfo, UserInfo, GroupInfo, FormatInfo, BaseMessageInfo, Seg

from .core.prompt_builder import build_state_analysis, build_prompt
from .core.action_handler import parse_mineland_action, execute_mineland_action
from mineland import Observation, CodeInfo, Event
# logger = get_logger("MinecraftPlugin") # 已由基类初始化


class MinecraftPlugin(BasePlugin):
    def __init__(self, core: AmaidesuCore, plugin_config: Dict[str, Any]):
        super().__init__(core, plugin_config)

        # self.plugin_config = load_plugin_config() # 基类已将正确的 plugin_config 赋值给 self.plugin_config
        # minecraft_config = self.plugin_config.get("minecraft", {}) # self.plugin_config 已经是 minecraft 插件的配置
        minecraft_config = self.plugin_config

        # 从配置文件加载所有配置
        self.task_id: str = minecraft_config.get("mineland_task_id", "playground")

        # 智能体配置，默认为1个智能体
        self.agents_count: int = 1  # 目前硬编码为1，将来可以考虑加入配置
        # self.agents_config: List[Dict[str, str]] = [{"name": f"MaiMai{i}"} for i in range(self.agents_count)]
        self.agents_config: List[Dict[str, str]] = [{"name": "MaiMai"}]

        self.headless: bool = minecraft_config.get("mineland_headless", True)

        # 检查 image_size 是否为列表并有两个元素
        image_size_config = minecraft_config.get("mineland_image_size", [180, 320])
        if isinstance(image_size_config, list) and len(image_size_config) == 2:
            self.image_size: tuple[int, int] = tuple(image_size_config)
        else:
            self.logger.warning(f"配置的 image_size 无效: {image_size_config}，使用默认值 (180, 320)")
            self.image_size: tuple[int, int] = (180, 320)

        self.ticks_per_step: int = minecraft_config.get("mineland_ticks_per_step", 20)

        self.user_id: str = minecraft_config.get("user_id", "minecraft_bot")
        self.group_id: Optional[str] = minecraft_config.get("group_id")
        self.nickname: str = minecraft_config.get("nickname", "Minecraft Observer")

        # 添加定期发送状态的配置
        self.auto_send_interval: float = minecraft_config.get("auto_send_interval", 30.0)  # 默认30秒
        self._auto_send_task: Optional[asyncio.Task] = None
        self._last_response_time: float = 0.0

        # 上下文标签配置
        self.context_tags: Optional[List[str]] = minecraft_config.get("context_tags")
        if not isinstance(self.context_tags, list):
            if self.context_tags is not None:
                self.logger.warning(
                    f"Config 'context_tags' is not a list ({type(self.context_tags)}), will fetch all context."
                )
            self.context_tags = None

        # Mineland 实例
        self.mland: Optional[mineland.MineLand] = None
        # Mineland 状态变量
        self.current_obs: Optional[List[Observation]] = None  # 当前观察值
        self.current_code_info: Optional[List[CodeInfo]] = None  # 当前代码信息 (根据mineland_script.py是列表)
        self.current_event: Optional[List[List[Event]]] = None  # 当前事件 (根据mineland_script.py是列表的列表)
        self.current_done: bool = False  # 当前是否完成
        self.current_task_info: Optional[Dict[str, Any]] = None  # 当前任务信息
        self.current_step_num: int = 0  # 当前步数

    async def setup(self):
        await super().setup()
        # MaiCore 将通过此 handler 发送动作指令给插件
        self.core.register_websocket_handler("text", self.handle_maicore_response)

        self.logger.info("Minecraft 插件已加载，正在初始化 MineLand 环境...")
        try:
            # self.mland = mineland.make(
            #     task_id=self.task_id,
            #     agents_count=self.agents_count,
            #     agents_config=self.agents_config,
            #     headless=self.headless,
            #     image_size=self.image_size,
            #     enable_low_level_action=self.enable_low_level_action,
            #     ticks_per_step=self.ticks_per_step,
            # )
            self.mland = mineland.MineLand(
                server_host="127.0.0.1",
                server_port=1746,
                agents_count=self.agents_count,
                agents_config=self.agents_config,
                headless=self.headless,
                image_size=self.image_size,
                enable_low_level_action=False,  # 全都使用高级动作
                ticks_per_step=self.ticks_per_step,
            )
            self.logger.info(f"MineLand 环境 (Task ID: {self.task_id}) 初始化成功。")

            # 重置环境并获取初始观察
            self.current_obs = self.mland.reset()  # 所有智能体的观察值
            self.current_code_info = [None] * self.agents_count
            self.current_event = [[] for _ in range(self.agents_count)]
            self.current_done = False
            self.current_task_info = {}  # 通常在 step 后更新
            self.current_step_num = 0

            self.logger.info(f"MineLand 环境已重置，收到初始观察: {len(self.current_obs)} 个智能体。")

            # 等待几秒钟，确保 MaiCore 连接
            await asyncio.sleep(5)

            # 发送初始状态给 MaiCore
            await self._send_state_to_maicore()

            # 启动自动发送任务
            self._auto_send_task = asyncio.create_task(self._auto_send_loop(), name="MinecraftAutoSend")
            self.logger.info(f"已启动自动发送状态任务，间隔: {self.auto_send_interval}秒")

        except Exception as e:
            self.logger.exception(f"初始化 MineLand 环境失败: {e}", exc_info=True)
            # 可以在这里决定是否阻止插件加载或进行其他处理
            return  # 阻止进一步设置

    async def _auto_send_loop(self):
        """定期发送状态的循环任务"""
        while True:
            try:
                await asyncio.sleep(self.auto_send_interval)

                # 检查是否收到过响应
                current_time = time.time()
                if current_time - self._last_response_time > self.auto_send_interval:
                    self.logger.info("未收到响应，重新发送状态...")
                    await self._send_state_to_maicore()

            except asyncio.CancelledError:
                self.logger.info("自动发送状态任务被取消")
                break
            except Exception as e:
                self.logger.error(f"自动发送状态时出错: {e}", exc_info=True)
                await asyncio.sleep(1)  # 出错时等待一秒再继续

    async def _send_state_to_maicore(self):
        """构建并发送当前Mineland状态给AmaidesuCore。"""

        # 确保有观察数据且为列表
        if not self.current_obs or not isinstance(self.current_obs, list) or len(self.current_obs) == 0:
            self.logger.warning("当前没有可用的观察数据，无法构建状态")
            return

        # 分析当前游戏状态
        agent_obs = self.current_obs[0]  # 当前仅支持单智能体
        status_prompts = build_state_analysis(agent_obs, self.current_event, self.current_code_info)

        # 准备发送消息
        current_time = int(time.time())
        message_id = int(time.time())

        user_info = UserInfo(platform=self.core.platform, user_id=str(self.user_id), user_nickname=self.nickname)

        group_info = None
        if self.group_id:
            group_info = GroupInfo(
                platform=self.core.platform,
                group_id=self.group_id,
            )

        format_info = FormatInfo(content_format="text", accept_format="text")  # 保持文本格式，内容是JSON字符串

        # --- 构建Template Info ---
        # 创建一个包含提示词的模板项字典
        template_items = build_prompt(status_prompts, self.current_obs)

        # 直接构建最终的template_info结构
        template_info = TemplateInfo(
            template_items=template_items,
            template_name="Minecraft",
            template_default=False,
        )

        message_info = BaseMessageInfo(
            platform=self.core.platform,
            message_id=message_id,
            time=current_time,
            user_info=user_info,
            group_info=group_info,
            format_info=format_info,
            additional_config={
                "maimcore_reply_probability_gain": 1,  # 确保必然回复
            },
            template_info=template_info,  # 使用构建好的template_info
        )

        # 当使用template_info时，消息内容可以简化
        message_text = f"你已完成了第{self.current_step_num}步动作，请根据当前游戏状态，给出下一步动作，目标是收集64个原木（oak_log）。"
        message_segment = Seg(type="text", data=message_text)

        msg_to_maicore = MessageBase(
            message_info=message_info, message_segment=message_segment, raw_message=message_text
        )

        await self.core.send_to_maicore(msg_to_maicore)
        self.logger.info(
            f"已将 Mineland 状态 (step {self.current_step_num}, done: {self.current_done}) 发送给 MaiCore。"
        )

    async def handle_maicore_response(self, message: MessageBase):
        """处理从 MaiCore 返回的动作指令。"""
        self.logger.info(f"收到来自 MaiCore 的响应: {message.message_segment.data}")

        # 更新最后响应时间
        self._last_response_time = time.time()

        if not self.mland:
            self.logger.exception("收到 MaiCore 响应，但 MineLand 环境未初始化。忽略消息。")
            return

        if message.message_segment.type != "text":
            self.logger.warning(
                f"MaiCore 返回的消息不是文本消息: type='{message.message_segment.type}'. 期望是'text' (包含JSON格式的动作指令)。丢弃消息。"
            )
            return

        action_json_str = message.message_segment.data.strip()
        self.logger.debug(f"从 MaiCore 收到原始动作指令: {action_json_str}")

        # 解析动作
        current_actions = parse_mineland_action(
            action_json_str=action_json_str,
            agents_count=self.agents_count,
            current_step_num=self.current_step_num,
        )

        # 在 MineLand 环境中执行动作
        try:
            next_obs, next_code_info, next_event, next_done, next_task_info = execute_mineland_action(
                mland=self.mland, current_actions=current_actions
            )

            # 更新状态
            self.current_obs = next_obs
            self.current_code_info = next_code_info
            self.current_event = next_event
            self.current_done = next_done
            self.current_task_info = next_task_info
            self.current_step_num += 1

            # 对于单Agent，通常直接取done[0]
            # 如果是多Agent，需要决定整体的done状态 (当前仅支持单Agent)
            effective_done = (
                self.current_done[0] if isinstance(self.current_done, list) and self.current_done else False
            )

            self.logger.debug(
                f"步骤 {self.current_step_num - 1} MineLand step 执行完毕。Effective Done: {effective_done}"
            )

            if effective_done:
                self.logger.info(f"任务在步骤 {self.current_step_num - 1} 完成。将重置环境并发送新初始状态。")
                self.current_obs = self.mland.reset()
                self.current_code_info = [None] * self.agents_count
                self.current_event = [[] for _ in range(self.agents_count)]
                self.current_done = False  # 重置 done 状态
                self.current_task_info = {}
                self.current_step_num = 0  # 为新的回合重置步数
                self.logger.info("环境已重置，收到新的初始观察。")

            # 发送新的状态给 MaiCore
            await self._send_state_to_maicore()

        except Exception as e:
            self.logger.exception(f"执行 Mineland step 或处理后续状态时出错: {e}", exc_info=True)
            # 此处可能需要更复杂的错误处理，例如尝试重置环境或停止插件

    async def cleanup(self):
        self.logger.info("正在清理 Minecraft 插件...")

        # 停止自动发送任务
        if self._auto_send_task:
            self.logger.info("正在停止自动发送状态任务...")
            self._auto_send_task.cancel()
            try:
                await self._auto_send_task
            except asyncio.CancelledError:
                pass
            self._auto_send_task = None

        if self.mland:
            try:
                self.logger.info("正在关闭 MineLand 环境...")
                self.mland.close()
                self.logger.info("MineLand 环境已关闭。")
            except Exception as e:
                self.logger.exception(f"关闭 MineLand 环境时发生错误: {e}", exc_info=True)

        self.logger.info("Minecraft 插件清理完毕。")


# --- Plugin Entry Point ---
# --- 插件入口点 ---
plugin_entrypoint = MinecraftPlugin
