from __future__ import annotations

from typing import Any, Optional
from .memory.position_memory import crafting_table_memory
from .utils import parse_tool_result


class BaseToolHandler:
    """工具处理器基类。用于在调用 MCP 工具前后做统一拦截/增强处理。

    子类需实现 supports 和 handle。
    """

    def supports(self, tool_name: str) -> bool:
        raise NotImplementedError

    async def post_process(
        self,
        tool_name: str,
        arguments: Any,
        result: Any,
        environment: Any,
        logger: Any,
    ) -> Any:
        """在 MCP 工具返回 result 之后的统一后处理钩子。

        返回值应为供后续流程继续使用的结果对象（可原样返回或包装）。
        """
        return result


class PlaceBlockHandler(BaseToolHandler):
    """放置方块工具的专用处理器。

    典型工具名包含：place_block / placeBlock / place。
    现阶段实现为参数规范化 + 直接透传调用，后续可在此处加入：
    - 目标位置推断与校验
    - 朝向/选择面校正
    - 与环境的冲突检测
    - 失败后的重试/降级策略
    """

    SUPPORTED_NAMES = {"place_block"}

    def supports(self, tool_name: str) -> bool:
        return tool_name is not None and tool_name.replace(" ", "").lower() in self.SUPPORTED_NAMES

    async def post_process(
        self,
        tool_name: str,
        arguments: Any,
        result: Any,
        environment: Any,
        logger: Any,
    ) -> Any:
        # 仅支持标准化 PlaceBlock 输入：{x, y, z, block, face, useAbsoluteCoords}
        try:
            logger.info("[PlaceBlockHandler] 放置方块结果后处理开始")
            placed_block = self._extract_block_name(arguments)
            if placed_block is not None and placed_block == "crafting_table":
                logger.info(f"[PlaceBlockHandler] 检测到工作台被放置: {placed_block}")
                try:
                    return await self._handle_crafting_table_placed(arguments, result, environment, logger)
                except Exception as inner_e:
                    logger.error(f"[PlaceBlockHandler] 处理工作台放置异常: {inner_e}")
                    return result

            return result
        except Exception as e:
            logger.error(f"[PlaceBlockHandler] 放置方块结果后处理异常: {e}")
            return result

    def _extract_block_name(self, arguments: Any) -> Optional[str]:
        # 仅从标准字段 arguments["block"] 读取
        if isinstance(arguments, dict) and isinstance(arguments.get("block"), str):
            return arguments.get("block")
        return None

    async def _handle_crafting_table_placed(
        self,
        arguments: Any,
        result: Any,
        environment: Any,
        logger: Any,
    ) -> Any:
        """工作台放置后的专用处理。

        可在此：
        - 记录工作台位置到内存/环境
        - 触发后续合成任务提示
        - 校验放置位置合法性
        目前：仅记录日志并透传结果。
        """
        try:
            # 仅在放置成功时记录工作台位置
            is_success = False
            try:
                is_success, _ = parse_tool_result(result)
            except Exception:
                # 兜底判断：直接从 result 判断常见字段
                try:
                    import json as _json
                    obj = None
                    if isinstance(result, str):
                        try:
                            obj = _json.loads(result)
                        except Exception:
                            obj = None
                    elif isinstance(result, dict):
                        obj = result
                    if isinstance(obj, dict):
                        ok_val = obj.get("ok")
                        success_val = obj.get("success")
                        is_success = bool(ok_val is True or success_val is True)
                except Exception:
                    is_success = False

            if not is_success:
                logger.info("[PlaceBlockHandler] 放置未成功，跳过记录工作台位置")
                return result
            # 仅支持顶层字段 x, y, z
            position = None

            x = arguments.get("x")
            y = arguments.get("y")
            z = arguments.get("z")
            if isinstance(x, (int, float)) and isinstance(y, (int, float)) and isinstance(z, (int, float)):
                position = (x, y, z)

            if position is not None:
                logger.info(f"[PlaceBlockHandler] 已在 {position} 放置工作台")
                try:
                    # 写入全局记忆
                    crafting_table_memory.add_crafting_table_point(
                        (int(position[0]), int(position[1]), int(position[2])),
                        "自动记录：放置工作台"
                    )

                    logger.info("[PlaceBlockHandler] 工作台位置已写入 CraftingTableMemory")
                except Exception as mem_e:
                    logger.error(f"[PlaceBlockHandler] 写入工作台位置记忆失败: {mem_e}")
            else:
                logger.info("[PlaceBlockHandler] 已放置工作台（未解析到坐标）")

            return result
        except Exception as e:
            logger.error(f"[PlaceBlockHandler] 工作台专用处理异常: {e}")
            return result


class ToolHandlerRegistry:
    """工具处理器注册表。根据工具名选择合适处理器。"""
    def __init__(self) -> None:
        self._handlers: list[BaseToolHandler] = []

    def register(self, handler: BaseToolHandler) -> None:
        self._handlers.append(handler)

    def find(self, tool_name: str) -> Optional[BaseToolHandler]:
        for handler in self._handlers:
            try:
                if handler.supports(tool_name):
                    return handler
            except Exception:
                continue
        return None


