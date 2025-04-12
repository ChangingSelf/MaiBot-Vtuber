from typing import Dict, List, Type, Any, Optional, Set, TypeVar, Callable, Union
import logging
import os
import importlib.util
import inspect
import json
import asyncio
import pkg_resources
from pathlib import Path

from src.core.neural_injector import NeuralInjector
from src.neurons.neuron import Neuron
from src.sensors.base_sensor import Sensor
from src.actuators.base_actuator import Actuator
from src.core.central_cortex import CentralCortex

T = TypeVar("T", bound=Neuron)
logger = logging.getLogger(__name__)


class PluginMetadata:
    """插件元数据 - 描述插件的基本信息和依赖关系"""

    def __init__(
        self,
        id: str,
        name: str,
        version: str,
        description: str = "",
        author: str = "",
        neuron_type: str = "neuron",  # 'sensor', 'actuator', 'neuron'
        entry_point: str = "",
        dependencies: Dict[str, str] = None,
        config_schema: Dict[str, Any] = None,
        enabled: bool = True,
    ):
        self.id = id
        self.name = name
        self.version = version
        self.description = description
        self.author = author
        self.neuron_type = neuron_type.lower()
        self.entry_point = entry_point
        self.dependencies = dependencies or {}
        self.config_schema = config_schema or {}
        self.enabled = enabled
        self.path = None  # 将在加载插件时设置

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PluginMetadata":
        """从字典创建元数据对象

        Args:
            data: 包含元数据的字典

        Returns:
            PluginMetadata实例
        """
        return cls(
            id=data.get("id", ""),
            name=data.get("name", ""),
            version=data.get("version", "0.1.0"),
            description=data.get("description", ""),
            author=data.get("author", ""),
            neuron_type=data.get("neuron_type", "neuron"),
            entry_point=data.get("entry_point", ""),
            dependencies=data.get("dependencies", {}),
            config_schema=data.get("config_schema", {}),
            enabled=data.get("enabled", True),
        )

    def to_dict(self) -> Dict[str, Any]:
        """将元数据转换为字典

        Returns:
            包含元数据的字典
        """
        return {
            "id": self.id,
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "author": self.author,
            "neuron_type": self.neuron_type,
            "entry_point": self.entry_point,
            "dependencies": self.dependencies,
            "config_schema": self.config_schema,
            "enabled": self.enabled,
        }


