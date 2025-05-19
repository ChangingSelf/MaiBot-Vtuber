import asyncio

# import logging
import os
import sys
import time
from typing import Dict, Any, Optional, List

# --- Dependency Check & TOML ---
try:
    import tomllib
except ModuleNotFoundError:
    try:
        import toml as tomllib
    except ImportError:
        print("依赖缺失: 请运行 'pip install toml' 来加载 Console Input 插件配置。", file=sys.stderr)
        tomllib = None

# --- Amaidesu Core Imports ---
from src.core.plugin_manager import BasePlugin
from src.core.amaidesu_core import AmaidesuCore
from maim_message import MessageBase, BaseMessageInfo, UserInfo, GroupInfo, Seg, FormatInfo

# --- Plugin Configuration Loading ---
# _PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
# _CONFIG_FILE = os.path.join(_PLUGIN_DIR, "config.toml")
#
#
# def load_plugin_config() -> Dict[str, Any]:
#     """Loads the plugin's specific config.toml file."""
#     if tomllib is None:
#         logger.error("TOML library not available, cannot load Console Input plugin config.")
#         return {}
#     try:
#         with open(_CONFIG_FILE, "rb") as f:
#             config = tomllib.load(f)
#             logger.info(f"成功加载 Console Input 插件配置文件: {_CONFIG_FILE}")
#             return config
#     except FileNotFoundError:
#         logger.warning(f"Console Input 插件配置文件未找到: {_CONFIG_FILE}。将使用默认值。")
#     except tomllib.TOMLDecodeError as e:
#         logger.error(f"Console Input 插件配置文件 '{_CONFIG_FILE}' 格式无效: {e}。将使用默认值。")
#     except Exception as e:
#         logger.error(f"加载 Console Input 插件配置文件 '{_CONFIG_FILE}' 时发生未知错误: {e}", exc_info=True)
#     return {}


