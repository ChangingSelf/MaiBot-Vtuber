from typing import Dict, Any, Optional, TYPE_CHECKING
import logging
import os
import sys
import tempfile
import shutil
import zipfile
import json
import time

from src.neural_plasticity.plugin_manager import PluginMetadata

# 使用TYPE_CHECKING条件导入
if TYPE_CHECKING:
    from src.core.neural_injector import NeuralInjector

logger = logging.getLogger(__name__)


class PluginSandbox:
    """插件沙箱 - 提供插件运行的隔离环境"""

    def __init__(self, plugin_id: str, base_dir: str):
        """初始化插件沙箱

        Args:
            plugin_id: 插件ID
            base_dir: 基础目录
        """
        self.plugin_id = plugin_id
        self.base_dir = base_dir
        self.sandbox_dir = os.path.join(base_dir, f"sandbox_{plugin_id}")

        # 创建沙箱目录
        os.makedirs(self.sandbox_dir, exist_ok=True)

        # 沙箱环境中允许的操作
        self.allowed_imports = {
            "src.neurons",
            "src.sensors",
            "src.actuators",
            "src.signals",
            "src.utils",
            "asyncio",
            "typing",
            "logging",
            "json",
            "os.path",
            "time",
        }

        # 沙箱环境中限制的操作
        self.restricted_imports = {
            "os.system",
            "subprocess",
            "socket",
            "http.server",
            "socketserver",
            "threading",
            "multiprocessing",
        }

    def setup(self) -> None:
        """设置沙箱环境"""
        # 创建一个临时的 sys.path 修改，让插件能够导入主代码
        sys.path.insert(0, self.sandbox_dir)

    def cleanup(self) -> None:
        """清理沙箱环境"""
        # 恢复 sys.path
        if self.sandbox_dir in sys.path:
            sys.path.remove(self.sandbox_dir)

        # 清理临时目录
        shutil.rmtree(self.sandbox_dir, ignore_errors=True)

    def is_import_allowed(self, name: str) -> bool:
        """检查导入是否被允许

        Args:
            name: 模块名称

        Returns:
            是否允许导入
        """
        # 检查是否是允许的导入
        for allowed in self.allowed_imports:
            if name == allowed or name.startswith(f"{allowed}."):
                return True

        # 检查是否是限制的导入
        for restricted in self.restricted_imports:
            if name == restricted or name.startswith(f"{restricted}."):
                return False

        # 默认允许其他Python标准库导入
        return True


