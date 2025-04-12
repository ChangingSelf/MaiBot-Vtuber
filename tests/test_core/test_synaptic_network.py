"""
测试神经突触网络模块。
"""

import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock
from src.core.synaptic_network import SynapticNetwork, SignalFilter
from src.signals.neural_signal import NeuralSignal, SignalType, SignalPriority


class TestSynapticNetwork:
    """测试神经突触网络类"""

    @pytest.fixture
    def network(self):
        """创建神经突触网络测试实例"""
        return SynapticNetwork()

    @pytest.fixture
    def test_signal(self):
        """创建测试信号"""
        return NeuralSignal(
            source="test_source",
            type=SignalType.SENSORY,
            content={"message": "测试消息"},
            priority=SignalPriority.NORMAL,
        )

    @pytest.mark.asyncio
    async def test_network_start_stop(self, network):
        """测试网络启动和停止功能"""
        # 测试启动
        await network.start()
        assert network._is_active is True
        assert network._processing_task is not None

        # 测试停止
        await network.stop()
        assert network._is_active is False
        assert network._processing_task is None or network._processing_task.done()

    @pytest.mark.asyncio
    async def test_register_unregister_receptor(self, network):
        """测试注册和注销接收器"""
        # 创建测试回调和过滤器
        callback = MagicMock()
        signal_filter = SignalFilter(signal_types=[SignalType.SENSORY])

        # 注册接收器
        receptor_id = network.register_receptor(callback, signal_filter)
        assert len(network._receptors[SignalType.SENSORY]) == 1
        assert network._receptors[SignalType.SENSORY][0]["id"] == receptor_id

        # 注销接收器
        result = network.unregister_receptor(receptor_id)
        assert result is True
        assert len(network._receptors[SignalType.SENSORY]) == 0

    @pytest.mark.asyncio
    async def test_register_async_receptor(self, network):
        """测试注册异步接收器"""
        async_callback = AsyncMock()
        signal_filter = SignalFilter(signal_types=[SignalType.SENSORY])

        # 注册异步接收器
        receptor_id = network.register_receptor(async_callback, signal_filter, is_async=True)
        assert len(network._async_receptors[SignalType.SENSORY]) == 1
        assert network._async_receptors[SignalType.SENSORY][0]["id"] == receptor_id

    @pytest.mark.asyncio
    async def test_signal_transmission(self, network, test_signal):
        """测试信号传输"""
        # 启动网络
        await network.start()

        # 创建同步和异步回调
        sync_callback = MagicMock()
        async_callback = AsyncMock()

        # 注册接收器
        network.register_receptor(sync_callback, SignalFilter(signal_types=[SignalType.SENSORY]))
        network.register_receptor(async_callback, SignalFilter(signal_types=[SignalType.SENSORY]), is_async=True)

        # 传输信号
        await network.transmit(test_signal)

        # 等待信号处理完成
        await asyncio.sleep(0.1)

        # 验证接收器被调用
        sync_callback.assert_called_once_with(test_signal)
        async_callback.assert_called_once_with(test_signal)

        # 停止网络
        await network.stop()

    @pytest.mark.asyncio
    async def test_global_receptors(self, network, test_signal):
        """测试全局接收器功能"""
        # 启动网络
        await network.start()

        # 创建全局回调
        global_callback = MagicMock()
        global_async_callback = AsyncMock()

        # 注册全局接收器
        network.register_receptor(global_callback)  # 无过滤器表示接收所有信号
        network.register_receptor(global_async_callback, is_async=True)  # 异步全局接收器

        # 传输不同类型的信号
        await network.transmit(test_signal)  # SENSORY类型

        # 等待信号处理完成
        await asyncio.sleep(0.1)

        # 验证全局接收器都接收到信号
        global_callback.assert_called_once_with(test_signal)
        global_async_callback.assert_called_once_with(test_signal)

        # 停止网络
        await network.stop()

    @pytest.mark.asyncio
    async def test_signal_filtering(self, network):
        """测试信号过滤功能"""
        # 启动网络
        await network.start()

        # 创建不同类型的信号
        sensory_signal = NeuralSignal(
            source="test_source",
            type=SignalType.SENSORY,
            content={"message": "感知信号"},
            priority=SignalPriority.NORMAL,
        )

        motor_signal = NeuralSignal(
            source="test_source", type=SignalType.MOTOR, content={"message": "运动信号"}, priority=SignalPriority.NORMAL
        )

        # 创建针对特定类型的回调
        sensory_callback = MagicMock()
        motor_callback = MagicMock()

        # 注册特定类型的接收器
        network.register_receptor(sensory_callback, SignalFilter(signal_types=[SignalType.SENSORY]))

        network.register_receptor(motor_callback, SignalFilter(signal_types=[SignalType.MOTOR]))

        # 传输两种不同类型的信号
        await network.transmit(sensory_signal)
        await network.transmit(motor_signal)

        # 等待信号处理完成
        await asyncio.sleep(0.1)

        # 验证回调只接收到匹配类型的信号
        sensory_callback.assert_called_once_with(sensory_signal)
        motor_callback.assert_called_once_with(motor_signal)

        # 停止网络
        await network.stop()

    @pytest.mark.asyncio
    async def test_network_stats(self, network, test_signal):
        """测试网络统计功能"""
        # 启动网络
        await network.start()

        # 传输几个信号
        for _ in range(5):
            await network.transmit(test_signal)

        # 等待信号处理完成
        await asyncio.sleep(0.1)

        # 获取并验证统计信息
        stats = network.get_stats()
        assert stats["signals_processed"] == 5
        assert stats["signals_by_type"][test_signal.signal_type.name] == 5
        assert stats["signals_by_priority"][test_signal.priority.name] == 5
        assert stats["average_process_time"] > 0

        # 停止网络
        await network.stop()
