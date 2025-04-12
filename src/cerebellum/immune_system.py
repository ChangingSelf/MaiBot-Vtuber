"""
免疫系统 - 负责系统异常处理

该模块提供了全局异常处理和故障隔离机制，
针对不同类型的神经元实现不同的恢复策略。
"""

import asyncio
import functools
import sys
import time
from enum import Enum, auto
from typing import Dict, Any, Optional, List, Callable, TypeVar, Set, Tuple

from src.cerebellum.neural_trace import get_logger, NeuronType

# 定义类型变量
T = TypeVar("T")
F = TypeVar("F", bound=Callable)

# 获取日志器
logger = get_logger("ImmuneSystem", NeuronType.SYSTEM)


class NeuralExceptionType(Enum):
    """神经异常类型"""

    SENSOR = auto()  # 感觉神经元异常
    ACTUATOR = auto()  # 运动神经元异常
    CONNECTOR = auto()  # 连接器异常
    NETWORK = auto()  # 网络通信异常
    CONFIG = auto()  # 配置异常
    RESOURCE = auto()  # 资源异常
    SYSTEM = auto()  # 系统异常
    UNKNOWN = auto()  # 未知异常


class RecoveryStrategy(Enum):
    """恢复策略类型"""

    RETRY = auto()  # 重试策略
    DEGRADATION = auto()  # 降级策略
    ISOLATION = auto()  # 隔离策略
    RESTART = auto()  # 重启策略


class NeuralException(Exception):
    """神经系统基础异常类"""

    def __init__(
        self,
        message: str,
        exception_type: NeuralExceptionType = NeuralExceptionType.UNKNOWN,
        original_exception: Optional[Exception] = None,
        neuron_name: Optional[str] = None,
        recovery_hint: Optional[str] = None,
    ):
        """初始化神经异常

        Args:
            message: 异常消息
            exception_type: 异常类型
            original_exception: 原始异常
            neuron_name: 相关神经元名称
            recovery_hint: 恢复提示
        """
        self.exception_type = exception_type
        self.original_exception = original_exception
        self.neuron_name = neuron_name
        self.recovery_hint = recovery_hint
        self.timestamp = time.time()

        # 构建完整消息
        full_message = f"[{exception_type.name}]"
        if neuron_name:
            full_message += f" [{neuron_name}]"
        full_message += f": {message}"

        if original_exception:
            full_message += f" | 原始异常: {str(original_exception)}"

        if recovery_hint:
            full_message += f" | 恢复提示: {recovery_hint}"

        super().__init__(full_message)


class SensorException(NeuralException):
    """感觉神经元异常"""

    def __init__(
        self,
        message: str,
        original_exception: Optional[Exception] = None,
        neuron_name: Optional[str] = None,
        recovery_hint: Optional[str] = None,
    ):
        """初始化感觉神经元异常

        Args:
            message: 异常消息
            original_exception: 原始异常
            neuron_name: 相关神经元名称
            recovery_hint: 恢复提示
        """
        super().__init__(
            message,
            NeuralExceptionType.SENSOR,
            original_exception,
            neuron_name,
            recovery_hint,
        )


class ActuatorException(NeuralException):
    """运动神经元异常"""

    def __init__(
        self,
        message: str,
        original_exception: Optional[Exception] = None,
        neuron_name: Optional[str] = None,
        recovery_hint: Optional[str] = None,
    ):
        """初始化运动神经元异常

        Args:
            message: 异常消息
            original_exception: 原始异常
            neuron_name: 相关神经元名称
            recovery_hint: 恢复提示
        """
        super().__init__(
            message,
            NeuralExceptionType.ACTUATOR,
            original_exception,
            neuron_name,
            recovery_hint,
        )


class ConnectorException(NeuralException):
    """连接器异常"""

    def __init__(
        self,
        message: str,
        original_exception: Optional[Exception] = None,
        neuron_name: Optional[str] = None,
        recovery_hint: Optional[str] = None,
    ):
        """初始化连接器异常

        Args:
            message: 异常消息
            original_exception: 原始异常
            neuron_name: 相关神经元名称
            recovery_hint: 恢复提示
        """
        super().__init__(
            message,
            NeuralExceptionType.CONNECTOR,
            original_exception,
            neuron_name,
            recovery_hint,
        )


