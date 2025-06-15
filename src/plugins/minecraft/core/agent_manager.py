# -*- coding: utf-8 -*-
"""
智能体管理器 - 负责智能体的注册、创建和切换
"""

import logging
from typing import Dict, Any, Optional, Type, List

from ..agents.base_agent import BaseAgent


class AgentManager:
    """智能体管理器"""

    def __init__(self):
        self._agent_registry: Dict[str, Type[BaseAgent]] = {}
        self._current_agent: Optional[BaseAgent] = None
        self._agent_configs: Dict[str, Dict[str, Any]] = {}
        self.logger = logging.getLogger(__name__)

    async def initialize(self, config: Dict[str, Any]) -> None:
        """
        初始化智能体管理器

        Args:
            config: 配置信息
        """
        # 注册内置智能体类型
        await self._register_builtin_agents()

        # 加载配置
        self._agent_configs = config.get("agents", {})

        # 创建默认智能体
        default_agent_type = config.get("default_agent_type", "simple")
        if default_agent_type in self._agent_registry:
            await self.switch_agent(default_agent_type)

        self.logger.info(f"智能体管理器初始化完成，可用智能体: {list(self._agent_registry.keys())}")

    async def _register_builtin_agents(self):
        """注册内置智能体类型"""
        try:
            from ..agents.simple_agent import SimpleAgent

            await self.register_agent_type("simple", SimpleAgent)
        except ImportError as e:
            self.logger.error(f"无法导入简单智能体: {e}")
            raise

    async def register_agent_type(self, name: str, agent_class: Type[BaseAgent]) -> None:
        """
        注册智能体类型

        Args:
            name: 智能体类型名称
            agent_class: 智能体类
        """
        self._agent_registry[name] = agent_class
        self.logger.info(f"已注册智能体类型: {name}")

    async def create_agent(self, agent_type: str, config: Dict[str, Any]) -> BaseAgent:
        """
        创建智能体实例

        Args:
            agent_type: 智能体类型
            config: 智能体配置

        Returns:
            智能体实例
        """
        if agent_type not in self._agent_registry:
            raise ValueError(f"未知的智能体类型: {agent_type}")

        agent_class = self._agent_registry[agent_type]
        agent = agent_class()
        await agent.initialize(config)

        self.logger.info(f"已创建智能体: {agent_type}")
        return agent

    async def switch_agent(self, agent_type: str, config: Optional[Dict] = None) -> None:
        """
        切换智能体

        Args:
            agent_type: 新的智能体类型
            config: 智能体配置（可选）
        """
        if agent_type not in self._agent_registry:
            raise ValueError(f"未知的智能体类型: {agent_type}")

        # 清理当前智能体
        if self._current_agent:
            await self._current_agent.cleanup()

        # 创建新智能体
        agent_config = config or self._agent_configs.get(agent_type, {})
        self._current_agent = await self.create_agent(agent_type, agent_config)

        self.logger.info(f"已切换到智能体: {agent_type}")

    async def get_current_agent(self) -> Optional[BaseAgent]:
        """获取当前智能体"""
        return self._current_agent

    async def get_available_agents(self) -> List[str]:
        """获取可用的智能体类型列表"""
        return list(self._agent_registry.keys())

    async def get_agent_status(self) -> Dict[str, Any]:
        """获取当前智能体状态"""
        if self._current_agent:
            return {
                "current_agent": self._current_agent.get_agent_type(),
                "status": await self._current_agent.get_status(),
            }
        return {"current_agent": None, "status": None}

    async def cleanup(self) -> None:
        """清理资源"""
        if self._current_agent:
            await self._current_agent.cleanup()
            self._current_agent = None

        self.logger.info("智能体管理器清理完成")
