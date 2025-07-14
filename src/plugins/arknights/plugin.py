# src/plugins/vtube_studio/plugin.py
from typing import Any, Dict
from maim_message.message_base import MessageBase

# 从 core 导入基类和核心类
from src.core.plugin_manager import BasePlugin
from src.core.amaidesu_core import AmaidesuCore

# logger = get_logger("ArknightsPlugin")


# --- Helper Function ---
# def load_plugin_config() -> Dict[str, Any]:
#     # (Config loading logic - keep for now, might be needed)
#     config_path = os.path.join(os.path.dirname(__file__), "config.toml")
#     try:
#         with open(config_path, "rb") as f:
#             if hasattr(tomllib, "load"):
#                 return tomllib.load(f)
#             else:
#                 try:
#                     import toml
#
#                     with open(config_path, "r", encoding="utf-8") as rf:
#                         return toml.load(rf)
#                 except ImportError:
#                     logger.error("toml package needed for Python < 3.11.")
#                     return {}
#                 except FileNotFoundError:
#                     logger.warning(f"Config file not found: {config_path}")
#                     return {}
#     except Exception as e:
#         logger.error(f"Error loading config: {config_path}: {e}", exc_info=True)
#         return {}


# --- Plugin Class ---
class ArknightsPlugin(BasePlugin):
    """
    让麦麦游玩明日方舟
    """

    def __init__(self, core: AmaidesuCore, plugin_config: Dict[str, Any]):
        super().__init__(core, plugin_config)
        # self.logger = logger # 已由基类初始化

        # loaded_config = load_plugin_config()
        # self.config = loaded_config.get("arknights", {})
        self.config = self.plugin_config  # 直接使用注入的 plugin_config
        self.enabled = self.config.get("enabled", True)

        # self.logger.info("明日方舟插件初始化完成") # 基类已有通用初始化日志

    async def setup(self):
        await super().setup()
        if not self.enabled:
            self.logger.warning("明日方舟插件设置跳过（已禁用）")
            return

        self.core.register_websocket_handler("emoji", self.handle_maicore_message)

        self.logger.info("明日方舟插件设置完成")

    async def cleanup(self):
        self.logger.info("明日方舟插件清理中...")
        # --- 新插件的清理逻辑 ---
        # 例如: 取消注册、关闭连接等
        # self.core.unregister_command(...)

        await super().cleanup()
        self.logger.info("明日方舟插件清理完成")

    # --- 新插件的方法 ---
    # 例如: 处理消息、执行分析等
    # async def analyze_emotion(self, text: str): ...

    async def handle_maicore_message(self, message: MessageBase):
        """处理从 MaiCore 收到的消息"""
        pass


# --- Plugin Entry Point ---
plugin_entrypoint = ArknightsPlugin
