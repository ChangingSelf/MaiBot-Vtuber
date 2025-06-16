# -*- coding: utf-8 -*-
import asyncio
import traceback
from typing import Any, Dict

from maim_message import MessageBase

from .base_handler import BaseModeHandler


class AgentModeHandler(BaseModeHandler):
    """处理智能体自主决策的模式"""

    def __init__(self, **kwargs: Any):
        super().__init__(**kwargs)

    async def start(self):
        """启动智能体决策循环和状态报告任务"""
        self._create_task(self._agent_decision_loop(), "agent_decision")

        maicore_config = self.plugin_config.get("maicore_integration", {})
        if maicore_config.get("accept_commands", True):
            interval = maicore_config.get("status_report_interval", 60)
            self._create_task(self._status_report_loop(interval), "status_report")

    async def handle_message(self, message: MessageBase):
        """处理外部指令，并传递给智能体"""
        maicore_config = self.plugin_config.get("maicore_integration", {})
        if not maicore_config.get("accept_commands", True):
            self.logger.debug("MaiCore集成已禁用，忽略外部消息")
            return

        self.logger.info(f"收到来自 MaiCore 的指令: {message.message_segment.data}")
        command = self.extract_text_callback(message)
        if not command:
            return

        try:
            agent = await self.agent_manager.get_current_agent()
            if agent:
                priority = maicore_config.get("default_command_priority", "normal")
                await agent.receive_command(command, priority)
                self.logger.info(f"已将指令 '{command}' (优先级: {priority}) 传递给智能体")
            else:
                self.logger.warning("没有可用的智能体接收指令")
        except Exception as e:
            self.logger.error(f"传递指令给智能体时出错: {e}")

    async def _agent_decision_loop(self):
        """智能体决策循环"""
        while True:
            try:
                agent = await self.agent_manager.get_current_agent()
                if not agent or not self.game_state.is_ready_for_next_action():
                    await asyncio.sleep(0.1)
                    continue

                obs = self._build_agent_observation()
                code_info = getattr(self.game_state.current_code_info, "__dict__", {})

                action = await agent.run(
                    obs,
                    code_info=code_info,
                    done=self.game_state.current_done,
                    task_info=self.game_state.current_task_info,
                )

                if action and action.code:
                    self.logger.info(f"智能体生成动作: {action.code}")
                    await self.action_executor.execute_action(action)
                else:
                    await self.action_executor.execute_no_op()

            except asyncio.CancelledError:
                self.logger.info("智能体决策循环被取消")
                break
            except Exception as e:
                self.logger.error(f"智能体决策循环错误: {e}\n{traceback.format_exc()}")
                await asyncio.sleep(1)

    async def _status_report_loop(self, interval: int):
        """定期向MaiCore报告状态"""
        while True:
            try:
                await asyncio.sleep(interval)
                agent = await self.agent_manager.get_current_agent()
                agent_status = await agent.get_status() if agent else {"status": "no_agent"}
                await self.send_state_callback(agent_status)
            except asyncio.CancelledError:
                self.logger.info("状态报告循环被取消")
                break
            except Exception as e:
                self.logger.error(f"状态报告循环错误: {e}")
                await asyncio.sleep(5)  # 发生错误时等待更长时间

    def _build_agent_observation(self) -> Dict[str, Any]:
        # sourcery skip: extract-method
        """构建智能体的观察数据"""
        if not self.game_state.current_obs:
            return {"error": "没有可用的观察数据"}

        try:
            obs_data = {"raw_observation": getattr(self.game_state.current_obs, "__dict__", {})}
            detailed_analysis = self.game_state.get_detailed_status_analysis()

            if not detailed_analysis:
                return obs_data

            obs_data["detailed_environment"] = detailed_analysis
            key_mappings = {
                "life_stats": "health_status",
                "environment": "surrounding_blocks",
                "position": "position_info",
                "inventory": "inventory_status",
                "equipment": "equipment_status",
                "collision": "movement_obstacles",
                "facing_wall": "facing_direction",
                "time": "game_time",
                "weather": "weather_info",
            }
            for src_key, dest_key in key_mappings.items():
                if src_key in detailed_analysis:
                    obs_data[dest_key] = detailed_analysis[src_key]

            return obs_data
        except Exception as e:
            self.logger.error(f"构建智能体观察数据时出错: {e}")
            return {"error": f"构建观察数据失败: {str(e)}"}
