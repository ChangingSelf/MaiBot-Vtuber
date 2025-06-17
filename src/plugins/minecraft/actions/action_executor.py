import asyncio
import re
from typing import Tuple, Any, Dict, Optional, List
import mineland
import json

from ..state.game_state import MinecraftGameState
from ..events.event_manager import MinecraftEventManager
from src.utils.logger import get_logger

logger = get_logger("MinecraftPlugin")


class MinecraftActionExecutor:
    """Minecraft动作执行器"""

    def __init__(
        self,
        game_state: MinecraftGameState,
        event_manager: MinecraftEventManager,
        config: Dict[str, Any],
        max_wait_cycles: int = 100,
        wait_cycle_interval: float = 0.1,
    ):
        self.game_state = game_state
        self.event_manager = event_manager
        self.mland: Optional[mineland.MineLand] = None
        self.max_wait_cycles = max_wait_cycles
        self.wait_cycle_interval = wait_cycle_interval
        self.config = config

        action_executor_config = self.config.get("action_executor", {})
        self.agents_count = self.config.get("agents_count", 1)
        self.low_level_action_length = action_executor_config.get("low_level_action_length", 8)

    def set_mland(self, mland: mineland.MineLand):
        """设置 MineLand 实例"""
        self.mland = mland

    async def execute_maicore_action(self, message_json_str: str) -> Tuple[bool, Dict[str, Any]]:
        """执行来自MaiCore的动作指令

        Returns:
            Tuple[bool, Dict[str, Any]]: 是否重置环境，动作数据
        """
        if not self.mland:
            raise RuntimeError("MineLand 实例未设置，无法执行动作")

        # 首先检查是否准备好执行新动作
        if not self.game_state.is_ready_for_next_action():
            logger.info("上一个动作尚未完成，等待动作完成...")
            await self._wait_for_action_completion()

        # 解析动作
        current_actions, action_data = self.parse_message_json(
            message_json_str=message_json_str,
            agents_count=self.agents_count,
            current_step_num=self.game_state.current_step_num,
        )

        # 更新动作数据
        self.game_state.update_action_data(action_data)
        self.game_state.update_goal(action_data.get("goal", self.game_state.goal))

        # 执行动作
        try:
            next_obs, next_code_info, next_event, next_done, next_task_info = self.mland.step(action=current_actions)

            # 更新状态
            self.game_state.update_state(next_obs, next_code_info, next_event, next_done, next_task_info)

            # 更新事件历史
            if self.game_state.current_event:
                self.event_manager.update_event_history(self.game_state.current_event, self.game_state.current_step_num)

            logger.info(f"代码信息: {str(self.game_state.current_code_info)}")
            logger.info(f"事件信息: {str(self.game_state.current_event)}")

            if self.game_state.get_effective_done():
                logger.info(f"任务在步骤 {self.game_state.current_step_num - 1} 完成。将重置环境。")
                self._reset_environment()
                return True, action_data  # 返回True表示环境已重置

            return False, action_data  # 返回False表示正常执行

        except Exception as e:
            logger.exception(f"执行 Mineland step 时出错: {e}")
            raise

    async def execute_no_op(self):
        """执行no_op操作并更新状态"""
        if not self.mland:
            raise RuntimeError("MineLand 实例未设置，无法执行 no_op")

        try:
            no_op_actions = mineland.Action.no_op(self.agents_count)
            next_obs, next_code_info, next_event, next_done, next_task_info = self.mland.step(action=no_op_actions)

            # 更新状态
            self.game_state.update_state(next_obs, next_code_info, next_event, next_done, next_task_info)

            # 更新事件历史
            if self.game_state.current_event:
                self.event_manager.update_event_history(self.game_state.current_event, self.game_state.current_step_num)

            logger.debug(f"no_op执行完毕，当前步骤: {self.game_state.current_step_num}")

        except Exception as e:
            logger.error(f"执行no_op时出错: {e}")

    async def execute_action(self, action: mineland.Action):
        """执行智能体生成的动作

        Args:
            action: 智能体生成的mineland.Action对象
        """
        if not self.mland:
            raise RuntimeError("MineLand 实例未设置，无法执行动作")

        # 首先检查是否准备好执行新动作
        if not self.game_state.is_ready_for_next_action():
            logger.info("上一个动作尚未完成，等待动作完成...")
            await self._wait_for_action_completion()

        try:
            # 对于单智能体，将动作包装成列表
            if self.agents_count == 1:
                actions = [action]
            else:
                # 多智能体情况下需要特殊处理
                actions = [action] * self.agents_count

            # 执行动作
            next_obs, next_code_info, next_event, next_done, next_task_info = self.mland.step(action=actions)

            # 更新状态
            self.game_state.update_state(next_obs, next_code_info, next_event, next_done, next_task_info)

            # 更新事件历史
            if self.game_state.current_event:
                self.event_manager.update_event_history(self.game_state.current_event, self.game_state.current_step_num)

            logger.debug(f"智能体动作执行完毕，当前步骤: {self.game_state.current_step_num}")
            logger.debug(f"代码信息: {str(self.game_state.current_code_info)}")
            logger.debug(f"事件信息: {str(self.game_state.current_event)}")

            # 检查是否完成任务
            if self.game_state.get_effective_done():
                logger.info(f"任务在步骤 {self.game_state.current_step_num - 1} 完成。将重置环境。")
                self._reset_environment()

        except Exception as e:
            logger.error(f"执行智能体动作时出错: {e}")
            raise

    async def _wait_for_action_completion(self):
        """等待当前动作完成，在动作未完成时执行no_op操作"""
        wait_cycles = 0

        while not self.game_state.is_ready_for_next_action() and wait_cycles < self.max_wait_cycles:
            logger.info(f"等待动作完成中... (周期 {wait_cycles + 1}/{self.max_wait_cycles})")

            await self.execute_no_op()
            wait_cycles += 1
            await asyncio.sleep(self.wait_cycle_interval)

        if wait_cycles >= self.max_wait_cycles:
            logger.warning(f"等待动作完成超时，已达到最大等待周期数 {self.max_wait_cycles}")
        else:
            logger.info(f"动作已完成，等待了 {wait_cycles} 个周期")

    def _reset_environment(self):
        """重置环境"""
        if not self.mland:
            raise RuntimeError("MineLand 实例未设置，无法重置环境")

        initial_obs = self.mland.reset()
        self.game_state.reset_state(initial_obs)
        logger.info("环境已重置，收到新的初始观察。")

    def strip_markdown_codeblock(self, text: str) -> str:
        """
        去除markdown代码块包装

        Args:
            text: 可能包含markdown代码块的文本

        Returns:
            str: 去除代码块包装后的内容
        """
        text = text.strip()

        if match := re.match(r"^```(?:json)?\s*\n?(.*?)\n?```$", text, re.DOTALL):
            # 如果匹配到代码块格式，返回内部内容
            return match[1].strip()

        # 如果不是代码块格式，返回原文本
        return text

    def parse_message_json(
        self, message_json_str: str, agents_count: int, current_step_num: int
    ) -> Tuple[List[mineland.Action], Dict[str, Any]]:
        """
        解析从MaiCore收到的动作JSON字符串，并返回MineLand格式的动作

        Args:
            message_json_str: JSON格式的动作字符串（可能包含markdown代码块包装）
            agents_count: 智能体数量
            current_step_num: 当前步数

        Returns:
            Tuple[List[Action], Dict[str, Any]]: MineLand格式的动作列表和解析出的信息字典
        """
        # 预处理：去除可能的markdown代码块包装
        cleaned_json_str = self.strip_markdown_codeblock(message_json_str)

        try:
            action_data = json.loads(cleaned_json_str)
        except json.JSONDecodeError as e:
            logger.error(f"解析来自 MaiCore 的动作 JSON 失败: {e}. 原始数据: {message_json_str}")
            return mineland.Action.no_op(agents_count), {}

        # --- 解析动作并准备 current_actions ---
        # 目前仅支持单智能体 (agents_count=1)
        current_actions = []

        if agents_count == 1:
            # 获取 actions 字段并根据类型判断是高级还是低级动作
            actions = action_data.get("actions")

            if actions is None:
                # 无 actions 字段，执行无操作
                logger.info(f"步骤 {current_step_num}: 未提供 actions 字段，将执行无操作。")
                current_actions = mineland.Action.no_op(agents_count)
            elif isinstance(actions, str) and actions.strip():
                # actions 是字符串，执行高级动作
                parsed_agent_action_obj = mineland.Action(type=mineland.Action.NEW, code=actions)
                current_actions = [parsed_agent_action_obj]
            elif isinstance(actions, list) and len(actions) == self.low_level_action_length:
                # actions 是数组，执行低级动作
                lla = mineland.LowLevelAction()
                for i in range(len(actions)):
                    try:
                        component_value = int(actions[i])
                        lla[i] = component_value
                    except (ValueError, AssertionError) as err_lla:
                        logger.warning(
                            f"步骤 {current_step_num}: 低级动作组件 {i} 值 '{actions[i]}' 无效 ({err_lla})。使用默认值 0。"
                        )
                        # lla[i] 将保留默认值 (0)
                current_actions = [lla]
            else:
                # actions 格式不正确，执行无操作
                logger.warning(
                    f"步骤 {current_step_num}: actions 字段格式不正确 (应为字符串或{self.low_level_action_length}元素数组)，将执行无操作。"
                )
                current_actions = mineland.Action.no_op(agents_count)
        else:  # 多智能体 (agents_count > 1)
            logger.warning(f"步骤 {current_step_num}: 多智能体 (AGENTS_COUNT > 1) 暂不支持，将执行无操作。")
            current_actions = mineland.Action.no_op(agents_count)

        return current_actions, action_data
