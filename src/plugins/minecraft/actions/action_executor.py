import asyncio
from typing import Tuple, Any, Dict, Optional
import mineland

from .action_handler import parse_message_json, execute_mineland_action
from ..state.game_state import MinecraftGameState
from ..events.event_manager import MinecraftEventManager


class MinecraftActionExecutor:
    """Minecraft动作执行器"""

    def __init__(
        self,
        game_state: MinecraftGameState,
        event_manager: MinecraftEventManager,
        mland: Optional[mineland.MineLand] = None,
        max_wait_cycles: int = 100,
        wait_cycle_interval: float = 0.1,
    ):
        self.game_state = game_state
        self.event_manager = event_manager
        self.mland = mland
        self.max_wait_cycles = max_wait_cycles
        self.wait_cycle_interval = wait_cycle_interval

    def set_mland(self, mland: mineland.MineLand):
        """设置 MineLand 实例"""
        self.mland = mland

    async def execute_maicore_action(self, message_json_str: str, logger) -> Tuple[bool, Dict[str, Any]]:
        """执行来自MaiCore的动作指令

        Returns:
            Tuple[bool, Dict[str, Any]]: 是否重置环境，动作数据
        """
        if not self.mland:
            raise RuntimeError("MineLand 实例未设置，无法执行动作")

        # 首先检查是否准备好执行新动作
        if not self.game_state.is_ready_for_next_action():
            logger.info("上一个动作尚未完成，等待动作完成...")
            await self._wait_for_action_completion(logger)

        # 解析动作
        current_actions, action_data = parse_message_json(
            message_json_str=message_json_str,
            agents_count=1,  # 固定为单智能体
            current_step_num=self.game_state.current_step_num,
        )

        # 更新动作数据
        self.game_state.update_action_data(action_data)
        self.game_state.update_goal(action_data.get("goal", self.game_state.goal))

        # 执行动作
        try:
            next_obs, next_code_info, next_event, next_done, next_task_info = execute_mineland_action(
                mland=self.mland, current_actions=current_actions
            )

            # 更新状态
            self.game_state.update_state(next_obs, next_code_info, next_event, next_done, next_task_info)

            # 更新事件历史
            self.event_manager.update_event_history(self.game_state.current_event, self.game_state.current_step_num)

            logger.info(f"代码信息: {str(self.game_state.current_code_info)}")
            logger.info(f"事件信息: {str(self.game_state.current_event)}")

            if self.game_state.get_effective_done():
                logger.info(f"任务在步骤 {self.game_state.current_step_num - 1} 完成。将重置环境。")
                self._reset_environment(logger)
                return True, action_data  # 返回True表示环境已重置

            return False, action_data  # 返回False表示正常执行

        except Exception as e:
            logger.exception(f"执行 Mineland step 时出错: {e}")
            raise

    async def execute_no_op(self, logger):
        """执行no_op操作并更新状态"""
        if not self.mland:
            raise RuntimeError("MineLand 实例未设置，无法执行 no_op")

        try:
            no_op_actions = mineland.Action.no_op(1)  # 固定为单智能体
            next_obs, next_code_info, next_event, next_done, next_task_info = execute_mineland_action(
                mland=self.mland, current_actions=no_op_actions
            )

            # 更新状态
            self.game_state.update_state(next_obs, next_code_info, next_event, next_done, next_task_info)

            # 更新事件历史
            self.event_manager.update_event_history(self.game_state.current_event, self.game_state.current_step_num)

            logger.debug(f"no_op执行完毕，当前步骤: {self.game_state.current_step_num}")

        except Exception as e:
            logger.error(f"执行no_op时出错: {e}")

    async def _wait_for_action_completion(self, logger):
        """等待当前动作完成，在动作未完成时执行no_op操作"""
        wait_cycles = 0

        while not self.game_state.is_ready_for_next_action() and wait_cycles < self.max_wait_cycles:
            logger.info(f"等待动作完成中... (周期 {wait_cycles + 1}/{self.max_wait_cycles})")

            await self.execute_no_op(logger)
            wait_cycles += 1
            await asyncio.sleep(self.wait_cycle_interval)

        if wait_cycles >= self.max_wait_cycles:
            logger.warning(f"等待动作完成超时，已达到最大等待周期数 {self.max_wait_cycles}")
        else:
            logger.info(f"动作已完成，等待了 {wait_cycles} 个周期")

    def _reset_environment(self, logger):
        """重置环境"""
        if not self.mland:
            raise RuntimeError("MineLand 实例未设置，无法重置环境")

        initial_obs = self.mland.reset()
        self.game_state.reset_state(initial_obs)
        logger.info("环境已重置，收到新的初始观察。")
