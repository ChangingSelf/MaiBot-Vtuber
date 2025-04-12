"""神经可塑性 - 提供系统动态扩展能力的插件系统

神经可塑性系统允许系统在运行时动态扩展和修改，类似于大脑的可塑性。
它通过插件机制实现，支持动态加载感觉神经元和运动神经元插件。
"""

from src.neural_plasticity.plugin_manager import PluginManager, PluginMetadata
from src.neural_plasticity.plugin_loader import PluginLoader, PluginSandbox

__all__ = ["PluginManager", "PluginMetadata", "PluginLoader", "PluginSandbox"]
