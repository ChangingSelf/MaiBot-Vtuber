# src/plugins/vtube_studio/plugin.py
import asyncio
import tomllib
import os
from typing import Any, Dict, Optional
import aiohttp
import time  # 添加 time 模块导入

from maim_message.message_base import MessageBase

# 从 core 导入基类和核心类
from core.plugin_manager import BasePlugin
from src.core.amaidesu_core import AmaidesuCore
from src.utils.logger import logger


# --- Helper Function ---
def load_plugin_config() -> Dict[str, Any]:
    # (Config loading logic - keep for now, might be needed)
    config_path = os.path.join(os.path.dirname(__file__), "config.toml")
    try:
        with open(config_path, "rb") as f:
            if hasattr(tomllib, "load"):
                return tomllib.load(f)
            else:
                try:
                    import toml

                    with open(config_path, "r", encoding="utf-8") as rf:
                        return toml.load(rf)
                except ImportError:
                    logger.error("toml package needed for Python < 3.11.")
                    return {}
                except FileNotFoundError:
                    logger.warning(f"Config file not found: {config_path}")
                    return {}
    except Exception as e:
        logger.error(f"Error loading config: {config_path}: {e}", exc_info=True)
        return {}


# --- Plugin Class ---
class StickerPlugin(BasePlugin):
    """
    将麦麦发送的表情图片作为表情贴纸发送给VTS
    """

    _is_amaidesu_plugin: bool = True

    def __init__(self, core: AmaidesuCore, plugin_config: Dict[str, Any]):
        super().__init__(core, plugin_config)
        self.logger = logger

        loaded_config = load_plugin_config()
        self.config = loaded_config.get("sticker", {})
        self.enabled = self.config.get("enabled", True)
        # 添加表情贴纸配置
        self.sticker_size = self.config.get("sticker_size", 0.33)
        self.sticker_rotation = self.config.get("sticker_rotation", 90)
        self.sticker_position_x = self.config.get("sticker_position_x", 0)
        self.sticker_position_y = self.config.get("sticker_position_y", 0)
        # 添加冷却时间配置和上次触发时间记录
        self.cool_down_seconds = self.config.get("cool_down_seconds", 5)  # 从配置读取冷却时间，默认为 5 秒
        self.last_trigger_time: float = 0.0  # 初始化上次触发时间
        self.display_duration_seconds = self.config.get(
            "display_duration_seconds", 3
        )  # 从配置读取显示时长，默认为 3 秒

        self.logger.info("表情贴纸插件初始化完成")

    async def setup(self):
        await super().setup()
        if not self.enabled:
            self.logger.warning("表情贴纸插件设置跳过（已禁用）")
            return

        self.core.register_websocket_handler("emoji", self.handle_maicore_message)

        self.logger.info("表情贴纸插件设置完成")

    async def cleanup(self):
        self.logger.info("表情贴纸插件清理中...")
        # --- 新插件的清理逻辑 ---
        # 例如: 取消注册、关闭连接等
        # self.core.unregister_command(...)

        await super().cleanup()
        self.logger.info("表情贴纸插件清理完成")

    # --- 新插件的方法 ---
    # 例如: 处理消息、执行分析等
    # async def analyze_emotion(self, text: str): ...

    async def handle_maicore_message(self, message: MessageBase):
        """处理从 MaiCore 收到的消息，如果是文本类型，则进行处理，触发热键。"""
        if not message or not message.message_segment or message.message_segment.type != "emoji":
            self.logger.debug("收到非表情消息，跳过")
            return

        # --- 将冷却时间检查移到此处 ---
        current_time = time.monotonic()
        if current_time - self.last_trigger_time < self.cool_down_seconds:
            remaining_cooldown = self.cool_down_seconds - (current_time - self.last_trigger_time)
            self.logger.debug(f"表情贴纸冷却中，跳过消息处理。剩余 {remaining_cooldown:.1f} 秒")
            return
        # --- 冷却时间检查结束 ---

        image_base64 = message.message_segment.data

        vts_control_service = self.core.get_service("vts_control")
        if not vts_control_service:
            self.logger.warning("未找到 VTS 控制服务。无法发送表情贴纸。")
            return

        item_instance_id = await vts_control_service.load_item(
            custom_data_base64=image_base64,
            position_x=self.sticker_position_x,
            position_y=self.sticker_position_y,
            size=self.sticker_size,
            rotation=self.sticker_rotation,
        )
        if not item_instance_id:
            self.logger.error("表情贴纸加载失败")
            return

        await asyncio.sleep(self.display_duration_seconds)

        success = await vts_control_service.unload_item(
            item_instance_id_list=[item_instance_id],
        )
        if not success:
            self.logger.error("表情贴纸卸载失败")


# --- Plugin Entry Point ---
plugin_entrypoint = StickerPlugin
