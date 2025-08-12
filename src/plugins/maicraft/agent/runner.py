import asyncio
import time
import uuid
import contextlib
from typing import Any, Dict, Optional, List

from maim_message import (
    MessageBase,
    BaseMessageInfo,
    UserInfo,
    GroupInfo,
    Seg,
    FormatInfo,
)

from src.core.amaidesu_core import AmaidesuCore
from src.utils.logger import get_logger
from .task_queue import TaskQueue, RunnerTask
from src.plugins.maicraft.mcp.client import MCPClient
from src.plugins.maicraft.agent.planner import LLMPlanner


class AgentRunner:
    """负责自主代理循环与消息处理的执行器。"""

    def __init__(
        self,
        *,
        core: AmaidesuCore,
        mcp_client: MCPClient,
        llm_planner: LLMPlanner,
        agent_cfg: Dict[str, Any],
    ) -> None:
        self.core = core
        self.mcp_client = mcp_client
        self.llm_planner = llm_planner
        self.agent_cfg = agent_cfg

        self.logger = get_logger("MaicraftAgent")
        # 执行互斥锁（执行阶段串行化，允许被取消以实现抢占）
        self._exec_lock = asyncio.Lock()
        # 运行控制
        self._stop_event = asyncio.Event()
        self._agent_task: Optional[asyncio.Task] = None  # 负责自提目标的循环
        self._dispatch_task: Optional[asyncio.Task] = None  # 负责从队列调度任务执行
        # 对话历史
        self._chat_history: List[str] = []
        self._chat_history_limit: int = int(agent_cfg.get("chat_history_limit", 50))
        # 任务队列管理器
        self._task_queue = TaskQueue(agent_cfg)
        self._current_exec_task: Optional[asyncio.Task] = None  # 当前正在执行的 asyncio.Task
        self._current_task_meta: Optional[RunnerTask] = None  # 当前执行任务的元信息
        self._running_priority: Optional[int] = None

        # 注入基于 LLM 的任务拆分器
        with contextlib.suppress(Exception):
            self._task_queue.set_splitter(self._split_goal_with_llm)

    # 生命周期
    async def start(self) -> None:
        if self._agent_task and not self._agent_task.done():
            return
        self._stop_event.clear()
        # 启动调度循环与自提目标循环
        self._dispatch_task = asyncio.create_task(self._dispatch_loop(), name="MaicraftDispatchLoop")
        self._agent_task = asyncio.create_task(self._agent_loop(), name="MaicraftAgentLoop")

    async def stop(self) -> None:
        self._stop_event.set()
        # 停止所有运行中的任务
        for t in [self._current_exec_task, self._dispatch_task, self._agent_task]:
            if t and not t.done():
                t.cancel()
        # 等待任务结束
        for t in [self._current_exec_task, self._dispatch_task, self._agent_task]:
            if t and not t.done():
                with contextlib.suppress(Exception):
                    await asyncio.wait_for(t, timeout=2.0)

    # 外部消息入口（抢占式：收到MaiCore消息→加入高优先队列并触发抢占）
    async def handle_message(self, message: MessageBase) -> None:
        if not self.mcp_client or not self.llm_planner:
            self.logger.error("[消息处理] 组件未就绪，忽略消息")
            return

        try:
            text_content = self._extract_text_from_message(message)
            if not text_content:
                self.logger.error("[消息处理] 消息中未找到有效文本内容")
                return

            self.logger.info(f"[消息处理] 提取到文本内容: {text_content}")
            self._append_chat(text_content)

            # 将收到的目标拆分为若干子任务并加入高优先队列
            await self._task_queue.enqueue_goal_with_split(
                text_content, priority=self._task_queue.PRIORITY_MAICORE, source="maicore"
            )
        except Exception as e:
            self.logger.error(f"[消息处理] 异常: {e}")

    # 自主循环
    async def _agent_loop(self) -> None:
        """自主代理循环：当队列空闲时，提出一个普通优先级目标并入队。"""
        tick_seconds = float(self.agent_cfg.get("tick_seconds", 8.0))
        loop_iteration = 0
        self.logger.info(f"自主代理循环开始运行 - tick间隔: {tick_seconds}s")
        while not self._stop_event.is_set():
            loop_iteration += 1
            try:
                if not self.mcp_client or not self.llm_planner:
                    await asyncio.sleep(tick_seconds)
                    continue

                # 仅在没有正在运行的任务且队列为空时，提出一个新目标
                if await self._task_queue.is_queue_idle() and self._current_exec_task is None:
                    tools_meta = await self.mcp_client.get_tools_metadata()
                    proposed_goal = await self.llm_planner.propose_next_goal(
                        chat_history=self._chat_history, mcp_tools=tools_meta
                    )
                    if goal := proposed_goal or str(self.agent_cfg.get("default_goal", "探索周围环境并汇报所见")):
                        await self._send_text_to_core(f"[Maicraft] 自主目标：{goal}")
                        await self._task_queue.enqueue_goal_with_split(
                            goal, priority=self._task_queue.PRIORITY_NORMAL, source="auto"
                        )

                await asyncio.sleep(tick_seconds)
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"[AgentLoop] 异常: {e}")
                await asyncio.sleep(tick_seconds)

        self.logger.info(f"自主代理循环结束，总共运行了 {loop_iteration} 轮")

    async def _dispatch_loop(self) -> None:
        """调度循环：从任务队列中取出任务并串行执行；当高优先任务到达时可抢占当前任务。"""
        self.logger.info("任务调度循环启动")
        try:
            while not self._stop_event.is_set():
                try:
                    if self._current_exec_task is None:
                        started = await self._try_start_next_task()
                        if not started:
                            await self._wait_for_new_task_idle(timeout=1.0)
                            continue

                    event_fired = await self._wait_for_event_or_task()
                    if event_fired:
                        await self._maybe_preempt()

                    await self._cleanup_finished_task()
                except asyncio.CancelledError:
                    if self._stop_event.is_set():
                        break
                    continue
                except Exception as e:
                    self.logger.error(f"[调度] 循环异常: {e}", exc_info=True)
                    await asyncio.sleep(0)
        finally:
            self.logger.info("任务调度循环结束")

    # ---- 调度循环辅助方法（提取以降低复杂度）----
    async def _try_start_next_task(self) -> bool:
        """尝试从队列中取出一个任务并启动执行。返回是否启动了任务。"""
        task_meta = await self._task_queue.pop_next_task()
        if task_meta is None:
            return False

        self._current_task_meta = task_meta
        self._running_priority = task_meta.priority
        self._current_exec_task = asyncio.create_task(self._execute_task(task_meta))
        return True

    async def _wait_for_new_task_idle(self, timeout: float) -> None:
        """在没有任务可执行时，带超时地等待新任务到达。"""
        new_task_event = self._task_queue.get_new_task_event()
        try:
            await asyncio.wait_for(new_task_event.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            return
        finally:
            # 即使超时也清理一次，防止遗留 set 状态导致误触发
            if new_task_event.is_set():
                new_task_event.clear()

    async def _wait_for_event_or_task(self) -> bool:
        """等待当前执行任务完成或有新任务事件到达。返回是否有新任务事件触发。"""
        if not self._current_exec_task:
            return False

        new_task_event = self._task_queue.get_new_task_event()
        event_task = asyncio.create_task(new_task_event.wait())
        try:
            await asyncio.wait(
                {self._current_exec_task, event_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
        finally:
            if not event_task.done():
                event_task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await event_task

        event_fired = new_task_event.is_set()
        if event_fired:
            new_task_event.clear()
        return event_fired

    async def _maybe_preempt(self) -> None:
        """当更高优先级任务到达时，尝试抢占当前任务。"""
        min_pending_pri = await self._task_queue.peek_min_priority()
        if (
            self._current_exec_task
            and not self._current_exec_task.done()
            and min_pending_pri is not None
            and self._running_priority is not None
            and min_pending_pri < self._running_priority
        ):
            self.logger.info(
                f"[调度] 发现更高优先任务(min={min_pending_pri}) < 运行中优先({self._running_priority})，触发抢占"
            )
            self._current_exec_task.cancel()
            # 让出控制权，确保取消信号传递
            await asyncio.sleep(0)
            if self._current_task_meta:
                await self._task_queue.push_task(self._current_task_meta)
            self._current_exec_task = None
            self._current_task_meta = None
            self._running_priority = None

    async def _cleanup_finished_task(self) -> None:
        """当任务完成时进行收尾和状态重置。"""
        if self._current_exec_task and self._current_exec_task.done():
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._current_exec_task
            self._current_exec_task = None
            self._current_task_meta = None
            self._running_priority = None

    async def _execute_task(self, task_meta: RunnerTask) -> None:
        """执行单个任务目标。支持被取消以实现抢占。"""
        if not (self.mcp_client and self.llm_planner):
            return
        report_each_step = bool(self.agent_cfg.get("report_each_step", True))
        tools_meta = await self.mcp_client.get_tools_metadata()

        async def _call_tool(tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
            result = await self.mcp_client.call_tool_directly(tool_name, arguments)
            if report_each_step:
                status = "成功" if result.get("success") else f"失败: {result.get('error', '未知错误')}"
                await self._send_text_to_core(f"[Maicraft] 执行工具：{tool_name} 参数={arguments} 结果={status}")
            return result

        try:
            async with self._exec_lock:
                await self._send_text_to_core(f"[Maicraft] 开始执行（{task_meta.source}）：{task_meta.goal}")
                plan_result = await self.llm_planner.plan_and_execute(
                    user_input=task_meta.goal,
                    mcp_tools=tools_meta,
                    call_tool=_call_tool,
                    max_steps_override=self._select_max_steps(task_meta.source),
                )
            final_text = plan_result.get("final") or plan_result.get("error") or "(无最终说明)"
            await self._send_text_to_core(f"[Maicraft] 完成：{final_text}")
        except asyncio.CancelledError:
            # 被高优先任务抢占：使用异步fire-and-forget避免在取消态下阻塞
            try:
                asyncio.create_task(
                    self._send_text_to_core(f"[Maicraft] 任务被中断，稍后将继续：{task_meta.goal[:40]}")
                )
            except Exception as e:
                self.logger.error(f"[执行任务] 发送中断消息失败: {e}", exc_info=True)
            raise
        except Exception as e:
            self.logger.error(f"[执行任务] 异常: {e}")
            await self._send_text_to_core(f"[Maicraft] 任务失败：{str(e)}")

    # 内部工具
    def _extract_text_from_message(self, message: MessageBase) -> Optional[str]:
        segment = message.message_segment
        if segment.type == "text" and isinstance(segment.data, str):
            return segment.data.strip()
        if segment.type == "seglist" and isinstance(segment.data, list):
            for seg in segment.data:
                if hasattr(seg, "type") and seg.type == "text" and hasattr(seg, "data"):
                    return str(seg.data).strip()
        self.logger.warning(f"收到不支持的消息格式: type='{segment.type}'，已忽略。")
        return None

    def _append_chat(self, text: str) -> None:
        if not text:
            return
        self._chat_history.append(text)
        if len(self._chat_history) > self._chat_history_limit:
            self._chat_history = self._chat_history[-self._chat_history_limit :]

    async def _send_text_to_core(self, text: str) -> None:
        try:
            message = self._build_text_message(text)
            await self.core.send_to_maicore(message)
        except Exception as e:
            self.logger.error(f"发送文本到 MaiCore 失败: {e}")

    def _build_text_message(self, text: str) -> MessageBase:
        now = time.time()
        message_id = f"maicraft_{int(now * 1000)}_{uuid.uuid4().hex[:6]}"
        user_info = UserInfo(
            platform=self.core.platform,
            user_id=self.agent_cfg.get("user_id", "maicraft_agent"),
            user_nickname=self.agent_cfg.get("user_nickname", "MaicraftAgent"),
            user_cardname=self.agent_cfg.get("user_cardname", "MaicraftAgent"),
        )
        group_info: Optional[GroupInfo] = None
        group_cfg = self.agent_cfg.get("group", {}) if isinstance(self.agent_cfg, dict) else {}
        if group_cfg and group_cfg.get("enabled", False):
            group_info = GroupInfo(
                platform=self.core.platform,
                group_id=group_cfg.get("group_id", 0),
                group_name=group_cfg.get("group_name", "default"),
            )

        format_info = FormatInfo(content_format=["text"], accept_format=["text"])
        message_info = BaseMessageInfo(
            platform=self.core.platform,
            message_id=message_id,
            time=now,
            user_info=user_info,
            group_info=group_info,
            template_info=None,
            format_info=format_info,
            additional_config={"source": "maicraft_plugin", "maimcore_reply_probability_gain": 0},
        )
        message_segment = Seg(type="text", data=text)
        return MessageBase(message_info=message_info, message_segment=message_segment, raw_message=text)

    # ---- 工具方法 ----

    def _select_max_steps(self, source: str) -> Optional[int]:
        """按来源选择最大步数覆盖。"""
        try:
            if source == "maicore":
                value = self.agent_cfg.get("max_steps_maicore")
            else:
                value = self.agent_cfg.get("max_steps_auto")
            if value is not None:
                return int(value)
            # 回退到通用 max_steps（若未设置则 None 表示使用 LLMPlanner 默认值）
            generic = self.agent_cfg.get("max_steps")
            return int(generic) if generic is not None else None
        except Exception:
            return None

    async def _split_goal_with_llm(self, goal: str) -> List[str]:
        """使用 LLMPlanner + MCP 工具上下文进行目标拆解。"""
        if not self.llm_planner:
            return [goal]
        try:
            tool_names = []
            if self.mcp_client and hasattr(self.mcp_client, "list_available_tools"):
                tool_names = await self.mcp_client.list_available_tools()
            max_steps = int(self.agent_cfg.get("split_max_steps", self.agent_cfg.get("max_steps", 5)))
            steps = await self.llm_planner.decompose_goal(goal=goal, max_steps=max_steps, tool_names=tool_names)
            return steps or [goal]
        except Exception:
            return [goal]
