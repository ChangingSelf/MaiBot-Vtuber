# -*- coding: utf-8 -*-
from typing import Any, Dict, List, Optional, Tuple

import mineland
from maim_message import MessageBase

from src.core.amaidesu_core import AmaidesuCore
from src.utils.logger import get_logger

from .actions.action_executor import MinecraftActionExecutor
from .agents.agent_manager import AgentManager
from .events.event_manager import MinecraftEventManager
from .message.message_builder import MinecraftMessageBuilder
from .state.game_state import MinecraftGameState
from .state.analyzers import StateAnalyzer


class MinecraftContext:
    """
    Minecraft插件的上下文，用于管理所有共享组件和状态。
    """

    def __init__(self, core: AmaidesuCore, plugin_config: Dict[str, Any]):
        self.core = core
        self.plugin_config = plugin_config
        self.logger = get_logger("MinecraftContext")

        self._setup_config()
        self._setup_components()

        # MineLand实例
        self.mland: Optional[mineland.MineLand] = None

    def _setup_config(self):
        """加载和初始化插件配置"""
        config = self.plugin_config

        # 基础配置
        self.server_host: str = config.get("server_host", "127.0.0.1")
        self.server_port: int = config.get("server_port", 1746)
        self.headless: bool = config.get("mineland_headless", True)
        self.ticks_per_step: int = config.get("mineland_ticks_per_step", 20)

        # 智能体配置
        self.agents_count: int = config.get("agents_count", 1)
        self.agents_config: List[Dict[str, Any]] = config.get("agents_config", [{"name": "Mai"}])

        # 图像大小配置
        image_size_config = config.get("mineland_image_size", [180, 320])
        if isinstance(image_size_config, list) and len(image_size_config) == 2:
            self.image_size: Tuple[int, int] = tuple(image_size_config)
        else:
            self.logger.warning(f"配置的 image_size 无效: {image_size_config}，使用默认值 (180, 320)")
            self.image_size: Tuple[int, int] = (180, 320)

    def _setup_components(self):
        """初始化插件的核心组件"""
        config = self.plugin_config

        # 状态分析器
        self.state_analyzer = StateAnalyzer(None, config)

        self.agent_manager = AgentManager()
        self.game_state = MinecraftGameState(config.get("game_state", {}), self.state_analyzer)
        self.event_manager = MinecraftEventManager(
            config.get("event_manager", {}).get("max_event_history", 20),
            config,
        )
        self.action_executor = MinecraftActionExecutor(
            game_state=self.game_state,
            event_manager=self.event_manager,
            config=config,
            max_wait_cycles=config.get("action_executor", {}).get("max_wait_cycles", 100),
            wait_cycle_interval=config.get("action_executor", {}).get("wait_cycle_interval", 0.1),
        )
        self.message_builder = MinecraftMessageBuilder(
            platform=self.core.platform,
            user_id=config.get("user_id", "minecraft_bot"),
            nickname=config.get("nickname", "Minecraft Observer"),
            group_id=config.get("group_id", ""),
            config=config.get("prompt", {}),
        )

    async def initialize_mineland(self):
        """初始化MineLand环境"""
        self.logger.info("正在初始化 MineLand 环境...")
        try:
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
            self.action_executor.set_mland(self.mland)

            initial_obs = self.mland.reset()
            self.game_state.reset_state(initial_obs)
            self.game_state.add_initial_goal_record()
            # 初始化时也设置一次观察数据
            self.state_analyzer.set_observation(self.game_state.current_obs)

            self.logger.info(f"MineLand 环境初始化成功，已连接到{self.server_host}:{self.server_port}")
            self.logger.info(f"已记录初始目标: {self.game_state.goal}")
        except Exception as e:
            self.logger.exception(f"初始化 MineLand 环境失败: {e}")
            raise

    def extract_text_from_message(self, message: MessageBase) -> Optional[str]:
        """从MessageBase中提取文本内容"""
        segment = message.message_segment
        if segment.type == "text" and isinstance(segment.data, str):
            return segment.data.strip()
        if segment.type == "seglist" and isinstance(segment.data, list):
            for seg in segment.data:
                if hasattr(seg, "type") and seg.type == "text" and hasattr(seg, "data"):
                    return str(seg.data).strip()
        self.logger.warning(f"收到不支持的消息格式: type='{segment.type}'，已忽略。")
        return None

    async def send_state_to_maicore(self, *args, **kwargs):
        """构建并发送当前状态给AmaidesuCore"""
        try:
            agents_config_str = [{k: str(v) for k, v in agent_cfg.items()} for agent_cfg in self.agents_config]
            if msg_to_maicore := self.message_builder.build_state_message(
                self.game_state, self.event_manager, agents_config_str
            ):
                await self.core.send_to_maicore(msg_to_maicore)
                self.logger.info(
                    f"已将状态 (step {self.game_state.current_step_num}, done: {self.game_state.current_done}) 发送给 MaiCore。"
                )
            else:
                await self.action_executor.execute_no_op()
        except Exception as e:
            self.logger.error(f"构建或发送状态消息时出错: {e}", exc_info=True)
