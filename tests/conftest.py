"""
Pytest配置文件，提供通用的测试fixtures。
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock
from src.core.synaptic_network import SynapticNetwork
from src.core.neural_injector import NeuralInjector
from src.core.brain_context import BrainContext
from src.signals.neural_signal import NeuralSignal


@pytest.fixture
def event_loop():
    """创建事件循环用于异步测试"""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def mock_synaptic_network():
    """创建模拟的神经突触网络"""
    network = MagicMock(spec=SynapticNetwork)
    network.transmit = AsyncMock()
    network.subscribe = MagicMock()
    network.unsubscribe = MagicMock()
    return network


@pytest.fixture
def mock_neural_injector():
    """创建模拟的神经注入器"""
    injector = MagicMock(spec=NeuralInjector)
    return injector


@pytest.fixture
def mock_brain_context():
    """创建模拟的思维中枢"""
    context = MagicMock(spec=BrainContext)
    return context


@pytest.fixture
def sample_neural_signal():
    """创建示例神经信号用于测试"""
    return NeuralSignal(source="test_source", type="test_type", content={"message": "测试消息"}, priority=5)


@pytest.fixture
def mock_config():
    """创建模拟配置用于测试"""
    return {
        "sensors": {"test_sensor": {"enabled": True, "parameter1": "value1", "parameter2": 42}},
        "actuators": {"test_actuator": {"enabled": True, "parameter1": "value1", "parameter2": 42}},
        "core": {"parameter1": "value1", "parameter2": 42},
    }
