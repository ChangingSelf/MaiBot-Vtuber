import asyncio
import json  # 用于解析和构建 JSON
import websockets  # 请确保已安装此依赖: pip install websockets
from typing import Any, Dict, Optional
import time  # 新增导入
import os
import tomllib

from src.core.plugin_manager import BasePlugin
from src.core.amaidesu_core import AmaidesuCore
from maim_message import MessageBase, UserInfo, GroupInfo, FormatInfo, BaseMessageInfo, Seg

from src.utils.logger import get_logger

logger = get_logger("MinecraftPlugin")


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
                    logger.error("toml package needed for Python < 3.11.")
                    return {}
                except FileNotFoundError:
                    logger.warning(f"Config file not found: {config_path}")
                    return {}
    except Exception as e:
        logger.error(f"Error loading config: {config_path}: {e}", exc_info=True)
        return {}


class MinecraftPlugin(BasePlugin):
    _is_amaidesu_plugin: bool = True

    def __init__(self, core: AmaidesuCore, plugin_config: Dict[str, Any]):
        super().__init__(core, plugin_config)

        self.plugin_config = load_plugin_config()

        self.server_host: str = self.plugin_config.get("server_host", "0.0.0.0")
        self.server_port: int = self.plugin_config.get("server_port", 8766)

        self.user_id: str = self.plugin_config.get("user_id", "minecraft_bot")
        self.group_id_str: Optional[str] = self.plugin_config.get("group_id")
        self.nickname: str = self.plugin_config.get("nickname", "Minecraft Observer")
        self.json_prompt_prefix: str = self.plugin_config.get(
            "json_prompt_prefix", "请以JSON格式返回Minecraft中的动作指令："
        )

        self._server_task: Optional[asyncio.Task] = None
        self._server: Optional[websockets.WebSocketServer] = None  # 保存服务器对象以便关闭

        # 用于存储当前活动客户端的 WebSocket 连接和其 low_level_action_enabled 状态
        # 简化假设：一次处理一个 Minecraft 客户端的请求-响应周期
        self._active_minecraft_client_ws: Optional[websockets.WebSocketServerProtocol] = None
        self._last_low_level_action_enabled: bool = False

    async def setup(self):
        await super().setup()
        self.core.register_websocket_handler("text", self.handle_maicore_response)

        self.logger.info(f"Minecraft 插件已加载，将启动 WebSocket 服务器于 ws://{self.server_host}:{self.server_port}")
        self._server_task = asyncio.create_task(self.start_minecraft_server())

    async def start_minecraft_server(self):
        """启动 WebSocket 服务器以监听来自 Minecraft 客户端的连接。"""
        try:
            self._server = await websockets.serve(self.handle_minecraft_client, self.server_host, self.server_port)
            self.logger.info(f"Minecraft WebSocket 服务器正在监听 ws://{self.server_host}:{self.server_port}")
            await self._server.wait_closed()  # 服务器将一直运行直到被关闭
        except OSError as e:
            self.logger.error(f"启动 Minecraft WebSocket 服务器失败: {e} (端口可能已被占用或地址无效)")
        except asyncio.CancelledError:
            self.logger.info("Minecraft WebSocket 服务器任务被取消。")
        except Exception as e:
            self.logger.error(f"Minecraft WebSocket 服务器意外终止: {e}", exc_info=True)
        finally:
            if self._server:
                self._server.close()
                await self._server.wait_closed()
            self.logger.info("Minecraft WebSocket 服务器已停止。")

    async def handle_minecraft_client(self, websocket: websockets.WebSocketServerProtocol):
        """处理来自单个 Minecraft 客户端的连接和消息。"""
        path = getattr(websocket, "path", "/")

        if self._active_minecraft_client_ws and not self._active_minecraft_client_ws.closed:
            self.logger.warning(
                f"新的 Minecraft 客户端连接自 {websocket.remote_address}，但已有活动连接。将关闭旧连接。"
            )

        self._active_minecraft_client_ws = websocket
        self.logger.info(f"Minecraft 客户端 {websocket.remote_address} 已连接。路径: {path}")

        try:
            async for message_str in websocket:
                try:
                    self.logger.debug(
                        f"从 Minecraft 客户端 {websocket.remote_address} 收到原始消息: {message_str[:200]}..."
                    )
                    data_from_minecraft = json.loads(message_str)

                    # 存储 low_level_action_enabled 状态
                    self._last_low_level_action_enabled = data_from_minecraft.get("low_level_action_enabled", False)
                    self.logger.debug(f"Minecraft low_level_action_enabled: {self._last_low_level_action_enabled}")

                    # 将整个从 Minecraft 收到的 JSON 转换为字符串，并添加提示前缀
                    prompted_message_content = f"{self.json_prompt_prefix}{json.dumps(data_from_minecraft)}"

                    # --- 构建 MessageBase ---
                    current_time = int(time.time())
                    message_id = f"mc_{self.server_port}_{current_time}_{hash(prompted_message_content + str(self.user_id)) % 10000}"

                    user_info = UserInfo(
                        platform=self.core.platform, user_id=str(self.user_id), user_nickname=self.nickname
                    )

                    group_info_obj = None
                    if self.group_id_str:
                        try:
                            parsed_group_id = int(self.group_id_str)
                            group_info_obj = GroupInfo(
                                platform=self.core.platform,
                                group_id=parsed_group_id,
                            )
                        except ValueError:
                            self.logger.warning(
                                f"配置的 group_id '{self.group_id_str}' 不是有效的整数。将忽略 GroupInfo。"
                            )

                    format_info = FormatInfo(content_format="text", accept_format="text")

                    additional_cfg = {
                        "source_plugin": "minecraft",
                        "minecraft_client_id": str(websocket.remote_address),
                        "low_level_action_enabled": self._last_low_level_action_enabled,
                    }

                    message_info = BaseMessageInfo(
                        platform=self.core.platform,
                        message_id=message_id,
                        time=current_time,
                        user_info=user_info,
                        group_info=group_info_obj,
                        format_info=format_info,
                        additional_config=additional_cfg,
                        template_info=None,
                    )

                    message_segment = Seg(type="text", data=prompted_message_content)

                    msg_to_maicore = MessageBase(
                        message_info=message_info, message_segment=message_segment, raw_message=prompted_message_content
                    )
                    # --- MessageBase 构建完毕 ---

                    # 直接发送给MaiCore，不等待响应
                    await self.core.send_to_maicore(msg_to_maicore)
                    self.logger.info(
                        f"已将 Minecraft 感知信息 (low_level_action_enabled={self._last_low_level_action_enabled}) 发送给 MaiCore。"
                    )

                except json.JSONDecodeError as e:
                    self.logger.exception(f"解析来自 Minecraft 客户端的 JSON 失败: {e}. 原始消息: {message_str[:200]}")
                    await websocket.send(json.dumps({"error": "Invalid JSON received", "details": str(e)}))
                except websockets.ConnectionClosed:
                    self.logger.info(f"与 Minecraft 客户端 {websocket.remote_address} 的连接已关闭。")
                    break
                except Exception as e:
                    self.logger.exception(
                        f"处理 Minecraft 客户端 {websocket.remote_address} 消息时发生错误: {e}", exc_info=True
                    )
                    try:
                        await websocket.send(json.dumps({"error": "Internal server error", "details": str(e)}))
                    except websockets.ConnectionClosed:
                        pass
                    break
        finally:
            self.logger.info(f"Minecraft 客户端 {websocket.remote_address} 断开连接。")
            if self._active_minecraft_client_ws == websocket:
                self._active_minecraft_client_ws = None

    async def handle_maicore_response(self, message: MessageBase):
        """处理从 MaiCore 返回的文本消息。"""
        if message.message_segment.type != "text":
            self.logger.warning(
                f"MaiCore 返回的消息不是文本消息: type='{message.message_segment.type}'. Expected 'text'. Discarding."
            )
            return

        content = message.message_segment.data.strip()
        self.logger.debug(f"从 MaiCore 收到响应内容准备转发: {content[:200]}...")

        active_ws = self._active_minecraft_client_ws
        can_send_to_ws = False

        if active_ws:
            client_addr = getattr(active_ws, "remote_address", "N/A")  # 获取地址用于日志
            self.logger.debug(
                f"MC_RESP_PING: active_ws object detected for {client_addr}. Type: {type(active_ws)}. Attempting ping."
            )
            try:
                # 发送 ping 并等待 pong。如果连接已关闭，这通常会引发 ConnectionClosed。
                # 添加一个合理的超时以防万一客户端不响应 pong 但连接未立即关闭。
                await asyncio.wait_for(active_ws.ping(), timeout=5.0)
                self.logger.debug(
                    f"MC_RESP_PING: Ping to {client_addr} successful (pong received or ping sent without error)."
                )
                can_send_to_ws = True
            except websockets.exceptions.ConnectionClosed as e_closed:
                self.logger.warning(f"MC_RESP_PING: Ping to {client_addr} failed. Connection closed: {e_closed}")
                # 确保清理掉无效的连接
                if self._active_minecraft_client_ws == active_ws:
                    self._active_minecraft_client_ws = None
            except asyncio.TimeoutError:
                self.logger.warning(
                    f"MC_RESP_PING: Ping to {client_addr} timed out after 5 seconds. Assuming connection is stale."
                )
                # 也可以选择关闭连接
                if self._active_minecraft_client_ws == active_ws:
                    await active_ws.close(code=1001, reason="Ping timeout")
                    self._active_minecraft_client_ws = None
            except Exception as e_ping:
                self.logger.error(f"MC_RESP_PING: Error during ping to {client_addr}: {e_ping}", exc_info=True)
        else:  # active_ws is None
            self.logger.warning("MC_RESP_PING: _active_minecraft_client_ws is None. Cannot send.")

        if can_send_to_ws and active_ws:  # 再次检查 active_ws 以防在 ping 过程中被设为 None
            # client_addr 已经从上面获取
            self.logger.info(f"尝试将响应 '{content[:50]}...' 转发给活跃的 Minecraft 客户端 {client_addr}.")
            try:
                try:
                    json.loads(content)  # 验证 MaiCore 的响应是否为有效的 JSON
                except json.JSONDecodeError as json_err:
                    error_msg = f"MaiCore 返回的内容不是有效的 JSON: {content[:200]}. Error: {json_err}"
                    self.logger.error(error_msg)
                    # 尝试向客户端发送错误，仍然需要检查连接是否在 ping 之后仍然存活
                    # （尽管 can_send_to_ws 为 True，但仍有可能在 ping 和此代码之间发生极小概率的关闭）
                    if active_ws:  # 再次检查 active_ws 是否仍被赋值
                        try:
                            await active_ws.send(
                                json.dumps({"error": "Received malformed data from core", "details": content[:200]})
                            )
                        except websockets.exceptions.ConnectionClosed:
                            self.logger.warning(f"发送 JSON 解析错误通知给 {client_addr} 失败：连接已关闭。")
                    return

                await active_ws.send(content)
                self.logger.info(f"成功将 MaiCore 响应转发给 Minecraft 客户端 {client_addr}: {content[:100]}...")

            except websockets.exceptions.ConnectionClosed:
                self.logger.warning(
                    f"转发响应给 Minecraft 客户端 {client_addr} 失败：连接已关闭 (ConnectionClosed exception during send)。"
                )
                if self._active_minecraft_client_ws == active_ws:
                    self._active_minecraft_client_ws = None
            except Exception as e_send:
                self.logger.error(
                    f"转发 MaiCore 响应给 Minecraft 客户端 {client_addr} 时发生未知错误: {e_send}", exc_info=True
                )
                # 尝试发送通用错误，同样需要检查连接
                if active_ws:
                    try:
                        await active_ws.send(json.dumps({"error": "Internal server error during response forwarding"}))
                    except websockets.exceptions.ConnectionClosed:
                        self.logger.warning(f"发送内部错误通知给 {client_addr} 失败：连接已关闭。")
                    except Exception as e_send_error_final:
                        self.logger.error(
                            f"发送错误消息给 Minecraft 客户端 {client_addr} 时再次失败: {e_send_error_final}",
                            exc_info=True,
                        )

        elif active_ws:  # active_ws 不为 None, 但 can_send_to_ws 是 False (例如 ping 失败)
            self.logger.warning(
                f"收到 MaiCore 响应，但与 Minecraft 客户端 (type: {type(active_ws)}, address: {getattr(active_ws, 'remote_address', 'N/A')}) 的连接在 ping 测试中失败或超时。丢弃消息: {content[:100]}..."
            )
        # 如果 active_ws 最初就是 None, 它已经在 MC_RESP_PING 日志中记录过了。

    async def cleanup(self):
        self.logger.info("正在清理 Minecraft 插件...")
        if self._server_task:
            self._server_task.cancel()
            try:
                await self._server_task
            except asyncio.CancelledError:
                self.logger.info("Minecraft 服务器任务已成功取消。")
            except Exception as e:  # pylint: disable=broad-except
                self.logger.error(f"等待 Minecraft 服务器任务结束时发生错误: {e}", exc_info=True)

        if self._server:  # Websockets.serve 返回的服务器对象
            self._server.close()
            try:
                await self._server.wait_closed()
                self.logger.info("Minecraft WebSocket 服务器已关闭。")
            except Exception as e:  # pylint: disable=broad-except
                self.logger.error(f"关闭 Minecraft WebSocket 服务器时出错: {e}", exc_info=True)

        if self._active_minecraft_client_ws and not self._active_minecraft_client_ws.closed:
            try:
                await self._active_minecraft_client_ws.close(code=1001, reason="服务器关闭")
                self.logger.info("已关闭活动的 Minecraft 客户端连接。")
            except Exception as e:  # pylint: disable=broad-except
                self.logger.error(f"关闭活动 Minecraft 客户端连接时出错: {e}", exc_info=True)

        self.logger.info("Minecraft 插件清理完毕。")


# --- Plugin Entry Point ---
plugin_entrypoint = MinecraftPlugin
