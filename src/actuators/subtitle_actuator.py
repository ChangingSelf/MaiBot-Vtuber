from typing import Dict, Any, Optional, Callable
import logging
import asyncio
import time

from src.core.synaptic_network import SynapticNetwork
from src.signals.neural_signal import NeuralSignal, SignalType
from src.signals.motor_signals import SubtitleSignal
from src.actuators.base_actuator import Actuator
from src.utils.subtitle_renderer import SubtitleRenderer

logger = logging.getLogger(__name__)


class SubtitleActuator(Actuator):
    """字幕执行器 - 负责将神经信号转换为字幕显示"""

    def __init__(self, synaptic_network: SynapticNetwork, name: Optional[str] = None):
        super().__init__(synaptic_network, name or "字幕执行器")
        self.subtitle_renderer = None  # 字幕渲染器（外部UI组件）
        self.active_subtitles = {}  # 当前活动的字幕 {id: subtitle_data}
        self.cleanup_task = None  # 清理过期字幕的任务
        self.max_subtitles = 5  # 同时显示的最大字幕数量
        self.default_style = {
            "font": "微软雅黑",
            "size": 20,
            "color": "#FFFFFF",
            "bg_color": "#000000AA",
            "position": "bottom",  # bottom, top, center
        }

    async def _initialize(self, config: Dict[str, Any]) -> None:
        """初始化字幕执行器

        Args:
            config: 字幕执行器配置
        """
        # 设置最大字幕数量
        if "max_subtitles" in config:
            self.max_subtitles = config["max_subtitles"]

        # 设置默认样式
        if "default_style" in config:
            self.default_style.update(config["default_style"])

        # 初始化字幕渲染器（如果配置中有相关参数）
        if "renderer" in config:
            renderer_config = config["renderer"]
            try:
                # 创建并设置渲染器
                renderer = SubtitleRenderer(
                    theme=renderer_config.get("theme", "dark"),
                    font_family=renderer_config.get("font_family", "微软雅黑"),
                    font_size=renderer_config.get("font_size", 24),
                    text_color=renderer_config.get("text_color", "#FFFFFF"),
                    bg_color=renderer_config.get("bg_color", "#333333BB"),
                    opacity=renderer_config.get("opacity", 0.8),
                    animation_speed=renderer_config.get("animation_speed", 10),
                    border_radius=renderer_config.get("border_radius", 10),
                    padding=renderer_config.get("padding", 15),
                    max_messages=renderer_config.get("max_messages", self.max_subtitles),
                    show_history=renderer_config.get("show_history", True),
                )
                self.set_renderer(renderer.handle_subtitle_data)

                # 启动渲染器
                renderer.start()
                # 保存渲染器实例
                self._renderer_instance = renderer
            except Exception as e:
                logger.error(f"初始化字幕渲染器时出错: {e}")

        logger.info(f"字幕执行器初始化完成: {self.name}, 最大字幕数量: {self.max_subtitles}")

    def set_renderer(self, renderer: Callable[[Dict[str, Any]], None]) -> None:
        """设置字幕渲染器

        Args:
            renderer: 字幕渲染回调函数
        """
        self.subtitle_renderer = renderer
        logger.info(f"字幕执行器设置了渲染器: {self.name}")

    async def _activate(self) -> None:
        """激活字幕执行器"""
        await super()._activate()
        # 启动清理任务
        self.cleanup_task = asyncio.create_task(self._cleanup_expired_subtitles())

    async def _deactivate(self) -> None:
        """停用字幕执行器"""
        # 停止清理任务
        if self.cleanup_task:
            self.cleanup_task.cancel()
            try:
                await self.cleanup_task
            except asyncio.CancelledError:
                pass
            self.cleanup_task = None

        # 清除所有活动字幕
        if self.subtitle_renderer and self.active_subtitles:
            for subtitle_id in list(self.active_subtitles.keys()):
                await self._hide_subtitle(subtitle_id)

        # 如果有渲染器实例，关闭它
        if hasattr(self, "_renderer_instance") and self._renderer_instance:
            try:
                self._renderer_instance.stop()
                logger.info("字幕渲染器已关闭")
            except Exception as e:
                logger.error(f"关闭字幕渲染器时出错: {e}")

        await super()._deactivate()

    async def _convert_signal_to_action(self, signal: NeuralSignal) -> Optional[Dict[str, Any]]:
        """将神经信号转换为字幕动作

        Args:
            signal: 神经信号

        Returns:
            字幕动作
        """
        # 检查是否为字幕信号
        if isinstance(signal, SubtitleSignal):
            text = signal.data.get("text", "")
            if not text:
                logger.warning(f"收到空字幕内容，忽略: {signal.id}")
                return None

            # 获取样式设置
            style = signal.data.get("style", {})
            combined_style = {**self.default_style, **style}

            # 创建字幕动作
            return {
                "type": "subtitle",
                "action": "show",
                "id": signal.id,
                "text": text,
                "style": combined_style,
                "duration": signal.data.get("duration", 5.0),
                "source_signal": signal.id,
            }

        # 如果不是字幕信号，检查其他可能需要字幕显示的信号
        elif signal.signal_type == SignalType.CORE:
            # 例如，核心系统的某些消息也需要以字幕形式显示
            if "display_text" in signal.data:
                return {
                    "type": "subtitle",
                    "action": "show",
                    "id": signal.id,
                    "text": signal.data["display_text"],
                    "style": self.default_style,
                    "duration": signal.data.get("duration", 3.0),
                    "source_signal": signal.id,
                }

        return None

    async def _perform_action(self, action: Dict[str, Any]) -> None:
        """执行字幕动作

        Args:
            action: 字幕动作
        """
        action_type = action.get("action")

        if action_type == "show":
            await self._show_subtitle(action)
        elif action_type == "hide":
            await self._hide_subtitle(action.get("id"))
        elif action_type == "update":
            await self._update_subtitle(action)
        else:
            logger.warning(f"未知字幕动作类型: {action_type}")

    async def _show_subtitle(self, subtitle_data: Dict[str, Any]) -> None:
        """显示字幕

        Args:
            subtitle_data: 字幕数据
        """
        subtitle_id = subtitle_data["id"]

        # 检查是否超过最大字幕数量
        if len(self.active_subtitles) >= self.max_subtitles:
            # 移除最早的字幕
            oldest_id = min(self.active_subtitles.items(), key=lambda x: x[1]["created_at"])[0]
            await self._hide_subtitle(oldest_id)

        # 添加创建时间
        subtitle_data["created_at"] = time.time()
        subtitle_data["expires_at"] = time.time() + subtitle_data["duration"]

        # 存储字幕数据
        self.active_subtitles[subtitle_id] = subtitle_data

        # 调用渲染器显示字幕
        if self.subtitle_renderer:
            self.subtitle_renderer(subtitle_data)
        else:
            logger.warning(f"字幕执行器无渲染器，无法显示字幕: {subtitle_id}")

    async def _hide_subtitle(self, subtitle_id: str) -> None:
        """隐藏字幕

        Args:
            subtitle_id: 字幕ID
        """
        if subtitle_id in self.active_subtitles:
            # 创建隐藏动作
            hide_data = {"type": "subtitle", "action": "hide", "id": subtitle_id}

            # 移除活动字幕
            del self.active_subtitles[subtitle_id]

            # 调用渲染器隐藏字幕
            if self.subtitle_renderer:
                self.subtitle_renderer(hide_data)

    async def _update_subtitle(self, subtitle_data: Dict[str, Any]) -> None:
        """更新字幕

        Args:
            subtitle_data: 字幕数据
        """
        subtitle_id = subtitle_data["id"]

        if subtitle_id in self.active_subtitles:
            # 更新字幕数据
            self.active_subtitles[subtitle_id].update(subtitle_data)
            # 确保保留创建时间
            if "duration" in subtitle_data:
                self.active_subtitles[subtitle_id]["expires_at"] = time.time() + subtitle_data["duration"]

            # 调用渲染器更新字幕
            if self.subtitle_renderer:
                self.subtitle_renderer(subtitle_data)
        else:
            # 如果字幕不存在，改为显示
            await self._show_subtitle(subtitle_data)

    async def _cleanup_expired_subtitles(self) -> None:
        """清理过期字幕的后台任务"""
        while self.is_active:
            try:
                current_time = time.time()
                # 查找并移除过期字幕
                expired_ids = [
                    subtitle_id
                    for subtitle_id, data in self.active_subtitles.items()
                    if data["expires_at"] <= current_time
                ]

                for subtitle_id in expired_ids:
                    await self._hide_subtitle(subtitle_id)

                # 间隔检查
                await asyncio.sleep(0.5)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"清理过期字幕时出错: {e}")
                await asyncio.sleep(1)  # 出错时延长间隔
