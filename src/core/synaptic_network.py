from typing import Any, Dict, Callable, List, Optional, Set, Type, Union, Awaitable
import asyncio
import logging
import time
from collections import defaultdict

from src.signals.neural_signal import NeuralSignal, SignalType, SignalPriority

logger = logging.getLogger(__name__)

# 回调函数类型定义
SignalCallback = Callable[[NeuralSignal], None]
AsyncSignalCallback = Callable[[NeuralSignal], Awaitable[Any]]


class SignalFilter:
    """信号过滤器 - 定义哪些信号会被传递到特定的接收器"""

    def __init__(
        self,
        signal_types: Optional[List[SignalType]] = None,
        source_patterns: Optional[List[str]] = None,
        target_patterns: Optional[List[str]] = None,
        min_priority: Optional[SignalPriority] = None,
        custom_filter: Optional[Callable[[NeuralSignal], bool]] = None,
    ):
        self.signal_types = set(signal_types) if signal_types else None
        self.source_patterns = source_patterns
        self.target_patterns = target_patterns
        self.min_priority = min_priority
        self.custom_filter = custom_filter

    def match(self, signal: NeuralSignal) -> bool:
        """检查信号是否匹配过滤条件"""
        # 检查信号类型
        if self.signal_types and signal.signal_type not in self.signal_types:
            return False

        # 检查源匹配
        if self.source_patterns:
            if not any(pattern in signal.source for pattern in self.source_patterns):
                return False

        # 检查目标匹配
        if self.target_patterns and signal.target:
            if not any(pattern in signal.target for pattern in self.target_patterns):
                return False

        # 检查优先级
        if self.min_priority and signal.priority.value < self.min_priority.value:
            return False

        # 运行自定义过滤器
        if self.custom_filter and not self.custom_filter(signal):
            return False

        return True


class SynapticNetwork:
    """神经突触网络 - 负责系统内部信号的传递与路由"""

    def __init__(self):
        self._receptors = defaultdict(list)  # 接收器集合，按信号类型分组
        self._async_receptors = defaultdict(list)  # 异步接收器集合
        self._global_receptors = []  # 全局接收器（接收所有信号）
        self._async_global_receptors = []  # 异步全局接收器
        self._stats = {
            "signals_processed": 0,
            "signals_by_type": defaultdict(int),
            "signals_by_priority": defaultdict(int),
            "average_process_time": 0,
            "total_process_time": 0,
        }
        self._is_active = False
        self._processing_queue = asyncio.Queue()
        self._processing_task = None

    async def start(self):
        """启动神经突触网络"""
        if self._is_active:
            return

        self._is_active = True
        self._processing_task = asyncio.create_task(self._process_queue())
        logger.info("神经突触网络已启动")

    async def stop(self):
        """停止神经突触网络"""
        if not self._is_active:
            return

        self._is_active = False
        if self._processing_task:
            self._processing_task.cancel()
            try:
                await self._processing_task
            except asyncio.CancelledError:
                pass
        logger.info("神经突触网络已停止")

    def register_receptor(
        self, callback: SignalCallback, signal_filter: Optional[SignalFilter] = None, is_async: bool = False
    ) -> str:
        """注册信号接收器

        Args:
            callback: 接收器回调函数
            signal_filter: 信号过滤器，定义哪些信号会传递给接收器
            is_async: 是否为异步回调

        Returns:
            接收器ID
        """
        receptor_id = str(id(callback))
        receptor = {"id": receptor_id, "callback": callback, "filter": signal_filter, "created_at": time.time()}

        if signal_filter and signal_filter.signal_types:
            # 按特定信号类型注册
            for signal_type in signal_filter.signal_types:
                if is_async:
                    self._async_receptors[signal_type].append(receptor)
                else:
                    self._receptors[signal_type].append(receptor)
        else:
            # 注册为全局接收器
            if is_async:
                self._async_global_receptors.append(receptor)
            else:
                self._global_receptors.append(receptor)

        return receptor_id

    def unregister_receptor(self, receptor_id: str) -> bool:
        """取消注册信号接收器

        Args:
            receptor_id: 接收器ID

        Returns:
            是否成功取消注册
        """
        # 在所有地方查找并删除接收器
        removed = False

        # 从类型特定接收器中移除
        for signal_type in SignalType:
            for receptors_list in [self._receptors[signal_type], self._async_receptors[signal_type]]:
                for i, receptor in enumerate(receptors_list):
                    if receptor["id"] == receptor_id:
                        receptors_list.pop(i)
                        removed = True
                        break

        # 从全局接收器中移除
        for receptors_list in [self._global_receptors, self._async_global_receptors]:
            for i, receptor in enumerate(receptors_list):
                if receptor["id"] == receptor_id:
                    receptors_list.pop(i)
                    removed = True
                    break

        return removed

    async def transmit(self, signal: NeuralSignal) -> None:
        """传输信号到神经网络

        Args:
            signal: 要传输的神经信号
        """
        if not self._is_active:
            logger.warning("尝试传输信号但神经突触网络未启动")
            return

        await self._processing_queue.put(signal)

    async def _process_queue(self) -> None:
        """处理信号队列的后台任务"""
        while self._is_active:
            try:
                signal = await self._processing_queue.get()
                await self._process_signal(signal)
                self._processing_queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"处理信号队列时出错: {e}")

    async def _process_signal(self, signal: NeuralSignal) -> None:
        """处理单个信号，将其分发给匹配的接收器"""
        start_time = time.time()

        # 更新统计信息
        self._stats["signals_processed"] += 1
        self._stats["signals_by_type"][signal.signal_type.name] += 1
        self._stats["signals_by_priority"][signal.priority.name] += 1

        # 获取针对特定类型的接收器
        type_receptors = self._receptors[signal.signal_type]
        async_type_receptors = self._async_receptors[signal.signal_type]

        # 同步处理匹配的接收器
        for receptor in self._global_receptors + type_receptors:
            try:
                if not receptor["filter"] or receptor["filter"].match(signal):
                    receptor["callback"](signal)
            except Exception as e:
                logger.error(f"调用接收器时出错: {e}, 接收器ID: {receptor['id']}")

        # 异步处理匹配的接收器
        async_tasks = []
        for receptor in self._async_global_receptors + async_type_receptors:
            if not receptor["filter"] or receptor["filter"].match(signal):
                async_tasks.append(self._call_async_receptor(receptor["callback"], signal, receptor["id"]))

        if async_tasks:
            await asyncio.gather(*async_tasks, return_exceptions=True)

        # 更新处理时间统计
        process_time = time.time() - start_time
        self._stats["total_process_time"] += process_time
        self._stats["average_process_time"] = self._stats["total_process_time"] / self._stats["signals_processed"]

    async def _call_async_receptor(self, callback, signal, receptor_id):
        """调用异步接收器并处理异常"""
        try:
            await callback(signal)
        except Exception as e:
            logger.error(f"调用异步接收器时出错: {e}, 接收器ID: {receptor_id}")

    def get_stats(self) -> Dict[str, Any]:
        """获取神经突触网络的统计信息"""
        return dict(self._stats)
