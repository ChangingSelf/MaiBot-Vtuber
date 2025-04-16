# src/plugins/command_processor/plugin.py

import asyncio
import logging
import re
import tomllib
import os
from typing import Any, Dict, Optional

from core.plugin_manager import BasePlugin
from core.amaidesu_core import AmaidesuCore
from maim_message import MessageBase  # 假设 MessageBase 可以从 maim_message 导入


# --- Helper Function ---
def load_plugin_config() -> Dict[str, Any]:
    # (Config loading logic - similar to other plugins)
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
                    logging.error("toml package needed for Python < 3.11.")
                    return {}
                except FileNotFoundError:
                    logging.warning(f"Config file not found: {config_path}")
                    return {}
    except Exception as e:
        logging.error(f"Error loading config: {config_path}: {e}", exc_info=True)
        return {}


# --- Plugin Class ---
class CommandProcessorPlugin(BasePlugin):
    """
    Intercepts messages from MaiCore, processes embedded commands (e.g., %{command:args}%),
    executes them via services, and removes them from the message text before further processing.
    """

    _is_amaidesu_plugin: bool = True

    def __init__(self, core: AmaidesuCore, plugin_config: Dict[str, Any]):
        super().__init__(core, plugin_config)
        self.logger = logging.getLogger(__name__)
        self.config = plugin_config.get("command_processor", {})
        self.enabled = self.config.get("enabled", True)

        if not self.enabled:
            self.logger.warning("CommandProcessorPlugin 在配置中被禁用。")
            return

        self.command_pattern_str = self.config.get("command_pattern", r"%\\{([^%{}]+)\\}")
        try:
            self.command_pattern = re.compile(self.command_pattern_str)
            self.logger.info(f"使用指令匹配模式: {self.command_pattern_str}")
        except re.error as e:
            self.logger.error(f"无效的指令匹配模式 '{self.command_pattern_str}': {e}。插件已禁用。")
            self.enabled = False
            self.command_pattern = None

        # --- Hardcoded command mapping (for now) ---
        # TODO: 使其可配置或使用更动态的服务发现
        self.command_map = {
            "vts_trigger_hotkey": {"service": "vts_control", "method": "trigger_hotkey"},
            # 在此处添加更多命令
            # "play_sound": {"service": "audio_player", "method": "play"},
        }
        self.logger.debug(f"使用命令映射初始化: {self.command_map}")

    async def setup(self):
        await super().setup()
        if not self.enabled:
            return

        # 注册通配符处理器以处理所有来自 MaiCore 的传入消息
        # 重要: 假设此处理器在特定处理器（如 TTS）之前运行。
        # 未来可能需要在 AmaidesuCore 中加入优先级系统。
        self.core.register_websocket_handler("*", self.process_message)
        self.logger.info("CommandProcessorPlugin 已注册为通配符消息处理器。")

    async def cleanup(self):
        # 如果 AmaidesuCore 支持，可能需要取消注册处理器
        self.logger.info("CommandProcessorPlugin 已清理。")
        await super().cleanup()

    async def process_message(self, message: MessageBase):
        """
        处理传入消息以查找、执行和移除命令标签。
        直接修改 message.message_segment.data。
        """
        if not self.enabled or not self.command_pattern:
            return  # 如果禁用或模式无效则不执行任何操作

        # 仅处理文本消息
        if not message.message_segment or message.message_segment.type != "text":
            return

        original_text = message.message_segment.data
        if not isinstance(original_text, str):
            # 对于文本段，应该不会发生这种情况，但检查一下比较好
            self.logger.warning(f"文本段预期为字符串数据，但得到 {type(original_text)}。跳过命令处理。")
            return

        processed_text = original_text
        commands_found = self.command_pattern.findall(original_text)

        if not commands_found:
            return  # 未找到命令，无需执行任何操作

        self.logger.info(f"在消息 {message.message_info.message_id} 中找到 {len(commands_found)} 个潜在指令。")

        execution_tasks = []

        for command_full_match in commands_found:
            # command_full_match 是 %{...}% 内部的内容
            self.logger.debug(f"处理指令标签内容: '{command_full_match}'")

            # 简单解析: command:arg1,arg2... (按第一个 ':' 分割)
            parts = command_full_match.strip().split(":", 1)
            command_name = parts[0]
            args_str = parts[1] if len(parts) > 1 else ""

            if command_name in self.command_map:
                command_config = self.command_map[command_name]
                service_name = command_config["service"]
                method_name = command_config["method"]

                service_instance = self.core.get_service(service_name)

                if service_instance:
                    if hasattr(service_instance, method_name):
                        method_to_call = getattr(service_instance, method_name)
                        if asyncio.iscoroutinefunction(method_to_call):
                            # 基本参数解析 (按逗号分割，去除空白)
                            # 对于复杂参数可能需要更健壮的解析
                            args = [arg.strip() for arg in args_str.split(",") if arg.strip()]
                            self.logger.info(
                                f"通过服务 '{service_name}'.{method_name} 执行指令 '{command_name}' (参数: {args})。"
                            )
                            # 异步执行命令，不等待
                            execution_tasks.append(asyncio.create_task(method_to_call(*args)))
                        else:
                            self.logger.warning(
                                f"服务 '{service_name}' 上的方法 '{method_name}' 不是异步函数。无法执行指令 '{command_name}'。"
                            )
                    else:
                        self.logger.warning(
                            f"找到服务 '{service_name}'，但未找到指令 '{command_name}' 所需的方法 '{method_name}'。"
                        )
                else:
                    self.logger.warning(f"未找到指令 '{command_name}' 所需的服务 '{service_name}'。")
            else:
                self.logger.warning(f"发现未知指令: '{command_name}'")

        # 从文本中移除所有命令标签
        # 我们使用带有原始模式的 re.sub
        processed_text = self.command_pattern.sub("", original_text).strip()

        # 直接修改消息段数据
        if processed_text != original_text:
            self.logger.debug(f"原始文本: '{original_text}'")
            self.logger.info(f"处理后文本 (指令已移除): '{processed_text}'")
            message.message_segment.data = processed_text

        # 消息将在此处理器完成后自然由其他处理器（如 TTS）处理，
        # 现在使用的是修改后的数据。


# --- Plugin Entry Point ---
plugin_entrypoint = CommandProcessorPlugin
