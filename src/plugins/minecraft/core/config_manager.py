# -*- coding: utf-8 -*-
"""
配置管理器 - 简化版本，负责读取和管理各种配置
"""

import logging
from typing import Dict, Any


class ConfigManager:
    """配置管理器 - 简化版本"""

    def __init__(self, plugin_config: Dict[str, Any]):
        self.config = plugin_config
        self.logger = logging.getLogger(__name__)

    def get_control_mode(self) -> str:
        """获取控制模式 (maicore/agent)"""
        return self.config.get("control_mode", "maicore")

    def get_agent_config(self) -> Dict[str, Any]:
        """获取智能体相关配置"""
        return {
            "default_agent_type": self.config.get("agent_manager", {}).get("default_agent_type", "simple"),
            "agents": self.config.get("agents", {}),
        }

    def get_maicore_integration_config(self) -> Dict[str, Any]:
        """获取MaiCore集成配置"""
        return self.config.get(
            "maicore_integration",
            {"accept_commands": True, "status_report_interval": 60, "default_command_priority": "normal"},
        )

    def is_mode_switching_allowed(self) -> bool:
        """检查是否允许模式切换"""
        return self.config.get("allow_mode_switching", True)
