from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Callable, Awaitable, cast

from openai import AsyncOpenAI
from openai.types.chat import (
    ChatCompletionMessageParam,
    ChatCompletionToolParam,
)
from src.utils.logger import get_logger


class LLMPlanner:
    """基于 OpenAI 的通用 LLM 规划器

    - 动态将 MCP tools 转换为 OpenAI function-calling 工具
    - 通过多轮工具调用执行任务
    - 不预设具体的 Minecraft 工具名称或能力
    """

    def __init__(
        self,
        *,
        api_key: Optional[str],
        base_url: Optional[str] = None,
        model: str,
        temperature: float = 0.2,
        max_steps: int = 5,
        system_prompt: Optional[str] = None,
    ) -> None:
        self.logger = get_logger("LLMPlanner")
        # 允许自定义兼容 OpenAI 的 base_url
        if base_url:
            self.client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        else:
            self.client = AsyncOpenAI(api_key=api_key)  # 如果 api_key=None 将走环境变量
        self.model = model
        self.temperature = temperature
        self.max_steps = max_steps
        self.system_prompt = (
            system_prompt
            or "你是一个 Minecraft 游戏助手。你可以使用提供的工具来完成玩家的目标。请尽量少步数、稳健地规划和调用工具；当任务完成或无法继续时，直接给出清晰的最终回答。"
        )

    @staticmethod
    def _normalize_schema(schema: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        if not schema:
            return {"type": "object", "properties": {}, "required": []}
        # fastmcp 可能字段为 inputSchema 或 input_schema
        return schema

    @staticmethod
    def _mcp_tools_to_openai_tools(mcp_tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        tools: List[Dict[str, Any]] = []
        for tool in mcp_tools:
            name = tool.get("name") or tool.get("tool_name") or "unknown_tool"
            description = tool.get("description", "")
            # 不同实现可能是 inputSchema 或 input_schema
            input_schema = (
                tool.get("inputSchema")
                or tool.get("input_schema")
                or {"type": "object", "properties": {}, "required": []}
            )
            # OpenAI 工具格式
            tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": name,
                        "description": description,
                        "parameters": LLMPlanner._normalize_schema(input_schema),
                    },
                }
            )
        return tools

    @staticmethod
    def _safe_json_loads(s: Any) -> Dict[str, Any]:
        if isinstance(s, dict):
            return s
        if s is None:
            return {}
        try:
            return json.loads(s)
        except Exception:
            return {}

    async def plan_and_execute(
        self,
        *,
        user_input: str,
        mcp_tools: List[Dict[str, Any]],
        call_tool: Callable[[str, Dict[str, Any]], Awaitable[Dict[str, Any]]],
        max_steps_override: Optional[int] = None,
    ) -> Dict[str, Any]:
        """用 LLM 规划并调用 MCP 工具直至完成或达到步数上限。

        Args:
            user_input: 用户自然语言意图
            mcp_tools: 从 MCP 服务器发现的工具原始元数据列表
            call_tool: 异步调用器 call_tool(name, arguments)->Dict

        Returns:
            { "success": bool, "final": str, "steps": [ ... ] }
        """
        self.logger.info(f"[LLM规划] 开始规划任务: {user_input}")
        self.logger.debug(f"[LLM规划] 使用模型: {self.model}, 温度: {self.temperature}, 最大步数: {self.max_steps}")

        steps: List[Dict[str, Any]] = []
        local_max_steps: int = int(max_steps_override) if max_steps_override is not None else int(self.max_steps)

        # 将 MCP 工具转换为 OpenAI 工具
        self.logger.debug(f"[LLM规划] 转换 {len(mcp_tools)} 个MCP工具为OpenAI格式")
        oa_tools = self._mcp_tools_to_openai_tools(mcp_tools)
        if not oa_tools:
            self.logger.error("[LLM规划] MCP未提供可用工具")
            return {"success": False, "error": "MCP 未提供可用工具"}

        tool_names = [tool["function"]["name"] for tool in oa_tools]
        self.logger.debug(f"[LLM规划] 可用工具: {', '.join(tool_names)}")

        messages: List[ChatCompletionMessageParam] = [
            {"role": "system", "content": self.system_prompt},
            {
                "role": "user",
                "content": (
                    "任务说明："
                    + user_input
                    + "\n注意：你只能通过提供的工具来影响游戏世界。必要时可分步执行；若需要探索环境，请先查询位置信息或背包等。"
                ),
            },
        ]

        self.logger.debug(f"[LLM规划] 初始消息数量: {len(messages)}")

        for step_idx in range(local_max_steps):
            self.logger.info(f"[LLM规划] 执行规划步骤 {step_idx + 1}/{local_max_steps}")

            try:
                # 调用 LLM 让其选择工具或产生最终回答
                self.logger.debug(f"[LLM规划] 发起LLM请求，当前消息数: {len(messages)}")

                import time

                llm_start = time.time()
                resp = await self.client.chat.completions.create(
                    model=self.model,
                    temperature=self.temperature,
                    messages=cast(List[ChatCompletionMessageParam], messages),
                    tools=cast(List[ChatCompletionToolParam], oa_tools),
                    tool_choice="auto",
                )
                llm_duration = time.time() - llm_start

                self.logger.debug(f"[LLM规划] LLM响应耗时: {llm_duration:.2f}s")

                choice = resp.choices[0]
                msg = choice.message

                # 记录LLM的响应内容
                if msg.content:
                    self.logger.debug(f"[LLM规划] LLM回复内容: {msg.content}")

                # 如果无工具调用，则认为已经给出最终答案
                tool_calls = getattr(msg, "tool_calls", None) or []
                if not tool_calls:
                    final_text = (msg.content or "").strip()
                    self.logger.info(f"[LLM规划] LLM给出最终答案，无需工具调用: {final_text}")
                    return {"success": True, "final": final_text, "steps": steps}

                self.logger.info(f"[LLM规划] 步骤 {step_idx + 1} - LLM要求调用 {len(tool_calls)} 个工具")

                # 存在一个或多个工具调用
                for tc_idx, tc in enumerate(tool_calls):
                    fn = tc.function
                    tool_name = fn.name
                    tool_args = self._safe_json_loads(fn.arguments)

                    self.logger.info(f"[LLM规划] 步骤 {step_idx + 1}.{tc_idx + 1} - 准备调用工具: {tool_name}")
                    self.logger.debug(f"[LLM规划] 工具参数: {tool_args}")

                    # 调用 MCP 工具
                    try:
                        tool_result = await call_tool(tool_name, tool_args)
                        self.logger.debug(f"[LLM规划] 工具 {tool_name} 返回: {tool_result}")
                    except Exception as e:  # 防御性
                        self.logger.error(f"[LLM规划] 工具 {tool_name} 调用异常: {e}")
                        tool_result = {"success": False, "error": str(e)}

                    steps.append(
                        {
                            "tool": tool_name,
                            "args": tool_args,
                            "result": tool_result,
                        }
                    )

                    # 将结果反馈给 LLM
                    messages.append(
                        {
                            "role": "assistant",
                            "tool_calls": [
                                {
                                    "id": tc.id,
                                    "type": "function",
                                    "function": {
                                        "name": tool_name,
                                        "arguments": json.dumps(tool_args, ensure_ascii=False),
                                    },
                                }
                            ],
                            "content": None,
                        }
                    )
                    # 严格保证 content 可被 JSON 序列化
                    try:
                        tool_content = json.dumps(tool_result, ensure_ascii=False)
                    except Exception:
                        # 回退：将不可序列化对象转换为字符串
                        try:
                            tool_content = json.dumps(str(tool_result), ensure_ascii=False)
                        except Exception:
                            tool_content = "{}"

                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": tool_content,
                        }
                    )

                self.logger.debug(f"[LLM规划] 步骤 {step_idx + 1} 完成，消息数增加到: {len(messages)}")

            except Exception as e:
                self.logger.error(f"[LLM规划] 步骤 {step_idx + 1} 执行异常: {e}", exc_info=True)
                return {
                    "success": False,
                    "error": f"规划步骤 {step_idx + 1} 异常: {str(e)}",
                    "steps": steps,
                }

        # 超过步数上限，返回当前结果
        self.logger.warning(f"[LLM规划] 达到最大步数限制 ({local_max_steps})，规划结束")
        self.logger.info(f"[LLM规划] 总共执行了 {len(steps)} 个工具调用")
        return {
            "success": False,
            "error": "达到最大计划步数，可能需要更高步数或更明确的目标",
            "steps": steps,
        }

    async def decompose_goal(
        self,
        *,
        goal: str,
        max_steps: int = 5,
        tool_names: Optional[List[str]] = None,
    ) -> List[str]:
        """使用 LLM 将一个自然语言目标拆分为若干可执行的子任务列表。

        - 仅返回中文短句子任务列表
        - 控制步数最大值，过滤无效/重复项
        - 若 LLM 失败或返回空，回退为 [goal]
        """
        import re

        self.logger.info(f"[任务拆解] 开始拆解目标: {goal}")
        try:
            tool_hint = "\n可用工具列表：" + ", ".join(tool_names or []) if tool_names else ""
            system = (
                "你是一个专业的任务拆解器，领域为 Minecraft 代理。\n"
                "请把给定的目标拆分为 1-" + str(max_steps) + " 个可以依次执行的简短中文步骤。\n"
                "每一步应可由工具执行，明确且原子化，避免模糊表达。\n"
                "偏向使用已知工具可实现的动作。" + tool_hint + "\n"
                "只输出一个 JSON 数组字符串，数组元素是每个步骤的中文短句；不需要任何解释、编号或其他文本。"
            )

            messages: List[ChatCompletionMessageParam] = [
                {"role": "system", "content": system},
                {
                    "role": "user",
                    "content": ("请拆解以下目标并仅以 JSON 数组输出：\n" + goal),
                },
            ]

            resp = await self.client.chat.completions.create(
                model=self.model,
                temperature=min(self.temperature, 0.3),
                messages=messages,
            )
            content = (resp.choices[0].message.content or "").strip()
            self.logger.debug(f"[任务拆解] LLM原始响应: {content}")

            # 解析 JSON 数组
            steps: List[str] = []
            try:
                parsed = json.loads(content)
                steps = [str(x).strip() for x in parsed] if isinstance(parsed, list) else []
            except Exception:
                if match := re.search(r"\[.*\]", content, re.S):
                    try:
                        parsed = json.loads(match.group(0))
                        if isinstance(parsed, list):
                            steps = [str(x).strip() for x in parsed]
                    except Exception:
                        steps = []

            # 结果清洗
            steps = [s for s in steps if s]
            # 去重保持顺序
            seen = set()
            uniq_steps: List[str] = []
            for s in steps:
                if s not in seen:
                    seen.add(s)
                    uniq_steps.append(s)
            steps = uniq_steps[: max(1, max_steps)]

            if not steps:
                self.logger.warning("[任务拆解] LLM返回为空，回退为原始目标")
                return [goal]

            self.logger.info(f"[任务拆解] 完成，共 {len(steps)} 步：{steps}")
            return steps
        except Exception as e:
            self.logger.error(f"[任务拆解] 异常: {e}", exc_info=True)
            return [goal]

    async def propose_next_goal(
        self,
        *,
        chat_history: List[str],
        mcp_tools: List[Dict[str, Any]],
        max_chars: int = 60,
    ) -> Optional[str]:
        """根据聊天记录与可用工具，提出一个下一步可执行的精简目标。

        仅返回一句话中文目标，不进行工具调用。
        """
        self.logger.info("[目标提议] 开始提议下一个目标")
        self.logger.debug(
            f"[目标提议] 聊天历史条数: {len(chat_history)}, 可用工具数: {len(mcp_tools)}, 最大字符数: {max_chars}"
        )

        try:
            tool_names = [t.get("name") or t.get("tool_name") for t in mcp_tools]
            valid_tool_names = [n for n in tool_names if n]
            self.logger.debug(f"[目标提议] 有效工具名称: {', '.join(valid_tool_names)}")

            chat_preview = "\n".join(chat_history[-10:]) if chat_history else ""
            if chat_preview:
                self.logger.debug(f"[目标提议] 聊天记录预览 (最近10条): {chat_preview[:200]}...")
            else:
                self.logger.debug("[目标提议] 无聊天记录")

            messages: List[ChatCompletionMessageParam] = [
                {
                    "role": "system",
                    "content": (
                        "你是一个 Minecraft 游戏代理的目标提议器。\n"
                        "- 仅输出一句中文目标（不超过" + str(max_chars) + "字）。\n"
                        "- 目标需要可通过已知工具完成，避免不可能的动作。\n"
                        "- 不要解释、不要编号、不要添加引号。\n"
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        "最近聊天记录如下（可能包含上层意图线索）：\n" + chat_preview + "\n\n"
                        "可用工具列表（名称）：\n" + ", ".join(valid_tool_names) + "\n\n"
                        "请给出一个最可能的下一步可执行目标。"
                    ),
                },
            ]

            self.logger.debug(f"[目标提议] 发起LLM请求，使用温度: {min(self.temperature, 0.5)}")

            import time

            start_time = time.time()
            resp = await self.client.chat.completions.create(
                model=self.model,
                temperature=min(self.temperature, 0.5),
                messages=messages,  # 不提供 tools，避免函数调用
            )
            duration = time.time() - start_time

            self.logger.debug(f"[目标提议] LLM响应耗时: {duration:.2f}s")

            text = (resp.choices[0].message.content or "").strip()
            self.logger.debug(f"[目标提议] LLM原始响应: {text}")

            if not text:
                self.logger.warning("[目标提议] LLM返回空内容")
                return None

            if len(text) > max_chars:
                original_text = text
                text = text[:max_chars]
                self.logger.debug(f"[目标提议] 目标被截断: '{original_text}' -> '{text}'")

            self.logger.info(f"[目标提议] 成功提议目标: {text}")
            return text

        except Exception as e:
            self.logger.error(f"[目标提议] 调用失败: {e}", exc_info=True)
            return None