class NetworkException(NeuralException):
    """网络通信异常"""

    def __init__(
        self,
        message: str,
        original_exception: Optional[Exception] = None,
        neuron_name: Optional[str] = None,
        recovery_hint: Optional[str] = None,
    ):
        """初始化网络通信异常

        Args:
            message: 异常消息
            original_exception: 原始异常
            neuron_name: 相关神经元名称
            recovery_hint: 恢复提示
        """
        super().__init__(
            message,
            NeuralExceptionType.NETWORK,
            original_exception,
            neuron_name,
            recovery_hint,
        )


class ConfigException(NeuralException):
    """配置异常"""

    def __init__(
        self,
        message: str,
        original_exception: Optional[Exception] = None,
        neuron_name: Optional[str] = None,
        recovery_hint: Optional[str] = None,
    ):
        """初始化配置异常

        Args:
            message: 异常消息
            original_exception: 原始异常
            neuron_name: 相关神经元名称
            recovery_hint: 恢复提示
        """
        super().__init__(
            message,
            NeuralExceptionType.CONFIG,
            original_exception,
            neuron_name,
            recovery_hint,
        )


class ResourceException(NeuralException):
    """资源异常"""

    def __init__(
        self,
        message: str,
        original_exception: Optional[Exception] = None,
        neuron_name: Optional[str] = None,
        recovery_hint: Optional[str] = None,
    ):
        """初始化资源异常

        Args:
            message: 异常消息
            original_exception: 原始异常
            neuron_name: 相关神经元名称
            recovery_hint: 恢复提示
        """
        super().__init__(
            message,
            NeuralExceptionType.RESOURCE,
            original_exception,
            neuron_name,
            recovery_hint,
        )


class SystemException(NeuralException):
    """系统异常"""

    def __init__(
        self,
        message: str,
        original_exception: Optional[Exception] = None,
        neuron_name: Optional[str] = None,
        recovery_hint: Optional[str] = None,
    ):
        """初始化系统异常

        Args:
            message: 异常消息
            original_exception: 原始异常
            neuron_name: 相关神经元名称
            recovery_hint: 恢复提示
        """
        super().__init__(
            message,
            NeuralExceptionType.SYSTEM,
            original_exception,
            neuron_name,
            recovery_hint,
        )


class RecoveryConfig:
    """恢复策略配置"""

    def __init__(
        self,
        strategy: RecoveryStrategy,
        max_attempts: int = 3,
        delay_seconds: float = 1.0,
        backoff_factor: float = 2.0,
        fallback_function: Optional[Callable] = None,
    ):
        """初始化恢复策略配置

        Args:
            strategy: 恢复策略类型
            max_attempts: 最大尝试次数
            delay_seconds: 初始延迟时间（秒）
            backoff_factor: 退避因子（每次重试延迟时间增加的倍数）
            fallback_function: 降级时使用的回退函数
        """
        self.strategy = strategy
        self.max_attempts = max_attempts
        self.delay_seconds = delay_seconds
        self.backoff_factor = backoff_factor
        self.fallback_function = fallback_function


