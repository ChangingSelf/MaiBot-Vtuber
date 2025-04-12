"""
测试神经元基类模块。
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from src.neurons.neuron import Neuron
from src.signals.neural_signal import NeuralSignal, SignalType


# 创建一个测试用的具体神经元实现，因为Neuron是抽象类
class TestNeuronImpl(Neuron):
    """用于测试的神经元实现类"""

    async def _initialize(self, config):
        self.test_config = config

    async def _activate(self):
        self.custom_activate_called = True

    async def _deactivate(self):
        self.custom_deactivate_called = True

    async def _register_receptors(self):
        self.register_called = True
        receptor_id = self.synaptic_network.register_receptor(self._handle_test_signal, is_async=True)
        self.receptor_ids.append(receptor_id)

    async def _handle_test_signal(self, signal):
        self.stats["signals_processed"] += 1
        self.last_signal = signal

    async def transmit_test_signal(self, content):
        signal = NeuralSignal(source=self.name, type=SignalType.CORE, content=content)
        await self.synaptic_network.transmit(signal)
        self.stats["signals_transmitted"] += 1
        return signal


class TestNeuron:
    """测试神经元基类"""

    @pytest.fixture
    def mock_synaptic_network(self):
        """创建模拟的神经突触网络"""
        network = MagicMock()
        network.transmit = AsyncMock()
        network.register_receptor = MagicMock(return_value="test-receptor-id")
        return network

    @pytest.fixture
    def test_neuron(self, mock_synaptic_network):
        """创建测试神经元实例"""
        return TestNeuronImpl(mock_synaptic_network, "TestNeuron")

    @pytest.fixture
    def test_config(self):
        """创建测试配置"""
        return {"param1": "value1", "param2": 42}

    @pytest.mark.asyncio
    async def test_neuron_initialization(self, test_neuron, test_config):
        """测试神经元初始化"""
        await test_neuron.initialize(test_config)
        assert test_neuron.test_config == test_config
        assert test_neuron.name == "TestNeuron"
        assert test_neuron.is_active is False

    @pytest.mark.asyncio
    async def test_neuron_activation(self, test_neuron, test_config):
        """测试神经元激活"""
        # 初始化神经元
        await test_neuron.initialize(test_config)

        # 激活神经元
        await test_neuron.activate()

        # 检查状态
        assert test_neuron.is_active is True
        assert test_neuron.custom_activate_called is True
        assert test_neuron.register_called is True

        # 检查接收器注册
        test_neuron.synaptic_network.register_receptor.assert_called_once()

    @pytest.mark.asyncio
    async def test_neuron_deactivation(self, test_neuron, test_config):
        """测试神经元停用"""
        # 初始化并激活神经元
        await test_neuron.initialize(test_config)
        await test_neuron.activate()

        # 停用神经元
        await test_neuron.deactivate()

        # 检查状态
        assert test_neuron.is_active is False
        assert test_neuron.custom_deactivate_called is True

        # 检查接收器取消注册
        test_neuron.synaptic_network.unregister_receptor.assert_called_once_with("test-receptor-id")

    @pytest.mark.asyncio
    async def test_signal_transmission(self, test_neuron, test_config):
        """测试信号传输"""
        # 初始化神经元
        await test_neuron.initialize(test_config)

        # 传输测试信号
        test_content = {"test": "data"}
        signal = await test_neuron.transmit_test_signal(test_content)

        # 检查信号是否正确传递
        test_neuron.synaptic_network.transmit.assert_called_once_with(signal)

        # 检查统计信息更新
        assert test_neuron.stats["signals_transmitted"] == 1

    @pytest.mark.asyncio
    async def test_error_handling(self, test_neuron):
        """测试错误处理"""
        # 模拟初始化过程中出现错误
        with patch.object(TestNeuronImpl, "_initialize", side_effect=Exception("测试异常")):
            with pytest.raises(Exception):
                await test_neuron.initialize({})

            # 检查错误计数
            assert test_neuron.stats["errors"] == 1
