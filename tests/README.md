# MaiBot-Vtuber测试框架

## 概述

本测试框架为MaiBot-Vtuber项目提供全面的单元测试和集成测试支持。系统基于神经系统隐喻设计，测试框架围绕不同类型的神经元组件和神经突触网络进行组织。

## 测试结构

测试目录结构如下：

```
tests/
├── __init__.py          # 测试包初始化
├── conftest.py          # Pytest配置和通用fixtures
├── test_core/           # 核心组件测试
│   ├── test_synaptic_network.py    # 神经突触网络测试
│   ├── test_central_cortex.py      # 中央皮层测试
│   └── test_neural_injector.py     # 神经注入器测试
├── test_neurons/        # 神经元基类测试
│   └── test_neuron.py              # 神经元基类测试
├── test_sensors/        # 感觉神经元测试
│   └── test_sensor.py              # 感觉神经元基类测试
├── test_actuators/      # 运动神经元测试
│   └── test_actuator.py            # 运动神经元基类测试
├── test_signals/        # 神经信号测试
│   └── test_neural_signal.py       # 神经信号基类测试
├── test_cerebellum/     # 辅助系统测试
│   ├── test_immune_system.py       # 免疫系统测试
│   └── test_neural_trace.py        # 神经痕迹测试
└── test_neural_plasticity/ # 神经可塑性测试
    ├── test_plugin_manager.py      # 插件管理器测试
    └── test_plugin_loader.py       # 插件加载器测试
```

## 运行测试

### 安装测试依赖

```bash
pip install -r requirements-dev.txt
```

### 运行所有测试

```bash
pytest
```

### 运行特定测试

```bash
# 运行核心组件测试
pytest tests/test_core/

# 运行单个测试文件
pytest tests/test_core/test_synaptic_network.py

# 运行特定测试函数
pytest tests/test_core/test_synaptic_network.py::TestSynapticNetwork::test_signal_transmission
```

## 测试fixtures

`conftest.py`文件提供了以下通用fixtures：

- `event_loop`: 创建异步测试使用的事件循环
- `mock_synaptic_network`: 创建模拟的神经突触网络
- `mock_neural_injector`: 创建模拟的神经注入器
- `mock_brain_context`: 创建模拟的思维中枢
- `sample_neural_signal`: 创建用于测试的示例神经信号
- `mock_config`: 创建用于测试的模拟配置

## 测试编写指南

### 1. 异步测试

系统大量使用异步代码，测试也需要使用异步方式：

```python
import pytest

@pytest.mark.asyncio
async def test_async_function():
    # 执行异步测试
    result = await some_async_function()
    assert result == expected_value
```

### 2. 模拟依赖

使用`unittest.mock`模拟依赖：

```python
from unittest.mock import AsyncMock, MagicMock, patch

# 模拟方法
with patch.object(TargetClass, 'method_name', return_value=mock_return) as mock_method:
    # 测试逻辑
    result = target_instance.call_method()
    
    # 验证模拟方法被调用
    mock_method.assert_called_once_with(expected_args)
```

### 3. 测试神经元

测试神经元时需要关注以下方面：

- 初始化: 配置和资源准备
- 激活: 启动任务和注册接收器
- 信号处理: 接收和发送神经信号
- 停用: 任务取消和资源释放

```python
@pytest.mark.asyncio
async def test_neuron_lifecycle(mock_synaptic_network):
    # 创建神经元
    neuron = SomeNeuron(mock_synaptic_network)
    
    # 测试初始化
    config = {"param": "value"}
    await neuron.initialize(config)
    
    # 测试激活
    await neuron.activate()
    assert neuron.is_active is True
    
    # 测试信号处理
    signal = create_test_signal()
    await neuron._handle_signal(signal)
    
    # 测试停用
    await neuron.deactivate()
    assert neuron.is_active is False
```

## 测试覆盖率

运行测试并生成覆盖率报告：

```bash
pytest --cov=src --cov-report=html
```

覆盖率报告将生成在`htmlcov`目录中。

## 集成测试

集成测试验证多个组件协同工作的情况：

```python
@pytest.mark.asyncio
async def test_sensor_to_actuator_integration():
    # 创建实际的神经突触网络
    network = SynapticNetwork()
    await network.start()
    
    # 创建感觉神经元和运动神经元
    sensor = TestSensor(network)
    actuator = TestActuator(network)
    
    # 初始化和激活
    await sensor.initialize({})
    await actuator.initialize({})
    await sensor.activate()
    await actuator.activate()
    
    # 发送测试输入
    test_input = {"message": "test"}
    await sensor.sense(test_input)
    
    # 等待信号处理
    await asyncio.sleep(0.1)
    
    # 验证结果
    assert actuator.last_executed_action is not None
    
    # 清理
    await actuator.deactivate()
    await sensor.deactivate()
    await network.stop()
```

## 模拟神经元

为了测试特定场景，可以使用以下模拟神经元：

```python
# 模拟感觉神经元
class MockSensor(Sensor):
    async def _initialize(self, config):
        pass
        
    async def sense(self, input_data):
        signal = NeuralSignal(
            source=self.name,
            type=SignalType.SENSORY,
            content=input_data
        )
        await self.synaptic_network.transmit(signal)
        
# 模拟运动神经元
class MockActuator(Actuator):
    async def _initialize(self, config):
        self.received_actions = []
        
    async def _execute_action(self, action):
        self.received_actions.append(action)
```

## 测试调试

### 启用详细日志

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

### 检查异步任务

```python
import asyncio

# 列出所有任务
all_tasks = asyncio.all_tasks()
for task in all_tasks:
    print(f"Task: {task.get_name()}, Done: {task.done()}")
``` 