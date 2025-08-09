"""
任务队列管理模块

负责管理Maicraft代理的任务队列，包括任务的入队、出队、优先级管理等功能。
"""

import asyncio
import time
import uuid
import heapq
from dataclasses import dataclass
from typing import Any, Dict, Optional, List, Tuple, Callable, Awaitable

from src.utils.logger import get_logger


@dataclass
class RunnerTask:
    """调度器中的任务单元。"""

    goal: str
    source: str  # 'maicore' | 'auto'
    priority: int
    task_id: str


class TaskQueue:
    """任务队列管理器，负责任务的调度和优先级管理。"""

    def __init__(self, agent_cfg: Dict[str, Any]) -> None:
        """
        初始化任务队列

        Args:
            agent_cfg: 代理配置字典
        """
        self.agent_cfg = agent_cfg
        self.logger = get_logger("MaicraftTaskQueue")
        # LLM 拆分器（异步），由外部注入
        self._async_splitter: Optional[Callable[[str], Awaitable[List[str]]]] = None

        # 任务调度结构
        self._task_heap: List[Tuple[int, int, RunnerTask]] = []  # (priority, seq, task)
        self._heap_lock = asyncio.Lock()
        self._seq_counter: int = 0
        self._new_task_event = asyncio.Event()

        # 优先级定义：数值越小优先级越高
        self.PRIORITY_MAICORE = int(agent_cfg.get("priority_maicore", 0))
        self.PRIORITY_NORMAL = int(agent_cfg.get("priority_normal", 10))

    async def enqueue_goal_with_split(self, goal: str, *, priority: int, source: str) -> None:
        """使用注入的 LLM 拆分器将目标拆分为子任务并入队。若未注入则不拆分。"""
        steps: List[str] = [goal]
        if self._async_splitter is not None:
            try:
                steps = await self._async_splitter(goal) or [goal]
            except Exception as e:
                self.logger.error(f"[拆分] 异常，回退为单一任务: {e}")
                steps = [goal]
        for step in steps:
            await self.push_task(
                RunnerTask(
                    goal=step,
                    source=source,
                    priority=priority,
                    task_id=f"task_{int(time.time() * 1000)}_{uuid.uuid4().hex[:6]}",
                )
            )

    async def push_task(self, task_meta: RunnerTask) -> None:
        """将任务推入队列。"""
        async with self._heap_lock:
            self._seq_counter += 1
            heapq.heappush(self._task_heap, (task_meta.priority, self._seq_counter, task_meta))
            self.logger.info(f"[入队] priority={task_meta.priority} source={task_meta.source} goal={task_meta.goal}")
            self._new_task_event.set()

    async def pop_next_task(self) -> Optional[RunnerTask]:
        """从队列中取出下一个任务。"""
        async with self._heap_lock:
            if not self._task_heap:
                return None
            priority, _, task_meta = heapq.heappop(self._task_heap)
            self.logger.info(f"[出队] priority={priority} source={task_meta.source} goal={task_meta.goal}")
            return task_meta

    async def peek_min_priority(self) -> Optional[int]:
        """查看队列中最高优先级（最小数值）。"""
        async with self._heap_lock:
            return self._task_heap[0][0] if self._task_heap else None

    async def is_queue_idle(self) -> bool:
        """检查队列是否为空。"""
        async with self._heap_lock:
            return len(self._task_heap) == 0

    def get_new_task_event(self) -> asyncio.Event:
        """获取新任务事件，用于外部监听。"""
        return self._new_task_event

    def set_splitter(self, splitter: Optional[Callable[[str], Awaitable[List[str]]]]) -> None:
        """注入/替换基于 LLM 的任务拆分器。传入 None 可禁用拆分。"""
        self._async_splitter = splitter
