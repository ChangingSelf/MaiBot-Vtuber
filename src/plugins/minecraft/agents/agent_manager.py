# -*- coding: utf-8 -*-
"""
智能体管理器 - 简化版本，负责智能体的注册、创建和切换
"""

from src.utils.logger import get_logger
from typing import Dict, Any, Optional, Type, List

from .base_agent import BaseAgent


class AgentManager:
    """智能体管理器 - 简化版本"""

    def __init__(self):
        self._agents: Dict[str, Type[BaseAgent]] = {}
        self._current_agent: Optional[BaseAgent] = None
        self._agent_configs: Dict[str, Dict[str, Any]] = {}
        self.logger = get_logger("MinecraftPlugin")

    async def initialize(self, config: Dict[str, Any]) -> None:
        """初始化智能体管理器"""
        # 注册内置智能体
        await self._register_builtin_agents()

        # 保存配置
        self._agent_configs = config.get("agents", {})

        # 创建默认智能体
        default_type = config.get("default_agent_type", "simple")
        if default_type in self._agents:
            await self.switch_to(default_type)

        self.logger.info(f"智能体管理器初始化完成，可用智能体: {list(self._agents.keys())}")

    async def _register_builtin_agents(self):
        """注册内置智能体类型"""
        try:
            from .simple_agent import SimpleAgent

            self._agents["simple"] = SimpleAgent
            self.logger.info("已注册简单智能体")
        except ImportError as e:
            self.logger.error(f"无法导入简单智能体: {e}")
            raise

    async def switch_to(self, agent_type: str) -> None:
        """切换到指定智能体"""
        if agent_type not in self._agents:
            raise ValueError(f"未知的智能体类型: {agent_type}")

        # 清理当前智能体
        if self._current_agent:
            await self._current_agent.cleanup()

        # 创建新智能体
        agent_config = self._agent_configs.get(agent_type, {})
        agent_class = self._agents[agent_type]
        self._current_agent = agent_class()
        await self._current_agent.initialize(agent_config)

        self.logger.info(f"已切换到智能体: {agent_type}")

    async def get_current_agent(self) -> Optional[BaseAgent]:
        """获取当前智能体"""
        return self._current_agent

    async def get_available_types(self) -> List[str]:
        """获取可用的智能体类型列表"""
        return list(self._agents.keys())

    async def get_agent_status(self) -> Dict[str, Any]:
        """获取当前智能体状态"""
        if self._current_agent:
            return {
                "current_type": self._current_agent.get_agent_type(),
                "status": await self._current_agent.get_status(),
            }
        return {"current_type": None, "status": None}

    async def cleanup(self) -> None:
        """清理资源"""
        if self._current_agent:
            await self._current_agent.cleanup()
            self._current_agent = None
        self.logger.info("智能体管理器清理完成")
