# -*- coding: utf-8 -*-
import asyncio
from typing import Any, Dict, Optional

from maim_message import MessageBase

from src.plugins.minecraft.context import MinecraftContext

from .base_handler import BaseModeHandler


class AgentModeHandler(BaseModeHandler):
    """
    智能体（Agent）控制模式的处理器。
    此模式下，智能体基于游戏状态自主决策，并执行动作。
    """

    def __init__(self, context: MinecraftContext):
        super().__init__(context)
        self.decision_task: Optional[asyncio.Task] = None
        self.report_task: Optional[asyncio.Task] = None

        agent_config = self.context.plugin_config.get("agent_mode", {})
        self.think_interval = agent_config.get("think_interval", 1.0)

        maicore_config = self.context.plugin_config.get("maicore_integration", {})
        self.accept_commands = maicore_config.get("accept_commands", True)
        self.status_report_interval = maicore_config.get("status_report_interval", 60)

    async def start(self):
        """启动智能体决策循环和状态报告任务"""
        await super().start()
        if self.decision_task is None or self.decision_task.done():
            self.decision_task = asyncio.create_task(self._agent_decision_loop())
            self.logger.info("智能体决策循环已启动。")
        if self.report_task is None or self.report_task.done():
            self.report_task = asyncio.create_task(self._status_report_loop())
            self.logger.info("智能体状态报告循环已启动。")

    async def stop(self):
        """停止智能体的后台任务。"""
        if self.decision_task and not self.decision_task.done():
            self.decision_task.cancel()
            self.decision_task = None
        if self.report_task and not self.report_task.done():
            self.report_task.cancel()
            self.report_task = None
        await super().stop()

    async def handle_message(self, message: MessageBase):
        """处理外部指令，并传递给智能体"""
        if not self.accept_commands:
            self.logger.debug("已配置为不接受外部指令，已忽略。")
            return

        command = self.context.extract_text_from_message(message)
        if not command:
            return

        try:
            agent = await self.context.agent_manager.get_current_agent()
            if agent:
                await agent.receive_command(command)
                self.logger.info(f"已将指令 '{command}' 传递给智能体")
            else:
                self.logger.warning("没有可用的智能体来接收指令。")
        except Exception as e:
            self.logger.error(f"向智能体传递指令时出错: {e}", exc_info=True)

    def _build_agent_observation(self) -> Dict[str, Any]:
        """构建智能体的观察数据"""
        # simplified version
        return {
            "game_state": self.context.game_state,
            "event_history": self.context.event_manager.event_history,
        }

    async def _agent_decision_loop(self):
        """智能体决策循环"""
        while self.is_running:
            try:
                agent = await self.context.agent_manager.get_current_agent()
                if not agent or not self.context.game_state.is_ready_for_next_action():
                    await asyncio.sleep(self.think_interval)
                    continue

                obs = self._build_agent_observation()
                action = await agent.run(obs)

                if action:
                    self.logger.info(f"智能体生成动作: {action.code if action.code else '低级动作'}")
                    await self.context.action_executor.execute_action(action)
                else:
                    await self.context.action_executor.execute_no_op()

                await asyncio.sleep(self.think_interval)

            except asyncio.CancelledError:
                self.logger.info("智能体决策循环被取消。")
                break
            except Exception as e:
                self.logger.error(f"智能体决策循环中发生致命错误: {e}", exc_info=True)
                await asyncio.sleep(self.think_interval * 2)  # 发生错误时等待更久

    async def _status_report_loop(self):
        """定期向MaiCore发送智能体状态"""
        while self.is_running:
            try:
                await asyncio.sleep(self.status_report_interval)
                self.logger.info("正在发送智能体状态报告...")
                # 当前send_state_to_maicore不直接支持发送agent状态，
                # 但调用它可以发送完整的游戏状态，其中可能间接包含agent信息。
                await self.context.send_state_to_maicore()
            except asyncio.CancelledError:
                self.logger.info("状态报告循环被取消。")
                break
            except Exception as e:
                self.logger.error(f"状态报告循环中出错: {e}", exc_info=True)
