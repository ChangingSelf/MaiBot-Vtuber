# -*- coding: utf-8 -*-
"""
控制策略基类 - 定义控制器接口
"""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..plugin import MinecraftPlugin
    from maim_message import MessageBase


class ControllerStrategy(ABC):
    """控制策略抽象基类"""

    @abstractmethod
    async def initialize(self, plugin_context: "MinecraftPlugin") -> None:
        """
        初始化控制器

        Args:
            plugin_context: 插件上下文
        """
        pass

    @abstractmethod
    async def start_control_loop(self) -> None:
        """启动控制循环"""
        pass

    @abstractmethod
    async def handle_external_message(self, message: "MessageBase") -> None:
        """
        处理外部消息

        Args:
            message: 外部消息
        """
        pass

    @abstractmethod
    async def cleanup(self) -> None:
        """清理资源"""
        pass

    @abstractmethod
    def get_mode_name(self) -> str:
        """获取模式名称"""
        pass
