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


class MinecraftPlugin(BasePlugin):
    """Minecraft插件"""

    def __init__(self, core: AmaidesuCore, plugin_config: Dict[str, Any]):
        super().__init__(core, plugin_config)

        config = self.plugin_config

        # 基础配置
        self.task_id: str = config.get("mineland_task_id", "playground")
        self.server_host: str = config.get("server_host", "127.0.0.1")
        self.server_port: int = config.get("server_port", 1746)
        self.agents_config: List[Dict[str, str]] = [{"name": "Mai"}]
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

        # 核心组件
        self.game_state = MinecraftGameState()
        self.event_manager = MinecraftEventManager(config.get("max_event_history", 20))
        self.action_executor = MinecraftActionExecutor(
            self.game_state,
            self.event_manager,
            config.get("max_wait_cycles", 100),
            config.get("wait_cycle_interval", 0.1),
        )
        self.message_builder = MinecraftMessageBuilder(
            platform=self.core.platform,
            user_id=config.get("user_id", "minecraft_bot"),
            nickname=config.get("nickname", "Minecraft Observer"),
            group_id=config.get("group_id"),
        )

    async def setup(self):
        """初始化插件"""
        await super().setup()
        self.core.register_websocket_handler("text", self.handle_maicore_response)

        self.logger.info("Minecraft 插件已加载，正在初始化 MineLand 环境...")
        try:
            # 初始化MineLand环境
            self.mland = mineland.MineLand(
                server_host=self.server_host,
                server_port=self.server_port,
                agents_count=1,
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

            # 发送初始状态
            if self.game_state.current_obs:
                await self._send_state_to_maicore()
            else:
                self.logger.warning("初始化时没有观察数据，将在自动发送循环中重试")

            # 启动自动发送任务
            self._auto_send_task = asyncio.create_task(self._auto_send_loop(), name="MinecraftAutoSend")
            self.logger.info(f"已启动自动发送状态任务，间隔: {self.auto_send_interval}秒")

        except Exception as e:
            self.logger.exception(f"初始化 MineLand 环境失败: {e}")
            return

    async def _auto_send_loop(self):
        """定期发送状态的循环任务"""
        while True:
            try:
                await asyncio.sleep(self.auto_send_interval)

                current_time = time.time()
                if current_time - self._last_response_time > self.auto_send_interval:
                    if self.game_state.is_ready_for_next_action():
                        self.logger.info("未收到响应且已准备好，重新发送状态...")
                        await self._send_state_to_maicore()
                    else:
                        self.logger.info("未收到响应但智能体未准备好，执行no_op等待...")
                        try:
                            await self.action_executor.execute_no_op()
                            self.logger.debug(
                                f"自动发送循环中执行no_op完毕，当前步骤: {self.game_state.current_step_num}"
                            )
                        except Exception as e:
                            self.logger.error(f"自动发送循环中执行no_op时出错: {e}")

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

            await self.core.send_to_maicore(msg_to_maicore)
            self.logger.info(
                f"已将 Mineland 事件状态 (step {self.game_state.current_step_num}, done: {self.game_state.current_done}) 发送给 MaiCore。"
            )
        except Exception as e:
            self.logger.error(f"构建或发送状态消息时出错: {e}")
            raise

    async def handle_maicore_response(self, message: MessageBase):
        """处理从 MaiCore 返回的动作指令"""
        self.logger.info(f"收到来自 MaiCore 的响应: {message.message_segment.data}")

        # 更新最后响应时间
        self._last_response_time = time.time()

        if not self.mland:
            self.logger.error("收到 MaiCore 响应，但 MineLand 环境未初始化。忽略消息。")
            return

        if message.message_segment.type != "text":
            self.logger.warning(
                f"MaiCore 返回的消息不是文本消息: type='{message.message_segment.type}'. 期望是'text'。丢弃消息。"
            )
            return

        message_json_str = message.message_segment.data.strip()
        self.logger.debug(f"从 MaiCore 收到原始动作指令: {message_json_str}")

        try:
            # 执行动作（包括等待完成、状态更新等）
            await self.action_executor.execute_maicore_action(message_json_str)

            # 发送新的状态给 MaiCore
            await self._send_state_to_maicore()

        except Exception as e:
            self.logger.exception(f"执行 Mineland step 或处理后续状态时出错: {e}")

    async def cleanup(self):
        """清理插件资源"""
        self.logger.info("正在清理 Minecraft 插件...")

        # 停止自动发送任务
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
