from __future__ import annotations

import contextlib
from typing import Any, Dict, List, Optional
import json
import os

from fastmcp import Client as FastMCPClient
from src.utils.logger import get_logger


class MCPClient:
    """基于 fastmcp 的 MCP 客户端"""

    def __init__(self, config: Dict[str, Any]) -> None:
        self.logger = get_logger("MCPClient")
        self.config = config
        self.connected = False
        self._client: Optional[FastMCPClient] = None

        # 硬编码：始终使用插件 mcp 目录下的 mcp_servers.json
        # 例如: src/plugins/maicraft/mcp/mcp_servers.json
        self.mcp_config_file: str = os.path.join(os.path.dirname(__file__), "mcp_servers.json")

    async def connect(self) -> bool:
        """读取 MCP JSON 配置并建立 fastmcp 客户端连接。"""
        try:
            with open(self.mcp_config_file, "r", encoding="utf-8") as f:
                config_obj = json.load(f)
        except Exception as e:
            self.logger.error(f"[MCP] 读取配置文件失败: {e}")
            return False

        try:
            self._client = FastMCPClient(config_obj)
            # 打开会话
            await self._client.__aenter__()
            self.connected = True
            self.logger.info("[MCP] fastmcp 客户端已连接 (MCP JSON 配置)")

            # 获取工具列表
            tools = await self.list_available_tools()
            self.logger.info(f"[MCP] 获取工具列表: {tools}")

            return True
        except Exception as e:
            self.logger.error(f"[MCP] 连接 fastmcp 客户端失败: {e}")
            self._client = None
            self.connected = False
            return False

    async def disconnect(self) -> None:
        if self._client:
            try:
                await self._client.__aexit__(None, None, None)
            except Exception as e:
                self.logger.error(f"[MCP] 断开 fastmcp 客户端异常: {e}")
        self._client = None
        self.connected = False
        self.logger.info("[MCP] fastmcp 客户端已断开")

    async def get_tools_metadata(self) -> List[Dict[str, Any]]:
        """列出所有可用工具的元数据（名称/描述/参数模式）。"""
        if not self._client:
            return []
        try:
            # fastmcp >=2.0: Client supports list_tools
            if hasattr(self._client, "list_tools"):
                tools = await self._client.list_tools()  # type: ignore[attr-defined]
            elif hasattr(self._client, "get_tools"):
                tools = await self._client.get_tools()  # type: ignore[attr-defined]
            else:
                tools = []

            metadata: List[Dict[str, Any]] = []
            for t in tools or []:
                if isinstance(t, dict):
                    name = t.get("name")
                    desc = t.get("description", "")
                    params = (
                        t.get("inputSchema")
                        or t.get("input_schema")
                        or {"type": "object", "properties": {}, "required": []}
                    )
                else:
                    name = getattr(t, "name", None)
                    desc = getattr(t, "description", "")
                    params = (
                        getattr(t, "input_schema", None)
                        or getattr(t, "inputSchema", None)
                        or {"type": "object", "properties": {}, "required": []}
                    )
                if name:
                    metadata.append({"name": name, "description": desc, "inputSchema": params})
            return metadata
        except Exception as e:
            self.logger.error(f"[MCP] 获取工具元数据失败: {e}")
            return []

    async def call_tool_directly(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """直接调用工具，返回统一结构。"""
        self.logger.info(f"[MCP] 开始调用工具: {tool_name}, 参数: {arguments}")
        self.logger.info(f"[MCP] 参数类型: {type(arguments)}")
        self.logger.info(f"[MCP] 参数键: {list(arguments.keys()) if isinstance(arguments, dict) else 'N/A'}")

        # 详细检查参数
        if isinstance(arguments, dict):
            for key, value in arguments.items():
                self.logger.info(f"[MCP] 参数 {key}: {value} (类型: {type(value)})")

        if not self._client:
            self.logger.error("[MCP] MCP客户端未连接")
            return {"success": False, "error": "MCP 客户端未连接"}

        # 检查客户端状态
        self.logger.info(f"[MCP] 客户端类型: {type(self._client)}")
        self.logger.info(f"[MCP] 客户端是否有call_tool方法: {hasattr(self._client, 'call_tool')}")

        try:
            self.logger.info(f"[MCP] 调用fastmcp客户端的call_tool方法")
            self.logger.info(f"[MCP] 传递给fastmcp的参数: tool_name={tool_name}, arguments={arguments}")

            # 尝试异步调用，如果失败则使用同步调用
            import asyncio

            try:
                result = await asyncio.wait_for(
                    self._client.call_tool(tool_name, arguments),
                    timeout=10.0,  # 10秒超时
                )
                self.logger.info(f"[MCP] fastmcp异步调用结果: {result}")
            except asyncio.TimeoutError:
                self.logger.warning(f"[MCP] 异步调用超时，尝试同步调用: {tool_name}")
                # 如果异步调用超时，尝试同步调用
                try:
                    import concurrent.futures

                    loop = asyncio.get_event_loop()
                    with concurrent.futures.ThreadPoolExecutor() as executor:
                        result = await loop.run_in_executor(
                            executor, lambda: self._client.call_tool(tool_name, arguments) if self._client else None
                        )
                    self.logger.info(f"[MCP] fastmcp同步调用结果: {result}")
                except Exception as sync_error:
                    self.logger.error(f"[MCP] 同步调用也失败: {sync_error}")
                    return {"success": False, "error": f"工具调用失败: {sync_error}"}

            jsonable_result = self._to_jsonable(result)
            self.logger.info(f"[MCP] 转换后的结果: {jsonable_result}")

            return {"success": True, "result": jsonable_result}
        except Exception as e:
            self.logger.error(f"[MCP] 调用工具失败: {e}")
            import traceback

            self.logger.error(f"[MCP] 异常堆栈: {traceback.format_exc()}")
            return {"success": False, "error": str(e)}

    async def list_available_tools(self) -> List[str]:
        metas = await self.get_tools_metadata()
        return [m.get("name", "") for m in metas if m.get("name")]

    # 内部：将任意对象转换为 JSON 可序列化结构
    def _to_jsonable(self, value: Any) -> Any:
        try:
            import dataclasses  # 延迟导入

            if value is None or isinstance(value, (bool, int, float, str)):
                return value
            if isinstance(value, dict):
                return {str(k): self._to_jsonable(v) for k, v in value.items()}
            if isinstance(value, (list, tuple, set)):
                return [self._to_jsonable(v) for v in list(value)]
            # pydantic v2
            if hasattr(value, "model_dump"):
                return self._to_jsonable(value.model_dump())  # type: ignore[attr-defined]
            # pydantic v1
            if hasattr(value, "dict") and callable(value.dict):  # type: ignore[attr-defined]
                return self._to_jsonable(value.dict())  # type: ignore[attr-defined]
            # dataclass 实例
            if dataclasses.is_dataclass(value) and not isinstance(value, type):
                return self._to_jsonable(dataclasses.asdict(value))
            # 通用 to_dict
            if hasattr(value, "to_dict") and callable(value.to_dict):  # type: ignore[attr-defined]
                return self._to_jsonable(value.to_dict())  # type: ignore[attr-defined]
            # 通用 json() → 解析
            if hasattr(value, "json") and callable(value.json):  # type: ignore[attr-defined]
                with contextlib.suppress(Exception):
                    import json as _json

                    return _json.loads(value.json())  # type: ignore[attr-defined]
            # 最后回退为字符串
            return str(value)
        except Exception:
            return str(value)
