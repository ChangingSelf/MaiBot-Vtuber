# 神经可塑性系统 - 插件开发指南

## 简介

神经可塑性系统允许 MaiBot-Vtuber 程序在运行时动态扩展和修改功能，类似于大脑的可塑性。通过开发插件，你可以为系统添加新的感知能力（如接入新的直播平台）或执行能力（如控制新的输出设备）。

## 插件类型

神经可塑性系统支持三种类型的插件：

1. **感知神经元(Sensor)** - 负责接收外部输入，例如从直播平台获取弹幕
2. **运动神经元(Actuator)** - 负责执行动作，例如控制VTubeStudio或输出字幕
3. **通用神经元(Neuron)** - 处理内部逻辑，可以同时接收和发送信号

## 插件结构

一个标准的插件包含以下文件结构：

```
my_plugin/
├── plugin.json    # 插件元数据
└── my_plugin.py   # 插件主要代码
```

### 插件元数据 (plugin.json)

plugin.json 文件包含插件的基本信息和配置：

```json
{
  "id": "my_plugin",
  "name": "我的插件",
  "version": "0.1.0",
  "description": "这是一个示例插件",
  "author": "开发者姓名",
  "neuron_type": "sensor",  // 可选值: "sensor", "actuator", "neuron"
  "entry_point": "my_plugin.py",
  "dependencies": {
    "another_plugin": ">=0.2.0"  // 可选的依赖项
  },
  "config_schema": {
    "enabled": {
      "type": "boolean",
      "default": true,
      "description": "是否启用该插件"
    },
    "custom_option": {
      "type": "string",
      "default": "默认值",
      "description": "自定义选项说明"
    }
  },
  "enabled": true
}
```

### 插件代码 (my_plugin.py)

插件代码需要定义一个继承自 `Sensor`、`Actuator` 或 `Neuron` 的类：

```python
import logging
import asyncio
import time
from typing import Dict, Any

from src.sensors.base_sensor import Sensor
from src.signals.sensory_signals import SensorySignal
from src.signals.neural_signal import SignalType, SignalFilter, SignalPriority

class MyPlugin(Sensor):
    """我的插件 - 简短描述"""
    
    def __init__(self, synaptic_network):
        """初始化插件
        
        Args:
            synaptic_network: 神经突触网络
        """
        super().__init__(synaptic_network, name="我的插件")
        self.logger = logging.getLogger(f"plugin.my_plugin")
        
    async def _initialize(self, config: Dict[str, Any]) -> None:
        """初始化插件
        
        Args:
            config: 插件配置
        """
        self.logger.info(f"初始化 {self.name}")
        
        # 从配置中获取参数
        self.enabled = config.get("enabled", True)
        self.custom_option = config.get("custom_option", "默认值")
        
    async def _activate(self) -> None:
        """激活插件"""
        self.logger.info(f"{self.name} 已激活")
        
        # 在这里添加激活逻辑
        
    async def _deactivate(self) -> None:
        """停用插件"""
        self.logger.info(f"{self.name} 已停用")
        
        # 在这里添加停用逻辑
        
    async def _register_receptors(self) -> None:
        """注册信号接收器"""
        # 如果需要接收信号，在这里注册接收器
        
    # 添加自定义方法...
    
    @classmethod
    def get_plugin_metadata(cls):
        """获取插件元数据
        
        Returns:
            包含插件元数据的字典
        """
        return {
            "id": "my_plugin",
            "name": "我的插件",
            "version": "0.1.0",
            "description": "这是一个示例插件",
            "author": "开发者姓名",
            "neuron_type": "sensor",
            "entry_point": "my_plugin.py",
            "dependencies": {},
            "enabled": True
        }
```

## 开发不同类型的插件

### 感知神经元 (Sensor)

感知神经元负责接收外部输入，并将其转换为系统内部的感知信号：

```python
from src.sensors.base_sensor import Sensor
from src.signals.sensory_signals import SensorySignal

class MySensor(Sensor):
    # ...
    
    async def _activate(self) -> None:
        """激活传感器"""
        self.logger.info(f"{self.name} 已激活")
        
        # 启动一个后台任务监听外部事件
        self._task = asyncio.create_task(self._monitor_events())
        
    async def _monitor_events(self) -> None:
        """监控外部事件"""
        try:
            while True:
                # 这里是监听外部事件的逻辑
                # ...
                
                # 创建感知信号
                signal = SensorySignal(
                    source=self.name,
                    data={"message": "这是从外部接收到的消息"},
                    timestamp=time.time()
                )
                
                # 发送信号
                await self.transmit_signal(signal)
                await asyncio.sleep(1)  # 避免过度循环
        except asyncio.CancelledError:
            # 正常取消
            pass
```

