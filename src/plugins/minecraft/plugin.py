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
        self._maicore_response_future: Optional[asyncio.Future] = None

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
        # 如果需要路径信息，可以使用 websocket.path
        path = getattr(websocket, "path", "/")

        # 简单处理：新的连接会覆盖旧的，或者可以拒绝新连接如果已有活动连接
        if self._active_minecraft_client_ws and not self._active_minecraft_client_ws.closed:
            self.logger.warning(
                f"新的 Minecraft 客户端连接自 {websocket.remote_address}，但已有活动连接。将关闭旧连接。"
            )
            # await self._active_minecraft_client_ws.close(code=1000, reason="被新连接取代") # 可选：通知旧客户端

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

                    # 将整个从 Minecraft 收到的 JSON（已解析为 dict）转换为字符串，并添加提示前缀
                    # MaiCore 将收到类似："请以JSON...：{\"step\": ..., \"observations\": ..., ...}"
                    prompted_message_content = f"{self.json_prompt_prefix}{json.dumps(data_from_minecraft)}"

                    # --- 构建 MessageBase ---
                    current_time = int(time.time())
                    message_id = f"mc_{self.server_port}_{current_time}_{hash(prompted_message_content + str(self.user_id)) % 10000}"

                    user_info = UserInfo(
                        platform=self.core.platform, user_id=str(self.user_id), user_nickname=self.nickname
                    )

                    group_info_obj: Optional[GroupInfo] = None
                    if self.group_id_str:  # 使用 self.group_id_str
                        try:
                            parsed_group_id = int(self.group_id_str)
                            group_info_obj = GroupInfo(
                                platform=self.core.platform,
                                group_id=parsed_group_id,
                                # group_name 可以从配置添加
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

                    # 创建一个 Future 来等待 MaiCore 的响应
                    self._maicore_response_future = asyncio.Future()

                    await self.core.send_to_maicore(msg_to_maicore)
                    self.logger.info(
                        f"已将 Minecraft 感知信息 (low_level_action_enabled={self._last_low_level_action_enabled}) 发送给 MaiCore。等待响应..."
                    )

                    # 等待 MaiCore 的响应通过 handle_maicore_response 设置 Future 结果
                    maicore_response_content = await asyncio.wait_for(
                        self._maicore_response_future, timeout=60.0
                    )  # 添加超时

                    # MaiCore 应返回一个 JSON 字符串，该字符串已根据 low_level_action_enabled 标志调整了结构
                    # 例如，如果 low_level_action_enabled=false, MaiCore 返回 {"action_type_name": "NEW", "code": "..."}
                    # 如果 low_level_action_enabled=true, MaiCore 返回 {"values": [0,0,...]}

                    # 我们直接将 MaiCore 返回的 JSON 字符串发送给 Minecraft 客户端
                    # (假设MaiCore已正确处理结构)
                    await websocket.send(maicore_response_content)
                    self.logger.info(
                        f"已将 MaiCore 的响应发送给 Minecraft 客户端 {websocket.remote_address}: {maicore_response_content[:100]}..."
                    )

                except json.JSONDecodeError as e:
                    self.logger.exception(f"解析来自 Minecraft 客户端的 JSON 失败: {e}. 原始消息: {message_str[:200]}")
                    await websocket.send(json.dumps({"error": "Invalid JSON received", "details": str(e)}))
                except websockets.ConnectionClosed:
                    self.logger.info(f"与 Minecraft 客户端 {websocket.remote_address} 的连接已关闭。")
                    break  # 退出此客户端的消息循环
                except asyncio.TimeoutError:
                    self.logger.warning(f"等待 MaiCore 对 Minecraft 客户端 {websocket.remote_address} 请求的响应超时。")
                    await websocket.send(json.dumps({"error": "Timeout waiting for MaiCore response"}))
                except Exception as e:
                    self.logger.exception(
                        f"处理 Minecraft 客户端 {websocket.remote_address} 消息时发生错误: {e}", exc_info=True
                    )
                    try:
                        await websocket.send(json.dumps({"error": "Internal server error", "details": str(e)}))
                    except websockets.ConnectionClosed:
                        pass  # 客户端可能已断开
                    break  # 发生错误，终止此客户端的处理
        finally:
            self.logger.info(f"Minecraft 客户端 {websocket.remote_address} 断开连接。")
            if self._active_minecraft_client_ws == websocket:
                self._active_minecraft_client_ws = None
                if self._maicore_response_future and not self._maicore_response_future.done():  # 清理 Future
                    self._maicore_response_future.cancel()
                self._maicore_response_future = None
                # self._last_low_level_action_enabled 状态会随下一个消息被覆盖，无需特意清理

    async def handle_maicore_response(self, message: MessageBase):
        """处理从 MaiCore 返回的文本消息。"""
        content = message.get_plaintext_content().strip()
        self.logger.debug(f"从 MaiCore 收到响应内容: {content[:200]}...")

        # 检查是否有等待此响应的 Future
        if self._maicore_response_future and not self._maicore_response_future.done():
            # 假设 MaiCore 返回的 content 就是可以直接发送给 Minecraft 的 JSON 字符串
            # MaiCore 需要根据其收到的 low_level_action_enabled 标志来决定返回的 JSON 结构
            try:
                # 尝试解析以确认是有效的 JSON，但实际发送的是原始字符串
                json.loads(content)
                self._maicore_response_future.set_result(content)
                self.logger.info("MaiCore 响应已转发给等待的 Minecraft 客户端处理程序。")
            except json.JSONDecodeError:
                error_msg = f"MaiCore 返回的响应不是有效的 JSON: {content[:200]}"
                self.logger.error(error_msg)
                self._maicore_response_future.set_exception(ValueError(error_msg))
            except Exception as e:
                self.logger.error(f"设置 MaiCore 响应 Future 时发生错误: {e}", exc_info=True)
                if not self._maicore_response_future.done():  # 以防万一在 set_exception 之前 Future 状态改变
                    self._maicore_response_future.set_exception(e)
        else:
            # 如果没有活动的 Minecraft 客户端或 Future，或者 Future 已完成/不存在，则记录
            relevant_future_info = (
                "不存在或已完成"
                if not self._maicore_response_future
                else f"状态: done={self._maicore_response_future.done()}, cancelled={self._maicore_response_future.cancelled()}"
            )
            self.logger.warning(
                f"收到 MaiCore 响应，但没有匹配的 Minecraft 客户端 Future 等待它 (Future {relevant_future_info}): {content[:100]}..."
            )
            # 可以考虑将这类消息存入一个队列或丢弃

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

        if self._maicore_response_future and not self._maicore_response_future.done():
            self._maicore_response_future.cancel()

        self.logger.info("Minecraft 插件清理完毕。")


# --- Plugin Entry Point ---
plugin_entrypoint = MinecraftPlugin
