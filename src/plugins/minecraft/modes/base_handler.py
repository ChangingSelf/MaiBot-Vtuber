# -*- coding: utf-8 -*-
import asyncio
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from maim_message import MessageBase

from src.plugins.minecraft.context import MinecraftContext
from src.utils.logger import get_logger

logger = get_logger("MinecraftPlugin")


class BaseModeHandler(ABC):
    """
    Minecraft插件不同控制模式处理器的基类。
    定义了所有模式处理器必须实现的通用接口。
    """

    def __init__(self, context: MinecraftContext):
        """
        初始化模式处理器。

        :param context: Minecraft插件的上下文对象，包含所有共享组件。
        """
        self.context = context
        self.logger = context.logger
        self.is_running = False

    async def start(self):
        """
        启动模式处理器的后台任务（如果需要）。
        """
        self.is_running = True
        self.logger.info(f"模式处理器 '{self.__class__.__name__}' 已启动。")

    async def stop(self):
        """
        停止模式处理器的后台任务。
        """
        self.is_running = False
        self.logger.info(f"模式处理器 '{self.__class__.__name__}' 已停止。")

    @abstractmethod
    async def handle_message(self, message: MessageBase):
        """
        处理传入的WebSocket消息。
        每个具体的模式处理器都需要实现此方法，以定义其独特的行为。

        :param message: 从WebSocket接收到的消息对象。
        """
        pass
