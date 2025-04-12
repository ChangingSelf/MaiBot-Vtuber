"""
测试中央皮层系统模块。
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from src.core.central_cortex import CortexBase, SensoryCortex, MotorCortex, CentralCortex
from src.core.synaptic_network import SynapticNetwork
from src.neurons.neuron import Neuron
from src.sensors.base_sensor import Sensor
from src.actuators.base_actuator import Actuator


class TestNeuron(Neuron):
    """用于测试的神经元实现"""

    def __init__(self, synaptic_network, name, dependencies=None):
        super().__init__(synaptic_network, name)
        self.dependencies = dependencies or []
        self.initialize_called = False
        self.activate_called = False
        self.deactivate_called = False

    async def _initialize(self, config):
        self.initialize_called = True
        self.config = config

    async def _activate(self):
        self.activate_called = True

    async def _deactivate(self):
        self.deactivate_called = True

    async def _register_receptors(self):
        pass

    def get_dependencies(self):
        return self.dependencies


class TestSensor(Sensor):
    """用于测试的感觉神经元实现"""

    def __init__(self, synaptic_network, name, dependencies=None):
        super().__init__(synaptic_network, name)
        self.dependencies = dependencies or []
        self.initialize_called = False
        self.activate_called = False
        self.deactivate_called = False

    async def _initialize(self, config):
        self.initialize_called = True
        self.config = config

    async def _activate(self):
        self.activate_called = True
        await super()._activate()

    async def _deactivate(self):
        self.deactivate_called = True
        await super()._deactivate()

    def get_dependencies(self):
        return self.dependencies


class TestActuator(Actuator):
    """用于测试的运动神经元实现"""

    def __init__(self, synaptic_network, name, dependencies=None):
        super().__init__(synaptic_network, name)
        self.dependencies = dependencies or []
        self.initialize_called = False
        self.activate_called = False
        self.deactivate_called = False

    async def _initialize(self, config):
        self.initialize_called = True
        self.config = config

    async def _activate(self):
        self.activate_called = True
        await super()._activate()

    async def _deactivate(self):
        self.deactivate_called = True
        await super()._deactivate()

    def get_dependencies(self):
        return self.dependencies


class TestCortexBase:
    """测试皮层基类"""

    @pytest.fixture
    def synaptic_network(self):
        return MagicMock(spec=SynapticNetwork)

    @pytest.fixture
    def cortex_base(self, synaptic_network):
        return CortexBase(synaptic_network)

    @pytest.fixture
    def test_neuron(self, synaptic_network):
        return TestNeuron(synaptic_network, "TestNeuron")

    @pytest.mark.asyncio
    async def test_register_neuron(self, cortex_base, test_neuron):
        """测试注册神经元"""
        await cortex_base.register_neuron(test_neuron)

        # 检查神经元是否被添加到列表
        assert test_neuron in cortex_base.neurons
        assert test_neuron in cortex_base.activation_order
        assert test_neuron in cortex_base.deactivation_order
        # 停用顺序应该是激活顺序的反向
        assert cortex_base.deactivation_order[0] == test_neuron

    @pytest.mark.asyncio
    async def test_unregister_neuron(self, cortex_base, test_neuron):
        """测试注销神经元"""
        # 先注册神经元
        await cortex_base.register_neuron(test_neuron)

        # 注销神经元
        result = await cortex_base.unregister_neuron(test_neuron)

        # 检查结果
        assert result is True
        assert test_neuron not in cortex_base.neurons
        assert test_neuron not in cortex_base.activation_order
        assert test_neuron not in cortex_base.deactivation_order

    @pytest.mark.asyncio
    async def test_activate_neuron(self, cortex_base, test_neuron):
        """测试激活神经元"""
        # 注册神经元
        await cortex_base.register_neuron(test_neuron)

        # 初始化神经元（通常在实际应用中会由CentralCortex完成）
        config = {"param": "value"}
        await test_neuron.initialize(config)

        # 激活神经元
        await cortex_base.activate_neuron(test_neuron)

        # 检查神经元状态
        assert test_neuron.activate_called is True
        assert test_neuron.is_active is True
        assert test_neuron in cortex_base.active_neurons

    @pytest.mark.asyncio
    async def test_deactivate_neuron(self, cortex_base, test_neuron):
        """测试停用神经元"""
        # 注册并激活神经元
        await cortex_base.register_neuron(test_neuron)
        config = {"param": "value"}
        await test_neuron.initialize(config)
        await cortex_base.activate_neuron(test_neuron)

        # 停用神经元
        await cortex_base.deactivate_neuron(test_neuron)

        # 检查神经元状态
        assert test_neuron.deactivate_called is True
        assert test_neuron.is_active is False
        assert test_neuron not in cortex_base.active_neurons


class TestSensoryCortex:
    """测试感觉中枢"""

    @pytest.fixture
    def synaptic_network(self):
        return MagicMock(spec=SynapticNetwork)

    @pytest.fixture
    def sensory_cortex(self, synaptic_network):
        return SensoryCortex(synaptic_network)

    @pytest.fixture
    def test_sensor(self, synaptic_network):
        return TestSensor(synaptic_network, "TestSensor")

    @pytest.mark.asyncio
    async def test_register_sensor(self, sensory_cortex, test_sensor):
        """测试注册感觉神经元"""
        await sensory_cortex.register_sensor(test_sensor)

        # 检查是否正确注册
        assert test_sensor in sensory_cortex.neurons
        assert test_sensor in sensory_cortex.get_sensors()

    @pytest.mark.asyncio
    async def test_get_sensor_by_name(self, sensory_cortex, test_sensor):
        """测试通过名称获取感觉神经元"""
        # 注册感觉神经元
        await sensory_cortex.register_sensor(test_sensor)

        # 通过名称获取
        found_sensor = sensory_cortex.get_sensor_by_name("TestSensor")

        # 检查结果
        assert found_sensor is test_sensor


class TestMotorCortex:
    """测试运动中枢"""

    @pytest.fixture
    def synaptic_network(self):
        return MagicMock(spec=SynapticNetwork)

    @pytest.fixture
    def motor_cortex(self, synaptic_network):
        return MotorCortex(synaptic_network)

    @pytest.fixture
    def test_actuator(self, synaptic_network):
        return TestActuator(synaptic_network, "TestActuator")

    @pytest.mark.asyncio
    async def test_register_actuator(self, motor_cortex, test_actuator):
        """测试注册运动神经元"""
        await motor_cortex.register_actuator(test_actuator)

        # 检查是否正确注册
        assert test_actuator in motor_cortex.neurons
        assert test_actuator in motor_cortex.get_actuators()

    @pytest.mark.asyncio
    async def test_get_actuator_by_name(self, motor_cortex, test_actuator):
        """测试通过名称获取运动神经元"""
        # 注册运动神经元
        await motor_cortex.register_actuator(test_actuator)

        # 通过名称获取
        found_actuator = motor_cortex.get_actuator_by_name("TestActuator")

        # 检查结果
        assert found_actuator is test_actuator


class TestCentralCortex:
    """测试中央皮层"""

    @pytest.fixture
    def synaptic_network(self):
        return MagicMock(spec=SynapticNetwork)

    @pytest.fixture
    def central_cortex(self, synaptic_network):
        return CentralCortex(synaptic_network)

    @pytest.fixture
    def test_sensor(self, synaptic_network):
        return TestSensor(synaptic_network, "TestSensor")

    @pytest.fixture
    def test_actuator(self, synaptic_network):
        return TestActuator(synaptic_network, "TestActuator")

    @pytest.fixture
    def dependent_sensor(self, synaptic_network, test_actuator):
        """创建依赖于其他神经元的感觉神经元"""
        return TestSensor(synaptic_network, "DependentSensor", [test_actuator])

    @pytest.mark.asyncio
    async def test_register_neurons(self, central_cortex, test_sensor, test_actuator):
        """测试注册各类神经元"""
        # 注册感觉神经元和运动神经元
        await central_cortex.register_sensor(test_sensor)
        await central_cortex.register_actuator(test_actuator)

        # 检查是否正确注册到相应中枢
        assert test_sensor in central_cortex.sensory_cortex.get_sensors()
        assert test_actuator in central_cortex.motor_cortex.get_actuators()

    @pytest.mark.asyncio
    async def test_initialize_all(self, central_cortex, test_sensor, test_actuator):
        """测试初始化所有神经元"""
        # 注册神经元
        await central_cortex.register_sensor(test_sensor)
        await central_cortex.register_actuator(test_actuator)

        # 创建配置
        config = {
            "sensors": {"TestSensor": {"param": "sensor_value"}},
            "actuators": {"TestActuator": {"param": "actuator_value"}},
        }

        # 初始化所有神经元
        await central_cortex.initialize_all(config)

        # 检查是否所有神经元都被初始化
        assert test_sensor.initialize_called is True
        assert test_sensor.config["param"] == "sensor_value"
        assert test_actuator.initialize_called is True
        assert test_actuator.config["param"] == "actuator_value"

    @pytest.mark.asyncio
    async def test_activate_all(self, central_cortex, test_sensor, test_actuator):
        """测试激活所有神经元"""
        # 注册神经元
        await central_cortex.register_sensor(test_sensor)
        await central_cortex.register_actuator(test_actuator)

        # 初始化神经元
        config = {
            "sensors": {"TestSensor": {"param": "sensor_value"}},
            "actuators": {"TestActuator": {"param": "actuator_value"}},
        }
        await central_cortex.initialize_all(config)

        # 激活所有神经元
        await central_cortex.activate_all()

        # 检查是否所有神经元都被激活
        assert test_sensor.activate_called is True
        assert test_sensor.is_active is True
        assert test_actuator.activate_called is True
        assert test_actuator.is_active is True

    @pytest.mark.asyncio
    async def test_deactivate_all(self, central_cortex, test_sensor, test_actuator):
        """测试停用所有神经元"""
        # 注册并激活神经元
        await central_cortex.register_sensor(test_sensor)
        await central_cortex.register_actuator(test_actuator)
        config = {"sensors": {"TestSensor": {}}, "actuators": {"TestActuator": {}}}
        await central_cortex.initialize_all(config)
        await central_cortex.activate_all()

        # 停用所有神经元
        await central_cortex.deactivate_all()

        # 检查是否所有神经元都被停用
        assert test_sensor.deactivate_called is True
        assert test_sensor.is_active is False
        assert test_actuator.deactivate_called is True
        assert test_actuator.is_active is False

    @pytest.mark.asyncio
    async def test_dependency_order_activation(self, central_cortex, test_actuator, dependent_sensor):
        """测试依赖顺序激活"""
        # 注册有依赖关系的神经元
        await central_cortex.register_sensor(dependent_sensor)
        await central_cortex.register_actuator(test_actuator)

        # 初始化神经元
        config = {"sensors": {"DependentSensor": {}}, "actuators": {"TestActuator": {}}}
        await central_cortex.initialize_all(config)

        # 激活所有神经元
        await central_cortex.activate_all()

        # 因为dependent_sensor依赖test_actuator，所以test_actuator应该先被激活
        assert central_cortex.activation_order.index(test_actuator) < central_cortex.activation_order.index(
            dependent_sensor
        )
