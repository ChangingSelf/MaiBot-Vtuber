from typing import Dict, List, Any, Optional, Callable
from langchain_core.tools import BaseTool, Tool
from pydantic import BaseModel, Field, create_model
from src.utils.logger import get_logger
import json
import asyncio
from functools import wraps


class MCPToolAdapter:
    """将MCP工具转换为LangChain Tool"""

    def __init__(self, mcp_client, error_detection_config=None):
        self.mcp_client = mcp_client
        self.logger = get_logger("MCPToolAdapter")
        self._tools_cache: Optional[List[BaseTool]] = None
        self._tools_metadata_cache: Optional[List[Dict[str, Any]]] = None

        # 错误检测配置，支持用户自定义
        self.error_detection_config = error_detection_config or {
            "mode": "full_json",  # "full_json" 或 "custom_keys"
            "error_keys": {"success": False, "ok": False, "error": True, "failed": True},
            "error_message_keys": ["error_message", "error", "message", "reason"],
            "error_code_keys": ["error_code", "code", "status_code"],
        }

    async def create_langchain_tools(self) -> List[BaseTool]:
        """将MCP工具转换为LangChain Tool列表"""
        if self._tools_cache is not None:
            return self._tools_cache

        try:
            self.logger.info("[MCP工具适配器] 开始获取MCP工具列表")

            # 获取MCP工具列表
            tools_info = await self._get_mcp_tools()
            if not tools_info:
                self.logger.warning("[MCP工具适配器] 未获取到MCP工具")
                return []

            # 缓存工具元数据
            self._tools_metadata_cache = tools_info

            langchain_tools = []
            for tool_info in tools_info:
                try:
                    tool = await self._create_langchain_tool(tool_info)
                    if tool:
                        langchain_tools.append(tool)
                        self.logger.info(f"[MCP工具适配器] 成功创建工具: {tool.name}")
                except Exception as e:
                    self.logger.error(f"[MCP工具适配器] 创建工具失败 {tool_info.get('name', 'unknown')}: {e}")

            self._tools_cache = langchain_tools
            self.logger.info(f"[MCP工具适配器] 成功创建 {len(langchain_tools)} 个LangChain工具")
            return langchain_tools

        except Exception as e:
            self.logger.error(f"[MCP工具适配器] 创建LangChain工具失败: {e}")
            return []

    async def _get_mcp_tools(self) -> List[Dict[str, Any]]:
        """获取MCP工具信息"""
        try:
            self.logger.info("[MCP工具适配器] 获取MCP工具信息")

            # 使用MCP客户端的get_tools_metadata方法
            if hasattr(self.mcp_client, "get_tools_metadata"):
                tools_info = await self.mcp_client.get_tools_metadata()
                self.logger.info(f"[MCP工具适配器] 获取到 {len(tools_info)} 个MCP工具")
                return tools_info
            else:
                self.logger.warning("[MCP工具适配器] MCP客户端不支持get_tools_metadata方法")
                return []

        except Exception as e:
            self.logger.error(f"[MCP工具适配器] 获取MCP工具信息失败: {e}")
            return []

    async def _create_langchain_tool(self, tool_info: Dict[str, Any]) -> Optional[BaseTool]:
        """创建单个LangChain工具"""
        try:
            name = tool_info.get("name", "")
            description = tool_info.get("description", "")
            schema = tool_info.get("inputSchema", {})

            if not name:
                self.logger.warning("[MCP工具适配器] 工具名称为空，跳过")
                return None

            # 生成包含参数信息的详细描述
            detailed_description = self._generate_detailed_description(name, description, schema)

            # 创建工具执行函数
            tool_func = self._create_tool_function(name)

            # 创建同步包装器
            def sync_wrapper(input_json: str) -> str:
                import asyncio

                try:
                    # 获取当前事件循环或创建新的
                    try:
                        loop = asyncio.get_event_loop()
                    except RuntimeError:
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)

                    # 运行异步函数
                    result = loop.run_until_complete(tool_func(input_json=input_json))

                    # 确保返回字符串格式
                    if isinstance(result, dict):
                        import json

                        return json.dumps(result, ensure_ascii=False)
                    else:
                        return str(result)
                except Exception as e:
                    self.logger.error(f"[MCP工具适配器] 工具执行异常 {name}: {e}")
                    import json

                    return json.dumps({"success": False, "tool": name, "error": str(e)}, ensure_ascii=False)

            # 使用Tool创建LangChain工具（不需要args_schema）
            langchain_tool = Tool(name=name, description=detailed_description, func=sync_wrapper)

            return langchain_tool

        except Exception as e:
            self.logger.error(f"[MCP工具适配器] 创建工具 {tool_info.get('name', 'unknown')} 失败: {e}")
            return None

    def _create_tool_model(self, name: str, schema: Dict[str, Any]) -> type:
        """根据MCP schema动态创建Pydantic模型"""
        try:
            # 对于ZeroShotAgent，我们需要创建单输入工具
            # 将所有参数合并为一个JSON字符串输入
            from pydantic import BaseModel, Field
            from typing import Annotated

            # 创建一个通用的输入模型类
            class GenericInputModel(BaseModel):
                input_json: Annotated[
                    str, Field(description="JSON格式的输入参数，包含所有必需和可选的参数", default="{}")
                ]

            # 动态设置类名
            GenericInputModel.__name__ = f"{name.capitalize()}Input"
            self.logger.debug(f"[MCP工具适配器] 创建单输入模型类: {name.capitalize()}Input")
            return GenericInputModel

        except Exception as e:
            self.logger.error(f"[MCP工具适配器] 创建模型类失败 {name}: {e}")
            # 返回默认模型
            from pydantic import BaseModel, Field
            from typing import Annotated

            class DefaultInputModel(BaseModel):
                input_json: Annotated[str, Field(default="{}", description="JSON格式的输入参数")]

            DefaultInputModel.__name__ = f"{name.capitalize()}Input"
            return DefaultInputModel

    def _convert_schema_type(self, schema_type: str) -> type:
        """转换JSON schema类型到Python类型"""
        type_mapping = {"string": str, "integer": int, "number": float, "boolean": bool, "array": List, "object": Dict}
        return type_mapping.get(schema_type, str)

    def _get_tool_metadata(self, tool_name: str) -> Optional[Dict[str, Any]]:
        """获取指定工具的元数据"""
        if not self._tools_metadata_cache:
            return None

        for tool_info in self._tools_metadata_cache:
            if tool_info.get("name") == tool_name:
                return tool_info
        return None

    def _generate_detailed_description(self, name: str, description: str, schema: Dict[str, Any]) -> str:
        """生成包含参数信息的详细工具描述"""
        detailed_desc = f"{description}\n\n"

        if schema:
            properties = schema.get("properties", {})
            required_fields = schema.get("required", [])

            if properties:
                detailed_desc += "参数说明:\n"

                for field_name, field_info in properties.items():
                    field_type = field_info.get("type", "unknown")
                    field_desc = field_info.get("description", "")
                    is_required = field_name in required_fields
                    default_value = field_info.get("default")

                    # 构建参数描述
                    param_desc = f"- {field_name} ({field_type})"
                    if is_required:
                        param_desc += " [必需]"
                    else:
                        param_desc += " [可选]"

                    if field_desc:
                        param_desc += f": {field_desc}"

                    if default_value is not None and not is_required:
                        param_desc += f" (默认值: {default_value})"

                    detailed_desc += param_desc + "\n"

        return detailed_desc.strip()

    def _validate_and_fix_parameters(self, tool_name: str, parsed_args: Dict[str, Any]) -> Dict[str, Any]:
        """基于工具元数据验证和修复参数"""
        tool_metadata = self._get_tool_metadata(tool_name)
        if not tool_metadata:
            self.logger.warning(f"[MCP工具适配器] 未找到工具 {tool_name} 的元数据，跳过参数验证")
            return parsed_args

        schema = tool_metadata.get("inputSchema", {})
        properties = schema.get("properties", {})
        required_fields = schema.get("required", [])

        self.logger.info(f"[MCP工具适配器] 验证工具 {tool_name} 的参数")
        self.logger.info(f"[MCP工具适配器] 必需字段: {required_fields}")
        self.logger.info(f"[MCP工具适配器] 可选字段: {list(properties.keys())}")
        self.logger.info(f"[MCP工具适配器] 传入参数: {list(parsed_args.keys())}")

        # 检查必需字段
        missing_required = []
        for field in required_fields:
            if field not in parsed_args:
                missing_required.append(field)

        if missing_required:
            self.logger.warning(f"[MCP工具适配器] 工具 {tool_name} 缺少必需字段: {missing_required}")

            # 尝试使用默认值
            for field in missing_required:
                if field in properties:
                    default_value = properties[field].get("default")
                    if default_value is not None:
                        parsed_args[field] = default_value
                        self.logger.info(f"[MCP工具适配器] 使用默认值: {field} = {default_value}")

        return parsed_args

    def _create_tool_function(self, tool_name: str) -> Callable:
        """创建工具执行函数"""

        async def tool_function(input_json: str):
            """工具执行函数"""
            try:
                self.logger.info(f"[MCP工具适配器] 执行工具: {tool_name}, 参数: {input_json}")

                # 解析JSON输入参数
                try:
                    import json
                    import re

                    # 如果输入是字符串，尝试解析为JSON
                    if isinstance(input_json, str):
                        if input_json.strip():
                            # 尝试修复常见的JSON格式错误
                            fixed_json = input_json

                            # 修复1: 修复缺少逗号的问题 (例如: "count": 10" -> "count": 10)
                            fixed_json = re.sub(r'(\d+)"(\s*[}\]])', r"\1\2", fixed_json)

                            # 修复2: 修复多余的引号 (例如: "count": "10" -> "count": 10)
                            fixed_json = re.sub(r':\s*"(\d+)"', r": \1", fixed_json)

                            # 修复3: 修复布尔值 (例如: "enabled": "true" -> "enabled": true)
                            fixed_json = re.sub(r':\s*"(true|false)"', r": \1", fixed_json)

                            # 如果修复后的JSON与原始不同，记录日志
                            if fixed_json != input_json:
                                self.logger.info(f"[MCP工具适配器] 修复JSON格式: {input_json} -> {fixed_json}")

                            try:
                                parsed_args = json.loads(fixed_json)
                            except json.JSONDecodeError:
                                # 如果修复后仍然失败，尝试更激进的修复
                                self.logger.warning(f"[MCP工具适配器] 修复后JSON仍无效，尝试更激进的修复: {fixed_json}")
                                # 尝试提取键值对
                                try:
                                    # 使用正则表达式提取键值对，支持包含逗号的值
                                    pattern = r'"([^"]+)"\s*:\s*"([^"]*)"'
                                    matches = re.findall(pattern, fixed_json)
                                    if matches:
                                        parsed_args = dict(matches)
                                        self.logger.info(f"[MCP工具适配器] 使用正则提取参数: {parsed_args}")
                                    else:
                                        # 如果正则表达式失败，尝试更简单的方法
                                        try:
                                            # 找到第一个冒号的位置
                                            colon_pos = fixed_json.find(":")
                                            if colon_pos > 0:
                                                # 提取键（去掉开头的{和引号）
                                                key_part = fixed_json[1:colon_pos].strip().strip('"')
                                                # 提取值（去掉结尾的}和引号）
                                                value_part = fixed_json[colon_pos + 1 : -1].strip().strip('"')
                                                parsed_args = {key_part: value_part}
                                                self.logger.info(f"[MCP工具适配器] 使用简单解析: {parsed_args}")
                                            else:
                                                raise ValueError("无法找到冒号分隔符")
                                        except Exception:
                                            raise ValueError("无法提取有效参数")
                                except Exception:
                                    # 最后的回退：尝试直接解析为键值对
                                    try:
                                        # 如果输入看起来像JSON但解析失败，尝试手动解析
                                        if input_json.startswith("{") and input_json.endswith("}"):
                                            # 移除大括号，分割键值对
                                            content = input_json[1:-1].strip()
                                            pairs = content.split(",")
                                            parsed_args = {}
                                            for pair in pairs:
                                                if ":" in pair:
                                                    key, value = pair.split(":", 1)
                                                    key = key.strip().strip('"')
                                                    value = value.strip().strip('"')
                                                    parsed_args[key] = value
                                        else:
                                            # 如果不是JSON格式，使用原始值
                                            parsed_args = {"value": input_json}
                                    except Exception:
                                        # 最后的回退：使用原始值
                                        parsed_args = {"value": input_json}
                        else:
                            parsed_args = {}
                    # 如果输入已经是字典，直接使用
                    elif isinstance(input_json, dict):
                        parsed_args = input_json
                    # 如果输入是其他类型，尝试转换为字符串再解析
                    else:
                        try:
                            parsed_args = json.loads(str(input_json))
                        except:
                            # 如果转换失败，尝试直接解析
                            try:
                                if (
                                    isinstance(input_json, str)
                                    and input_json.startswith("{")
                                    and input_json.endswith("}")
                                ):
                                    # 手动解析JSON格式的字符串
                                    content = input_json[1:-1].strip()
                                    pairs = content.split(",")
                                    parsed_args = {}
                                    for pair in pairs:
                                        if ":" in pair:
                                            key, value = pair.split(":", 1)
                                            key = key.strip().strip('"')
                                            value = value.strip().strip('"')
                                            parsed_args[key] = value
                                else:
                                    # 如果不是JSON格式，使用原始值
                                    parsed_args = {"value": input_json}
                            except Exception:
                                # 最后的回退：使用原始值
                                parsed_args = {"value": input_json}

                    self.logger.info(f"[MCP工具适配器] 解析后的参数: {parsed_args}")
                except json.JSONDecodeError as e:
                    self.logger.warning(f"[MCP工具适配器] JSON解析失败 {tool_name}: {e}, 尝试手动解析")
                    # 如果JSON解析失败，尝试手动解析
                    try:
                        if isinstance(input_json, str) and input_json.startswith("{") and input_json.endswith("}"):
                            # 手动解析JSON格式的字符串
                            content = input_json[1:-1].strip()
                            pairs = content.split(",")
                            parsed_args = {}
                            for pair in pairs:
                                if ":" in pair:
                                    key, value = pair.split(":", 1)
                                    key = key.strip().strip('"')
                                    value = value.strip().strip('"')
                                    parsed_args[key] = value
                        else:
                            # 如果不是JSON格式，使用原始值
                            parsed_args = {"value": input_json}
                    except Exception:
                        # 最后的回退：使用原始值
                        parsed_args = {"value": input_json}

                # 基于工具元数据验证和修复参数
                if isinstance(parsed_args, dict):
                    parsed_args = self._validate_and_fix_parameters(tool_name, parsed_args)

                # 检查MCP客户端状态
                if not self.mcp_client:
                    self.logger.error("[MCP工具适配器] MCP客户端为空")
                    return {"success": False, "tool": tool_name, "error": "MCP客户端为空"}

                if not hasattr(self.mcp_client, "call_tool_directly"):
                    self.logger.warning("[MCP工具适配器] MCP客户端不支持call_tool_directly方法")
                    return {"success": False, "tool": tool_name, "error": "MCP客户端不支持工具调用"}

                # 使用MCP客户端的call_tool_directly方法
                self.logger.info(f"[MCP工具适配器] 准备调用MCP工具: {tool_name}")
                result = await self.mcp_client.call_tool_directly(tool_name, parsed_args)
                self.logger.info(f"[MCP工具适配器] MCP工具调用结果: {result}")

                if result.get("success"):
                    # 获取工具的实际返回结果
                    tool_result = result.get("result", result)

                    # 根据配置模式处理错误检测
                    if self.error_detection_config["mode"] == "full_json":
                        # 模式1：返回完整JSON，让LLM自己判断
                        self.logger.info(f"[MCP工具适配器] 工具执行成功: {tool_name}，返回完整JSON")
                        return tool_result
                    else:
                        # 模式2：使用自定义key检测错误
                        if isinstance(tool_result, dict):
                            # 检查配置的错误字段
                            error_detected = False
                            error_key_found = None

                            for key, expected_value in self.error_detection_config["error_keys"].items():
                                if tool_result.get(key) == expected_value:
                                    error_detected = True
                                    error_key_found = key
                                    break

                            if error_detected:
                                # 工具返回了错误，提取错误信息
                                error_message = None
                                error_code = None

                                # 查找错误消息
                                for key in self.error_detection_config["error_message_keys"]:
                                    if key in tool_result:
                                        error_message = tool_result[key]
                                        break

                                # 查找错误代码
                                for key in self.error_detection_config["error_code_keys"]:
                                    if key in tool_result:
                                        error_code = tool_result[key]
                                        break

                                if not error_message:
                                    error_message = f"工具执行失败 (检测到错误字段: {error_key_found})"

                                self.logger.error(
                                    f"[MCP工具适配器] 工具执行失败: {tool_name}, 错误代码: {error_code}, 错误信息: {error_message}"
                                )
                                return {
                                    "success": False,
                                    "tool": tool_name,
                                    "error_code": error_code,
                                    "error_message": error_message,
                                    "raw_result": tool_result,
                                }

                    # 工具执行成功
                    self.logger.info(f"[MCP工具适配器] 工具执行成功: {tool_name}")
                    return tool_result
                else:
                    # MCP客户端调用失败
                    self.logger.error(f"[MCP工具适配器] MCP客户端调用失败: {tool_name}, 错误: {result.get('error')}")
                    return result

            except Exception as e:
                self.logger.error(f"[MCP工具适配器] 工具执行失败 {tool_name}: {e}")
                import traceback

                self.logger.error(f"[MCP工具适配器] 异常堆栈: {traceback.format_exc()}")
                return {"success": False, "tool": tool_name, "error": str(e)}

        return tool_function

    def clear_cache(self):
        """清除工具缓存"""
        self._tools_cache = None
        self.logger.info("[MCP工具适配器] 清除工具缓存")