class ImmuneSystem:
    """免疫系统 - 负责异常处理和恢复策略"""

    def __init__(self):
        """初始化免疫系统"""
        self.exception_handlers: Dict[NeuralExceptionType, List[Callable]] = {
            ex_type: [] for ex_type in NeuralExceptionType
        }
        self.exception_history: List[Tuple[float, NeuralException]] = []
        self.max_history_size = 100
        self.quarantined_neurons: Set[str] = set()

        # 神经元恢复策略配置
        self.recovery_configs: Dict[str, RecoveryConfig] = {}

        # 神经元失败计数
        self.failure_counters: Dict[str, int] = {}

        # 神经元最后失败时间
        self.last_failure_time: Dict[str, float] = {}

        # 神经元健康状态
        self.neuron_health: Dict[str, float] = {}  # 0.0-1.0, 1.0为完全健康

    def register_exception_handler(
        self, exception_type: NeuralExceptionType, handler: Callable[[NeuralException], None]
    ) -> None:
        """注册异常处理器

        Args:
            exception_type: 要处理的异常类型
            handler: 处理函数
        """
        self.exception_handlers[exception_type].append(handler)
        logger.info(f"已注册异常处理器: {exception_type.name} -> {handler.__name__}")

    def handle_exception(self, exception: NeuralException) -> None:
        """处理神经异常

        Args:
            exception: 要处理的异常
        """
        # 记录异常
        self.exception_history.append((time.time(), exception))
        if len(self.exception_history) > self.max_history_size:
            self.exception_history = self.exception_history[-self.max_history_size :]

        # 记录日志
        logger.error(str(exception), exc_info=exception.original_exception)

        # 更新神经元健康状态
        if exception.neuron_name:
            self._update_neuron_health(exception.neuron_name, -0.2)  # 每次异常降低健康值

            # 增加失败计数
            if exception.neuron_name not in self.failure_counters:
                self.failure_counters[exception.neuron_name] = 0
            self.failure_counters[exception.neuron_name] += 1

            # 记录最后失败时间
            self.last_failure_time[exception.neuron_name] = time.time()

        # 调用相应类型的处理器
        for handler in self.exception_handlers[exception.exception_type]:
            try:
                handler(exception)
            except Exception as e:
                logger.error(f"异常处理器出错: {handler.__name__}, 错误: {e}")

        # 调用通用处理器
        for handler in self.exception_handlers[NeuralExceptionType.UNKNOWN]:
            try:
                handler(exception)
            except Exception as e:
                logger.error(f"通用异常处理器出错: {handler.__name__}, 错误: {e}")

        # 应用恢复策略
        if exception.neuron_name and exception.neuron_name in self.recovery_configs:
            self._apply_recovery_strategy(exception)

    def _apply_recovery_strategy(self, exception: NeuralException) -> None:
        """应用恢复策略

        Args:
            exception: 要处理的异常
        """
        neuron_name = exception.neuron_name
        if not neuron_name:
            return

        config = self.recovery_configs.get(neuron_name)
        if not config:
            return

        # 获取失败计数
        failure_count = self.failure_counters.get(neuron_name, 0)

        # 如果超过最大尝试次数，执行相应策略
        if failure_count > config.max_attempts:
            if config.strategy == RecoveryStrategy.ISOLATION:
                self.quarantine_neuron(neuron_name)
                logger.warning(f"神经元 {neuron_name} 失败次数超过阈值，已隔离")
            elif config.strategy == RecoveryStrategy.DEGRADATION:
                if config.fallback_function:
                    try:
                        logger.info(f"神经元 {neuron_name} 降级为备用功能")
                        config.fallback_function()
                    except Exception as e:
                        logger.error(f"降级功能执行失败: {e}")

    def register_recovery_config(self, neuron_name: str, recovery_config: RecoveryConfig) -> None:
        """注册神经元恢复策略配置

        Args:
            neuron_name: 神经元名称
            recovery_config: 恢复策略配置
        """
        self.recovery_configs[neuron_name] = recovery_config
        logger.info(f"已注册神经元 {neuron_name} 恢复策略: {recovery_config.strategy.name}")

    def quarantine_neuron(self, neuron_name: str) -> None:
        """隔离神经元

        Args:
            neuron_name: 要隔离的神经元名称
        """
        self.quarantined_neurons.add(neuron_name)
        self._update_neuron_health(neuron_name, -1.0)  # 隔离时健康值降为0
        logger.warning(f"已隔离神经元: {neuron_name}")

    def release_neuron(self, neuron_name: str) -> None:
        """释放被隔离的神经元

        Args:
            neuron_name: 要释放的神经元名称
        """
        if neuron_name in self.quarantined_neurons:
            self.quarantined_neurons.remove(neuron_name)
            self._update_neuron_health(neuron_name, 0.5)  # 释放时健康值回升
            # 重置失败计数
            self.failure_counters[neuron_name] = 0
            logger.info(f"已释放神经元: {neuron_name}")

    def is_quarantined(self, neuron_name: str) -> bool:
        """检查神经元是否被隔离

        Args:
            neuron_name: 神经元名称

        Returns:
            是否被隔离
        """
        return neuron_name in self.quarantined_neurons

    def apply_retry_strategy(self, sensor_name: str, max_retries: int = 3, delay: float = 1.0) -> None:
        """对感知神经元应用重试策略

        Args:
            sensor_name: 感知神经元名称
            max_retries: 最大重试次数
            delay: 重试延迟（秒）
        """
        config = RecoveryConfig(
            strategy=RecoveryStrategy.RETRY,
            max_attempts=max_retries,
            delay_seconds=delay,
            backoff_factor=2.0,
        )
        self.register_recovery_config(sensor_name, config)
        logger.info(f"已为感知神经元 {sensor_name} 应用重试策略: 最大重试 {max_retries} 次, 初始延迟 {delay}秒")

    def apply_degradation_strategy(
        self, actuator_name: str, fallback_function: Callable, max_failures: int = 3
    ) -> None:
        """对运动神经元应用降级策略

        Args:
            actuator_name: 运动神经元名称
            fallback_function: 降级时调用的备用功能
            max_failures: 触发降级的最大失败次数
        """
        config = RecoveryConfig(
            strategy=RecoveryStrategy.DEGRADATION,
            max_attempts=max_failures,
            fallback_function=fallback_function,
        )
        self.register_recovery_config(actuator_name, config)
        logger.info(f"已为运动神经元 {actuator_name} 应用降级策略: 最大失败 {max_failures} 次")

    def _update_neuron_health(self, neuron_name: str, delta: float) -> None:
        """更新神经元健康状态

        Args:
            neuron_name: 神经元名称
            delta: 健康值变化量（可正可负）
        """
        current = self.neuron_health.get(neuron_name, 1.0)
        new_value = max(0.0, min(1.0, current + delta))
        self.neuron_health[neuron_name] = new_value

        # 记录健康状态变化
        if abs(new_value - current) > 0.01:  # 只记录显著变化
            if delta < 0:
                logger.warning(f"神经元 {neuron_name} 健康状态降低: {current:.2f} -> {new_value:.2f}")
            else:
                logger.info(f"神经元 {neuron_name} 健康状态提升: {current:.2f} -> {new_value:.2f}")

    def heal_neuron(self, neuron_name: str, amount: float = 0.1) -> None:
        """提升神经元健康状态

        Args:
            neuron_name: 神经元名称
            amount: 提升量
        """
        if neuron_name not in self.quarantined_neurons:
            self._update_neuron_health(neuron_name, amount)

            # 连续成功恢复一段时间后，重置失败计数
            if self.neuron_health.get(neuron_name, 0) > 0.8:
                self.failure_counters[neuron_name] = 0

    def get_stats(self) -> Dict[str, Any]:
        """获取免疫系统统计信息

        Returns:
            统计信息
        """
        stats = {
            "total_exceptions": len(self.exception_history),
            "quarantined_neurons": len(self.quarantined_neurons),
            "quarantined_neuron_list": list(self.quarantined_neurons),
            "exception_types": {},
            "neuron_health": {k: f"{v:.2f}" for k, v in self.neuron_health.items()},
            "failure_counters": dict(self.failure_counters),
            "recovery_strategies": {k: v.strategy.name for k, v in self.recovery_configs.items()},
        }

        # 统计各类型异常数量
        for _, exception in self.exception_history:
            ex_type = exception.exception_type.name
            if ex_type not in stats["exception_types"]:
                stats["exception_types"][ex_type] = 0
            stats["exception_types"][ex_type] += 1

        return stats


