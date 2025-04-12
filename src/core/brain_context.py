from typing import Dict, Any, Type, List, Optional, TypeVar, Set, Union, Callable
import logging
import asyncio
import os
import json
import yaml
import time
import sys
from pathlib import Path
from datetime import datetime

from src.core.neural_injector import NeuralInjector
from src.core.synaptic_network import SynapticNetwork
from src.core.central_cortex import CentralCortex
from src.neurons.neuron import Neuron
from src.sensors.base_sensor import Sensor
from src.actuators.base_actuator import Actuator
from src.cerebellum.immune_system import (
    get_immune_system,
    ImmuneSystem,
    RecoveryStrategy,
    RecoveryConfig,
    install_global_exception_handler,
)
from src.cerebellum.neural_trace import (
    setup_neural_trace,
    NeuralTrace,
    TraceLevel,
    NeuronType,
    LogRotationStrategy,
)
from src.neural_plasticity.plugin_manager import PluginManager

T = TypeVar("T")
logger = logging.getLogger(__name__)


class BrainContext:
    """思维中枢 - 系统的中央访问点和生命周期管理器"""

    _instance = None

    @classmethod
    def get_instance(cls) -> "BrainContext":
        """获取BrainContext单例实例

        Returns:
            BrainContext单例实例
        """
        if cls._instance is None:
            raise RuntimeError("BrainContext尚未初始化，无法获取实例")
        return cls._instance

    def __init__(self, config_path: Optional[str] = None):
        """初始化思维中枢

        Args:
            config_path: 配置文件路径
        """
        # 设置单例实例
        if BrainContext._instance is not None:
            logger.warning("BrainContext已经实例化，重复实例化可能导致问题")
        BrainContext._instance = self

        self.running = False
        self.config = self._load_config(config_path)

        # 初始化神经痕迹系统
        self._setup_neural_trace()

        # 初始化免疫系统
        self._setup_immune_system()

        self.injector = NeuralInjector(self.config)
        self.neurons: Set[Neuron] = set()
        self.startup_time = None
        self.shutdown_time = None

        # 获取中央皮层
        self._central_cortex = None  # 延迟初始化

    def _setup_neural_trace(self) -> None:
        """初始化神经痕迹系统"""
        trace_config = self.config.get("neural_trace", {})

        # 提取配置参数
        log_dir = trace_config.get("log_dir", "logs")
        console_level_str = trace_config.get("console_level", "INFO")
        file_level_str = trace_config.get("file_level", "DEBUG")
        max_file_size = trace_config.get("max_file_size", 10 * 1024 * 1024)  # 默认10MB
        backup_count = trace_config.get("backup_count", 5)
        enable_console = trace_config.get("enable_console", True)
        enable_file = trace_config.get("enable_file", True)
        rotation_strategy_str = trace_config.get("rotation_strategy", "SIZE")
        enable_json_format = trace_config.get("enable_json_format", False)

        # 转换枚举类型
        console_level = getattr(TraceLevel, console_level_str, TraceLevel.INFO)
        file_level = getattr(TraceLevel, file_level_str, TraceLevel.DEBUG)
        rotation_strategy = getattr(LogRotationStrategy, rotation_strategy_str, LogRotationStrategy.SIZE)

        # 初始化神经痕迹系统
        neural_trace = setup_neural_trace(
            log_dir=log_dir,
            console_level=console_level,
            file_level=file_level,
            max_file_size=max_file_size,
            backup_count=backup_count,
            enable_console=enable_console,
            enable_file=enable_file,
            rotation_strategy=rotation_strategy,
            enable_json_format=enable_json_format,
        )

        # 神经元类型特定配置
        neuron_type_levels = trace_config.get("neuron_type_levels", {})
        for type_name, level_name in neuron_type_levels.items():
            try:
                neuron_type = getattr(NeuronType, type_name.upper())
                level = getattr(TraceLevel, level_name.upper())
                neural_trace.set_neuron_type_level(neuron_type, level)
            except (AttributeError, TypeError):
                logger.warning(f"无效的神经元类型或日志级别: {type_name}:{level_name}")

        # 设置日志清理策略
        cleanup = trace_config.get("cleanup", {})
        if cleanup:
            max_days = cleanup.get("max_days", 30)
            enabled = cleanup.get("enabled", True)
            neural_trace.set_cleanup_policy(max_days, enabled)

        logger.info("神经痕迹系统已初始化")

    def _setup_immune_system(self) -> None:
        """初始化免疫系统"""
        immune_config = self.config.get("immune_system", {})

        # 获取全局免疫系统实例
        immune_system = get_immune_system()

        # 安装全局异常处理器
        if immune_config.get("install_global_handler", True):
            install_global_exception_handler()

        # 读取策略配置
        strategies = immune_config.get("strategies", {})

        # 应用感知神经元重试策略
        sensor_strategies = strategies.get("sensors", {})
        for sensor_name, strategy in sensor_strategies.items():
            max_retries = strategy.get("max_retries", 3)
            delay = strategy.get("delay", 1.0)
            # 将在神经元注册时应用
            logger.info(f"已配置感知神经元 {sensor_name} 重试策略: 最大{max_retries}次, 延迟{delay}秒")

        # 应用运动神经元降级策略
        actuator_strategies = strategies.get("actuators", {})
        for actuator_name, strategy in actuator_strategies.items():
            max_failures = strategy.get("max_failures", 3)
            # 降级函数将在神经元注册时添加
            logger.info(f"已配置运动神经元 {actuator_name} 降级策略: 最大失败{max_failures}次")

        logger.info("免疫系统已初始化")

    def _load_config(self, config_path: Optional[str]) -> Dict[str, Any]:
        """加载配置

        Args:
            config_path: 配置文件路径

        Returns:
            配置字典
        """
        config = {}

        # 默认配置
        default_config = {
            "system": {"log_level": "INFO", "debug_mode": False},
            "neural_trace": {
                "log_dir": "logs",
                "console_level": "INFO",
                "file_level": "DEBUG",
                "rotation_strategy": "SIZE",
                "neuron_type_levels": {"SENSOR": "DEBUG", "ACTUATOR": "DEBUG", "CONNECTOR": "INFO"},
                "cleanup": {"enabled": True, "max_days": 30},
            },
            "immune_system": {
                "install_global_handler": True,
                "strategies": {
                    "sensors": {
                        "DanmakuSensor": {"max_retries": 3, "delay": 1.0},
                        "CommandSensor": {"max_retries": 5, "delay": 0.5},
                    },
                    "actuators": {"SubtitleActuator": {"max_failures": 3}, "Live2DActuator": {"max_failures": 2}},
                },
            },
        }

        # 合并配置
        config.update(default_config)

        # 如果提供了配置文件路径，加载配置文件
        if config_path and os.path.exists(config_path):
            try:
                # 根据文件扩展名选择解析方法
                if config_path.endswith(".json"):
                    with open(config_path, "r", encoding="utf-8") as f:
                        file_config = json.load(f)
                elif config_path.endswith((".yaml", ".yml")):
                    with open(config_path, "r", encoding="utf-8") as f:
                        file_config = yaml.safe_load(f)
                else:
                    logger.warning(f"不支持的配置文件格式: {config_path}")
                    file_config = {}

                # 打印加载的配置
                logger.debug(f"从文件加载的配置: {file_config}")

                # 合并配置
                config.update(file_config)
                logger.info(f"已加载配置文件: {config_path}")

                # 检查关键配置项
                if "maibot_core_connector" in config:
                    logger.debug(f"MaiBot Core配置已加载: {config['maibot_core_connector']}")
                else:
                    logger.warning("配置中缺少 maibot_core_connector 部分")

            except Exception as e:
                logger.error(f"加载配置文件出错: {e}")
        else:
            logger.info("未提供配置文件，使用默认配置")

        # 从环境变量加载配置
        for key, value in os.environ.items():
            if key.startswith("MAIBOT_"):
                # 将环境变量转换为配置项
                config_key = key[7:].lower()  # 移除 "MAIBOT_" 前缀
                config_parts = config_key.split("_")

                # 构建嵌套配置
                current = config
                for part in config_parts[:-1]:
                    if part not in current:
                        current[part] = {}
                    current = current[part]

                # 设置最终值
                try:
                    # 尝试解析为JSON
                    current[config_parts[-1]] = json.loads(value)
                except json.JSONDecodeError:
                    # 如果不是有效的JSON，使用原始字符串
                    current[config_parts[-1]] = value

                logger.debug(f"从环境变量加载配置: {key} = {value}")

        # 最后输出所有配置键
        logger.debug(f"最终配置包含以下键: {list(config.keys())}")
        # 检查MaiBot核心连接器配置
        possible_keys = ["maibot_core_connector", "maibotcoreconnector", "maibot_core", "core_connector"]
        for key in possible_keys:
            if key in config:
                logger.debug(f"找到配置键 '{key}': {config[key]}")

        return config

    def get_component(self, component_type: Type[T]) -> T:
        """获取系统组件

        Args:
            component_type: 组件类型

        Returns:
            组件实例
        """
        return self.injector.get(component_type)

    def _get_central_cortex(self) -> CentralCortex:
        """获取中央皮层，延迟初始化

        Returns:
            中央皮层实例
        """
        if self._central_cortex is None:
            self._central_cortex = self.get_component(CentralCortex)
        return self._central_cortex

    async def register_neuron(self, neuron: Neuron) -> None:
        """注册神经元

        Args:
            neuron: 要注册的神经元
        """
        # 先添加到内部集合，用于记录
        self.neurons.add(neuron)

        # 通过中央皮层注册神经元
        central_cortex = self._get_central_cortex()
        await central_cortex.register_neuron(neuron)

        # 为神经元应用恢复策略
        self._apply_recovery_strategies(neuron)

        # 如果系统正在运行，立即激活神经元
        if self.running and not neuron.is_active:
            if isinstance(neuron, Sensor):
                await central_cortex.sensory_cortex.activate_neuron(neuron)
            elif isinstance(neuron, Actuator):
                await central_cortex.motor_cortex.activate_neuron(neuron)

        logger.info(f"已注册神经元: {neuron.name}")

    def _apply_recovery_strategies(self, neuron: Neuron) -> None:
        """为神经元应用恢复策略

        Args:
            neuron: 神经元
        """
        immune_system = get_immune_system()
        neuron_name = neuron.__class__.__name__

        if isinstance(neuron, Sensor):
            # 应用感知神经元重试策略
            sensor_strategies = self.config.get("immune_system", {}).get("strategies", {}).get("sensors", {})
            if neuron_name in sensor_strategies:
                strategy = sensor_strategies[neuron_name]
                max_retries = strategy.get("max_retries", 3)
                delay = strategy.get("delay", 1.0)
                immune_system.apply_retry_strategy(neuron_name, max_retries, delay)

        elif isinstance(neuron, Actuator):
            # 应用运动神经元降级策略
            actuator_strategies = self.config.get("immune_system", {}).get("strategies", {}).get("actuators", {})
            if neuron_name in actuator_strategies:
                strategy = actuator_strategies[neuron_name]
                max_failures = strategy.get("max_failures", 3)

                # 创建降级函数
                async def fallback_function():
                    """降级功能"""
                    logger.warning(f"执行 {neuron_name} 降级功能")
                    try:
                        # 尝试降级处理
                        if hasattr(neuron, "fallback"):
                            await neuron.fallback()
                        else:
                            # 通用降级方案
                            if hasattr(neuron, "last_successful_state"):
                                logger.info(f"恢复 {neuron_name} 到上一个成功状态")
                    except Exception as e:
                        logger.error(f"降级功能执行出错: {e}")

                immune_system.apply_degradation_strategy(neuron_name, fallback_function, max_failures)

    async def unregister_neuron(self, neuron: Neuron) -> None:
        """取消注册神经元

        Args:
            neuron: 要取消注册的神经元
        """
        # 从内部集合中移除
        if neuron in self.neurons:
            self.neurons.remove(neuron)

        # 通过中央皮层取消注册神经元
        central_cortex = self._get_central_cortex()
        await central_cortex.unregister_neuron(neuron)

        logger.info(f"已取消注册神经元: {neuron.name}")

    async def create_neuron(self, neuron_class: Type[Neuron], **kwargs) -> Neuron:
        """创建并注册神经元

        Args:
            neuron_class: 神经元类
            **kwargs: 额外参数

        Returns:
            创建的神经元
        """
        # 创建神经元实例
        neuron = await self.injector.create_instance(neuron_class, **kwargs)

        # 注册神经元
        await self.register_neuron(neuron)

        return neuron

    async def start(self) -> None:
        """启动整个系统，协调组件启动顺序"""
        if self.running:
            logger.warning("系统已经在运行中")
            return

        logger.info("正在启动系统...")
        self.startup_time = time.time()

        # 获取系统组件
        synaptic_network = self.get_component(SynapticNetwork)
        central_cortex = self._get_central_cortex()

        # 启动神经突触网络
        await synaptic_network.start()

        # 初始化和启动神经可塑性系统
        try:
            plugin_manager = self.get_component(PluginManager)
            await plugin_manager.initialize()
            logger.info("神经可塑性系统已初始化")
        except Exception as e:
            logger.error(f"初始化神经可塑性系统时出错: {e}")

        # 激活所有神经元
        await central_cortex.activate_all()

        # 更新系统状态
        self.running = True
        logger.info(f"系统已启动，耗时: {time.time() - self.startup_time:.2f}秒")

    async def stop(self) -> None:
        """停止系统，释放资源"""
        if not self.running:
            logger.warning("系统未运行")
            return

        logger.info("正在停止系统...")
        self.shutdown_time = time.time()

        try:
            # 获取系统组件
            synaptic_network = self.get_component(SynapticNetwork)
            central_cortex = self._get_central_cortex()

            # 停用所有神经元
            await central_cortex.deactivate_all()

            # 停止神经突触网络
            await synaptic_network.stop()

            # 清理神经可塑性系统
            try:
                plugin_manager = self.get_component(PluginManager)
                # 卸载所有插件
                for plugin_id in list(plugin_manager.loaded_plugins.keys()):
                    await plugin_manager.unload_plugin(plugin_id)
                logger.info("神经可塑性系统已清理")
            except Exception as e:
                logger.error(f"清理神经可塑性系统时出错: {e}")

            # 更新系统状态
            self.running = False
            logger.info(f"系统已停止，耗时: {time.time() - self.shutdown_time:.2f}秒")
        except Exception as e:
            logger.error(f"系统停止时出错: {e}")
            raise

    def get_system_stats(self) -> Dict[str, Any]:
        """获取系统统计信息

        Returns:
            系统统计信息
        """
        stats = {
            "running": self.running,
            "startup_time": self.startup_time,
            "shutdown_time": self.shutdown_time,
            "uptime": time.time() - self.startup_time if self.startup_time and self.running else 0,
        }

        # 获取系统组件统计
        try:
            synaptic_network = self.get_component(SynapticNetwork)
            stats["synaptic_network"] = synaptic_network.get_stats()
        except Exception:
            pass

        try:
            central_cortex = self._get_central_cortex()
            stats["central_cortex"] = central_cortex.get_stats()
        except Exception:
            pass

        # 获取神经可塑性系统统计
        try:
            plugin_manager = self.get_component(PluginManager)
            plugins_stats = {
                "total_plugins": len(plugin_manager.plugins),
                "loaded_plugins": len(plugin_manager.loaded_plugins),
                "plugins": {},
            }

            # 添加每个插件的详细信息
            for plugin_id, metadata in plugin_manager.plugins.items():
                plugins_stats["plugins"][plugin_id] = {
                    "name": metadata.name,
                    "version": metadata.version,
                    "neuron_type": metadata.neuron_type,
                    "enabled": metadata.enabled,
                    "loaded": plugin_id in plugin_manager.loaded_plugins,
                }

            stats["neural_plasticity"] = plugins_stats
        except Exception:
            pass

        return stats
