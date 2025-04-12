from typing import Dict, Any, Type, List, Optional, TypeVar, Generic, Union, get_type_hints
import logging
import importlib
import inspect
from injector import Injector, Module, singleton, provider, inject, Binder

from src.core.synaptic_network import SynapticNetwork
from src.core.central_cortex import CentralCortex
from src.cerebellum.neural_trace import NeuralTrace, setup_neural_trace
from src.cerebellum.immune_system import ImmuneSystem, get_immune_system
from src.cerebellum.homeostasis import Homeostasis, get_homeostasis
from src.neural_plasticity.plugin_manager import PluginManager
from src.neural_plasticity.plugin_loader import PluginLoader

T = TypeVar("T")
logger = logging.getLogger(__name__)


class NeuralModule(Module):
    """神经模块 - 定义系统组件的提供方式"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config

    def configure(self, binder: Binder) -> None:
        """配置模块绑定

        Args:
            binder: 绑定器
        """
        # 绑定配置
        binder.bind(Dict[str, Any], to=self.config, scope=singleton)

    @singleton
    @provider
    def provide_synaptic_network(self) -> SynapticNetwork:
        """提供神经突触网络

        Returns:
            SynapticNetwork实例
        """
        return SynapticNetwork()

    @singleton
    @provider
    def provide_central_cortex(self, synaptic_network: SynapticNetwork) -> CentralCortex:
        """提供中央皮层

        Args:
            synaptic_network: 神经突触网络

        Returns:
            CentralCortex实例
        """
        return CentralCortex(synaptic_network)

    @singleton
    @provider
    def provide_neural_trace(self) -> NeuralTrace:
        """提供神经痕迹系统

        Returns:
            NeuralTrace实例
        """
        log_config = self.config.get("logging", {})
        return setup_neural_trace(
            log_dir=log_config.get("log_dir", "logs"),
            console_level=log_config.get("console_level", "INFO"),
            file_level=log_config.get("file_level", "DEBUG"),
            max_file_size=log_config.get("max_file_size", 10 * 1024 * 1024),
            backup_count=log_config.get("backup_count", 5),
            enable_console=log_config.get("enable_console", True),
            enable_file=log_config.get("enable_file", True),
        )

    @singleton
    @provider
    def provide_immune_system(self) -> ImmuneSystem:
        """提供免疫系统

        Returns:
            ImmuneSystem实例
        """
        return get_immune_system()

    @singleton
    @provider
    def provide_homeostasis(self) -> Homeostasis:
        """提供稳态系统

        Returns:
            Homeostasis实例
        """
        return get_homeostasis()

    @singleton
    @provider
    def provide_plugin_manager(self) -> PluginManager:
        """提供插件管理器

        Returns:
            PluginManager实例
        """
        plugin_config = self.config.get("plugins", {})
        return PluginManager(self._get_neural_injector(), plugin_config)

    @singleton
    @provider
    def provide_plugin_loader(self) -> PluginLoader:
        """提供插件加载器

        Returns:
            PluginLoader实例
        """
        plugin_config = self.config.get("plugins", {})
        return PluginLoader(self._get_neural_injector(), plugin_config)

    def _get_neural_injector(self) -> "NeuralInjector":
        """获取神经注入器实例

        Returns:
            NeuralInjector实例
        """
        # 这个方法是为了解决循环依赖问题
        from src.core.brain_context import BrainContext

        return BrainContext.get_instance().injector


class NeuralInjector:
    """神经注入器 - 管理系统组件的依赖注入"""

    def __init__(self, config: Dict[str, Any], additional_modules: Optional[List[Module]] = None):
        """初始化神经注入器

        Args:
            config: 系统配置
            additional_modules: 额外的依赖注入模块
        """
        modules = [NeuralModule(config)]
        if additional_modules:
            modules.extend(additional_modules)

        self.injector = Injector(modules)
        logger.info(f"神经注入器初始化完成，加载了{len(modules)}个模块")

    def get(self, interface: Type[T]) -> T:
        """获取组件实例

        Args:
            interface: 组件类型

        Returns:
            组件实例
        """
        return self.injector.get(interface)

    async def create_instance(self, cls: Type[T], *args, **kwargs) -> T:
        """创建类的实例，自动注入依赖

        Args:
            cls: 要创建的类
            *args: 位置参数
            **kwargs: 关键字参数

        Returns:
            创建的实例
        """
        # 获取类的构造函数
        init_func = cls.__init__

        # 获取构造函数的参数类型
        type_hints = get_type_hints(init_func)

        # 移除返回类型提示（如果存在）
        if "return" in type_hints:
            del type_hints["return"]

        # 获取已有参数
        arg_spec = inspect.getfullargspec(init_func)
        arg_names = arg_spec.args[1:]  # 排除 'self'

        # 准备注入的参数
        injected_kwargs = {}

        # 遍历构造函数的参数
        for arg_name in arg_names:
            # 如果参数已经提供，使用提供的值
            if arg_name in kwargs:
                continue

            # 尝试获取参数类型
            if arg_name in type_hints:
                arg_type = type_hints[arg_name]

                try:
                    # 从注入器获取依赖
                    dependency = self.injector.get(arg_type)
                    injected_kwargs[arg_name] = dependency
                except Exception as e:
                    logger.debug(f"无法注入参数: {arg_name}: {arg_type}, 错误: {e}")

        # 合并注入的参数和显式提供的参数
        final_kwargs = {**injected_kwargs, **kwargs}

        # 创建实例
        instance = cls(*args, **final_kwargs)

        # 如果是异步初始化，调用initialize方法
        if hasattr(instance, "initialize") and callable(instance.initialize):
            # 获取组件的配置
            component_config = {}

            # 从全局配置中提取组件配置
            component_name = cls.__name__.lower()
            config = self.injector.get(Dict[str, Any])

            # 优先使用instance.name作为配置键（如果存在）
            if hasattr(instance, "name"):
                component_config = config.get(instance.name.lower(), {})

            # 如果没有找到，使用类名作为配置键
            if not component_config and component_name in config:
                component_config = config[component_name]

            # 调用异步初始化方法
            await instance.initialize(component_config)

        return instance
