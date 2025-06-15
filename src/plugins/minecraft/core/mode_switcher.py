# -*- coding: utf-8 -*-
"""
模式切换器 - 负责在不同控制模式间切换
"""

import logging
from typing import Dict, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from ..plugin import MinecraftPlugin
    from ..controllers.base_controller import ControllerStrategy


class ModeSwitcher:
    """模式切换器"""

    def __init__(self, plugin: "MinecraftPlugin"):
        self.plugin = plugin
        self.logger = logging.getLogger(__name__)

    def _create_controller(self, mode: str):
        """延迟创建控制器以避免循环依赖"""
        if mode == "maicore":
            from ..controllers.maicore_controller import MaiCoreController

            return MaiCoreController()
        elif mode == "agent":
            from ..controllers.agent_controller import AgentController

            return AgentController()
        else:
            raise ValueError(f"不支持的模式: {mode}")

    async def switch_mode(self, new_mode: str, **kwargs) -> bool:
        """
        切换控制模式

        Args:
            new_mode: 新的模式名称 ("maicore" 或 "agent")
            **kwargs: 其他参数

        Returns:
            切换是否成功
        """
        try:
            current_mode = self.plugin.mode_controller.get_mode_name()
            if current_mode == new_mode:
                self.logger.info(f"已经处于{new_mode}模式")
                return True

            self.logger.info(f"开始从{current_mode}模式切换到{new_mode}模式")

            # 保存当前状态
            current_state = await self._save_current_state()

            # 清理当前控制器
            await self.plugin.mode_controller.cleanup()

            # 创建新控制器
            new_controller = self._create_controller(new_mode)

            # 初始化新控制器
            await new_controller.initialize(self.plugin)

            # 恢复状态
            await self._restore_state(current_state)

            # 更新插件引用
            self.plugin.mode_controller = new_controller

            # 启动新控制器的控制循环
            await new_controller.start_control_loop()

            self.logger.info(f"成功从{current_mode}模式切换到{new_mode}模式")
            return True

        except Exception as e:
            self.logger.error(f"模式切换失败: {e}")
            return False

    async def _save_current_state(self) -> Dict[str, Any]:
        """保存当前状态"""
        try:
            state = {
                "game_state": {
                    "current_step_num": self.plugin.game_state.current_step_num,
                    "current_done": self.plugin.game_state.current_done,
                    "goal": self.plugin.game_state.goal,
                },
                "agent_status": None,
            }

            # 如果当前是智能体模式，保存智能体状态
            if hasattr(self.plugin, "agent_manager") and self.plugin.agent_manager:
                agent_status = await self.plugin.agent_manager.get_agent_status()
                state["agent_status"] = agent_status

            self.logger.debug("已保存当前状态")
            return state

        except Exception as e:
            self.logger.error(f"保存状态时出错: {e}")
            return {}

    async def _restore_state(self, state: Dict[str, Any]) -> None:
        """恢复状态"""
        try:
            if not state:
                return

            # 恢复游戏状态
            game_state = state.get("game_state", {})
            if game_state:
                # 这里可以根据需要恢复游戏状态
                # 目前保持简单，只记录日志
                self.logger.debug(f"恢复游戏状态: step={game_state.get('current_step_num')}")

            # 如果是切换到智能体模式且有智能体状态，可以尝试恢复
            agent_status = state.get("agent_status")
            if agent_status and hasattr(self.plugin, "agent_manager"):
                self.logger.debug(f"检测到智能体状态: {agent_status}")

            self.logger.debug("状态恢复完成")

        except Exception as e:
            self.logger.error(f"恢复状态时出错: {e}")

    async def get_current_mode(self) -> str:
        """获取当前模式"""
        return self.plugin.mode_controller.get_mode_name()

    async def is_mode_switch_allowed(self) -> bool:
        """检查是否允许模式切换"""
        # 从配置中读取
        return self.plugin.plugin_config.get("allow_mode_switching", True)