class PluginLoader:
    """插件加载器 - 负责安装、提取和准备插件"""

    def __init__(self, neural_injector: "NeuralInjector", config: Dict[str, Any]):
        """初始化插件加载器

        Args:
            neural_injector: 神经注入器
            config: 配置字典
        """
        self.neural_injector = neural_injector
        self.config = config
        self.plugin_dirs = config.get("plugin_dirs", ["plugins"])
        self.temp_dir = config.get("plugin_temp_dir", os.path.join(tempfile.gettempdir(), "maibot_plugins"))

        # 创建临时目录
        os.makedirs(self.temp_dir, exist_ok=True)

        # 已创建的沙箱环境
        self.sandboxes: Dict[str, PluginSandbox] = {}

    async def install_from_zip(self, zip_path: str, plugin_type: str = None) -> Optional[PluginMetadata]:
        """从zip文件安装插件

        Args:
            zip_path: zip文件路径
            plugin_type: 插件类型 ('sensor', 'actuator', 'neuron')，如果为None则自动检测

        Returns:
            安装的插件元数据，如果安装失败则返回None
        """
        try:
            # 确保zip文件存在
            if not os.path.exists(zip_path) or not zipfile.is_zipfile(zip_path):
                logger.error(f"无效的zip文件: {zip_path}")
                return None

            # 创建临时目录解压文件
            with tempfile.TemporaryDirectory(dir=self.temp_dir) as temp_dir:
                # 解压文件
                with zipfile.ZipFile(zip_path, "r") as zip_ref:
                    zip_ref.extractall(temp_dir)

                # 查找 plugin.json
                metadata_path = os.path.join(temp_dir, "plugin.json")
                if not os.path.exists(metadata_path):
                    logger.error(f"缺少 plugin.json 文件: {zip_path}")
                    return None

                # 读取元数据
                with open(metadata_path, "r", encoding="utf-8") as f:
                    metadata_dict = json.load(f)

                # 创建元数据对象
                metadata = PluginMetadata.from_dict(metadata_dict)

                # 如果指定了插件类型，覆盖元数据中的类型
                if plugin_type:
                    metadata.neuron_type = plugin_type.lower()

                # 验证元数据
                if not metadata.id or not metadata.name or not metadata.version:
                    logger.error(f"无效的插件元数据: {zip_path}")
                    return None

                # 选择目标目录
                if metadata.neuron_type == "sensor":
                    sub_dir = "sensors"
                elif metadata.neuron_type == "actuator":
                    sub_dir = "actuators"
                else:
                    sub_dir = "neurons"

                # 创建目标目录
                for plugin_dir in self.plugin_dirs:
                    target_dir = os.path.join(plugin_dir, sub_dir, metadata.id)
                    if os.path.exists(target_dir):
                        # 如果插件已存在，先备份
                        backup_dir = f"{target_dir}_backup_{int(time.time())}"
                        shutil.move(target_dir, backup_dir)
                        logger.info(f"备份已存在的插件: {target_dir} -> {backup_dir}")

                    # 复制文件
                    shutil.copytree(temp_dir, target_dir)
                    logger.info(f"安装插件到: {target_dir}")

                    # 设置元数据路径
                    metadata.path = target_dir

                    return metadata

                logger.error("未找到有效的插件目录")
                return None
        except Exception as e:
            logger.error(f"安装插件时出错: {zip_path}, 错误: {e}")
            return None

    async def install_from_directory(self, directory: str, plugin_type: str = None) -> Optional[PluginMetadata]:
        """从目录安装插件

        Args:
            directory: 源目录路径
            plugin_type: 插件类型 ('sensor', 'actuator', 'neuron')，如果为None则自动检测

        Returns:
            安装的插件元数据，如果安装失败则返回None
        """
        try:
            # 确保目录存在
            if not os.path.exists(directory) or not os.path.isdir(directory):
                logger.error(f"无效的目录: {directory}")
                return None

            # 查找 plugin.json
            metadata_path = os.path.join(directory, "plugin.json")
            if not os.path.exists(metadata_path):
                logger.error(f"缺少 plugin.json 文件: {directory}")
                return None

            # 读取元数据
            with open(metadata_path, "r", encoding="utf-8") as f:
                metadata_dict = json.load(f)

            # 创建元数据对象
            metadata = PluginMetadata.from_dict(metadata_dict)

            # 如果指定了插件类型，覆盖元数据中的类型
            if plugin_type:
                metadata.neuron_type = plugin_type.lower()

            # 验证元数据
            if not metadata.id or not metadata.name or not metadata.version:
                logger.error(f"无效的插件元数据: {directory}")
                return None

            # 选择目标目录
            if metadata.neuron_type == "sensor":
                sub_dir = "sensors"
            elif metadata.neuron_type == "actuator":
                sub_dir = "actuators"
            else:
                sub_dir = "neurons"

            # 创建目标目录
            for plugin_dir in self.plugin_dirs:
                target_dir = os.path.join(plugin_dir, sub_dir, metadata.id)
                if os.path.exists(target_dir):
                    # 如果插件已存在，先备份
                    backup_dir = f"{target_dir}_backup_{int(time.time())}"
                    shutil.move(target_dir, backup_dir)
                    logger.info(f"备份已存在的插件: {target_dir} -> {backup_dir}")

                # 复制文件
                shutil.copytree(directory, target_dir)
                logger.info(f"安装插件到: {target_dir}")

                # 设置元数据路径
                metadata.path = target_dir

                return metadata

            logger.error("未找到有效的插件目录")
            return None
        except Exception as e:
            logger.error(f"安装插件时出错: {directory}, 错误: {e}")
            return None

    async def uninstall_plugin(self, plugin_id: str) -> bool:
        """卸载插件

        Args:
            plugin_id: 插件ID

        Returns:
            是否卸载成功
        """
        try:
            for plugin_dir in self.plugin_dirs:
                # 查找所有可能的位置
                for sub_dir in ["sensors", "actuators", "neurons"]:
                    target_dir = os.path.join(plugin_dir, sub_dir, plugin_id)
                    if os.path.exists(target_dir):
                        # 删除目录
                        shutil.rmtree(target_dir)
                        logger.info(f"卸载插件: {target_dir}")
                        return True

            logger.warning(f"未找到插件目录: {plugin_id}")
            return False
        except Exception as e:
            logger.error(f"卸载插件时出错: {plugin_id}, 错误: {e}")
            return False

    def create_sandbox(self, plugin_id: str) -> PluginSandbox:
        """为插件创建沙箱环境

        Args:
            plugin_id: 插件ID

        Returns:
            创建的沙箱环境
        """
        if plugin_id in self.sandboxes:
            return self.sandboxes[plugin_id]

        sandbox = PluginSandbox(plugin_id, self.temp_dir)
        self.sandboxes[plugin_id] = sandbox
        return sandbox

    def cleanup_sandbox(self, plugin_id: str) -> None:
        """清理插件沙箱环境

        Args:
            plugin_id: 插件ID
        """
        if plugin_id in self.sandboxes:
            self.sandboxes[plugin_id].cleanup()
            del self.sandboxes[plugin_id]

    def cleanup_all_sandboxes(self) -> None:
        """清理所有插件沙箱环境"""
        for plugin_id in list(self.sandboxes.keys()):
            self.cleanup_sandbox(plugin_id)

    async def create_plugin_template(
        self, plugin_id: str, name: str, neuron_type: str, output_dir: str
    ) -> Optional[str]:
        """创建插件模板

        Args:
            plugin_id: 插件ID
            name: 插件名称
            neuron_type: 神经元类型 ('sensor', 'actuator', 'neuron')
            output_dir: 输出目录

        Returns:
            创建的插件目录路径，如果创建失败则返回None
        """
        try:
            # 验证神经元类型
            if neuron_type.lower() not in ["sensor", "actuator", "neuron"]:
                logger.error(f"无效的神经元类型: {neuron_type}")
                return None

            # 创建输出目录
            plugin_dir = os.path.join(output_dir, plugin_id)
            os.makedirs(plugin_dir, exist_ok=True)

            # 创建元数据文件
            metadata = {
                "id": plugin_id,
                "name": name,
                "version": "0.1.0",
                "description": f"一个{neuron_type}插件模板",
                "author": "MaiBot",
                "neuron_type": neuron_type.lower(),
                "entry_point": f"{plugin_id}.py",
                "dependencies": {},
                "config_schema": {"enabled": {"type": "boolean", "default": True, "description": "是否启用该插件"}},
                "enabled": True,
            }

            # 写入元数据文件
            with open(os.path.join(plugin_dir, "plugin.json"), "w", encoding="utf-8") as f:
                json.dump(metadata, f, indent=2, ensure_ascii=False)

            # 创建模板代码
            template_code = self._generate_template_code(plugin_id, name, neuron_type)

            # 写入模板代码
            with open(os.path.join(plugin_dir, f"{plugin_id}.py"), "w", encoding="utf-8") as f:
                f.write(template_code)

            logger.info(f"创建插件模板: {plugin_dir}")
            return plugin_dir
        except Exception as e:
            logger.error(f"创建插件模板时出错: {plugin_id}, 错误: {e}")
            return None

    def _generate_template_code(self, plugin_id: str, name: str, neuron_type: str) -> str:
        """生成插件模板代码

        Args:
            plugin_id: 插件ID
            name: 插件名称
            neuron_type: 神经元类型 ('sensor', 'actuator', 'neuron')

        Returns:
            生成的模板代码
        """
        class_name = "".join(word.capitalize() for word in plugin_id.split("_"))

        if neuron_type.lower() == "sensor":
            base_class = "Sensor"
            imports = (
                "from src.sensors.base_sensor import Sensor\nfrom src.signals.sensory_signals import SensorySignal"
            )
            signal_type = "SensorySignal"
            methods = """
    async def _activate(self) -> None:
        \"\"\"激活传感器\"\"\"
        self.logger.info(f"{self.name} 已激活")
        
        # 在这里启动你的传感器逻辑
        # 例如：启动一个后台任务监听外部事件
        # self._task = asyncio.create_task(self._monitor_events())
        
    async def _deactivate(self) -> None:
        \"\"\"停用传感器\"\"\"
        # 在这里停止你的传感器逻辑
        # 例如：取消后台任务
        # if self._task:
        #     self._task.cancel()
        #     try:
        #         await self._task
        #     except asyncio.CancelledError:
        #         pass
        
        self.logger.info(f"{self.name} 已停用")
        
    async def _register_receptors(self) -> None:
        \"\"\"注册信号接收器\"\"\"
        # 传感器通常不需要注册接收器
        # 但如果需要响应某些系统信号，可以在这里注册
        pass
        
    # 示例：监控外部事件的后台任务
    # async def _monitor_events(self) -> None:
    #     \"\"\"监控外部事件\"\"\"
    #     try:
    #         while True:
    #             # 模拟接收外部事件
    #             await asyncio.sleep(5)
    #             
    #             # 创建感知信号
    #             signal = SensorySignal(
    #                 source=self.name,
    #                 data={"message": "这是一个测试事件"},
    #                 timestamp=time.time()
    #             )
    #             
    #             # 传输信号
    #             await self.transmit_signal(signal)
    #     except asyncio.CancelledError:
    #         # 正常取消
    #         pass
    #     except Exception as e:
    #         self.logger.error(f"监控事件时出错: {e}")
"""
        elif neuron_type.lower() == "actuator":
            base_class = "Actuator"
            imports = (
                "from src.actuators.base_actuator import Actuator\nfrom src.signals.motor_signals import MotorSignal"
            )
            signal_type = "MotorSignal"
            methods = """
    async def _activate(self) -> None:
        \"\"\"激活执行器\"\"\"
        self.logger.info(f"{self.name} 已激活")
        
        # 在这里初始化你的执行器
        # 例如：连接到外部设备或服务
        
    async def _deactivate(self) -> None:
        \"\"\"停用执行器\"\"\"
        # 在这里清理你的执行器资源
        # 例如：断开与外部设备或服务的连接
        
        self.logger.info(f"{self.name} 已停用")
        
    async def _register_receptors(self) -> None:
        \"\"\"注册信号接收器\"\"\"
        # 注册接收器，接收需要处理的信号
        filter = SignalFilter(signal_types=[SignalType.MOTOR])
        receptor_id = self.synaptic_network.register_receptor(
            self._handle_signal, filter, is_async=True
        )
        self.receptor_ids.append(receptor_id)
        
    async def _handle_signal(self, signal: MotorSignal) -> None:
        \"\"\"处理接收到的信号
        
        Args:
            signal: 接收到的信号
        \"\"\"
        try:
            self.logger.debug(f"接收到信号: {signal}")
            
            # 在这里实现你的信号处理逻辑
            # 例如：控制外部设备或服务
            
            # 示例：打印信号内容
            self.logger.info(f"执行操作: {signal.data}")
            
        except Exception as e:
            self.logger.error(f"处理信号时出错: {e}")
            # 可以选择重新抛出异常，或者在这里处理错误
"""
        else:
            base_class = "Neuron"
            imports = "from src.neurons.neuron import Neuron\nfrom src.signals.neural_signal import NeuralSignal"
            signal_type = "NeuralSignal"
            methods = """
    async def _activate(self) -> None:
        \"\"\"激活神经元\"\"\"
        self.logger.info(f"{self.name} 已激活")
        
        # 在这里启动你的神经元逻辑
        
    async def _deactivate(self) -> None:
        \"\"\"停用神经元\"\"\"
        # 在这里停止你的神经元逻辑
        
        self.logger.info(f"{self.name} 已停用")
        
    async def _register_receptors(self) -> None:
        \"\"\"注册信号接收器\"\"\"
        # 注册接收器，接收需要处理的信号
        filter = SignalFilter(signal_types=[SignalType.SENSORY])  # 根据需要调整
        receptor_id = self.synaptic_network.register_receptor(
            self._handle_signal, filter, is_async=True
        )
        self.receptor_ids.append(receptor_id)
        
    async def _handle_signal(self, signal: NeuralSignal) -> None:
        \"\"\"处理接收到的信号
        
        Args:
            signal: 接收到的信号
        \"\"\"
        try:
            self.logger.debug(f"接收到信号: {signal}")
            
            # 在这里实现你的信号处理逻辑
            
            # 示例：处理信号并可能生成新的信号
            processed_data = self._process_data(signal.data)
            
            # 创建新的神经信号
            new_signal = NeuralSignal(
                source=self.name,
                data=processed_data,
                timestamp=time.time()
            )
            
            # 传输信号
            await self.transmit_signal(new_signal)
            
        except Exception as e:
            self.logger.error(f"处理信号时出错: {e}")
            
    def _process_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        \"\"\"处理数据
        
        Args:
            data: 输入数据
            
        Returns:
            处理后的数据
        \"\"\"
        # 在这里实现你的数据处理逻辑
        return data
"""

        template = f"""import logging
import asyncio
import time
from typing import Dict, Any, List, Optional

{imports}
from src.signals.neural_signal import SignalType, SignalFilter, SignalPriority

class {class_name}({base_class}):
    \"\"\"
    {name} - 一个{neuron_type}插件
    
    这是一个模板插件，可以根据需要修改。
    \"\"\"
    
    def __init__(self, synaptic_network):
        \"\"\"初始化{class_name}
        
        Args:
            synaptic_network: 神经突触网络
        \"\"\"
        super().__init__(synaptic_network, name="{name}")
        self.logger = logging.getLogger(f"plugin.{plugin_id}")
        
    async def _initialize(self, config: Dict[str, Any]) -> None:
        \"\"\"初始化插件
        
        Args:
            config: 插件配置
        \"\"\"
        self.logger.info(f"初始化 {self.name}")
        
        # 从配置中获取参数
        self.enabled = config.get("enabled", True)
        
        # 在这里进行其他初始化操作
{methods}

# 提供插件元数据的类方法，用于从已安装的包中加载
@classmethod
def get_plugin_metadata(cls):
    \"\"\"获取插件元数据
    
    Returns:
        包含插件元数据的字典
    \"\"\"
    return {{
        "id": "{plugin_id}",
        "name": "{name}",
        "version": "0.1.0",
        "description": "一个{neuron_type}插件模板",
        "author": "MaiBot",
        "neuron_type": "{neuron_type.lower()}",
        "entry_point": "{plugin_id}.py",
        "dependencies": {{}},
        "enabled": True
    }}
"""
        return template
