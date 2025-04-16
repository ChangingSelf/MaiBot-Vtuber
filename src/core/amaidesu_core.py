import asyncio
from typing import Callable, Dict, Any, Optional, Type

# 注意：需要安装 aiohttp
# pip install aiohttp
from aiohttp import web

from maim_message import Router, RouteConfig, TargetConfig, MessageBase
from src.utils.logger import logger


class AmaidesuCore:
    """
    Amaidesu 核心模块，负责与 MaiCore 的通信以及消息的分发。
    """

    def __init__(
        self,
        platform: str,
        maicore_host: str,
        maicore_port: int,
        http_host: Optional[str] = None,
        http_port: Optional[int] = None,
        http_callback_path: str = "/callback",
    ):
        """
        初始化 Amaidesu Core。

        Args:
            platform: 平台标识符 (例如 "amaidesu_default")。
            maicore_host: MaiCore WebSocket 服务器的主机地址。
            maicore_port: MaiCore WebSocket 服务器的端口。
            http_host: (可选) 监听 HTTP 回调的主机地址。如果为 None，则不启动 HTTP 服务器。
            http_port: (可选) 监听 HTTP 回调的端口。
            http_callback_path: (可选) 接收 HTTP 回调的路径。
        """
        # 初始化 AmaidesuCore 自己的 logger
        self.logger = logger
        self.logger.debug("AmaidesuCore 初始化开始")

        self.platform = platform
        self.ws_url = f"ws://{maicore_host}:{maicore_port}/ws"
        self._router: Optional[Router] = None
        self._message_handlers: Dict[
            str, list[Callable[[MessageBase], asyncio.Task]]
        ] = {}  # 按消息类型或其他标识符存储处理器
        self._http_request_handlers: Dict[str, list[Callable[[web.Request], asyncio.Task]]] = {}  # 用于 HTTP 请求处理
        self._services: Dict[str, Any] = {}  # 新增：用于存储已注册的服务
        self._is_connected = False
        self._connect_lock = asyncio.Lock()  # 防止并发连接

        # HTTP 服务器相关配置
        self._http_host = http_host
        self._http_port = http_port
        self._http_callback_path = http_callback_path
        self._http_runner: Optional[web.AppRunner] = None
        self._http_site: Optional[web.TCPSite] = None
        self._http_app: Optional[web.Application] = None

        self._ws_task: Optional[asyncio.Task] = None  # 添加用于存储 WebSocket 运行任务的属性
        self._monitor_task: Optional[asyncio.Task] = None  # 添加用于监控 ws_task 的任务

        self._setup_router()
        if self._http_host and self._http_port:
            self._setup_http_server()
        self.logger.debug("AmaidesuCore 初始化完成")

    def _setup_router(self):
        """配置 maim_message Router。"""
        route_config = RouteConfig(
            route_config={
                self.platform: TargetConfig(
                    url=self.ws_url,
                    token=None,  # 根据需要配置 Token
                )
            }
        )
        self._router = Router(route_config)
        # 注册内部处理函数，用于接收所有来自 MaiCore 的消息
        self._router.register_class_handler(self._handle_maicore_message)
        logger.info(f"Router 配置完成，目标 MaiCore: {self.ws_url}")

    def _setup_http_server(self):
        """配置 aiohttp 应用和路由。"""
        if not (self._http_host and self._http_port):
            return
        self._http_app = web.Application()
        # 注册统一的 HTTP 回调处理入口
        self._http_app.router.add_post(self._http_callback_path, self._handle_http_request)
        logger.info(f"HTTP 服务器配置完成，监听路径: {self._http_callback_path}")

    async def connect(self):
        """启动 WebSocket 连接后台任务和 HTTP 服务器（如果配置了）。"""
        async with self._connect_lock:
            if self._is_connected or self._ws_task:
                self.logger.warning("核心已连接或正在连接中，无需重复连接。")
                return
            if not self._router:
                self.logger.error("Router 未初始化，无法连接 WebSocket。")
                return

            connect_tasks = []
            http_server_task = None

            # 准备启动 WebSocket 连接任务
            self.logger.info(f"准备启动 MaiCore WebSocket 连接 ({self.ws_url})...")
            # 注意：这里不直接 await，而是创建任务
            self._ws_task = asyncio.create_task(self._run_websocket(), name="WebSocketRunTask")

            # 添加监控任务
            self._monitor_task = asyncio.create_task(self._monitor_ws_connection(), name="WebSocketMonitorTask")

            # 立即乐观地设置状态 (或等待一小段时间让连接有机会建立)
            # self._is_connected = True # 过于乐观，可能连接尚未成功
            # self.logger.info("WebSocket 连接任务已启动 (状态暂标记为连接中/成功)")
            # 更准确的状态应由 _monitor_ws_connection 或 Router 回调设置
            # 这里可以先不设置 _is_connected，等监控任务确认

            # 启动 HTTP 服务器 (如果配置了)
            if self._http_host and self._http_port:
                self.logger.info(f"正在启动 HTTP 服务器 ({self._http_host}:{self._http_port})...")
                http_server_task = asyncio.create_task(self._start_http_server_internal(), name="HttpServerStartTask")
                connect_tasks.append(http_server_task)

            # 等待 HTTP 服务器启动完成 (如果启动了)
            if connect_tasks:
                results = await asyncio.gather(*connect_tasks, return_exceptions=True)
                # 检查 HTTP 启动结果
                for i, task in enumerate(connect_tasks):
                    if task.get_coro().__name__ == "_start_http_server_internal":
                        if isinstance(results[i], Exception):
                            self.logger.error(f"启动 HTTP 服务器失败: {results[i]}", exc_info=results[i])
                        else:
                            self.logger.info(
                                f"HTTP 服务器成功启动于 http://{self._http_host}:{self._http_port}{self._http_callback_path}"
                            )
                        break

            # 注意：现在 connect 方法会很快返回，WebSocket 在后台连接
            self.logger.info("核心连接流程启动完成 (WebSocket 在后台运行)。")
            # 实际连接状态由 _monitor_ws_connection 更新

    async def _run_websocket(self):
        """内部方法：运行 WebSocket router.run()。"""
        if not self._router:
            self.logger.error("Router 未初始化，无法运行 WebSocket。")
            return  # 或者 raise
        try:
            self.logger.info("WebSocket run() 任务开始运行...")
            # 第一次成功连接时，可以在这里或通过 Router 回调设置 _is_connected = True
            # 但为了简化，我们让监控任务处理状态
            await self._router.run()  # 这个会一直运行直到断开
        except asyncio.CancelledError:
            self.logger.info("WebSocket run() 任务被取消。")
        except Exception as e:
            self.logger.error(f"WebSocket run() 任务异常终止: {e}", exc_info=True)
            # 异常退出也意味着断开连接，监控任务会处理状态
        finally:
            self.logger.info("WebSocket run() 任务已结束。")
            # 确保任务结束后状态被标记为 False (虽然监控任务也会做)
            # self._is_connected = False

    async def _monitor_ws_connection(self):
        """内部方法：监控 WebSocket 连接任务的状态。"""
        if not self._ws_task:
            return
        self.logger.info("WebSocket 连接监控任务已启动。")
        try:
            # 初始时认为未连接，等待 run() 任务稳定运行
            # 可以增加一个短暂的延迟，或者依赖 Router 的内部状态/回调（如果可用）
            # 简单起见，我们假设任务启动后一小段时间就算连接成功
            await asyncio.sleep(1)  # 等待 1 秒尝试连接
            if self._ws_task and not self._ws_task.done():
                self.logger.info("WebSocket 连接初步建立，标记核心为已连接。")
                self._is_connected = True
            else:
                self.logger.warning("WebSocket 任务在监控开始前已结束，连接失败。")
                self._is_connected = False
                return  # 任务启动失败，监控结束

            # 等待任务结束 (表示断开连接)
            await self._ws_task
            self.logger.warning("检测到 WebSocket 连接任务已结束，标记核心为未连接。")

        except asyncio.CancelledError:
            self.logger.info("WebSocket 连接监控任务被取消。")
        except Exception as e:
            self.logger.error(f"WebSocket 连接监控任务异常退出: {e}", exc_info=True)
        finally:
            self.logger.info("WebSocket 连接监控任务已结束。")
            self._is_connected = False  # 最终确保状态为未连接
            self._ws_task = None  # 清理任务引用
            self._monitor_task = None  # 清理自身引用

    async def _start_http_server_internal(self):
        """内部方法：启动 aiohttp 服务器。"""
        if not self._http_app or not self._http_host or not self._http_port:
            raise ConnectionError("HTTP 服务器未正确配置")
        try:
            self._http_runner = web.AppRunner(self._http_app)
            await self._http_runner.setup()
            self._http_site = web.TCPSite(self._http_runner, self._http_host, self._http_port)
            await self._http_site.start()
        except Exception as e:
            # 清理可能已部分创建的资源
            if self._http_runner:
                await self._http_runner.cleanup()
                self._http_runner = None
            self._http_site = None
            raise ConnectionError(f"无法启动 HTTP 服务器: {e}") from e

    async def disconnect(self):
        """取消 WebSocket 任务并停止 HTTP 服务器。"""
        async with self._connect_lock:
            tasks = []
            # 停止 WebSocket 任务
            if self._ws_task and not self._ws_task.done():
                self.logger.info("正在取消 WebSocket run() 任务...")
                self._ws_task.cancel()
                tasks.append(self._ws_task)  # 等待任务实际结束
            # 停止监控任务
            if self._monitor_task and not self._monitor_task.done():
                self.logger.debug("正在取消 WebSocket 监控任务...")
                self._monitor_task.cancel()
                tasks.append(self._monitor_task)  # 等待任务实际结束

            # 停止 HTTP 服务器
            if self._http_runner:
                self.logger.info("正在停止 HTTP 服务器...")
                tasks.append(asyncio.create_task(self._stop_http_server_internal()))

            if not tasks:
                self.logger.warning("核心没有活动的任务需要停止。")
                return

            # 等待所有任务结束
            self.logger.debug(f"等待 {len(tasks)} 个任务结束...")
            results = await asyncio.gather(*tasks, return_exceptions=True)
            self.logger.debug(f"所有停止任务已完成，结果: {results}")

            # 清理状态
            self._is_connected = False
            self._ws_task = None
            self._monitor_task = None
            # self._http_runner, self._http_site 等在 _stop_http_server_internal 中被清理
            self.logger.info("核心服务已断开并清理。")

    async def _stop_http_server_internal(self):
        """内部方法：停止 aiohttp 服务器。"""
        if self._http_runner:
            await self._http_runner.cleanup()
            self._http_runner = None
            self._http_site = None  # 标记已停止
            self._http_app = None  # 可以考虑是否需要重置 app

    async def send_to_maicore(self, message: MessageBase):
        """
        向 MaiCore 发送 MessageBase 消息。

        Args:
            message: 要发送的 MessageBase 对象。
        """
        if not self._is_connected or not self._router:
            logger.warning(f"核心未连接，无法发送消息: {message.message_info.message_id}")
            # 可以考虑将消息放入待发队列
            return

        logger.debug(f"准备向 MaiCore 发送消息: {message.message_info.message_id}")
        try:
            # Add debug log for the message content just before sending via router
            try:
                message_dict_for_log = message.to_dict()
                logger.debug(f"发送给 Router 的消息内容: {str(message_dict_for_log)}...")  # Log partial dict string
            except Exception as log_err:
                logger.error(f"在记录消息日志时出错: {log_err}")  # Log error during logging itself
                logger.debug(f"发送给 Router 的消息对象 (repr): {repr(message)}")  # Fallback to repr

            await self._router.send_message(message)
            logger.info(
                f"消息已发送: {message.message_info.message_id} (Type: {message.message_segment.type if message.message_segment else 'N/A'})"
            )
        except Exception as e:
            logger.error(f"发送消息到 MaiCore 时出错: {e}", exc_info=True)
            # 发送失败处理，例如重试或通知插件

    async def _handle_maicore_message(self, message_data: Dict[str, Any]):
        """
        内部方法，处理从 MaiCore WebSocket 收到的原始消息。
        负责解析消息并将其分发给已注册的处理器。

        Args:
            message_data: 从 Router 收到的原始消息字典。
        """
        logger.debug(f"收到来自 MaiCore 的原始数据: {str(message_data)[:200]}...")
        try:
            message_base = MessageBase.from_dict(message_data)
            logger.info(
                f"收到并解析消息: {message_base.message_info.message_id} (Type: {message_base.message_segment.type if message_base.message_segment else 'N/A'})"
            )

            # --- 消息分发逻辑 ---
            # 这里需要确定如何根据消息内容决定分发给哪些处理器
            # 可以根据 message_segment.type, message_info.additional_config 中的字段等
            # 示例：根据 segment 类型分发
            dispatch_key = "default"  # 默认分发键
            if message_base.message_segment:
                dispatch_key = message_base.message_segment.type  # 使用 segment 类型作为分发键

            # 查找并调用处理器
            if dispatch_key in self._message_handlers:
                handlers = self._message_handlers[dispatch_key]
                logger.info(
                    f"为消息 {message_base.message_info.message_id} 找到 {len(handlers)} 个 '{dispatch_key}' 处理器"
                )
                # 并发执行所有匹配的处理器
                tasks = [asyncio.create_task(handler(message_base)) for handler in handlers]
                await asyncio.gather(*tasks, return_exceptions=True)  # return_exceptions=True 方便调试
            else:
                logger.info(f"没有找到适用于消息类型 '{dispatch_key}' 的处理器: {message_base.message_info.message_id}")

            # 也可以有一个处理所有消息的 "通配符" 处理器列表
            if "*" in self._message_handlers:
                wildcard_handlers = self._message_handlers["*"]
                logger.info(
                    f"为消息 {message_base.message_info.message_id} 找到 {len(wildcard_handlers)} 个通配符处理器"
                )
                tasks = [asyncio.create_task(handler(message_base)) for handler in wildcard_handlers]
                await asyncio.gather(*tasks, return_exceptions=True)

        except Exception as e:
            logger.error(f"处理 MaiCore 消息时发生错误: {e}", exc_info=True)

    def register_websocket_handler(self, message_type_or_key: str, handler: Callable[[MessageBase], asyncio.Task]):
        """
        注册一个消息处理器。

        插件或其他模块可以使用此方法来监听特定类型的消息。

        Args:
            message_type_or_key: 标识消息类型的字符串 (例如 "text", "vts_command", "danmu", 或自定义键, "*" 表示所有消息)。
            handler: 一个异步函数，接收 MessageBase 对象作为参数。
        """
        if not asyncio.iscoroutinefunction(handler):
            logger.warning(f"注册的 WebSocket 处理器 '{handler.__name__}' 不是一个异步函数 (async def)。")
            # raise TypeError("Handler must be an async function")

        if message_type_or_key not in self._message_handlers:
            self._message_handlers[message_type_or_key] = []
        self._message_handlers[message_type_or_key].append(handler)
        logger.info(f"成功注册 WebSocket 消息处理器: Key='{message_type_or_key}', Handler='{handler.__name__}'")

    async def _handle_http_request(self, request: web.Request) -> web.Response:
        """
        内部方法，处理所有到达指定回调路径的 HTTP POST 请求。
        负责初步解析请求并将其分发给已注册的 HTTP 处理器。
        """
        logger.info(f"收到来自 {request.remote} 的 HTTP 请求: {request.method} {request.path}")
        # --- HTTP 请求分发逻辑 ---
        # 这里需要更复杂的分发策略，例如根据 request.path, headers, 或请求体内容
        # 简单示例：使用固定 key "http_callback" 分发给所有注册的 HTTP 处理器
        dispatch_key = "http_callback"  # 或者从 request 中提取更具体的 key

        response_tasks = []
        if dispatch_key in self._http_request_handlers:
            handlers = self._http_request_handlers[dispatch_key]
            logger.info(f"为 HTTP 请求找到 {len(handlers)} 个 '{dispatch_key}' 处理器")
            # 让每个 handler 处理请求，它们应该返回 web.Response 或引发异常
            for handler in handlers:
                response_tasks.append(asyncio.create_task(handler(request)))
        else:
            logger.warning(f"没有找到适用于 HTTP 回调 Key='{dispatch_key}' 的处理器")
            return web.json_response(
                {"status": "error", "message": "No handler configured for this request"}, status=404
            )

        # --- 处理来自 handlers 的响应 ---
        # 策略：
        # 1. 如果只有一个 handler，直接返回它的响应。
        # 2. 如果有多个 handlers，如何合并响应？或者只取第一个成功的？
        #    目前简单起见，假设只有一个主要的 handler 应该返回实际响应，其他的可能是后台任务。
        #    这里我们仅等待所有任务完成，并尝试找到第一个有效响应。
        gathered_responses = await asyncio.gather(*response_tasks, return_exceptions=True)

        final_response: Optional[web.Response] = None
        first_exception: Optional[Exception] = None

        for result in gathered_responses:
            if isinstance(result, web.Response):
                if final_response is None:  # 取第一个有效响应
                    final_response = result
            elif isinstance(result, Exception):
                logger.error(f"处理 HTTP 请求时，某个 handler 抛出异常: {result}", exc_info=result)
                if first_exception is None:
                    first_exception = result

        if final_response:
            logger.info(f"HTTP 请求处理完成，返回状态: {final_response.status}")
            return final_response
        elif first_exception:
            # 如果有异常但没有成功响应，返回 500
            return web.json_response(
                {"status": "error", "message": f"Error processing request: {first_exception}"}, status=500
            )
        else:
            # 如果没有 handler 返回响应也没有异常 (可能 handler 设计为不返回)，返回一个默认成功响应
            logger.info("HTTP 请求处理完成，没有显式响应，返回默认成功状态。")
            return web.json_response({"status": "accepted"}, status=202)  # 202 Accepted 表示已接受处理

    def register_http_handler(self, key: str, handler: Callable[[web.Request], asyncio.Task]):
        """
        注册一个处理 HTTP 回调请求的处理器。

        Args:
            key: 用于匹配请求的键 (当前简单实现只支持固定 key)。
            handler: 一个异步函数，接收 aiohttp.web.Request 对象，并应返回 aiohttp.web.Response 对象。
        """
        if not asyncio.iscoroutinefunction(handler):
            logger.warning(f"注册的 HTTP 处理器 '{handler.__name__}' 不是一个异步函数 (async def)。")
            # raise TypeError("Handler must be an async function")

        if key not in self._http_request_handlers:
            self._http_request_handlers[key] = []
        self._http_request_handlers[key].append(handler)
        logger.info(f"成功注册 HTTP 请求处理器: Key='{key}', Handler='{handler.__name__}'")

    # --- 服务注册与发现 ---
    def register_service(self, name: str, service_instance: Any):
        """
        注册一个服务实例，供其他插件或模块使用。

        Args:
            name: 服务的唯一名称 (例如 "text_cleanup", "vts_client")。
            service_instance: 提供服务的对象实例。
        """
        if name in self._services:
            self.logger.warning(f"服务名称 '{name}' 已被注册，将被覆盖！")
        self._services[name] = service_instance
        self.logger.info(f"服务已注册: '{name}' (类型: {type(service_instance).__name__})")

    def get_service(self, name: str) -> Optional[Any]:
        """
        根据名称获取已注册的服务实例。

        Args:
            name: 要获取的服务名称。

        Returns:
            服务实例，如果找到的话；否则返回 None。
        """
        service = self._services.get(name)
        if service:
            self.logger.debug(f"获取服务 '{name}' 成功。")
        else:
            self.logger.warning(f"尝试获取未注册的服务: '{name}'")
        return service

    # --- 插件管理占位符 (可移除) ---
    # ...

    # --- 未来可以添加内部事件分发机制 ---
    # async def dispatch_event(self, event_name: str, **kwargs): ...
    # def subscribe_event(self, event_name: str, handler: Callable): ...
