# -*- coding: utf-8 -*-
import asyncio
import contextlib
from abc import ABC, abstractmethod
from typing import Any, Callable, Coroutine, Dict, Optional

from maim_message import MessageBase
from src.utils.logger import get_logger

from ..actions.action_executor import MinecraftActionExecutor
from ..agents.agent_manager import AgentManager
from ..state.game_state import MinecraftGameState

logger = get_logger("MinecraftPlugin")


class BaseModeHandler(ABC):
    """模式处理器的抽象基类"""

    def __init__(
        self,
        action_executor: MinecraftActionExecutor,
        game_state: MinecraftGameState,
        agent_manager: AgentManager,
        plugin_config: Dict[str, Any],
        send_state_callback: Callable[[Optional[Dict[str, Any]]], Coroutine[Any, Any, None]],
        extract_text_callback: Callable[[MessageBase], Optional[str]],
    ):
        self.action_executor = action_executor
        self.game_state = game_state
        self.agent_manager = agent_manager
        self.plugin_config = plugin_config
        self.send_state_callback = send_state_callback
        self.extract_text_callback = extract_text_callback
        self._tasks: Dict[str, Optional[asyncio.Task]] = {}
        self.logger = logger

    @abstractmethod
    async def start(self):
        """启动模式的主循环和任务"""
        raise NotImplementedError

    async def stop(self):
        """停止该模式下的所有任务"""
        for task_name, task in self._tasks.items():
            if task and not task.done():
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
                self.logger.info(f"模式任务 '{task_name}' 已停止。")
        self._tasks.clear()

    @abstractmethod
    async def handle_message(self, message: MessageBase):
        """处理来自外部的消息"""
        raise NotImplementedError

    def _create_task(self, coro, name: str):
        """为当前模式创建并注册一个后台任务"""
        if self._tasks.get(name):
            self.logger.warning(f"任务 {name} 已在运行，无法重复创建。")
            return
        task = asyncio.create_task(coro, name=f"{self.__class__.__name__}_{name}")
        self._tasks[name] = task
        self.logger.info(f"已启动模式任务: {task.get_name()}")
