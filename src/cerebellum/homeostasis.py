"""
稳态系统 - 负责监控系统健康状态

该模块提供了系统状态监控和健康检查机制，
包括监控和报告神经元的状态和系统资源使用情况。
"""

import asyncio
import time
import psutil
import platform
import logging
from typing import Dict, Any, Optional, List, Set, Tuple, Callable
from enum import Enum, auto

from src.cerebellum.neural_trace import get_logger, NeuronType
from src.cerebellum.immune_system import NeuralException, SystemException, get_immune_system

# 获取日志器
logger = get_logger("Homeostasis", NeuronType.SYSTEM)


class HealthStatus(Enum):
    """健康状态枚举"""

    HEALTHY = auto()  # 健康
    WARNING = auto()  # 警告
    CRITICAL = auto()  # 严重
    UNKNOWN = auto()  # 未知


class HealthCheck:
    """健康检查 - 单个检查项"""

    def __init__(
        self,
        name: str,
        check_func: Callable[[], Tuple[HealthStatus, str]],
        description: str = "",
        interval: float = 60.0,
    ):
        """初始化健康检查

        Args:
            name: 检查名称
            check_func: 检查函数，返回(状态, 消息)
            description: 检查描述
            interval: 检查间隔（秒）
        """
        self.name = name
        self.check_func = check_func
        self.description = description
        self.interval = interval
        self.last_check_time = 0
        self.last_status = HealthStatus.UNKNOWN
        self.last_message = "尚未执行检查"
        self.consecutive_warnings = 0
        self.consecutive_criticals = 0

    async def run(self) -> Tuple[HealthStatus, str]:
        """执行健康检查

        Returns:
            (健康状态, 消息)
        """
        self.last_check_time = time.time()

        try:
            status, message = self.check_func()
            self.last_status = status
            self.last_message = message

            # 更新连续状态计数
            if status == HealthStatus.WARNING:
                self.consecutive_warnings += 1
                self.consecutive_criticals = 0
            elif status == HealthStatus.CRITICAL:
                self.consecutive_criticals += 1
                self.consecutive_warnings = 0
            else:
                self.consecutive_warnings = 0
                self.consecutive_criticals = 0

            return status, message
        except Exception as e:
            error_message = f"健康检查执行失败: {str(e)}"
            logger.error(error_message, exc_info=e)
            self.last_status = HealthStatus.UNKNOWN
            self.last_message = error_message
            return HealthStatus.UNKNOWN, error_message

    def get_stats(self) -> Dict[str, Any]:
        """获取健康检查统计信息

        Returns:
            统计信息
        """
        return {
            "name": self.name,
            "description": self.description,
            "interval": self.interval,
            "last_check_time": self.last_check_time,
            "last_status": self.last_status.name,
            "last_message": self.last_message,
            "consecutive_warnings": self.consecutive_warnings,
            "consecutive_criticals": self.consecutive_criticals,
        }


