# -*- coding: utf-8 -*-
import asyncio
import time
from typing import Optional

from maim_message import MessageBase

from src.plugins.minecraft.context import MinecraftContext

from .base_handler import BaseModeHandler


class MaiCoreModeHandler(BaseModeHandler):
    """
    MaiCore控制模式的处理器。
    此模式下，插件将游戏状态发送给MaiCore，并接收和执行来自MaiCore的动作指令。
    """

    def __init__(self, context: MinecraftContext):
        super().__init__(context)
        self.background_task: Optional[asyncio.Task] = None
        maicore_config = self.context.plugin_config.get("maicore_mode", {})
        self.send_interval = maicore_config.get("send_state_interval", 1.0)
        self.auto_send_interval = maicore_config.get("auto_send_interval", 30.0)
        self._last_response_time = 0.0

    async def start(self):
        """启动定期向MaiCore发送状态的后台任务。"""
        await super().start()
        self._last_response_time = time.time()
        if self.background_task is None or self.background_task.done():
            self.background_task = asyncio.create_task(self._send_state_periodically())
            self.logger.info("MaiCore模式后台任务已启动。")

    async def stop(self):
        """停止后台任务。"""
        if self.background_task and not self.background_task.done():
            self.background_task.cancel()
            self.background_task = None
            self.logger.info("MaiCore模式后台任务已停止。")
        await super().stop()

    async def handle_message(self, message: MessageBase):
        """处理来自MaiCore的动作指令。"""
        self.logger.info("MaiCore模式处理器正在处理消息...")
        if not self.is_running:
            self.logger.warning("处理器未运行，已忽略消息。")
            return

        self._last_response_time = time.time()
        text_content = self.context.extract_text_from_message(message)
        if not text_content:
            self.logger.warning("从消息中未提取到文本内容，已忽略。")
            return

        try:
            await self.context.action_executor.execute_maicore_action(text_content)
            self.logger.info("成功执行了来自MaiCore的动作指令。")
            # 动作执行后，立即发送一次状态，以提供即时反馈
            await self.context.send_state_to_maicore()
        except Exception as e:
            self.logger.error(f"处理来自MaiCore的消息时出错: {e}", exc_info=True)

    async def _send_state_periodically(self):
        """定期发送游戏状态到MaiCore，并在超时后尝试刷新状态。"""
        while self.is_running:
            try:
                # 检查是否到了发送常规状态更新的时间
                if self.context.game_state.is_ready_for_next_action():
                    await self.context.send_state_to_maicore()

                # 等待下一次发送
                await asyncio.sleep(self.send_interval)

                # 检查是否长时间未收到响应
                if time.time() - self._last_response_time > self.auto_send_interval:
                    self.logger.info("长时间未收到MaiCore响应，尝试执行no-op并重新发送状态。")
                    await self.context.action_executor.execute_no_op()
                    if self.context.game_state.is_ready_for_next_action():
                        await self.context.send_state_to_maicore()
                    # 重置计时器，避免连续发送
                    self._last_response_time = time.time()

            except asyncio.CancelledError:
                self.logger.info("状态发送任务被取消。")
                break
            except Exception as e:
                self.logger.error(f"发送状态到MaiCore时发生异常: {e}", exc_info=True)
                await asyncio.sleep(self.send_interval * 2)
