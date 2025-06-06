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
from .core.action_handler import parse_message_json, execute_mineland_action
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
        self.server_host: str = minecraft_config.get("server_host", "127.0.0.1")
        self.server_port: int = minecraft_config.get("server_port", 1746)

        # 智能体配置，默认为1个智能体
        self.agents_count: int = 1  # 目前硬编码为1，将来可以考虑加入配置
        # self.agents_config: List[Dict[str, str]] = [{"name": f"MaiMai{i}"} for i in range(self.agents_count)]
        self.agents_config: List[Dict[str, str]] = [{"name": "Mai"}]

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

        # 添加动作完成等待配置
        self.max_wait_cycles: int = minecraft_config.get("max_wait_cycles", 100)  # 最大等待周期数
        self.wait_cycle_interval: float = minecraft_config.get("wait_cycle_interval", 0.1)  # 等待周期间隔(秒)

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
        self.goal: str = "挖到铁矿"  # 当前目标

        # 目标历史记录
        self.goal_history: List[Dict[str, Any]] = []  # 存储目标历史，每个元素包含目标、时间戳和步数

        # 添加计划和进度相关字段
        self.current_plan: List[str] = []  # 当前计划
        self.current_step: str = "暂无步骤"  # 当前执行步骤
        self.target_value: int = 0  # 目标值
        self.current_value: int = 0  # 当前完成度

        # 添加事件历史记录
        self.event_history: List[Dict[str, Any]] = []  # 存储去重后的事件历史，最多保留20条
        self.max_event_history: int = 20  # 最大事件历史记录数量

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
                server_host=self.server_host,
                server_port=self.server_port,
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

            # 记录初始目标到历史中
            initial_goal_record = {
                "goal": "初始化",
                "timestamp": time.time(),
                "step_num": 0,
                "completed_time": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
            }
            self.goal_history.append(initial_goal_record)
            self.logger.info(f"已记录初始目标: {self.goal}")

            # 发送初始状态给 MaiCore (只有在准备好时才发送)
            if self._is_ready_for_next_action():
                await self._send_state_to_maicore()
            else:
                self.logger.info("初始化时智能体未准备好，将在自动发送循环中处理")

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
                    # 检查是否准备好发送新状态
                    if self._is_ready_for_next_action():
                        self.logger.info("未收到响应且已准备好，重新发送状态...")
                        await self._send_state_to_maicore()
                    else:
                        # 如果未准备好，执行no_op等待，但不发送状态给MaiCore
                        self.logger.info("未收到响应但智能体未准备好，执行no_op等待...")
                        try:
                            no_op_actions = mineland.Action.no_op(self.agents_count)
                            next_obs, next_code_info, next_event, next_done, next_task_info = execute_mineland_action(
                                mland=self.mland, current_actions=no_op_actions
                            )

                            # 更新状态
                            self.current_obs = next_obs
                            self.current_code_info = next_code_info
                            self.current_event = next_event
                            self.current_done = next_done
                            self.current_task_info = next_task_info
                            self.current_step_num += 1

                            # 更新事件历史记录
                            self._update_event_history(next_event)

                            self.logger.debug(f"自动发送循环中执行no_op完毕，当前步骤: {self.current_step_num}")

                        except Exception as e:
                            self.logger.error(f"自动发送循环中执行no_op时出错: {e}")

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
        agent_event = self.current_event[0]  # 当前仅支持单智能体
        agent_info = self.agents_config[0]
        status_prompts = build_state_analysis(agent_info, agent_obs, agent_event, self.current_code_info)

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
        template_items = build_prompt(
            agent_info=self.agents_config[0],
            status_prompts=status_prompts,
            obs=self.current_obs,
            events=self.current_event[0],
            code_infos=self.current_code_info,
            event_history=self.event_history,
        )

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
        if self.target_value >= self.current_value:
            message_text = (
                f"请根据上一次游戏目标，制定下一个具体目标：\n\n"
                f"- 目标：{self.goal}\n"
                f"- 计划：{';'.join(self.current_plan)}\n"
                f"- 当前步骤：{self.current_step}\n"
                f"- 目标值：{self.target_value}\n"
                f"- 当前完成度：{self.current_value}"
            )
        else:
            message_text = (
                f"请根据当前游戏状态，给出下一步动作，逐步实现目标：\n\n"
                f"- 目标：{self.goal}\n"
                f"- 计划：{';'.join(self.current_plan)}\n"
                f"- 当前步骤：{self.current_step}\n"
                f"- 目标值：{self.target_value}\n"
                f"- 当前完成度：{self.current_value}"
            )

        message_segment = Seg(type="text", data=message_text)

        msg_to_maicore = MessageBase(
            message_info=message_info, message_segment=message_segment, raw_message=message_text
        )

        await self.core.send_to_maicore(msg_to_maicore)
        self.logger.info(
            f"已将 Mineland 状态 (step {self.current_step_num}, done: {self.current_done}) 发送给 MaiCore。"
        )

    def _is_ready_for_next_action(self) -> bool:
        """
        检查所有智能体是否准备好执行下一个动作
        要么正在执行代码（is_running=true, is_ready=false），要么准备好接受新代码（is_running=false, is_ready=true），两种状态是互斥的。

        Returns:
            bool: 如果所有智能体都准备好执行下一个动作则返回True，否则返回False
        """
        if not self.current_code_info:
            # 如果没有代码信息，认为是准备好的状态
            self.logger.debug("没有代码信息，认为准备好执行下一个动作")
            return True

        for i, code_info in enumerate(self.current_code_info):
            if code_info is None:
                # 如果代码信息为空，认为是准备好的状态
                self.logger.debug(f"智能体 {i} 代码信息为空，认为准备好")
                continue

            # 检查是否正在运行代码或未准备好
            is_ready = code_info.is_ready

            self.logger.debug(f"智能体 {i} 状态检查: is_ready={is_ready}")
            if not is_ready:
                self.logger.info(f"智能体 {i} 未准备好执行下一个动作 (is_ready: {is_ready})")
                return False

        self.logger.debug("所有智能体都准备好执行下一个动作")
        return True

    async def _wait_for_action_completion(self):
        """
        等待当前动作完成，在动作未完成时执行no_op操作
        """
        wait_cycles = 0

        while not self._is_ready_for_next_action() and wait_cycles < self.max_wait_cycles:
            self.logger.info(f"等待动作完成中... (周期 {wait_cycles + 1}/{self.max_wait_cycles})")

            try:
                # 执行no_op动作获取下一个状态
                no_op_actions = mineland.Action.no_op(self.agents_count)
                next_obs, next_code_info, next_event, next_done, next_task_info = execute_mineland_action(
                    mland=self.mland, current_actions=no_op_actions
                )

                # 更新状态
                self.current_obs = next_obs
                self.current_code_info = next_code_info
                self.current_event = next_event
                self.current_done = next_done
                self.current_task_info = next_task_info
                self.current_step_num += 1

                # 更新事件历史记录
                self._update_event_history(next_event)

                self.logger.debug(f"No-op执行完毕，当前步骤: {self.current_step_num}")

            except Exception as e:
                self.logger.error(f"执行no_op等待时出错: {e}")
                break

            wait_cycles += 1

            # 短暂等待避免过于频繁的检查
            await asyncio.sleep(self.wait_cycle_interval)

        if wait_cycles >= self.max_wait_cycles:
            self.logger.warning(f"等待动作完成超时，已达到最大等待周期数 {self.max_wait_cycles}")
        else:
            self.logger.info(f"动作已完成，等待了 {wait_cycles} 个周期")

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

        # 首先检查是否准备好执行新动作
        # 如果上一个动作还在执行中，等待其完成
        if not self._is_ready_for_next_action():
            self.logger.info("上一个动作尚未完成，等待动作完成...")
            await self._wait_for_action_completion()

        message_json_str = message.message_segment.data.strip()
        self.logger.debug(f"从 MaiCore 收到原始动作指令: {message_json_str}")

        # 解析动作
        current_actions, action_data = parse_message_json(
            message_json_str=message_json_str,
            agents_count=self.agents_count,
            current_step_num=self.current_step_num,
        )

        # 更新所有相关字段
        self._update_action_data(action_data)

        self._update_goal(action_data.get("goal", self.goal))

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

            # 更新事件历史记录
            self._update_event_history(next_event)

            self.logger.info(f"代码信息: {str(self.current_code_info[0])}")
            self.logger.info(f"事件信息: {str(self.current_event[0])}")

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

    def _update_goal(self, new_goal: str):
        """更新目标并记录历史"""
        if new_goal != self.goal:
            # 记录旧目标到历史中
            goal_record = {
                "goal": self.goal,
                "timestamp": time.time(),
                "step_num": self.current_step_num,
                "completed_time": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
            }
            self.goal_history.append(goal_record)

            # 保持历史记录在合理范围内（最多保留50条）
            if len(self.goal_history) > 50:
                self.goal_history.pop(0)

            self.logger.info(f"目标已更新: '{self.goal}' -> '{new_goal}' (步骤 {self.current_step_num})")
            self.goal = new_goal

    def _get_goal_history_text(self, max_count: int = 10) -> str:
        """获取目标历史的文本描述"""
        if not self.goal_history:
            return "暂无目标历史记录"

        # 获取最新的max_count条记录
        recent_history = self.goal_history[-max_count:]

        history_lines = []
        for i, record in enumerate(recent_history, 1):
            history_lines.append(
                f"{i}. 目标: {record['goal']} (完成于步骤 {record['step_num']}, 时间: {record['completed_time']})"
            )

        return "\n".join(history_lines)

    def _update_action_data(self, action_data: Dict[str, Any]):
        """更新从AI响应中解析出的动作数据"""
        if not action_data:
            return

        # 更新计划
        if "plan" in action_data:
            self.current_plan = action_data["plan"]

        # 更新当前步骤
        if "step" in action_data:
            self.current_step = action_data["step"]

        # 更新目标值
        if "targetValue" in action_data:
            try:
                self.target_value = int(action_data["targetValue"])
            except (ValueError, TypeError):
                self.logger.warning(f"无法解析目标值: {action_data['targetValue']}")

        # 更新当前完成度
        if "currentValue" in action_data:
            try:
                self.current_value = int(action_data["currentValue"])
            except (ValueError, TypeError):
                self.logger.warning(f"无法解析当前完成度: {action_data['currentValue']}")

        self.logger.info(
            f"已更新动作数据 - 计划: {self.current_plan}, 步骤: {self.current_step}, 目标值: {self.target_value}, 当前值: {self.current_value}"
        )

    def _update_event_history(self, new_events: List[List[Event]]):
        """更新事件历史记录，去重并保留最近的记录"""
        if not new_events or not isinstance(new_events, list) or len(new_events) == 0:
            return

        # 处理第一个智能体的事件（当前仅支持单智能体）
        agent_events = new_events[0] if len(new_events) > 0 else []

        for event in agent_events:
            if not event:
                continue

            # 将事件转换为字典格式以便存储和去重
            event_dict = {
                "type": getattr(event, "type", "unknown"),
                "message": getattr(event, "message", ""),
                "timestamp": time.time(),
                "step_num": self.current_step_num,
            }

            # 检查是否已存在相同的事件（基于type和message去重）
            is_duplicate = False
            for existing_event in self.event_history:
                if (
                    existing_event.get("type") == event_dict["type"]
                    and existing_event.get("message") == event_dict["message"]
                ):
                    is_duplicate = True
                    break

            if not is_duplicate:
                self.event_history.append(event_dict)
                self.logger.debug(f"添加新事件到历史: {event_dict}")

        # 保持历史记录数量在限制范围内
        if len(self.event_history) > self.max_event_history:
            self.event_history = self.event_history[-self.max_event_history :]
            self.logger.debug(f"事件历史已裁剪到 {self.max_event_history} 条")


# --- Plugin Entry Point ---
# --- 插件入口点 ---
plugin_entrypoint = MinecraftPlugin