### 运动神经元 (Actuator)

运动神经元负责执行动作，响应系统内部的信号：

```python
from src.actuators.base_actuator import Actuator
from src.signals.motor_signals import MotorSignal
from src.signals.neural_signal import SignalType, SignalFilter

class MyActuator(Actuator):
    # ...
    
    async def _register_receptors(self) -> None:
        """注册信号接收器"""
        # 注册接收器，接收需要处理的信号
        filter = SignalFilter(signal_types=[SignalType.MOTOR])
        receptor_id = self.synaptic_network.register_receptor(
            self._handle_signal, filter, is_async=True
        )
        self.receptor_ids.append(receptor_id)
        
    async def _handle_signal(self, signal: MotorSignal) -> None:
        """处理接收到的信号
        
        Args:
            signal: 接收到的信号
        """
        try:
            self.logger.debug(f"接收到信号: {signal}")
            
            # 在这里处理信号和执行相应动作
            await self._perform_action(signal.data)
            
        except Exception as e:
            self.logger.error(f"处理信号时出错: {e}")
            
    async def _perform_action(self, data: Dict[str, Any]) -> None:
        """执行动作
        
        Args:
            data: 信号数据
        """
        # 在这里实现具体的动作逻辑
        pass
```

### 通用神经元 (Neuron)

通用神经元可以同时接收和发送信号，处理内部逻辑：

```python
from src.neurons.neuron import Neuron
from src.signals.neural_signal import NeuralSignal, SignalType, SignalFilter

class MyNeuron(Neuron):
    # ...
    
    async def _register_receptors(self) -> None:
        """注册信号接收器"""
        # 注册接收器，接收需要处理的信号
        filter = SignalFilter(signal_types=[SignalType.SENSORY])
        receptor_id = self.synaptic_network.register_receptor(
            self._handle_signal, filter, is_async=True
        )
        self.receptor_ids.append(receptor_id)
        
    async def _handle_signal(self, signal: NeuralSignal) -> None:
        """处理接收到的信号
        
        Args:
            signal: 接收到的信号
        """
        try:
            # 在这里处理信号
            processed_data = self._process_data(signal.data)
            
            # 创建新的信号
            new_signal = NeuralSignal(
                source=self.name,
                data=processed_data,
                timestamp=time.time()
            )
            
            # 发送信号
            await self.transmit_signal(new_signal)
            
        except Exception as e:
            self.logger.error(f"处理信号时出错: {e}")
            
    def _process_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """处理数据
        
        Args:
            data: 输入数据
            
        Returns:
            处理后的数据
        """
        # 在这里实现数据处理逻辑
        return data
```

## 插件开发流程

1. 使用插件模板生成器创建插件模板：

```python
from src.neural_plasticity.plugin_loader import PluginLoader

async def create_plugin():
    loader = PluginLoader(injector, config)
    plugin_dir = await loader.create_plugin_template(
        plugin_id="my_plugin",
        name="我的插件",
        neuron_type="sensor",  # 或 "actuator" 或 "neuron"
        output_dir="plugins"
    )
    print(f"插件模板已创建在: {plugin_dir}")
```

2. 修改生成的模板代码，实现你的插件逻辑
3. 安装插件：

```python
from src.neural_plasticity.plugin_loader import PluginLoader
from src.neural_plasticity.plugin_manager import PluginManager

async def install_and_load_plugin():
    # 安装插件
    loader = PluginLoader(injector, config)
    metadata = await loader.install_from_directory("path/to/my_plugin")
    
    # 加载插件
    plugin_manager = PluginManager(injector, config)
    await plugin_manager.initialize()
    plugin_instance = await plugin_manager.load_plugin(metadata.id)
    
    if plugin_instance:
        print(f"插件 {metadata.name} 已成功加载")
```

## 最佳实践

1. **异常处理** - 在插件中妥善处理异常，避免未捕获的异常导致系统崩溃
2. **资源管理** - 在 `_deactivate` 方法中清理所有资源，如关闭连接、取消任务等
3. **配置验证** - 在 `_initialize` 方法中验证配置的有效性
4. **适当日志** - 使用适当的日志级别记录重要事件和错误
5. **文档** - 为您的插件提供清晰的文档，包括功能描述、配置选项和使用示例

## 示例插件

请参考 `plugins/sensors/demo_sensor` 目录中的示例插件，了解如何创建一个基本的感知神经元插件。 