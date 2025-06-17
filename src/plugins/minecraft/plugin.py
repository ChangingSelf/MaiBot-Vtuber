# -*- coding: utf-8 -*-
import asyncio
from typing import Any, Dict, Optional

from maim_message import MessageBase

from src.core.amaidesu_core import AmaidesuCore
from src.core.plugin_manager import BasePlugin

from .context import MinecraftContext
from .modes.agent_handler import AgentModeHandler
from .modes.base_handler import BaseModeHandler
from .modes.maicore_handler import MaiCoreModeHandler


class MinecraftPlugin(BasePlugin):
    """
    Minecraft插件 - 支持MaiCore和智能体两种控制模式。
    """

    def __init__(self, core: AmaidesuCore, plugin_config: Dict[str, Any]):
        super().__init__(core, plugin_config)
        self.context = MinecraftContext(core, plugin_config)
        self._setup_mode_handler()

        self.handler: BaseModeHandler

    def _setup_mode_handler(self):
        """初始化并设置当前控制模式的处理器"""
        self.mode_handlers: Dict[str, BaseModeHandler] = {
            "maicore": MaiCoreModeHandler(self.context),
            "agent": AgentModeHandler(self.context),
        }
        initial_mode = self.plugin_config.get("control_mode", "maicore")
        if initial_mode not in self.mode_handlers:
            self.logger.warning(f"不支持的控制模式: {initial_mode}，使用默认maicore模式")
            initial_mode = "maicore"

        self.mode: str = initial_mode
        self.handler: BaseModeHandler = self.mode_handlers[self.mode]

    async def _websocket_message_handler(self, message: MessageBase):
        """处理传入的WebSocket消息并委派给当前模式的处理器。"""
        asyncio.create_task(self.handler.handle_message(message))

    async def setup(self):
        """初始化插件、环境和当前模式"""
        await super().setup()
        await self.context.initialize_mineland()
        agent_config = {
            "default_agent_type": self.plugin_config.get("agent_manager", {}).get("default_agent_type", "simple"),
            "agents": self.plugin_config.get("agents", {}),
        }
        await self.context.agent_manager.initialize(agent_config)

        self.core.register_websocket_handler(
            "*",
            self._websocket_message_handler,  # type: ignore
        )
        await self.handler.start()
        self.logger.info(f"Minecraft插件初始化完成，模式: {self.mode}")

    async def cleanup(self):
        """清理插件资源"""
        self.logger.info("正在清理 Minecraft 插件...")
        await self.context.agent_manager.cleanup()

        if self.context.mland:
            try:
                self.logger.info("正在关闭 MineLand 环境...")
                loop = asyncio.get_running_loop()
                await loop.run_in_executor(None, self.context.mland.close)
                self.logger.info("MineLand 环境已关闭。")
            except Exception as e:
                self.logger.error(f"关闭 MineLand 环境时出错: {e}", exc_info=True)

        self.logger.info("Minecraft 插件清理完毕。")


# --- 插件入口点 ---
plugin_entrypoint = MinecraftPlugin
