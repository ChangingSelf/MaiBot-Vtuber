"""
测试感觉神经元基类模块。
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from src.sensors.base_sensor import Sensor
from src.signals.neural_signal import NeuralSignal, SignalType


class TestSensorImpl(Sensor):
    """用于测试的感觉神经元实现类"""

    async def _initialize(self, config):
        self.test_config = config
        self.initialized = True

    async def sense(self, input_data):
        """处理外部输入并转换为神经信号"""
        self.stats["inputs_processed"] += 1
        self.stats["last_input_time"] = asyncio.get_event_loop().time()

        # 创建神经信号
        signal = NeuralSignal(source=self.name, type=SignalType.SENSORY, content=input_data)

        # 传输到神经网络
        await self.synaptic_network.transmit(signal)
        self.stats["signals_transmitted"] += 1
        return signal


class TestSensor:
    """测试感觉神经元基类"""

    @pytest.fixture
    def mock_synaptic_network(self):
        """创建模拟的神经突触网络"""
        network = MagicMock()
        network.transmit = AsyncMock()
        return network

    @pytest.fixture
    def test_sensor(self, mock_synaptic_network):
        """创建测试感觉神经元实例"""
        return TestSensorImpl(mock_synaptic_network, "TestSensor")

    @pytest.fixture
    def test_config(self):
        """创建测试配置"""
        return {"sensor_type": "test", "poll_interval": 1.0}

    @pytest.mark.asyncio
    async def test_sensor_initialization(self, test_sensor, test_config):
        """测试感觉神经元初始化"""
        await test_sensor.initialize(test_config)
        assert test_sensor.initialized is True
        assert test_sensor.test_config == test_config
        assert test_sensor.name == "TestSensor"
        assert test_sensor.is_active is False
        assert "inputs_processed" in test_sensor.stats
        assert "last_input_time" in test_sensor.stats

    @pytest.mark.asyncio
    async def test_sensor_activation(self, test_sensor, test_config):
        """测试感觉神经元激活"""
        # 初始化神经元
        await test_sensor.initialize(test_config)

        # 激活神经元
        await test_sensor.activate()

        # 检查状态
        assert test_sensor.is_active is True
        assert test_sensor.input_task is not None

    @pytest.mark.asyncio
    async def test_sensor_deactivation(self, test_sensor, test_config):
        """测试感觉神经元停用"""
        # 初始化并激活神经元
        await test_sensor.initialize(test_config)
        await test_sensor.activate()

        # 保存任务引用用于检查
        input_task = test_sensor.input_task

        # 停用神经元
        await test_sensor.deactivate()

        # 检查状态
        assert test_sensor.is_active is False
        assert test_sensor.input_task is None
        assert input_task.cancelled() or input_task.done()

    @pytest.mark.asyncio
    async def test_sensor_sensing(self, test_sensor, test_config):
        """测试感知功能"""
        # 初始化神经元
        await test_sensor.initialize(test_config)

        # 测试感知输入
        test_input = {"source": "test", "content": "测试内容"}
        signal = await test_sensor.sense(test_input)

        # 检查信号是否正确创建和传输
        assert signal.source == "TestSensor"
        assert signal.signal_type == SignalType.SENSORY
        assert signal.content == test_input

        # 检查是否调用了传输方法
        test_sensor.synaptic_network.transmit.assert_called_once_with(signal)

        # 检查统计信息更新
        assert test_sensor.stats["inputs_processed"] == 1
        assert test_sensor.stats["signals_transmitted"] == 1
        assert test_sensor.stats["last_input_time"] is not None

    @pytest.mark.asyncio
    async def test_input_queue_processing(self, test_sensor, test_config):
        """测试输入队列处理"""

        # 模拟输入队列处理的方法
        async def process_mock(input_data):
            # 记录处理过的数据
            if not hasattr(test_sensor, "processed_inputs"):
                test_sensor.processed_inputs = []
            test_sensor.processed_inputs.append(input_data)

        # 替换内部处理方法
        with patch.object(TestSensorImpl, "_process_input_queue", new_callable=AsyncMock) as mock_process:
            # 初始化并激活感觉神经元
            await test_sensor.initialize(test_config)
            await test_sensor.activate()

            # 等待一小段时间确保任务启动
            await asyncio.sleep(0.1)

            # 检查任务是否启动
            mock_process.assert_called_once()

            # 停用神经元
            await test_sensor.deactivate()