class PluginManager:
    """插件管理器 - 管理神经可塑性插件的发现、加载和生命周期"""

    def __init__(self, neural_injector: NeuralInjector, config: Dict[str, Any]):
        """初始化插件管理器

        Args:
            neural_injector: 神经注入器
            config: 配置字典
        """
        self.neural_injector = neural_injector
        self.config = config
        self.plugin_dirs = config.get("plugin_dirs", ["plugins"])
        self.enabled_plugins = config.get("enabled_plugins", [])
        self.disabled_plugins = config.get("disabled_plugins", [])

        # 添加自定义插件路径
        for plugin_dir in self.plugin_dirs:
            if not os.path.exists(plugin_dir):
                os.makedirs(plugin_dir, exist_ok=True)

            # 创建传感器和执行器子目录
            sensors_dir = os.path.join(plugin_dir, "sensors")
            actuators_dir = os.path.join(plugin_dir, "actuators")
            os.makedirs(sensors_dir, exist_ok=True)
            os.makedirs(actuators_dir, exist_ok=True)

        # 插件元数据缓存
        self.plugins: Dict[str, PluginMetadata] = {}

        # 已加载的插件实例
        self.loaded_plugins: Dict[str, Any] = {}

        # 插件依赖图
        self.dependency_graph: Dict[str, Set[str]] = {}

        # 中央皮层引用（将在加载时注入）
        self.central_cortex = None

    async def initialize(self) -> None:
        """初始化插件管理器，发现和解析插件元数据"""
        logger.info("正在初始化插件管理器...")

        # 获取中央皮层
        self.central_cortex = self.neural_injector.get(CentralCortex)

        # 发现所有插件
        await self.discover_plugins()

        # 解析依赖关系
        self._build_dependency_graph()

        # 如果配置为自动加载插件，则加载启用的插件
        if self.config.get("auto_load_plugins", True):
            await self.load_enabled_plugins()

        logger.info(f"插件管理器初始化完成，发现了 {len(self.plugins)} 个插件")

    async def discover_plugins(self) -> None:
        """发现所有可用的插件，读取它们的元数据"""
        logger.info("正在发现插件...")
        self.plugins.clear()

        # 从指定目录中发现插件
        for plugin_dir in self.plugin_dirs:
            if not os.path.exists(plugin_dir):
                logger.warning(f"插件目录不存在: {plugin_dir}")
                continue

            await self._scan_directory(plugin_dir)

        # 从已安装的Python包中发现插件
        await self._discover_installed_plugins()

        logger.info(f"发现了 {len(self.plugins)} 个插件")

    async def _scan_directory(self, directory: str) -> None:
        """扫描目录寻找插件

        Args:
            directory: 要扫描的目录
        """
        for root, dirs, files in os.walk(directory):
            # 查找 plugin.json 文件
            if "plugin.json" in files:
                try:
                    # 读取插件元数据
                    metadata_path = os.path.join(root, "plugin.json")
                    with open(metadata_path, "r", encoding="utf-8") as f:
                        metadata_dict = json.load(f)

                    # 创建元数据对象
                    metadata = PluginMetadata.from_dict(metadata_dict)
                    metadata.path = root

                    # 存储元数据
                    self.plugins[metadata.id] = metadata
                    logger.debug(f"发现插件: {metadata.name} (ID: {metadata.id}, 版本: {metadata.version})")
                except Exception as e:
                    logger.error(f"加载插件元数据时出错: {root}, 错误: {e}")

    async def _discover_installed_plugins(self) -> None:
        """发现已安装的Python包中的插件"""
        try:
            # 查找所有以 'maibot-vtuber-plugin-' 开头的安装包
            for entry_point in pkg_resources.iter_entry_points("maibot_vtuber_plugins"):
                try:
                    # 加载入口点
                    plugin_class = entry_point.load()

                    # 获取元数据
                    if hasattr(plugin_class, "get_plugin_metadata"):
                        metadata_dict = plugin_class.get_plugin_metadata()
                        metadata = PluginMetadata.from_dict(metadata_dict)
                        metadata.path = entry_point.dist.location

                        # 存储元数据
                        self.plugins[metadata.id] = metadata
                        logger.debug(f"发现已安装插件: {metadata.name} (ID: {metadata.id}, 版本: {metadata.version})")
                except Exception as e:
                    logger.error(f"加载已安装插件入口点时出错: {entry_point.name}, 错误: {e}")
        except Exception as e:
            logger.error(f"发现已安装插件时出错: {e}")

    def _build_dependency_graph(self) -> None:
        """构建插件依赖图，用于确定加载顺序"""
        self.dependency_graph.clear()

        # 为每个插件创建一个依赖集
        for plugin_id, metadata in self.plugins.items():
            self.dependency_graph[plugin_id] = set()
            for dep_id in metadata.dependencies.keys():
                if dep_id in self.plugins:
                    self.dependency_graph[plugin_id].add(dep_id)
                else:
                    logger.warning(f"插件 {plugin_id} 依赖不存在的插件: {dep_id}")

    def _get_load_order(self) -> List[str]:
        """获取插件的加载顺序，考虑依赖关系

        Returns:
            按照依赖顺序排列的插件ID列表
        """
        # 使用拓扑排序获取加载顺序
        visited = set()
        temp_mark = set()
        order = []

        def visit(node):
            if node in temp_mark:
                # 检测到循环依赖
                logger.error(f"检测到循环依赖: {node}")
                return

            if node in visited:
                return

            temp_mark.add(node)

            # 递归访问所有依赖
            for dep in self.dependency_graph.get(node, set()):
                visit(dep)

            temp_mark.remove(node)
            visited.add(node)
            order.append(node)

        # 访问所有节点
        for node in self.dependency_graph:
            if node not in visited:
                visit(node)

        # 反转顺序，从无依赖到有依赖
        return list(reversed(order))

    def _check_version_compatibility(self, required: str, available: str) -> bool:
        """检查版本兼容性

        Args:
            required: 要求的版本
            available: 可用的版本

        Returns:
            是否兼容
        """
        # 简单实现，仅支持相等和大于等于
        if required.startswith(">="):
            req_version = required[2:].strip()
            return pkg_resources.parse_version(available) >= pkg_resources.parse_version(req_version)
        else:
            # 精确匹配
            return pkg_resources.parse_version(available) == pkg_resources.parse_version(required)

    async def load_plugin(self, plugin_id: str) -> Optional[Neuron]:
        """加载单个插件

        Args:
            plugin_id: 插件ID

        Returns:
            加载的神经元实例，如果加载失败则返回None
        """
        if plugin_id not in self.plugins:
            logger.error(f"插件不存在: {plugin_id}")
            return None

        if plugin_id in self.loaded_plugins:
            logger.warning(f"插件已经加载: {plugin_id}")
            return self.loaded_plugins[plugin_id]

        metadata = self.plugins[plugin_id]

        # 检查插件是否启用
        if not metadata.enabled:
            logger.info(f"插件已禁用，跳过加载: {plugin_id}")
            return None

        # 检查依赖
        for dep_id, dep_version in metadata.dependencies.items():
            if dep_id not in self.plugins:
                logger.error(f"无法加载插件 {plugin_id}: 依赖 {dep_id} 不存在")
                return None

            dep_metadata = self.plugins[dep_id]
            if not self._check_version_compatibility(dep_version, dep_metadata.version):
                logger.error(
                    f"无法加载插件 {plugin_id}: 依赖 {dep_id} 版本不兼容 (需要 {dep_version}, 可用 {dep_metadata.version})"
                )
                return None

            # 如果依赖未加载，先加载依赖
            if dep_id not in self.loaded_plugins:
                dep_instance = await self.load_plugin(dep_id)
                if dep_instance is None:
                    logger.error(f"无法加载插件 {plugin_id}: 依赖 {dep_id} 加载失败")
                    return None

        try:
            # 加载插件模块
            if metadata.path and metadata.entry_point:
                # 构建模块路径
                if os.path.isfile(os.path.join(metadata.path, metadata.entry_point)):
                    module_path = os.path.join(metadata.path, metadata.entry_point)
                    module_name = f"maibot_plugin_{metadata.id}"

                    # 导入模块
                    spec = importlib.util.spec_from_file_location(module_name, module_path)
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)

                    # 查找神经元类
                    neuron_class = None
                    for name, obj in inspect.getmembers(module):
                        if inspect.isclass(obj) and issubclass(obj, Neuron) and obj is not Neuron:
                            neuron_class = obj
                            break

                    if neuron_class is None:
                        logger.error(f"无法加载插件 {plugin_id}: 未找到神经元类")
                        return None

                    # 创建神经元实例
                    neuron_instance = await self.neural_injector.create_instance(neuron_class)

                    # 注册到中央皮层
                    if isinstance(neuron_instance, Sensor):
                        await self.central_cortex.sensory_cortex.register_neuron(neuron_instance)
                    elif isinstance(neuron_instance, Actuator):
                        await self.central_cortex.motor_cortex.register_neuron(neuron_instance)
                    else:
                        # 通用神经元，直接注册到中央皮层
                        await self.central_cortex.register_neuron(neuron_instance)

                    # 存储实例
                    self.loaded_plugins[plugin_id] = neuron_instance
                    logger.info(f"成功加载插件: {metadata.name} (ID: {plugin_id})")

                    return neuron_instance
                else:
                    logger.error(f"无法加载插件 {plugin_id}: 入口点文件不存在: {metadata.entry_point}")
            else:
                logger.error(f"无法加载插件 {plugin_id}: 缺少路径或入口点信息")
        except Exception as e:
            logger.error(f"加载插件时出错: {plugin_id}, 错误: {e}")

        return None

    async def unload_plugin(self, plugin_id: str) -> bool:
        """卸载单个插件

        Args:
            plugin_id: 插件ID

        Returns:
            是否成功卸载
        """
        if plugin_id not in self.loaded_plugins:
            logger.warning(f"插件未加载，无法卸载: {plugin_id}")
            return False

        neuron_instance = self.loaded_plugins[plugin_id]

        try:
            # 从中央皮层中取消注册
            if isinstance(neuron_instance, Sensor):
                await self.central_cortex.sensory_cortex.unregister_neuron(neuron_instance)
            elif isinstance(neuron_instance, Actuator):
                await self.central_cortex.motor_cortex.unregister_neuron(neuron_instance)
            else:
                # 通用神经元
                await self.central_cortex.unregister_neuron(neuron_instance)

            # 移除实例
            del self.loaded_plugins[plugin_id]
            logger.info(f"成功卸载插件: {plugin_id}")

            return True
        except Exception as e:
            logger.error(f"卸载插件时出错: {plugin_id}, 错误: {e}")
            return False

    async def load_enabled_plugins(self) -> None:
        """加载所有启用的插件"""
        logger.info("正在加载启用的插件...")

        # 获取加载顺序
        load_order = self._get_load_order()

        # 加载插件
        for plugin_id in load_order:
            metadata = self.plugins.get(plugin_id)
            if not metadata:
                continue

            # 检查是否启用
            if (
                metadata.enabled
                and (not self.enabled_plugins or plugin_id in self.enabled_plugins)
                and plugin_id not in self.disabled_plugins
            ):
                await self.load_plugin(plugin_id)

        logger.info(f"已加载 {len(self.loaded_plugins)} 个插件")

    async def reload_plugin(self, plugin_id: str) -> Optional[Neuron]:
        """重新加载插件

        Args:
            plugin_id: 插件ID

        Returns:
            重新加载的神经元实例，如果重新加载失败则返回None
        """
        # 先卸载
        if plugin_id in self.loaded_plugins:
            await self.unload_plugin(plugin_id)

        # 重新发现，以获取最新元数据
        await self.discover_plugins()

        # 重新加载
        return await self.load_plugin(plugin_id)

    def get_plugin_metadata(self, plugin_id: str) -> Optional[PluginMetadata]:
        """获取插件元数据

        Args:
            plugin_id: 插件ID

        Returns:
            插件元数据，如果插件不存在则返回None
        """
        return self.plugins.get(plugin_id)

    def get_plugins_by_type(self, neuron_type: str) -> List[PluginMetadata]:
        """获取特定类型的插件列表

        Args:
            neuron_type: 神经元类型 ('sensor', 'actuator', 'neuron')

        Returns:
            该类型的插件元数据列表
        """
        return [metadata for metadata in self.plugins.values() if metadata.neuron_type.lower() == neuron_type.lower()]

    def is_plugin_loaded(self, plugin_id: str) -> bool:
        """检查插件是否已加载

        Args:
            plugin_id: 插件ID

        Returns:
            是否已加载
        """
        return plugin_id in self.loaded_plugins

    def get_plugin_instance(self, plugin_id: str) -> Optional[Neuron]:
        """获取已加载的插件实例

        Args:
            plugin_id: 插件ID

        Returns:
            插件实例，如果插件未加载则返回None
        """
        return self.loaded_plugins.get(plugin_id)

    def enable_plugin(self, plugin_id: str) -> bool:
        """启用插件

        Args:
            plugin_id: 插件ID

        Returns:
            是否成功启用
        """
        if plugin_id not in self.plugins:
            logger.error(f"插件不存在: {plugin_id}")
            return False

        metadata = self.plugins[plugin_id]

        if metadata.enabled:
            logger.warning(f"插件已经启用: {plugin_id}")
            return True

        # 更新元数据
        metadata.enabled = True

        # 如果有元数据文件，更新文件
        if metadata.path:
            metadata_path = os.path.join(metadata.path, "plugin.json")
            if os.path.exists(metadata_path):
                try:
                    with open(metadata_path, "w", encoding="utf-8") as f:
                        json.dump(metadata.to_dict(), f, indent=2)
                except Exception as e:
                    logger.error(f"更新插件元数据文件时出错: {plugin_id}, 错误: {e}")

        # 从禁用列表中移除
        if plugin_id in self.disabled_plugins:
            self.disabled_plugins.remove(plugin_id)

        # 添加到启用列表
        if self.enabled_plugins and plugin_id not in self.enabled_plugins:
            self.enabled_plugins.append(plugin_id)

        logger.info(f"已启用插件: {plugin_id}")
        return True

    def disable_plugin(self, plugin_id: str) -> bool:
        """禁用插件

        Args:
            plugin_id: 插件ID

        Returns:
            是否成功禁用
        """
        if plugin_id not in self.plugins:
            logger.error(f"插件不存在: {plugin_id}")
            return False

        metadata = self.plugins[plugin_id]

        if not metadata.enabled:
            logger.warning(f"插件已经禁用: {plugin_id}")
            return True

        # 更新元数据
        metadata.enabled = False

        # 如果有元数据文件，更新文件
        if metadata.path:
            metadata_path = os.path.join(metadata.path, "plugin.json")
            if os.path.exists(metadata_path):
                try:
                    with open(metadata_path, "w", encoding="utf-8") as f:
                        json.dump(metadata.to_dict(), f, indent=2)
                except Exception as e:
                    logger.error(f"更新插件元数据文件时出错: {plugin_id}, 错误: {e}")

        # 从启用列表中移除
        if self.enabled_plugins and plugin_id in self.enabled_plugins:
            self.enabled_plugins.remove(plugin_id)

        # 添加到禁用列表
        if plugin_id not in self.disabled_plugins:
            self.disabled_plugins.append(plugin_id)

        # 如果插件已加载，尝试卸载
        if plugin_id in self.loaded_plugins:
            asyncio.create_task(self.unload_plugin(plugin_id))

        logger.info(f"已禁用插件: {plugin_id}")
        return True

    def get_all_plugins(self) -> Dict[str, PluginMetadata]:
        """获取所有插件的元数据

        Returns:
            所有插件的元数据字典
        """
        return dict(self.plugins)

    def get_loaded_plugins(self) -> Dict[str, Neuron]:
        """获取所有已加载的插件

        Returns:
            所有已加载的插件实例字典
        """
        return dict(self.loaded_plugins)