# 全局免疫系统实例
_immune_system: Optional[ImmuneSystem] = None


def get_immune_system() -> ImmuneSystem:
    """获取全局免疫系统实例

    Returns:
        全局免疫系统实例
    """
    global _immune_system
    if _immune_system is None:
        _immune_system = ImmuneSystem()
    return _immune_system


def with_immune_system(
    exception_type: NeuralExceptionType = NeuralExceptionType.UNKNOWN,
    neuron_name: Optional[str] = None,
    recovery_hint: Optional[str] = None,
    max_retries: int = 0,
    retry_delay: float = 1.0,
):
    """装饰器：添加免疫系统保护

    Args:
        exception_type: 默认异常类型
        neuron_name: 相关神经元名称
        recovery_hint: 恢复提示
        max_retries: 最大重试次数
        retry_delay: 重试延迟（秒）

    Returns:
        装饰后的函数
    """

    def decorator(func: F) -> F:
        is_async = asyncio.iscoroutinefunction(func)

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            retries = 0
            while True:
                try:
                    result = func(*args, **kwargs)
                    # 成功执行，提升神经元健康状态
                    if neuron_name:
                        immune_system = get_immune_system()
                        immune_system.heal_neuron(neuron_name, 0.05)
                    return result
                except NeuralException as e:
                    # 直接处理已经是NeuralException的异常
                    immune_system = get_immune_system()
                    immune_system.handle_exception(e)

                    # 如果超过重试次数，重新抛出
                    if retries >= max_retries:
                        raise

                    retries += 1
                    time.sleep(retry_delay)
                except Exception as e:
                    # 将普通异常转换为NeuralException
                    immune_system = get_immune_system()
                    neural_ex = NeuralException(
                        f"函数 {func.__name__} 执行出错",
                        exception_type=exception_type,
                        original_exception=e,
                        neuron_name=neuron_name,
                        recovery_hint=recovery_hint,
                    )
                    immune_system.handle_exception(neural_ex)

                    # 如果超过重试次数，重新抛出
                    if retries >= max_retries:
                        raise neural_ex

                    retries += 1
                    time.sleep(retry_delay)

        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            retries = 0
            while True:
                try:
                    result = await func(*args, **kwargs)
                    # 成功执行，提升神经元健康状态
                    if neuron_name:
                        immune_system = get_immune_system()
                        immune_system.heal_neuron(neuron_name, 0.05)
                    return result
                except NeuralException as e:
                    # 直接处理已经是NeuralException的异常
                    immune_system = get_immune_system()
                    immune_system.handle_exception(e)

                    # 如果超过重试次数，重新抛出
                    if retries >= max_retries:
                        raise

                    retries += 1
                    await asyncio.sleep(retry_delay)
                except Exception as e:
                    # 将普通异常转换为NeuralException
                    immune_system = get_immune_system()
                    neural_ex = NeuralException(
                        f"异步函数 {func.__name__} 执行出错",
                        exception_type=exception_type,
                        original_exception=e,
                        neuron_name=neuron_name,
                        recovery_hint=recovery_hint,
                    )
                    immune_system.handle_exception(neural_ex)

                    # 如果超过重试次数，重新抛出
                    if retries >= max_retries:
                        raise neural_ex

                    retries += 1
                    await asyncio.sleep(retry_delay)

        return async_wrapper if is_async else sync_wrapper

    return decorator


