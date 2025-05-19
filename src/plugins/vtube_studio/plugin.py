# src/plugins/vtube_studio/plugin.py

import asyncio
import tomllib
import os
from typing import Any, Dict, Optional
import re

from maim_message.message_base import MessageBase

import pyvts

# 从 core 导入基类和核心类
from src.core.plugin_manager import BasePlugin
from src.core.amaidesu_core import AmaidesuCore


# --- Helper Function ---


# --- Plugin Class ---
class VTubeStudioPlugin(BasePlugin):
    """
    Connects to VTube Studio, allows triggering hotkeys,
    and registers available actions to PromptContext.
    """

    def __init__(self, core: AmaidesuCore, plugin_config: Dict[str, Any]):
        super().__init__(core, plugin_config)
        self.config = self.plugin_config
        self.enabled = self.config.get("enabled", True)

        # --- pyvts 实例 ---
        self.vts: Optional[pyvts.vts] = None
        self._connection_task: Optional[asyncio.Task] = None
        self._is_connected_and_authenticated = False
        self._auth_token = None
        self._auth_task = None
        self._stop_event = asyncio.Event()

        # --- 依赖检查 ---
        if pyvts is None:
            self.logger.error(
                "pyvts library not found. Please install it (`pip install pyvts`). VTubeStudioPlugin disabled."
            )
            self.enabled = False
            return

        if not self.enabled:
            self.logger.warning("VTubeStudioPlugin is disabled in the configuration.")
            return

        # --- 加载配置 ---
        self.plugin_name = self.config.get("plugin_name", "Amaidesu_VTS_Connector")
        self.developer = self.config.get("developer", "Amaidesu User")
        self.token_path = self.config.get("authentication_token_path", "./vts_token.txt")
        self.vts_host = self.config.get("vts_host")  # None means use default
        self.vts_port = self.config.get("vts_port")  # None means use default

        # Prompt Context 相关配置
        self.register_hotkeys = self.config.get("register_hotkeys_context", True)
        self.hotkeys_priority = self.config.get("hotkeys_context_priority", 50)
        self.hotkeys_prefix = self.config.get("hotkeys_context_prefix", "你可以触发以下模型热键：")
        self.hotkey_format = self.config.get("hotkey_format", "'%s' (ID: %s)")
        self.hotkeys_separator = self.config.get("hotkeys_separator", ", ")

        # --- 初始化 pyvts ---
        plugin_info = {
            "plugin_name": self.plugin_name,
            "developer": self.developer,
            "authentication_token_path": self.token_path,
        }
        # 处理 host, port, name, version，确保字典包含它们，使用默认值填充
        vts_api_info = {
            "host": self.config.get("vts_host", "localhost"),  # Use config value or default
            "port": self.config.get("vts_port", 8001),  # Use config value or default
            "name": self.config.get("vts_api_name", "VTubeStudioPublicAPI"),  # Use config value or default
            "version": self.config.get("vts_api_version", "1.0"),  # Use config value or default
        }

        try:
            # Pass the guaranteed populated vts_api_info dict
            self.vts = pyvts.vts(plugin_info=plugin_info, vts_api_info=vts_api_info)
            self.logger.info("pyvts instance created.")
        except Exception as e:
            self.logger.error(f"Failed to initialize pyvts: {e}", exc_info=True)
            self.enabled = False

    async def setup(self):
        await super().setup()
        if not self.enabled or not self.vts:
            self.logger.warning("VTubeStudioPlugin setup skipped (disabled or failed init).")
            return
        # 注册处理函数，监听所有 WebSocket 消息
        self.core.register_websocket_handler("*", self.handle_maicore_message)
        self.logger.info("VTube Studio 插件已设置，监听所有 MaiCore WebSocket 消息。")

        # 启动连接和认证的后台任务
        self._connection_task = asyncio.create_task(self._connect_and_auth(), name="VTS_ConnectAuth")
        self.logger.info("VTube Studio connection and authentication task started.")

        # --- Register self as a service for triggering actions ---
        self.core.register_service("vts_control", self)
        self.logger.info("Registered 'vts_control' service.")

    async def _connect_and_auth(self):
        """Internal task to connect, authenticate, and register context."""
        if not self.vts:
            return
        try:
            self.logger.info("Attempting to connect to VTube Studio...")
            await self.vts.connect()
            self.logger.info("Connected to VTube Studio WebSocket.")

            # --- 调整顺序：总是先处理 token ---
            self.logger.info("Requesting authentication token (will prompt in VTS if needed)...")
            # 这会请求新token或检查/加载现有token
            await self.vts.request_authenticate_token()
            # self._auth_token = self.vts.token # 会报错
            self.logger.info("Token request process completed.")

            # --- 然后再进行认证 ---
            self.logger.info("Attempting to authenticate using token...")
            authenticated = await self.vts.request_authenticate()

            if authenticated:
                self.logger.info("Successfully authenticated with VTube Studio API.")
                self._is_connected_and_authenticated = True
                # --- 认证成功后，注册 Prompt 上下文 ---
                if self.register_hotkeys:
                    await self._register_hotkeys_context()
                # --- 在这里可以添加注册其他上下文的逻辑 (如表情) ---
                # if self.register_expressions: ...

                # 测试微笑
                await self.smile(0)

                # 测试闭眼
                # await asyncio.sleep(5)
                await self.close_eyes()

            else:
                # 如果 token 流程没问题，这里应该不会失败，但还是处理一下
                self.logger.error("Authentication failed even after token request process.")
                self._is_connected_and_authenticated = False

        except ConnectionRefusedError:
            self.logger.error("Connection to VTube Studio refused. Is VTS running and the API enabled?")
        except asyncio.TimeoutError:
            self.logger.error("Connection or authentication to VTube Studio timed out.")
        except Exception as e:
            # 加一个特定的 KeyErorr 检查，以防万一
            if isinstance(e, KeyError) and "authenticated" in str(e):
                self.logger.error(
                    f"KeyError accessing 'authenticated' during authentication. Unexpected VTS response? {e}",
                    exc_info=True,
                )
            else:
                self.logger.error(f"Error during VTube Studio connection/authentication: {e}", exc_info=True)
            self._is_connected_and_authenticated = False  # 保证出错时状态为 False
        finally:
            # 如果认证失败，确保状态正确
            if not self._is_connected_and_authenticated:
                self.logger.warning("VTS Connection/Authentication failed.")
                # 可以在这里尝试关闭连接，防止 pyvts 内部状态问题
                if self.vts and self.vts.ws and not self.vts.ws.closed:
                    await self.vts.close()
                    self.logger.debug("Closed VTS connection due to auth failure.")

    async def get_hotkey_list(self) -> Optional[list[Dict[str, Any]]]:
        """Requests the list of available hotkeys from VTube Studio.

        Returns:
            A list of hotkey dictionaries (containing 'name', 'hotkeyID', etc.)
            if successful, None otherwise.
        """
        if not self._is_connected_and_authenticated or not self.vts:
            self.logger.warning("Cannot get hotkey list: Not connected or authenticated.")
            return None

        try:
            self.logger.warning("Requesting VTube Studio hotkey list...")
            response = await self.vts.request(self.vts.vts_request.requestHotKeyList())

            if response and response.get("data") and "availableHotkeys" in response["data"]:
                hotkeys = response["data"]["availableHotkeys"]
                self.logger.warning(f"Received {len(hotkeys)} hotkeys from VTS.")
                return hotkeys
            else:
                self.logger.warning(f"Could not get hotkey list from VTS or invalid response format: {response}")
                return None
        except Exception as e:
            self.logger.error(f"Error requesting hotkey list from VTS: {e}", exc_info=True)
            return None

    async def _register_hotkeys_context(self):
        """获取 VTS 热键并将其使用说明注册到 PromptContextPlugin。"""
        prompt_ctx_service = self.core.get_service("prompt_context")
        if not prompt_ctx_service:
            self.logger.warning("未找到 PromptContext 服务。无法注册热键。")
            return

        hotkeys = None  # Initialize hotkeys variable
        try:
            # Call the new method to get the hotkey list
            hotkeys = await self.get_hotkey_list()

            instructional_text = "对于每一次回复，请在回复文本末尾添加指令标记来表达你现在的情感。对于日常聊天，进行情感与动作的表现是被鼓励的，通过热键名称可以看出该热键对应的情感。格式为 `%{vts_trigger_hotkey:热键名称}%`，例如 `%{vts_trigger_hotkey:微笑}%`。"
            hotkey_list_text = ""

            if hotkeys is not None:  # Check if get_hotkey_list was successful
                if hotkeys:  # Check if the list is not empty
                    formatted_hotkeys = [
                        hotkey.get("name", "Unknown Hotkey") for hotkey in hotkeys
                    ]  # Safer access with .get()
                    hotkey_list_text = "可用的热键有：\n- " + "\n- ".join(formatted_hotkeys)
                else:
                    hotkey_list_text = "当前模型没有可用的热键。"
            else:
                # get_hotkey_list already logged the error
                hotkey_list_text = "无法获取当前可用的热键信息。"

            # 组合最终的上下文信息
            context_info = instructional_text + "\n" + hotkey_list_text

            # 注册或更新上下文
            provider_name = "vts_hotkeys_instruction"  # 使用新名称
            prompt_ctx_service.register_context_provider(
                provider_name=provider_name,
                context_info=context_info,
                priority=self.hotkeys_priority,
                tags=["vts", "action", "hotkey", "instruction"],  # 添加 instruction 标签
            )
            self.logger.info(f"成功注册/更新 '{provider_name}' 上下文。")
            # 确保移除旧的或错误的注册（如果之前用过 vts_hotkeys）
            prompt_ctx_service.unregister_context_provider("vts_hotkeys")
            prompt_ctx_service.unregister_context_provider("vts_hotkeys_error")

        except Exception as e:
            self.logger.error(f"获取或注册热键说明时出错: {e}", exc_info=True)
            # 出错时注册错误信息
            if prompt_ctx_service:
                prompt_ctx_service.register_context_provider(
                    provider_name="vts_hotkeys_error",
                    context_info="系统提示：暂时无法获取 VTube Studio 的可用动作信息。",
                    priority=self.hotkeys_priority,
                )
                # 同样，确保移除其他可能的注册
                prompt_ctx_service.unregister_context_provider("vts_hotkeys")
                prompt_ctx_service.unregister_context_provider("vts_hotkeys_instruction")

    async def cleanup(self):
        self.logger.info("Cleaning up VTubeStudioPlugin...")
        # 停止后台连接任务
        if self._connection_task and not self._connection_task.done():
            self.logger.debug("Cancelling VTS connection task...")
            self._connection_task.cancel()
            try:
                await asyncio.wait_for(self._connection_task, timeout=2.0)
            except asyncio.TimeoutError:
                self.logger.warning("VTS connection task did not finish cancelling in time.")
            except asyncio.CancelledError:
                pass  # Expected

        # 关闭 pyvts 连接
        if self.vts and self.vts.ws and not self.vts.ws.closed:
            try:
                self.logger.info("Closing connection to VTube Studio...")
                await self.vts.close()
                self.logger.info("VTube Studio connection closed.")
            except Exception as e:
                self.logger.error(f"Error closing VTube Studio connection: {e}", exc_info=True)

        # (可选) 取消注册服务，如果 Core 支持的话
        # self.core.unregister_service("vts_control")

        # (可选) 取消注册 Prompt 上下文，如果需要的话
        prompt_ctx_service = self.core.get_service("prompt_context")
        if prompt_ctx_service:
            prompt_ctx_service.unregister_context_provider("vts_hotkeys")
            # prompt_ctx_service.unregister_context_provider("vts_hotkeys_error") # 如果注册了错误信息
            self.logger.debug("Unregistered VTS context providers.")

        self._is_connected_and_authenticated = False
        await super().cleanup()

    # --- Public method for triggering hotkey (to be called by CommandProcessor) ---
    async def handle_maicore_message(self, message: MessageBase):
        """处理从 MaiCore 收到的消息，如果是文本类型，则进行处理，触发热键。"""
        # 检查消息段是否存在且类型为 'text'
        if message.message_segment and message.message_segment.type == "text":
            original_text = message.message_segment.data
            if not isinstance(original_text, str) or not original_text.strip():
                self.logger.debug("收到非字符串或空文本消息段，跳过")
                return

            original_text = original_text.strip()
            self.logger.info(f"收到文本消息: '{original_text[:50]}...'")

            # 使用正则表达式匹配热键标记
            hotkey_pattern = r"%\{vts_trigger_hotkey:([^}]+)\}%"
            hotkey_matches = re.findall(hotkey_pattern, original_text)

            # 触发所有匹配到的热键
            for hotkey_name in hotkey_matches:
                self.logger.info(f"尝试触发热键: {hotkey_name}")
                await self.trigger_hotkey(hotkey_name)

            # 移除所有热键标记，得到最终文本
            final_text = re.sub(hotkey_pattern, "", original_text).strip()

            # 如果最终文本不为空，可以在这里添加其他处理逻辑
            if final_text:
                self.logger.debug(f"处理后的文本: '{final_text[:50]}...'")

    async def trigger_hotkey(self, hotkey_id: str) -> bool:
        """
        Triggers a hotkey in VTube Studio by its ID.

        Args:
            hotkey_id: The ID of the hotkey to trigger.Hotkey name or unique id of hotkey to execute, can be obtained via VTSRequest.requestHotKeyList()

        Returns:
            True if the request was sent successfully, False otherwise.
        """
        if not self._is_connected_and_authenticated or not self.vts:
            self.logger.warning(f"Cannot trigger hotkey '{hotkey_id}': Not connected or authenticated.")
            return False

        self.logger.info(f"Attempting to trigger hotkey with ID: {hotkey_id}")
        try:
            request_msg = self.vts.vts_request.requestTriggerHotKey(hotkeyID=hotkey_id)
            response = await self.vts.request(request_msg)
            # Check response for success/error if needed - pyvts might raise exceptions on API errors
            if response and response.get("messageType") == "APIError":
                error_data = response.get("data", {})
                self.logger.error(
                    f"API Error triggering hotkey '{hotkey_id}': ID {error_data.get('errorID')}, Msg: {error_data.get('message')}"
                )
                return False
            elif response and response.get("messageType") == "HotkeyTriggerResponse":
                self.logger.info(f"Successfully sent trigger request for hotkey: {hotkey_id}")
                return True
            else:
                self.logger.warning(
                    f"Unexpected response type when triggering hotkey '{hotkey_id}': {response.get('messageType') if response else 'No Response'}"
                )
                return False

        except Exception as e:
            self.logger.error(f"Error sending trigger hotkey request for '{hotkey_id}': {e}", exc_info=True)
            return False

    async def get_parameter_value(self, parameter_name: str) -> bool:
        """
        获取 VTS 参数值
        parameter : str
            参数名称
        """
        if not self._is_connected_and_authenticated or not self.vts:
            self.logger.warning(f"无法获取 '{parameter_name}' 参数值: 未连接或未认证。")
            return False

        try:
            response = await self.vts.request(self.vts.vts_request.requestParameterValue(parameter_name))
            if response and response.get("messageType") == "ParameterValueResponse":
                self.logger.info(f"成功获取 '{parameter_name}' 参数值为 {response}")
                return response.get("data", {}).get("value", 0)
            else:
                self.logger.warning(f"获取 '{parameter_name}' 参数值失败: {response}")
                return False
        except Exception as e:
            self.logger.error(f"获取 '{parameter_name}' 参数值失败: {e}", exc_info=True)
            return False

    async def set_parameter_value(self, parameter_name: str, value: float, weight: float = 1) -> bool:
        """
        设置 VTS 参数值
        parameter : str
            参数名称
        value : float
            数据值，范围为 [-1000000, 1000000]
        weight : float, optional
            可以混合你的值与 VTS 面部跟踪参数，从 0 到 1,
        """
        if not self._is_connected_and_authenticated or not self.vts:
            self.logger.warning(f"无法设置 '{parameter_name}' 参数值: 未连接或未认证。")
            return False

        try:
            response = await self.vts.request(
                self.vts.vts_request.requestSetParameterValue(parameter_name, value, weight)
            )
            if response and response.get("messageType") == "InjectParameterDataResponse":
                self.logger.info(f"成功设置 '{parameter_name}' 参数值为 {value}")
                return True
            else:
                self.logger.warning(f"设置 '{parameter_name}' 参数值失败: {response}")
                return False
        except Exception as e:
            self.logger.error(f"设置 '{parameter_name}' 参数值失败: {e}", exc_info=True)
            return False

    async def close_eyes(self) -> bool:
        """
        闭眼
        """
        # 并行闭上左右眼好像会有问题
        # return await asyncio.gather(
        #     self.set_parameter_value("EyeOpenLeft", 0), self.set_parameter_value("EyeOpenRight", 0)
        # )
        await self.set_parameter_value("EyeOpenLeft", 0)
        await self.set_parameter_value("EyeOpenRight", 0)

    async def open_eyes(self) -> bool:
        """
        睁眼
        """
        # 并行睁开左右眼
        # return await asyncio.gather(
        #     self.set_parameter_value("EyeOpenLeft", 1), self.set_parameter_value("EyeOpenRight", 1)
        # )
        await self.set_parameter_value("EyeOpenLeft", 1)
        await self.set_parameter_value("EyeOpenRight", 1)

    async def smile(self, value: float = 1) -> bool:
        """
        微笑控制,1 为嘻嘻,0 为不嘻嘻
        """
        return await self.set_parameter_value("MouthSmile", value)

    async def load_item(
        self,
        file_name: str = "filename.png",
        position_x: float = 0,
        position_y: float = 0.5,
        size: float = 0.33,
        rotation: float = 90,
        fade_time: float = 0.5,
        order: int = 4,
        fail_if_order_taken: bool = False,
        smoothing: float = 0,
        censored: bool = False,
        flipped: bool = False,
        locked: bool = False,
        unload_when_plugin_disconnects: bool = True,
        custom_data_base64: str = "",
        custom_data_ask_user_first: bool = False,
        custom_data_skip_asking_user_if_whitelisted: bool = False,
        custom_data_ask_timer: int = -1,
    ) -> Optional[str]:
        """
        加载挂件
        """
        data = {
            "fileName": file_name,  # 就算用的是base64，但也要指定文件名
            "positionX": position_x,  # 屏幕范围为 [-1, 1]，0 为屏幕中心，合法范围为[-1000, 1000]
            "positionY": position_y,  # 屏幕范围为 [-1, 1]，0 为屏幕中心，合法范围为[-1000, 1000]
            "size": size,  # 范围为 [0, 1]
            "rotation": rotation,  # 范围为 [0, 360]
            "fadeTime": fade_time,  # 范围为 [0, 2]
            "order": order,  # 范围为 [0, 100]
            "failIfOrderTaken": fail_if_order_taken,
            "smoothing": smoothing,
            "censored": censored,
            "flipped": flipped,
            "locked": locked,
            "unloadWhenPluginDisconnects": unload_when_plugin_disconnects,
            "customDataBase64": custom_data_base64,
            "customDataAskUserFirst": custom_data_ask_user_first,
            "customDataSkipAskingUserIfWhitelisted": custom_data_skip_asking_user_if_whitelisted,
            "customDataAskTimer": custom_data_ask_timer,
        }

        response = await self.vts.request(self.vts.vts_request.BaseRequest(message_type="ItemLoadRequest", data=data))
        if not response or response.get("messageType") != "ItemLoadResponse":
            self.logger.error(f"加载挂件失败: {response}")
            return None

        self.logger.info(f"成功加载挂件: {response}")
        return response.get("data", {}).get("instanceID", None)

    async def unload_item(
        self,
        item_instance_id_list: list[str] = [],
        file_name_list: list[str] = [],
        unload_all_in_scene: bool = False,
        unload_all_loaded_by_this_plugin: bool = False,
        allow_unloading_items_loaded_by_user_or_other_plugins: bool = True,
    ) -> bool:
        """
        卸载挂件
        """
        data = {
            "unloadAllInScene": unload_all_in_scene,
            "unloadAllLoadedByThisPlugin": unload_all_loaded_by_this_plugin,
            "allowUnloadingItemsLoadedByUserOrOtherPlugins": allow_unloading_items_loaded_by_user_or_other_plugins,
            "instanceIDs": item_instance_id_list,
            "fileNames": file_name_list,
        }

        response = await self.vts.request(self.vts.vts_request.BaseRequest(message_type="ItemUnloadRequest", data=data))
        if response and response.get("messageType") == "ItemUnloadResponse":
            self.logger.info(f"成功卸载挂件: {response}")
            return True
        else:
            self.logger.error(f"卸载挂件失败: {response}")
            return False

    # --- 未来可以添加处理 VTS 事件的方法 ---
    # async def handle_vts_event(self, event_data): ...

    # --- 未来可以添加触发热键的服务方法 ---
    # async def trigger_hotkey(self, hotkey_id: str) -> bool: ...
    # 并将 trigger_hotkey 注册为 Core 的服务


# --- Plugin Entry Point ---
plugin_entrypoint = VTubeStudioPlugin
