# -*- coding: utf-8 -*-
"""
智能体控制器 - 实现智能体自主决策模式
"""

import asyncio
from typing import Optional, Dict, Any, TYPE_CHECKING

from .base_controller import ControllerStrategy

if TYPE_CHECKING:
    from ..plugin import MinecraftPlugin
    from ..core.agent_manager import AgentManager
    from maim_message import MessageBase


class AgentController(ControllerStrategy):
    """智能体控制器 - 负责智能体的自主决策"""

    def __init__(self):
        self.plugin: Optional["MinecraftPlugin"] = None
        self.agent_manager: Optional["AgentManager"] = None
        self._decision_loop_task: Optional[asyncio.Task] = None
        self._maicore_integration_enabled: bool = True
        self._status_report_task: Optional[asyncio.Task] = None

    async def initialize(self, plugin_context: "MinecraftPlugin") -> None:
        """初始化控制器"""
        self.plugin = plugin_context
        self.agent_manager = plugin_context.agent_manager

        # 读取MaiCore集成配置
        maicore_config = plugin_context.plugin_config.get("maicore_integration", {})
        self._maicore_integration_enabled = maicore_config.get("accept_commands", True)

        self.plugin.logger.info("智能体控制器初始化完成")

    async def start_control_loop(self) -> None:
        """启动控制循环 - 智能体决策循环"""
        if self._decision_loop_task is None:
            self._decision_loop_task = asyncio.create_task(self._agent_decision_loop(), name="AgentDecisionLoop")
            self.plugin.logger.info("已启动智能体决策循环")

        # 如果启用了MaiCore集成，启动状态报告任务
        if self._maicore_integration_enabled and self._status_report_task is None:
            maicore_config = self.plugin.plugin_config.get("maicore_integration", {})
            report_interval = maicore_config.get("status_report_interval", 60)
            self._status_report_task = asyncio.create_task(
                self._status_report_loop(report_interval), name="StatusReportLoop"
            )
            self.plugin.logger.info(f"已启动状态报告任务，间隔: {report_interval}秒")

    async def _agent_decision_loop(self):
        """智能体决策循环"""
        loop_count = 0
        while True:
            try:
                loop_count += 1

                # 每100次循环输出一次调试信息
                if loop_count % 100 == 1:
                    self.plugin.logger.info(f"智能体决策循环运行中，第 {loop_count} 次")

                # 获取当前智能体
                agent = await self.agent_manager.get_current_agent()
                if not agent:
                    if loop_count % 100 == 1:
                        self.plugin.logger.warning("没有当前智能体，等待中...")
                    await asyncio.sleep(1)
                    continue

                # 检查游戏状态是否准备好
                is_ready = self.plugin.game_state.is_ready_for_next_action()
                if not is_ready:
                    if loop_count % 100 == 1:
                        self.plugin.logger.debug(
                            f"游戏状态未准备好，等待中... (code_info: {self.plugin.game_state.current_code_info is not None})"
                        )
                    await asyncio.sleep(0.1)
                    continue

                # 构建观察数据
                obs = self._build_observation()
                if loop_count % 100 == 1:
                    self.plugin.logger.debug(f"构建观察数据: {len(str(obs))} 字符")

                # 智能体决策
                self.plugin.logger.debug(f"开始智能体决策...")
                action = await agent.run(
                    obs,
                    code_info=self.plugin.game_state.current_code_info,
                    done=self.plugin.game_state.current_done,
                    task_info=self.plugin.game_state.current_task_info,
                )

                if action:
                    # 执行动作
                    self.plugin.logger.info(f"智能体生成动作: {action.code}")
                    await self.plugin.action_executor.execute_action(action)
                    self.plugin.logger.debug(f"动作执行完成")
                else:
                    # 如果智能体没有返回动作，执行no_op
                    self.plugin.logger.warning("智能体没有返回动作，执行no_op")
                    await self.plugin.action_executor.execute_no_op()

                await asyncio.sleep(0.1)

            except asyncio.CancelledError:
                self.plugin.logger.info("智能体决策循环被取消")
                break
            except Exception as e:
                self.plugin.logger.error(f"智能体决策循环错误: {e}")
                import traceback

                self.plugin.logger.error(f"错误详情: {traceback.format_exc()}")
                await asyncio.sleep(1)

    def _build_observation(self) -> Dict[str, Any]:
        """构建智能体的观察数据"""
        try:
            # 从游戏状态中获取当前观察
            current_obs = self.plugin.game_state.current_obs
            if current_obs:
                return current_obs[0] if isinstance(current_obs, list) and current_obs else current_obs
            return {}
        except Exception as e:
            self.plugin.logger.error(f"构建观察数据时出错: {e}")
            return {}

    async def _status_report_loop(self, interval: int):
        """定期向MaiCore报告状态"""
        while True:
            try:
                await asyncio.sleep(interval)
                await self._report_to_maicore()
            except asyncio.CancelledError:
                self.plugin.logger.info("状态报告循环被取消")
                break
            except Exception as e:
                self.plugin.logger.error(f"状态报告循环错误: {e}")
                await asyncio.sleep(1)

    async def _report_to_maicore(self):
        """向MaiCore报告当前状态"""
        try:
            # 获取智能体状态
            agent = await self.agent_manager.get_current_agent()
            if agent:
                agent_status = await agent.get_status()
            else:
                agent_status = {"status": "no_agent"}

            # 构建状态消息
            msg_to_maicore = self.plugin.message_builder.build_state_message(
                self.plugin.game_state, self.plugin.event_manager, self.plugin.agents_config
            )

            if msg_to_maicore:
                await self.plugin.core.send_to_maicore(msg_to_maicore)
                self.plugin.logger.debug("已向MaiCore报告智能体状态")

        except Exception as e:
            self.plugin.logger.error(f"向MaiCore报告状态时出错: {e}")

    async def handle_external_message(self, message: "MessageBase") -> None:
        """处理外部消息 - 可选地传递给智能体"""
        if not self._maicore_integration_enabled:
            self.plugin.logger.debug("MaiCore集成已禁用，忽略外部消息")
            return

        self.plugin.logger.info(f"收到来自 MaiCore 的指令: {message.message_segment.data}")

        # 提取消息内容
        if message.message_segment.type == "text":
            command = message.message_segment.data.strip()
        elif message.message_segment.type == "seglist":
            # 取出其中的text类型消息
            for seg in message.message_segment.data:
                if seg.type == "text":
                    command = seg.data.strip()
                    break
            else:
                self.plugin.logger.warning("从 MaiCore 收到seglist消息，但其中没有text类型消息。忽略消息。")
                return
        else:
            self.plugin.logger.warning(f"不支持的消息类型: {message.message_segment.type}")
            return

        # 获取指令优先级配置
        maicore_config = self.plugin.plugin_config.get("maicore_integration", {})
        priority = maicore_config.get("default_command_priority", "normal")

        # 传递给当前智能体
        try:
            agent = await self.agent_manager.get_current_agent()
            if agent:
                await agent.receive_command(command, priority)
                self.plugin.logger.info(f"已将MaiCore指令传递给智能体: {command}")
            else:
                self.plugin.logger.warning("没有可用的智能体接收MaiCore指令")

        except Exception as e:
            self.plugin.logger.error(f"传递MaiCore指令给智能体时出错: {e}")

    async def cleanup(self) -> None:
        """清理资源"""
        # 取消决策循环
        if self._decision_loop_task:
            self._decision_loop_task.cancel()
            try:
                await self._decision_loop_task
            except asyncio.CancelledError:
                pass
            self._decision_loop_task = None

        # 取消状态报告任务
        if self._status_report_task:
            self._status_report_task.cancel()
            try:
                await self._status_report_task
            except asyncio.CancelledError:
                pass
            self._status_report_task = None

        self.plugin.logger.info("智能体控制器清理完成")

    def get_mode_name(self) -> str:
        """获取模式名称"""
        return "agent"