def install_global_exception_handler() -> None:
    """安装全局异常处理器，捕获未处理的异常"""

    def global_exception_handler(exctype, value, tb):
        """处理未捕获的异常"""
        # 将普通异常转换为系统异常
        neural_ex = SystemException(
            "未捕获的全局异常",
            original_exception=value,
            recovery_hint="请检查日志并修复相关代码",
        )

        # 使用免疫系统处理
        immune_system = get_immune_system()
        immune_system.handle_exception(neural_ex)

        # 调用默认处理器
        sys.__excepthook__(exctype, value, tb)

    # 设置全局异常处理器
    sys.excepthook = global_exception_handler

    # 设置asyncio任务异常处理器
    def async_exception_handler(loop, context):
        """处理asyncio未捕获的异常"""
        exception = context.get("exception")
        message = context.get("message", "无消息")

        # 将普通异常转换为系统异常
        neural_ex = SystemException(
            f"未捕获的asyncio异常: {message}",
            original_exception=exception,
            recovery_hint="请检查日志并修复相关异步代码",
        )

        # 使用免疫系统处理
        immune_system = get_immune_system()
        immune_system.handle_exception(neural_ex)

        # 记录详细信息
        logger.error(f"AsyncIO异常上下文: {context}")

    # 获取事件循环并设置异常处理器
    try:
        loop = asyncio.get_event_loop()
        loop.set_exception_handler(async_exception_handler)
    except RuntimeError:
        logger.warning("无法获取事件循环，跳过asyncio异常处理器安装")
