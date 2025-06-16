# -*- coding: utf-8 -*-
import asyncio
import time
from typing import Any

from maim_message import MessageBase

from .base_handler import BaseModeHandler


class MaiCoreModeHandler(BaseModeHandler):
    """处理与MaiCore交互的模式"""

    def __init__(self, **kwargs: Any):
        super().__init__(**kwargs)
        self.auto_send_interval = self.plugin_config.get("auto_send_interval", 30.0)
        self._last_response_time = 0.0

    async def start(self):
        """启动MaiCore模式的自动发送循环"""
        self._last_response_time = time.time()
        self._create_task(self._auto_send_loop(), "maicore_auto_send")

    async def handle_message(self, message: MessageBase):
        """处理从MaiCore返回的动作指令"""
        self.logger.info(f"收到来自 MaiCore 的响应: {message.message_segment.data}")
        self._last_response_time = time.time()

        command = self.extract_text_callback(message)
        if not command:
            return

        try:
            await self.action_executor.execute_maicore_action(command)
        except Exception as e:
            self.logger.error(f"处理 MaiCore 动作指令时出错: {e}")
        finally:
            # 无论成功失败，都发送最新状态
            await self.send_state_callback(None)

    async def _auto_send_loop(self):
        """定期检查是否需要向MaiCore发送状态"""
        while True:
            try:
                await asyncio.sleep(self.auto_send_interval)

                # 检查是否长时间未收到响应
                if time.time() - self._last_response_time > self.auto_send_interval:
                    self.logger.info("超时未收到响应，刷新状态并准备重新发送。")
                    await self.action_executor.execute_no_op()
                    if self.game_state.is_ready_for_next_action():
                        await self.send_state_callback(None)

            except asyncio.CancelledError:
                self.logger.info("MaiCore自动发送任务已取消")
                break
            except Exception as e:
                self.logger.error(f"MaiCore自动发送状态时出错: {e}")
                await asyncio.sleep(5)  # 发生错误时等待更长时间