class Homeostasis:
    """稳态系统 - 系统状态监控器"""

    def __init__(self):
        """初始化稳态系统"""
        self.health_checks: Dict[str, HealthCheck] = {}
        self.status_listeners: List[Callable[[str, HealthStatus, str], None]] = []
        self.running = False
        self.monitor_task = None
        self.last_system_stats: Dict[str, Any] = {}
        self.check_interval = 5.0  # 秒

    def register_health_check(self, health_check: HealthCheck) -> None:
        """注册健康检查

        Args:
            health_check: 健康检查
        """
        self.health_checks[health_check.name] = health_check
        logger.info(f"已注册健康检查: {health_check.name}")

    def register_status_listener(self, listener: Callable[[str, HealthStatus, str], None]) -> None:
        """注册状态监听器

        Args:
            listener: 监听器函数，接收(检查名称, 状态, 消息)
        """
        self.status_listeners.append(listener)
        logger.info(f"已注册状态监听器: {listener.__name__}")

    def create_system_health_checks(self) -> None:
        """创建默认的系统健康检查"""
        # CPU使用率检查
        self.register_health_check(
            HealthCheck(
                name="cpu_usage",
                check_func=self._check_cpu_usage,
                description="监控CPU使用率",
                interval=30.0,
            )
        )

        # 内存使用率检查
        self.register_health_check(
            HealthCheck(
                name="memory_usage",
                check_func=self._check_memory_usage,
                description="监控内存使用率",
                interval=30.0,
            )
        )

        # 磁盘使用率检查
        self.register_health_check(
            HealthCheck(
                name="disk_usage",
                check_func=self._check_disk_usage,
                description="监控磁盘使用率",
                interval=300.0,
            )
        )

    def _check_cpu_usage(self) -> Tuple[HealthStatus, str]:
        """检查CPU使用率

        Returns:
            (健康状态, 消息)
        """
        cpu_percent = psutil.cpu_percent(interval=1)

        if cpu_percent > 90:
            return HealthStatus.CRITICAL, f"CPU使用率过高: {cpu_percent}%"
        elif cpu_percent > 70:
            return HealthStatus.WARNING, f"CPU使用率较高: {cpu_percent}%"
        else:
            return HealthStatus.HEALTHY, f"CPU使用率正常: {cpu_percent}%"

    def _check_memory_usage(self) -> Tuple[HealthStatus, str]:
        """检查内存使用率

        Returns:
            (健康状态, 消息)
        """
        memory = psutil.virtual_memory()
        memory_percent = memory.percent

        if memory_percent > 90:
            return HealthStatus.CRITICAL, f"内存使用率过高: {memory_percent}%"
        elif memory_percent > 80:
            return HealthStatus.WARNING, f"内存使用率较高: {memory_percent}%"
        else:
            return HealthStatus.HEALTHY, f"内存使用率正常: {memory_percent}%"

    def _check_disk_usage(self) -> Tuple[HealthStatus, str]:
        """检查磁盘使用率

        Returns:
            (健康状态, 消息)
        """
        disk = psutil.disk_usage("/")
        disk_percent = disk.percent

        if disk_percent > 95:
            return HealthStatus.CRITICAL, f"磁盘使用率过高: {disk_percent}%"
        elif disk_percent > 85:
            return HealthStatus.WARNING, f"磁盘使用率较高: {disk_percent}%"
        else:
            return HealthStatus.HEALTHY, f"磁盘使用率正常: {disk_percent}%"

    async def _monitor_loop(self) -> None:
        """监控循环"""
        try:
            while self.running:
                # 更新系统统计信息
                self.last_system_stats = self._get_system_stats()

                # 执行到期的健康检查
                current_time = time.time()
                for name, check in self.health_checks.items():
                    # 检查是否到达检查间隔
                    if current_time - check.last_check_time >= check.interval:
                        status, message = await check.run()

                        # 通知状态监听器
                        for listener in self.status_listeners:
                            try:
                                listener(name, status, message)
                            except Exception as e:
                                logger.error(f"状态监听器 {listener.__name__} 执行出错: {e}")

                        # 记录日志
                        if status == HealthStatus.CRITICAL:
                            logger.error(f"健康检查 {name} 失败: {message}")
                        elif status == HealthStatus.WARNING:
                            logger.warning(f"健康检查 {name} 警告: {message}")
                        else:
                            logger.debug(f"健康检查 {name} 通过: {message}")

                # 等待下一个检查周期
                await asyncio.sleep(self.check_interval)

        except asyncio.CancelledError:
            logger.info("健康监控循环已取消")
        except Exception as e:
            logger.error(f"健康监控循环出错: {e}", exc_info=e)
            # 上报到免疫系统
            immune_system = get_immune_system()
            if immune_system:
                immune_system.handle_exception(
                    SystemException(
                        "稳态系统监控循环异常",
                        original_exception=e,
                        recovery_hint="检查稳态系统监控代码是否有错误",
                    )
                )

    async def start(self) -> None:
        """启动稳态系统"""
        if self.running:
            logger.warning("稳态系统已经在运行")
            return

        logger.info("正在启动稳态系统...")
        self.running = True

        # 创建默认的系统健康检查
        if not self.health_checks:
            self.create_system_health_checks()

        # 启动监控循环
        self.monitor_task = asyncio.create_task(self._monitor_loop())

        logger.info("稳态系统已启动")

    async def stop(self) -> None:
        """停止稳态系统"""
        if not self.running:
            logger.warning("稳态系统未在运行")
            return

        logger.info("正在停止稳态系统...")
        self.running = False

        # 取消监控任务
        if self.monitor_task:
            self.monitor_task.cancel()
            try:
                await self.monitor_task
            except asyncio.CancelledError:
                pass
            self.monitor_task = None

        logger.info("稳态系统已停止")

    def _get_system_stats(self) -> Dict[str, Any]:
        """获取系统统计信息

        Returns:
            系统统计信息
        """
        try:
            stats = {
                "cpu": {
                    "percent": psutil.cpu_percent(interval=None),
                    "count": psutil.cpu_count(),
                },
                "memory": {
                    "total": psutil.virtual_memory().total,
                    "available": psutil.virtual_memory().available,
                    "percent": psutil.virtual_memory().percent,
                },
                "disk": {
                    "total": psutil.disk_usage("/").total,
                    "free": psutil.disk_usage("/").free,
                    "percent": psutil.disk_usage("/").percent,
                },
                "network": {
                    "connections": len(psutil.net_connections()),
                },
                "system": {
                    "platform": platform.system(),
                    "version": platform.version(),
                    "python": platform.python_version(),
                },
                "process": {
                    "pid": psutil.Process().pid,
                    "memory_percent": psutil.Process().memory_percent(),
                    "cpu_percent": psutil.Process().cpu_percent(interval=None),
                    "threads": psutil.Process().num_threads(),
                },
            }
            return stats
        except Exception as e:
            logger.error(f"获取系统统计信息出错: {e}")
            return {
                "error": str(e),
                "timestamp": time.time(),
            }

    def get_health_status(self) -> Dict[str, Any]:
        """获取系统健康状态

        Returns:
            健康状态信息
        """
        status = {
            "overall": HealthStatus.HEALTHY.name,
            "checks": {},
        }

        critical_count = 0
        warning_count = 0

        for name, check in self.health_checks.items():
            check_status = check.get_stats()
            status["checks"][name] = check_status

            if check.last_status == HealthStatus.CRITICAL:
                critical_count += 1
            elif check.last_status == HealthStatus.WARNING:
                warning_count += 1

        # 计算总体状态
        if critical_count > 0:
            status["overall"] = HealthStatus.CRITICAL.name
        elif warning_count > 0:
            status["overall"] = HealthStatus.WARNING.name

        return status

    def get_stats(self) -> Dict[str, Any]:
        """获取稳态系统统计信息

        Returns:
            统计信息
        """
        stats = {
            "running": self.running,
            "health_checks_count": len(self.health_checks),
            "listeners_count": len(self.status_listeners),
            "health_status": self.get_health_status(),
            "system_stats": self.last_system_stats,
        }
        return stats


# 全局稳态系统实例
_homeostasis: Optional[Homeostasis] = None


def get_homeostasis() -> Homeostasis:
    """获取全局稳态系统实例

    Returns:
        全局稳态系统实例
    """
    global _homeostasis
    if _homeostasis is None:
        _homeostasis = Homeostasis()
    return _homeostasis
