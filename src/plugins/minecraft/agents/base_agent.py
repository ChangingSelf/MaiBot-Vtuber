# -*- coding: utf-8 -*-
"""
智能体基类 - 定义智能体接口
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
from mineland import Action


class BaseAgent(ABC):
    """智能体抽象基类"""

    @abstractmethod
    async def initialize(self, config: Dict[str, Any]) -> None:
        """
        初始化智能体

        Args:
            config: 智能体配置
        """
        pass

    @abstractmethod
    async def run(
        self,
        obs: Dict[str, Any],
        code_info: Optional[Dict] = None,
        done: Optional[bool] = None,
        task_info: Optional[Dict] = None,
        maicore_command: Optional[str] = None,
    ) -> Optional[Action]:
        """
        执行一步决策

        Args:
            obs: 观察数据
            code_info: 代码执行信息
            done: 是否完成
            task_info: 任务信息
            maicore_command: MaiCore指令

        Returns:
            执行的动作
        """
        pass

    @abstractmethod
    async def reset(self) -> None:
        """重置智能体状态"""
        pass

    @abstractmethod
    async def receive_command(self, command: str, priority: str = "normal") -> None:
        """
        接收上层指令

        Args:
            command: 指令内容
            priority: 指令优先级 (high/normal/low)
        """
        pass

    @abstractmethod
    async def get_status(self) -> Dict[str, Any]:
        """
        获取智能体状态

        Returns:
            智能体状态信息
        """
        pass

    @abstractmethod
    def get_agent_type(self) -> str:
        """
        获取智能体类型

        Returns:
            智能体类型名称
        """
        pass

    async def cleanup(self) -> None:
        """清理资源 - 默认实现"""
        pass
