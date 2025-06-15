# -*- coding: utf-8 -*-
"""
配置管理器 - 负责读取和管理各种配置
"""

import logging
from typing import Dict, Any


class ConfigManager:
    """配置管理器"""

    def __init__(self, plugin_config: Dict[str, Any]):
        self.plugin_config = plugin_config
        self.logger = logging.getLogger(__name__)

    def get_control_mode(self) -> str:
        """
        获取控制模式

        Returns:
            控制模式 ("maicore" 或 "agent")
        """
        return self.plugin_config.get("control_mode", "maicore")

    def get_agent_config(self) -> Dict[str, Any]:
        """
        获取智能体配置

        Returns:
            智能体相关配置
        """
        agent_manager_config = self.plugin_config.get("agent_manager", {})
        return {
            "default_agent_type": agent_manager_config.get("default_agent_type", "simple"),
            "agents": self.plugin_config.get("agents", {}),
            "agent_manager": agent_manager_config,
        }

    def get_maicore_integration_config(self) -> Dict[str, Any]:
        """
        获取MaiCore集成配置

        Returns:
            MaiCore集成配置
        """
        return self.plugin_config.get(
            "maicore_integration",
            {"accept_commands": True, "status_report_interval": 60, "default_command_priority": "normal"},
        )

    def get_agent_specific_config(self, agent_type: str) -> Dict[str, Any]:
        """
        获取特定智能体的配置

        Args:
            agent_type: 智能体类型

        Returns:
            智能体特定配置
        """
        agents_config = self.plugin_config.get("agents", {})
        return agents_config.get(agent_type, {})

    def is_mode_switching_allowed(self) -> bool:
        """
        检查是否允许模式切换

        Returns:
            是否允许模式切换
        """
        return self.plugin_config.get("allow_mode_switching", True)

    def get_agent_switch_timeout(self) -> int:
        """
        获取智能体切换超时时间

        Returns:
            超时时间（秒）
        """
        agent_manager_config = self.plugin_config.get("agent_manager", {})
        return agent_manager_config.get("agent_switch_timeout", 30)