class ConsoleInputPlugin(BasePlugin):
    """通过控制台接收用户输入并发送消息的插件"""

    def __init__(self, core: AmaidesuCore, plugin_config: Dict[str, Any]):
        super().__init__(core, plugin_config)
        # self.config = load_plugin_config()
        self.config = self.plugin_config  # 直接使用注入的 plugin_config
        self.enabled = True

        # --- Dependency Check ---
        if tomllib is None:
            self.logger.error("缺少 TOML 依赖，Console Input 插件禁用。")
            self.enabled = False
            return

        # --- Load Message Config Defaults from plugin's config.toml ---
        self.message_config = self.config.get("message_config", {})  # Expecting a [message_config] section
        if not self.message_config:
            self.logger.warning("在 console_input/config.toml 中未找到 [message_config] 配置段，将使用硬编码默认值。")
            # Define fallback defaults if message_config is missing
            self.message_config = {
                "user_id": "console_user_fallback",
                "user_nickname": "控制台",
                "user_cardname": "Fallback",
                "enable_group_info": False,
                "group_id": 0,
                "group_name": "default",
                "content_format": ["text"],
                "accept_format": ["text"],
                "enable_template_info": False,
                "template_name": "default",
                "template_default": False,
                "additional_config": {},
            }
        else:
            self.logger.info("已加载来自 console_input/config.toml 的 [message_config]。")

        # --- Prompt Context Tags ---
        # Read from message_config section
        self.context_tags: Optional[List[str]] = self.message_config.get("context_tags")
        if not isinstance(self.context_tags, list):
            if self.context_tags is not None:
                self.logger.warning(
                    f"Config 'context_tags' in [message_config] is not a list ({type(self.context_tags)}), will fetch all context."
                )
            self.context_tags = None  # None tells get_formatted_context to get all
        elif not self.context_tags:
            self.logger.info("'context_tags' in [message_config] is empty, will fetch all context.")
            self.context_tags = None  # Treat empty list same as None
        else:
            self.logger.info(f"Will fetch context with tags: {self.context_tags}")

        # --- Load Template Items Separately (if enabled and exists within message_config) ---
        self.template_items = None
        if self.message_config.get("enable_template_info", False):
            # Load template_items directly from the message_config dictionary
            self.template_items = self.message_config.get("template_items", {})
            if not self.template_items:
                self.logger.warning("配置启用了 template_info，但在 message_config 中未找到 template_items。")

        self._input_task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()

    async def setup(self):
        """启动控制台输入监听任务。"""
        await super().setup()
        if not self.enabled:
            self.logger.warning("Console Input 插件未启用，不启动监听任务。")
            return
        self.logger.info("启动控制台输入监听任务...")
        self._stop_event.clear()
        self._input_task = asyncio.create_task(self._input_loop(), name="ConsoleInputLoop")

    async def cleanup(self):
        """停止控制台输入任务。"""
        self.logger.info("请求停止 Console Input 插件...")
        self._stop_event.set()
        # Give the input loop a chance to exit gracefully
        if self._input_task and not self._input_task.done():
            self.logger.info("正在等待控制台输入任务结束 (最多 2 秒)...")
            try:
                # Signal stdin to unblock (implementation specific)
                # On Windows, sending a newline might work if blocked on input()
                # On Linux/macOS, this might be more complex (e.g., closing stdin requires care)
                # For simplicity, we rely on the timeout/cancellation here.
                await asyncio.wait_for(self._input_task, timeout=2.0)
            except asyncio.TimeoutError:
                self.logger.warning("控制台输入任务在超时后仍未结束，将强制取消。")
                self._input_task.cancel()
            except asyncio.CancelledError:
                self.logger.info("控制台输入任务已被取消。")
            except Exception as e:
                self.logger.error(f"等待控制台输入任务结束时出错: {e}", exc_info=True)
        self.logger.info("Console Input 插件清理完成。")
        await super().cleanup()

    async def _input_loop(self):
        """异步循环以读取控制台输入。"""
        self.logger.info("控制台输入已准备就绪。输入 'exit()' 来停止。")
        loop = asyncio.get_event_loop()
        while not self._stop_event.is_set():
            try:
                line = await loop.run_in_executor(None, sys.stdin.readline)
                text = line.strip()

                if not text:
                    continue  # Ignore empty lines
                if text.lower() == "exit()":
                    self.logger.info("收到 'exit()' 命令，正在停止...")
                    self._stop_event.set()
                    break
                if self._stop_event.is_set():  # Check again after potential blocking read
                    break

                # Create message using loaded config
                message = await self._create_console_message(text)
                await self.core.send_to_maicore(message)

            except asyncio.CancelledError:
                self.logger.info("控制台输入循环被取消。")
                break
            except Exception as e:
                self.logger.error(f"控制台输入循环出错: {e}", exc_info=True)
                # Avoid busy-looping on persistent errors
                await asyncio.sleep(1)
        self.logger.info("控制台输入循环结束。")

    async def _create_console_message(self, text: str) -> MessageBase:
        """使用从 config.toml 加载的配置创建 MessageBase 对象。"""
        timestamp = time.time()
        cfg = self.message_config  # Use the loaded message config

        # --- User Info ---
        user_id_from_config = cfg.get("user_id", 0)  # Assume int from config, default to 0
        user_info = UserInfo(
            platform=self.core.platform,
            user_id=user_id_from_config,
            user_nickname=cfg.get("user_nickname", "ConsoleUser"),
            user_cardname=cfg.get("user_cardname", ""),
        )

        # --- Group Info (Conditional) ---
        group_info: Optional[GroupInfo] = None
        if cfg.get("enable_group_info", False):
            group_info = GroupInfo(
                platform=self.core.platform,
                group_id=cfg.get("group_id", 0),
                group_name=cfg.get("group_name", "default"),
            )

        # --- Format Info ---
        format_info = FormatInfo(
            content_format=cfg.get("content_format", ["text"]), accept_format=cfg.get("accept_format", ["text"])
        )

        # --- Template Info (Conditional & Modification) ---
        final_template_info_value = None
        if cfg.get("enable_template_info", False) and self.template_items:
            # 1. 获取原始模板项 (创建副本)
            modified_template_items = (self.template_items or {}).copy()

            # 2. --- 获取并追加 Prompt 上下文 ---
            additional_context = ""
            prompt_ctx_service = self.core.get_service("prompt_context")
            if prompt_ctx_service:
                try:
                    # 使用 self.context_tags 获取上下文
                    additional_context = await prompt_ctx_service.get_formatted_context(tags=self.context_tags)
                    if additional_context:
                        self.logger.debug(f"获取到聚合 Prompt 上下文: '{additional_context[:100]}...'")
                except Exception as e:
                    self.logger.error(f"调用 prompt_context 服务时出错: {e}", exc_info=True)

            # 3. 修改主 Prompt (如果上下文非空且主 Prompt 存在)
            main_prompt_key = "reasoning_prompt_main"  # 假设主 Prompt 的键
            if additional_context and main_prompt_key in modified_template_items:
                original_prompt = modified_template_items[main_prompt_key]
                modified_template_items[main_prompt_key] = original_prompt + "\n" + additional_context
                self.logger.debug(f"已将聚合上下文追加到 '{main_prompt_key}'。")

            # 4. 使用修改后的模板项构建最终结构
            final_template_info_value = {"template_items": modified_template_items}
        # else: # 不需要模板或模板项为空时，final_template_info_value 保持 None

        # --- Additional Config ---
        additional_config = cfg.get("additional_config", {})
        additional_config["source"] = "console_input_plugin"
        additional_config["sender_name"] = user_info.user_nickname
        additional_config["maimcore_reply_probability_gain"] = 1

        # --- Base Message Info ---
        message_info = BaseMessageInfo(
            platform=self.core.platform,
            # Consider casting time to int for consistency, but optional for now
            message_id=f"console_{int(timestamp * 1000)}_{hash(text) % 10000}",
            time=timestamp,
            user_info=user_info,
            group_info=group_info,
            # 使用可能已修改的 template_info
            template_info=final_template_info_value,
            format_info=format_info,
            additional_config=additional_config,
        )

        # --- Message Segment ---
        # Segment type is usually fixed for console input
        message_segment = Seg(type="text", data=text)

        # --- Final MessageBase ---
        return MessageBase(message_info=message_info, message_segment=message_segment, raw_message=text)


# --- Plugin Entry Point ---
plugin_entrypoint = ConsoleInputPlugin
