"""
神经痕迹系统 - 负责系统日志记录

该模块提供了结构化日志功能，支持按神经元类型分类记录日志，
以及动态调整日志级别和日志轮转功能。
"""

import logging
import logging.handlers
import os
import sys
import time
import json
import threading
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Set, Union, Callable
from enum import Enum, auto


class TraceLevel(Enum):
    """神经痕迹级别"""

    CRITICAL = auto()
    ERROR = auto()
    WARNING = auto()
    INFO = auto()
    DEBUG = auto()
    TRACE = auto()  # 比DEBUG更详细的级别


class NeuronType(Enum):
    """神经元类型"""

    SENSOR = auto()
    ACTUATOR = auto()
    CONNECTOR = auto()
    CORE = auto()
    SYSTEM = auto()
    UNKNOWN = auto()


class LogRotationStrategy(Enum):
    """日志轮转策略"""

    SIZE = auto()  # 按大小轮转
    TIME = auto()  # 按时间轮转
    HYBRID = auto()  # 混合策略


class NeuralTrace:
    """神经痕迹 - 系统日志管理器"""

    # 映射自定义级别到标准logging级别
    _LEVEL_MAP = {
        TraceLevel.CRITICAL: logging.CRITICAL,
        TraceLevel.ERROR: logging.ERROR,
        TraceLevel.WARNING: logging.WARNING,
        TraceLevel.INFO: logging.INFO,
        TraceLevel.DEBUG: logging.DEBUG,
        TraceLevel.TRACE: 5,  # 自定义TRACE级别
    }

    # 反向映射，方便查找
    _REVERSE_LEVEL_MAP = {v: k for k, v in _LEVEL_MAP.items()}

    def __init__(
        self,
        log_dir: str = "logs",
        console_level: TraceLevel = TraceLevel.INFO,
        file_level: TraceLevel = TraceLevel.DEBUG,
        max_file_size: int = 10 * 1024 * 1024,  # 10MB
        backup_count: int = 5,
        enable_console: bool = True,
        enable_file: bool = True,
        rotation_strategy: LogRotationStrategy = LogRotationStrategy.SIZE,
        rotation_interval: Optional[timedelta] = None,
        enable_json_format: bool = False,
    ):
        """初始化神经痕迹系统

        Args:
            log_dir: 日志文件目录
            console_level: 控制台日志级别
            file_level: 文件日志级别
            max_file_size: 单个日志文件最大大小（字节）
            backup_count: 保留的备份文件数量
            enable_console: 是否启用控制台日志
            enable_file: 是否启用文件日志
            rotation_strategy: 日志轮转策略
            rotation_interval: 时间轮转间隔（仅当rotation_strategy为TIME或HYBRID时有效）
            enable_json_format: 是否启用JSON格式日志
        """
        # 注册自定义日志级别
        logging.addLevelName(self._LEVEL_MAP[TraceLevel.TRACE], "TRACE")

        # 创建根日志器
        self.logger = logging.getLogger()
        self.logger.setLevel(logging.DEBUG)  # 设置为最低级别，让handlers决定过滤

        # 清除现有的handlers
        for handler in self.logger.handlers[:]:
            self.logger.removeHandler(handler)

        # 记录当前设置
        self.log_dir = log_dir
        self.console_level = console_level
        self.file_level = file_level
        self.max_file_size = max_file_size
        self.backup_count = backup_count
        self.enable_console = enable_console
        self.enable_file = enable_file
        self.rotation_strategy = rotation_strategy
        self.rotation_interval = rotation_interval or timedelta(days=1)
        self.enable_json_format = enable_json_format

        # 神经元类型日志器缓存
        self.neuron_loggers: Dict[NeuronType, logging.Logger] = {}

        # 神经元类型日志级别设置
        self.neuron_type_levels: Dict[NeuronType, TraceLevel] = {neuron_type: file_level for neuron_type in NeuronType}

        # 启动时间
        self.start_time = datetime.now()

        # 创建锁，用于线程安全操作
        self.lock = threading.RLock()

        # 轮转计时器
        self.last_rotation_time = datetime.now()

        # 自动清理设置
        self.max_log_days = 30  # 默认保留30天的日志
        self.auto_cleanup_enabled = True

        # 日志处理器字典，便于后续调整
        self.handlers: Dict[str, logging.Handler] = {}

        # 初始化日志处理器
        self._setup_handlers()

        # 如果使用时间轮转，设置定时器
        if rotation_strategy in (LogRotationStrategy.TIME, LogRotationStrategy.HYBRID):
            self._setup_rotation_timer()

        # 首次运行执行日志清理
        if self.auto_cleanup_enabled:
            self._cleanup_old_logs()

    def _setup_handlers(self):
        """设置日志处理器"""
        # 控制台处理器
        if self.enable_console:
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setLevel(self._LEVEL_MAP[self.console_level])

            if self.enable_json_format:
                console_formatter = self._create_json_formatter()
            else:
                console_formatter = logging.Formatter(
                    "%(asctime)s - %(levelname)s - [%(neuron_type)s] - %(name)s - %(message)s"
                )

            console_handler.setFormatter(console_formatter)
            self.logger.addHandler(console_handler)
            self.handlers["console"] = console_handler

        # 文件处理器
        if self.enable_file:
            # 确保日志目录存在
            os.makedirs(self.log_dir, exist_ok=True)

            # 主日志文件
            main_log_file = os.path.join(self.log_dir, "maibot.log")

            # 根据轮转策略选择不同的处理器
            if self.rotation_strategy == LogRotationStrategy.TIME:
                file_handler = logging.handlers.TimedRotatingFileHandler(
                    main_log_file,
                    when="midnight",
                    interval=1,
                    backupCount=self.backup_count,
                    encoding="utf-8",
                )
            else:
                file_handler = logging.handlers.RotatingFileHandler(
                    main_log_file,
                    maxBytes=self.max_file_size,
                    backupCount=self.backup_count,
                    encoding="utf-8",
                )

            file_handler.setLevel(self._LEVEL_MAP[self.file_level])

            if self.enable_json_format:
                file_formatter = self._create_json_formatter()
            else:
                file_formatter = logging.Formatter(
                    "%(asctime)s - %(levelname)s - [%(neuron_type)s] - %(name)s - %(message)s"
                )

            file_handler.setFormatter(file_formatter)
            self.logger.addHandler(file_handler)
            self.handlers["main"] = file_handler

            # 为每种神经元类型创建单独的日志文件
            for neuron_type in NeuronType:
                if neuron_type == NeuronType.UNKNOWN:
                    continue

                type_log_file = os.path.join(self.log_dir, f"{neuron_type.name.lower()}.log")

                # 根据轮转策略选择不同的处理器
                if self.rotation_strategy == LogRotationStrategy.TIME:
                    type_handler = logging.handlers.TimedRotatingFileHandler(
                        type_log_file,
                        when="midnight",
                        interval=1,
                        backupCount=self.backup_count,
                        encoding="utf-8",
                    )
                else:
                    type_handler = logging.handlers.RotatingFileHandler(
                        type_log_file,
                        maxBytes=self.max_file_size,
                        backupCount=self.backup_count,
                        encoding="utf-8",
                    )

                # 使用神经元类型特定的日志级别
                type_handler.setLevel(self._LEVEL_MAP[self.neuron_type_levels[neuron_type]])

                if self.enable_json_format:
                    type_formatter = self._create_json_formatter()
                else:
                    type_formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(name)s - %(message)s")

                type_handler.setFormatter(type_formatter)

                # 创建过滤器，只接收指定类型的日志
                type_filter = (
                    lambda record, t=neuron_type: getattr(record, "neuron_type", NeuronType.UNKNOWN.name) == t.name
                )
                type_handler.addFilter(type_filter)

                self.logger.addHandler(type_handler)
                self.handlers[f"type_{neuron_type.name.lower()}"] = type_handler

    def _create_json_formatter(self):
        """创建JSON格式日志格式化器"""

        class JsonFormatter(logging.Formatter):
            def format(self, record):
                log_data = {
                    "timestamp": self.formatTime(record, "%Y-%m-%d %H:%M:%S,%03d"),
                    "level": record.levelname,
                    "logger": record.name,
                    "message": record.getMessage(),
                }

                # 添加神经元类型
                neuron_type = getattr(record, "neuron_type", NeuronType.UNKNOWN.name)
                log_data["neuron_type"] = neuron_type

                # 添加异常信息
                if record.exc_info:
                    log_data["exception"] = self.formatException(record.exc_info)

                # 添加其他自定义字段
                for key, value in getattr(record, "extra_fields", {}).items():
                    log_data[key] = value

                return json.dumps(log_data)

        return JsonFormatter()

    def _setup_rotation_timer(self):
        """设置日志轮转定时器"""

        def rotation_check():
            while True:
                # 检查是否需要轮转
                now = datetime.now()
                if now - self.last_rotation_time >= self.rotation_interval:
                    with self.lock:
                        self.rotate_logs()
                        self.last_rotation_time = now

                # 检查是否需要清理
                if self.auto_cleanup_enabled and now.hour == 2 and now.minute < 5:  # 凌晨2点左右执行清理
                    self._cleanup_old_logs()

                # 休眠5分钟后再次检查
                time.sleep(300)

        # 启动后台线程
        thread = threading.Thread(target=rotation_check, daemon=True)
        thread.start()

    def get_logger(self, name: str, neuron_type: NeuronType = NeuronType.UNKNOWN) -> logging.Logger:
        """获取命名日志器

        Args:
            name: 日志器名称
            neuron_type: 神经元类型

        Returns:
            命名日志器
        """
        logger = logging.getLogger(name)

        # 给日志器添加额外属性，用于过滤
        logger = logging.LoggerAdapter(logger, {"neuron_type": neuron_type.name})

        return logger

    def set_logger_level(self, name: str, level: TraceLevel, neuron_type: Optional[NeuronType] = None) -> None:
        """设置指定日志器的级别

        Args:
            name: 日志器名称
            level: 新的日志级别
            neuron_type: 神经元类型（可选）
        """
        logger = logging.getLogger(name)
        logger.setLevel(self._LEVEL_MAP[level])

        # 记录日志
        self.logger.info(f"已设置日志器 {name} 级别为 {level.name}")

    def set_console_level(self, level: TraceLevel) -> None:
        """设置控制台日志级别

        Args:
            level: 新的日志级别
        """
        if not self.enable_console:
            return

        self.console_level = level
        handler = self.handlers.get("console")
        if handler:
            handler.setLevel(self._LEVEL_MAP[level])

        # 记录日志
        self.logger.info(f"已设置控制台日志级别为 {level.name}")

    def set_file_level(self, level: TraceLevel) -> None:
        """设置文件日志级别

        Args:
            level: 新的日志级别
        """
        if not self.enable_file:
            return

        self.file_level = level
        handler = self.handlers.get("main")
        if handler:
            handler.setLevel(self._LEVEL_MAP[level])

        # 记录日志
        self.logger.info(f"已设置主文件日志级别为 {level.name}")

    def set_neuron_type_level(self, neuron_type: NeuronType, level: TraceLevel) -> None:
        """设置指定神经元类型的日志级别

        Args:
            neuron_type: 神经元类型
            level: 新的日志级别
        """
        if not self.enable_file:
            return

        self.neuron_type_levels[neuron_type] = level
        handler = self.handlers.get(f"type_{neuron_type.name.lower()}")
        if handler:
            handler.setLevel(self._LEVEL_MAP[level])

        # 记录日志
        self.logger.info(f"已设置 {neuron_type.name} 类型日志级别为 {level.name}")

    def get_neuron_type_level(self, neuron_type: NeuronType) -> TraceLevel:
        """获取指定神经元类型的日志级别

        Args:
            neuron_type: 神经元类型

        Returns:
            日志级别
        """
        return self.neuron_type_levels.get(neuron_type, self.file_level)

    def enable_trace_level(self) -> None:
        """启用TRACE级别日志"""
        self.logger.setLevel(self._LEVEL_MAP[TraceLevel.TRACE])
        # 记录日志
        self.logger.info("已启用TRACE级别日志")

    def disable_trace_level(self) -> None:
        """禁用TRACE级别日志，恢复到DEBUG级别"""
        self.logger.setLevel(logging.DEBUG)
        # 记录日志
        self.logger.info("已禁用TRACE级别日志")

    def enable_neural_tracing(self, neuron_type: NeuronType) -> None:
        """为指定神经元类型启用最详细的跟踪

        Args:
            neuron_type: 神经元类型
        """
        self.set_neuron_type_level(neuron_type, TraceLevel.TRACE)
        # 记录日志
        self.logger.info(f"已为 {neuron_type.name} 类型启用详细跟踪")

    def disable_neural_tracing(self, neuron_type: NeuronType) -> None:
        """为指定神经元类型禁用详细跟踪，恢复到默认级别

        Args:
            neuron_type: 神经元类型
        """
        self.set_neuron_type_level(neuron_type, self.file_level)
        # 记录日志
        self.logger.info(f"已为 {neuron_type.name} 类型禁用详细跟踪")

    def rotate_logs(self) -> None:
        """强制轮转所有日志文件"""
        with self.lock:
            for name, handler in self.handlers.items():
                if isinstance(
                    handler, (logging.handlers.RotatingFileHandler, logging.handlers.TimedRotatingFileHandler)
                ):
                    try:
                        handler.doRollover()
                        self.logger.info(f"已轮转日志文件: {name}")
                    except Exception as e:
                        self.logger.error(f"轮转日志文件 {name} 失败: {e}")

            self.last_rotation_time = datetime.now()

    def set_cleanup_policy(self, max_days: int, enabled: bool = True) -> None:
        """设置日志自动清理策略

        Args:
            max_days: 最大保留天数
            enabled: 是否启用自动清理
        """
        self.max_log_days = max_days
        self.auto_cleanup_enabled = enabled
        self.logger.info(f"已设置日志清理策略: 保留{max_days}天, 自动清理{'启用' if enabled else '禁用'}")

    def _cleanup_old_logs(self) -> None:
        """清理过期日志文件"""
        try:
            now = datetime.now()
            cutoff_date = now - timedelta(days=self.max_log_days)
            cutoff_timestamp = cutoff_date.timestamp()

            for root, _, files in os.walk(self.log_dir):
                for file in files:
                    # 只处理日志文件
                    if not file.endswith(".log") and not file.endswith(".log."):
                        continue

                    file_path = os.path.join(root, file)
                    file_mtime = os.path.getmtime(file_path)

                    # 如果文件修改时间早于截止日期，删除它
                    if file_mtime < cutoff_timestamp:
                        try:
                            os.remove(file_path)
                            self.logger.info(f"已清理过期日志文件: {file_path}")
                        except Exception as e:
                            self.logger.error(f"清理日志文件 {file_path} 失败: {e}")

        except Exception as e:
            self.logger.error(f"执行日志清理时出错: {e}")

    def add_file_handler(
        self, file_name: str, level: TraceLevel = TraceLevel.INFO, filter_func: Optional[Callable] = None
    ) -> None:
        """添加自定义文件处理器

        Args:
            file_name: 文件名（不含路径）
            level: 日志级别
            filter_func: 过滤函数（可选）
        """
        with self.lock:
            file_path = os.path.join(self.log_dir, file_name)

            # 根据轮转策略选择不同的处理器
            if self.rotation_strategy == LogRotationStrategy.TIME:
                handler = logging.handlers.TimedRotatingFileHandler(
                    file_path,
                    when="midnight",
                    interval=1,
                    backupCount=self.backup_count,
                    encoding="utf-8",
                )
            else:
                handler = logging.handlers.RotatingFileHandler(
                    file_path,
                    maxBytes=self.max_file_size,
                    backupCount=self.backup_count,
                    encoding="utf-8",
                )

            handler.setLevel(self._LEVEL_MAP[level])

            if self.enable_json_format:
                formatter = self._create_json_formatter()
            else:
                formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(name)s - %(message)s")

            handler.setFormatter(formatter)

            # 应用自定义过滤器
            if filter_func:
                handler.addFilter(filter_func)

            self.logger.addHandler(handler)
            self.handlers[f"custom_{file_name}"] = handler

            # 记录日志
            self.logger.info(f"已添加自定义日志文件: {file_name}, 级别: {level.name}")

    def get_stats(self) -> Dict[str, Any]:
        """获取日志系统统计信息

        Returns:
            统计信息
        """
        stats = {
            "console_level": self.console_level.name if self.enable_console else "DISABLED",
            "file_level": self.file_level.name if self.enable_file else "DISABLED",
            "log_dir": self.log_dir,
            "handlers_count": len(self.logger.handlers),
            "rotation_strategy": self.rotation_strategy.name,
            "last_rotation_time": self.last_rotation_time.strftime("%Y-%m-%d %H:%M:%S"),
            "json_format_enabled": self.enable_json_format,
            "neuron_type_levels": {
                neuron_type.name: level.name for neuron_type, level in self.neuron_type_levels.items()
            },
            "uptime": str(datetime.now() - self.start_time),
            "auto_cleanup": {
                "enabled": self.auto_cleanup_enabled,
                "max_days": self.max_log_days,
            },
        }
        return stats


# 全局神经痕迹实例
_neural_trace: Optional[NeuralTrace] = None


def setup_neural_trace(**kwargs) -> NeuralTrace:
    """设置全局神经痕迹实例

    Args:
        **kwargs: 传递给NeuralTrace构造函数的参数

    Returns:
        全局神经痕迹实例
    """
    global _neural_trace
    _neural_trace = NeuralTrace(**kwargs)
    return _neural_trace


def get_neural_trace() -> NeuralTrace:
    """获取全局神经痕迹实例

    如果实例不存在，使用默认参数创建

    Returns:
        全局神经痕迹实例
    """
    global _neural_trace
    if _neural_trace is None:
        _neural_trace = NeuralTrace()
    return _neural_trace


def get_logger(name: str, neuron_type: NeuronType = NeuronType.UNKNOWN) -> logging.Logger:
    """获取命名日志器的快捷方式

    Args:
        name: 日志器名称
        neuron_type: 神经元类型

    Returns:
        命名日志器
    """
    neural_trace = get_neural_trace()
    return neural_trace.get_logger(name, neuron_type)
