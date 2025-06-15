import asyncio
import contextlib
from typing import Any, Dict, Optional, List
import time
import mineland

from src.core.plugin_manager import BasePlugin
from src.core.amaidesu_core import AmaidesuCore
from maim_message import MessageBase

from .state.game_state import MinecraftGameState
from .events.event_manager import MinecraftEventManager
from .actions.action_executor import MinecraftActionExecutor
from .message.message_builder import MinecraftMessageBuilder

# 新增导入 - 延迟导入控制器以避免循环依赖
from .core.config_manager import ConfigManager
from .core.agent_manager import AgentManager
from .core.mode_switcher import ModeSwitcher
from .controllers.maicore_controller import MaiCoreController
from .controllers.agent_controller import AgentController


class MinecraftPlugin(BasePlugin):
    """Minecraft插件"""

    def __init__(self, core: AmaidesuCore, plugin_config: Dict[str, Any]):
        super().__init__(core, plugin_config)

        config = self.plugin_config

        # 基础配置
        self.task_id: str = config.get("mineland_task_id", "playground")
        self.server_host: str = config.get("server_host", "127.0.0.1")
        self.server_port: int = config.get("server_port", 1746)

        # 智能体配置（从配置文件读取）
        self.agents_count: int = config.get("agents_count", 1)
        self.agents_config: List[Dict[str, str]] = config.get("agents_config", [{"name": "Mai"}])

        self.headless: bool = config.get("mineland_headless", True)
        self.ticks_per_step: int = config.get("mineland_ticks_per_step", 20)

        # 图像大小配置
        image_size_config = config.get("mineland_image_size", [180, 320])
        if isinstance(image_size_config, list) and len(image_size_config) == 2:
            self.image_size: tuple[int, int] = tuple(image_size_config)
        else:
            self.logger.warning(f"配置的 image_size 无效: {image_size_config}，使用默认值 (180, 320)")
            self.image_size: tuple[int, int] = (180, 320)

        # 自动发送配置
        self.auto_send_interval: float = config.get("auto_send_interval", 30.0)
        self._auto_send_task: Optional[asyncio.Task] = None
        self._last_response_time: float = 0.0

        # MineLand实例
        self.mland: Optional[mineland.MineLand] = None

        # 新增组件
        self.config_manager = ConfigManager(plugin_config)
        self.agent_manager = AgentManager()
        self.mode_switcher = ModeSwitcher(self)

        # 控制策略（延迟创建以避免循环依赖）
        self.mode_controller = None

        # 核心组件 - 使用配置文件中的参数
        action_executor_config = config.get("action_executor", {})
        event_manager_config = config.get("event_manager", {})
        game_state_config = config.get("game_state", {})

        self.game_state = MinecraftGameState(game_state_config)
        self.event_manager = MinecraftEventManager(
            event_manager_config.get("max_event_history", 20),
            config,  # 传递完整配置
        )
        self.action_executor = MinecraftActionExecutor(
            self.game_state,
            self.event_manager,
            max_wait_cycles=action_executor_config.get("max_wait_cycles", 100),
            wait_cycle_interval=action_executor_config.get("wait_cycle_interval", 0.1),
            config=config,  # 传递完整配置
        )
        self.message_builder = MinecraftMessageBuilder(
            platform=self.core.platform,
            user_id=config.get("user_id", "minecraft_bot"),
            nickname=config.get("nickname", "Minecraft Observer"),
            group_id=config.get("group_id", ""),
            config=config.get("prompt", {}),
        )

    def _create_initial_controller(self):
        """延迟创建初始控制器以避免循环依赖"""
        control_mode = self.config_manager.get_control_mode()
        if control_mode == "maicore":
            return MaiCoreController()
        elif control_mode == "agent":
            return AgentController()
        else:
            self.logger.warning(f"不支持的控制模式: {control_mode}，使用默认maicore模式")

            return MaiCoreController()

    async def setup(self):
        """重构后的初始化方法"""
        await super().setup()

        # 创建控制器（延迟创建）
        self.mode_controller = self._create_initial_controller()

        # 初始化MineLand环境（保持现有逻辑）
        await self._initialize_mineland()

        # 初始化智能体管理器
        await self.agent_manager.initialize(self.config_manager.get_agent_config())

        # 初始化控制器
        await self.mode_controller.initialize(self)

        # 注册消息处理器
        self.core.register_websocket_handler("*", self.handle_external_message)

        # 启动控制循环
        await self.mode_controller.start_control_loop()

        self.logger.info(f"Minecraft插件初始化完成，当前模式: {self.mode_controller.get_mode_name()}")

    async def _initialize_mineland(self):
        """初始化MineLand环境"""
        self.logger.info("Minecraft 插件已加载，正在初始化 MineLand 环境...")
        try:
            # 初始化MineLand环境
            self.mland = mineland.MineLand(
                server_host=self.server_host,
                server_port=self.server_port,
                agents_count=self.agents_count,
                agents_config=self.agents_config,
                headless=self.headless,
                image_size=self.image_size,
                enable_low_level_action=False,
                ticks_per_step=self.ticks_per_step,
            )
            self.logger.info(f"MineLand 环境 (Task ID: {self.task_id}) 初始化成功。")

            # 将 mland 实例注入到 action_executor 中
            self.action_executor.set_mland(self.mland)

            # 重置环境并初始化状态
            initial_obs = self.mland.reset()
            self.game_state.reset_state(initial_obs)
            self.game_state.add_initial_goal_record()

            self.logger.info(f"MineLand 环境已重置，收到初始观察: {len(initial_obs)} 个智能体。")
            self.logger.info(f"已记录初始目标: {self.game_state.goal}")

        except Exception as e:
            self.logger.exception(f"初始化 MineLand 环境失败: {e}")
            raise

    async def _auto_send_loop(self):
        """定期发送状态的循环任务"""
        while True:
            try:
                await asyncio.sleep(self.auto_send_interval)

                current_time = time.time()
                if current_time - self._last_response_time > self.auto_send_interval:
                    # 超时时间内未收到响应，刷新状态并重新发送
                    await self.action_executor.execute_no_op()
                    self.logger.info("超时时间内未收到响应，刷新状态并重新发送")
                    if self.game_state.is_ready_for_next_action():
                        # 如果智能体准备好，则发送状态
                        await self._send_state_to_maicore()
            except asyncio.CancelledError:
                self.logger.info("自动发送状态任务被取消")
                break
            except Exception as e:
                self.logger.error(f"自动发送状态时出错: {e}")
                await asyncio.sleep(1)

    async def _send_state_to_maicore(self):
        """构建并发送当前Mineland状态给AmaidesuCore"""
        try:
            msg_to_maicore = self.message_builder.build_state_message(
                self.game_state, self.event_manager, self.agents_config
            )

            # 如果消息为空，则执行no_op
            if not msg_to_maicore:
                await self.action_executor.execute_no_op()
                return

            await self.core.send_to_maicore(msg_to_maicore)
            self.logger.info(
                f"已将 Mineland 事件状态 (step {self.game_state.current_step_num}, done: {self.game_state.current_done}) 发送给 MaiCore。"
            )
        except Exception as e:
            self.logger.error(f"构建或发送状态消息时出错: {e}")
            raise

    async def handle_external_message(self, message: MessageBase):
        """委托给当前控制器处理外部消息"""
        await self.mode_controller.handle_external_message(message)

    async def get_current_mode(self) -> str:
        """获取当前模式"""
        return await self.mode_switcher.get_current_mode()

    async def get_agent_status(self) -> dict:
        """获取智能体状态"""
        if hasattr(self, "agent_manager") and self.agent_manager:
            return await self.agent_manager.get_agent_status()
        return {"error": "智能体管理器未初始化"}

    async def cleanup(self):
        """清理插件资源"""
        self.logger.info("正在清理 Minecraft 插件...")

        # 清理控制器
        if hasattr(self, "mode_controller") and self.mode_controller:
            try:
                await self.mode_controller.cleanup()
            except Exception as e:
                self.logger.error(f"清理控制器时出错: {e}")

        # 清理智能体管理器
        if hasattr(self, "agent_manager") and self.agent_manager:
            try:
                await self.agent_manager.cleanup()
            except Exception as e:
                self.logger.error(f"清理智能体管理器时出错: {e}")

        # 停止自动发送任务（向后兼容）
        if self._auto_send_task:
            self.logger.info("正在停止自动发送状态任务...")
            self._auto_send_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._auto_send_task
            self._auto_send_task = None

        # 关闭MineLand环境
        if self.mland:
            try:
                self.logger.info("正在关闭 MineLand 环境...")
                self.mland.close()
                self.logger.info("MineLand 环境已关闭。")
            except Exception as e:
                self.logger.exception(f"关闭 MineLand 环境时发生错误: {e}")

        self.logger.info("Minecraft 插件清理完毕。")


# --- 插件入口点 ---
plugin_entrypoint = MinecraftPlugin
