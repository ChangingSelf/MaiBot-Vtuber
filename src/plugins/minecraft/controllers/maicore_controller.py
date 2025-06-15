# -*- coding: utf-8 -*-
"""
MaiCore控制器 - 实现原有的MaiCore通信模式
"""

import asyncio
import time
from typing import Optional, TYPE_CHECKING

from .base_controller import ControllerStrategy

if TYPE_CHECKING:
    from ..plugin import MinecraftPlugin
    from maim_message import MessageBase


class MaiCoreController(ControllerStrategy):
    """MaiCore控制器 - 保持原有的MaiCore通信模式"""

    def __init__(self):
        self.plugin: Optional["MinecraftPlugin"] = None
        self._auto_send_task: Optional[asyncio.Task] = None
        self._last_response_time: float = 0.0

    async def initialize(self, plugin_context: "MinecraftPlugin") -> None:
        """初始化控制器"""
        self.plugin = plugin_context
        self.plugin.logger.info("MaiCore控制器初始化完成")

    async def start_control_loop(self) -> None:
        """启动控制循环 - 自动发送循环"""
        if self._auto_send_task is None:
            self._auto_send_task = asyncio.create_task(self._auto_send_loop(), name="MaiCoreAutoSend")
            self.plugin.logger.info(f"已启动自动发送状态任务，间隔: {self.plugin.auto_send_interval}秒")

    async def _auto_send_loop(self):
        """定期发送状态的循环任务"""
        while True:
            try:
                await asyncio.sleep(self.plugin.auto_send_interval)

                current_time = time.time()
                if current_time - self._last_response_time > self.plugin.auto_send_interval:
                    # 超时时间内未收到响应，刷新状态并重新发送
                    await self.plugin.action_executor.execute_no_op()
                    self.plugin.logger.info("超时时间内未收到响应，刷新状态并重新发送")
                    if self.plugin.game_state.is_ready_for_next_action():
                        # 如果智能体准备好，则发送状态
                        await self._send_state_to_maicore()
            except asyncio.CancelledError:
                self.plugin.logger.info("自动发送状态任务被取消")
                break
            except Exception as e:
                self.plugin.logger.error(f"自动发送状态时出错: {e}")
                await asyncio.sleep(1)

    async def _send_state_to_maicore(self):
        """构建并发送当前Mineland状态给AmaidesuCore"""
        try:
            msg_to_maicore = self.plugin.message_builder.build_state_message(
                self.plugin.game_state, self.plugin.event_manager, self.plugin.agents_config
            )

            # 如果消息为空，则执行no_op
            if not msg_to_maicore:
                await self.plugin.action_executor.execute_no_op()
                return

            await self.plugin.core.send_to_maicore(msg_to_maicore)
            self.plugin.logger.info(
                f"已将 Mineland 事件状态 (step {self.plugin.game_state.current_step_num}, done: {self.plugin.game_state.current_done}) 发送给 MaiCore。"
            )
        except Exception as e:
            self.plugin.logger.error(f"构建或发送状态消息时出错: {e}")
            raise

    async def handle_external_message(self, message: "MessageBase") -> None:
        """处理从 MaiCore 返回的动作指令"""
        self.plugin.logger.info(f"收到来自 MaiCore 的响应: {message.message_segment.data}")

        # 更新最后响应时间
        self._last_response_time = time.time()

        if not self.plugin.mland:
            self.plugin.logger.error("收到 MaiCore 响应，但 MineLand 环境未初始化。忽略消息。")
            return

        if message.message_segment.type not in ["text", "seglist"]:
            self.plugin.logger.warning(
                f"MaiCore 返回的消息不是文本消息: type='{message.message_segment.type}'. 期望是'text'或'seglist'。丢弃消息。"
            )
            return

        if message.message_segment.type == "seglist":
            # 取出其中的text类型消息
            for seg in message.message_segment.data:
                if seg.type == "text":
                    message_json_str = seg.data.strip()
                    self.plugin.logger.debug(f"从 MaiCore 收到原始动作指令: {message_json_str}")
                    break
            else:
                self.plugin.logger.warning("从 MaiCore 收到seglist消息，但其中没有text类型消息。丢弃消息。")
                return
        elif message.message_segment.type == "text":
            message_json_str = message.message_segment.data.strip()
            self.plugin.logger.debug(f"从 MaiCore 收到原始动作指令: {message_json_str}")

        try:
            # 执行动作（包括等待完成、状态更新等）
            await self.plugin.action_executor.execute_maicore_action(message_json_str)

            # 发送新的状态给 MaiCore
            await self._send_state_to_maicore()

        except Exception as e:
            self.plugin.logger.error(f"处理 MaiCore 动作指令时出错: {e}")
            # 发送错误状态给 MaiCore
            await self._send_state_to_maicore()

    async def cleanup(self) -> None:
        """清理资源"""
        if self._auto_send_task:
            self._auto_send_task.cancel()
            try:
                await self._auto_send_task
            except asyncio.CancelledError:
                pass
            self._auto_send_task = None
        self.plugin.logger.info("MaiCore控制器清理完成")

    def get_mode_name(self) -> str:
        """获取模式名称"""
        return "maicore"
