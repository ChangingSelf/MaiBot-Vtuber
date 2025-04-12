from typing import Dict, List, Type, Set, Optional, TypeVar, Any
import logging
import asyncio
from collections import defaultdict

from src.neurons.neuron import Neuron
from src.sensors.base_sensor import Sensor
from src.actuators.base_actuator import Actuator
from src.connectors.base_connector import Connector
from src.core.synaptic_network import SynapticNetwork

T = TypeVar("T", bound=Neuron)
logger = logging.getLogger(__name__)


class CortexBase:
    """皮层基类 - 神经元管理的基础类"""

    def __init__(self, synaptic_network: SynapticNetwork):
        """初始化皮层基类

        Args:
            synaptic_network: 神经突触网络
        """
        self.synaptic_network = synaptic_network
        self.neurons: Set[Neuron] = set()
        self.active_neurons: Set[Neuron] = set()
        self.activation_order: List[Neuron] = []
        self.deactivation_order: List[Neuron] = []

    async def register_neuron(self, neuron: Neuron) -> None:
        """注册神经元

        Args:
            neuron: 要注册的神经元
        """
        if neuron in self.neurons:
            logger.warning(f"神经元 {neuron.name} 已经注册")
            return

        self.neurons.add(neuron)
        self.activation_order.append(neuron)
        self.deactivation_order.insert(0, neuron)  # 停用顺序与激活顺序相反

        logger.info(f"已注册神经元: {neuron.name}")

    async def unregister_neuron(self, neuron: Neuron) -> None:
        """取消注册神经元

        Args:
            neuron: 要取消注册的神经元
        """
        if neuron not in self.neurons:
            logger.warning(f"神经元 {neuron.name} 未注册")
            return

        # 如果处于激活状态，先停用
        if neuron.is_active:
            await self.deactivate_neuron(neuron)

        # 从集合中移除
        self.neurons.remove(neuron)
        self.active_neurons.discard(neuron)

        # 从激活和停用顺序中移除
        if neuron in self.activation_order:
            self.activation_order.remove(neuron)
        if neuron in self.deactivation_order:
            self.deactivation_order.remove(neuron)

        logger.info(f"已取消注册神经元: {neuron.name}")

    async def activate_neuron(self, neuron: Neuron) -> None:
        """激活神经元

        Args:
            neuron: 要激活的神经元
        """
        if neuron not in self.neurons:
            logger.error(f"无法激活未注册的神经元: {neuron.name}")
            return

        if neuron in self.active_neurons:
            logger.warning(f"神经元 {neuron.name} 已经处于激活状态")
            return

        try:
            await neuron.activate()
            self.active_neurons.add(neuron)
            logger.info(f"已激活神经元: {neuron.name}")
        except Exception as e:
            logger.error(f"激活神经元 {neuron.name} 时出错: {e}")
            raise

    async def deactivate_neuron(self, neuron: Neuron) -> None:
        """停用神经元

        Args:
            neuron: 要停用的神经元
        """
        if neuron not in self.neurons:
            logger.error(f"无法停用未注册的神经元: {neuron.name}")
            return

        if neuron not in self.active_neurons:
            logger.warning(f"神经元 {neuron.name} 未处于激活状态")
            return

        try:
            await neuron.deactivate()
            self.active_neurons.discard(neuron)
            logger.info(f"已停用神经元: {neuron.name}")
        except Exception as e:
            logger.error(f"停用神经元 {neuron.name} 时出错: {e}")
            raise

    async def activate_all(self) -> None:
        """激活所有注册的神经元"""
        logger.info(f"正在激活 {len(self.neurons)} 个神经元...")

        # 按照激活顺序依次激活
        for neuron in self.activation_order:
            try:
                await self.activate_neuron(neuron)
            except Exception as e:
                logger.error(f"激活神经元 {neuron.name} 时出错: {e}")

        logger.info(f"已激活 {len(self.active_neurons)}/{len(self.neurons)} 个神经元")

    async def deactivate_all(self) -> None:
        """停用所有激活的神经元"""
        logger.info(f"正在停用 {len(self.active_neurons)} 个神经元...")

        # 按照停用顺序依次停用
        for neuron in self.deactivation_order:
            if neuron in self.active_neurons:
                try:
                    await self.deactivate_neuron(neuron)
                except Exception as e:
                    logger.error(f"停用神经元 {neuron.name} 时出错: {e}")

        logger.info(f"已停用所有神经元，还有 {len(self.active_neurons)} 个未能正常停用")

    def get_neuron_by_name(self, name: str) -> Optional[Neuron]:
        """通过名称获取神经元

        Args:
            name: 神经元名称

        Returns:
            对应的神经元，如果不存在则返回None
        """
        for neuron in self.neurons:
            if neuron.name == name:
                return neuron
        return None

    def get_neurons_by_type(self, neuron_type: Type[T]) -> List[T]:
        """通过类型获取神经元列表

        Args:
            neuron_type: 神经元类型

        Returns:
            对应类型的神经元列表
        """
        return [neuron for neuron in self.neurons if isinstance(neuron, neuron_type)]

    def is_active(self, neuron: Neuron) -> bool:
        """检查神经元是否处于激活状态

        Args:
            neuron: 要检查的神经元

        Returns:
            是否处于激活状态
        """
        return neuron in self.active_neurons

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息

        Returns:
            统计信息
        """
        stats = {"total_neurons": len(self.neurons), "active_neurons": len(self.active_neurons), "neurons": {}}

        for neuron in self.neurons:
            stats["neurons"][neuron.name] = {"active": neuron in self.active_neurons, "type": neuron.__class__.__name__}

        return stats


class SensoryCortex(CortexBase):
    """感觉中枢 - 管理所有感觉神经元"""

    def __init__(self, synaptic_network: SynapticNetwork):
        """初始化感觉中枢

        Args:
            synaptic_network: 神经突触网络
        """
        super().__init__(synaptic_network)
        self.sensor_types: Dict[str, Set[Sensor]] = defaultdict(set)

    async def register_neuron(self, neuron: Neuron) -> None:
        """注册感觉神经元

        Args:
            neuron: 要注册的感觉神经元
        """
        if not isinstance(neuron, Sensor):
            logger.error(f"只能在感觉中枢注册Sensor类型的神经元，收到: {neuron.__class__.__name__}")
            return

        await super().register_neuron(neuron)

        # 将传感器按类型分类
        sensor_type = neuron.__class__.__name__
        self.sensor_types[sensor_type].add(neuron)

    async def unregister_neuron(self, neuron: Neuron) -> None:
        """取消注册感觉神经元

        Args:
            neuron: 要取消注册的感觉神经元
        """
        if not isinstance(neuron, Sensor):
            logger.error(f"只能在感觉中枢取消注册Sensor类型的神经元，收到: {neuron.__class__.__name__}")
            return

        await super().unregister_neuron(neuron)

        # 从类型分类中移除
        sensor_type = neuron.__class__.__name__
        if neuron in self.sensor_types[sensor_type]:
            self.sensor_types[sensor_type].remove(neuron)

        # 如果类型为空，移除键
        if not self.sensor_types[sensor_type]:
            del self.sensor_types[sensor_type]

    def get_sensors_by_type(self, sensor_type: str) -> List[Sensor]:
        """获取特定类型的传感器列表

        Args:
            sensor_type: 传感器类型名称

        Returns:
            该类型的传感器列表
        """
        return list(self.sensor_types.get(sensor_type, set()))

    def get_stats(self) -> Dict[str, Any]:
        """获取感觉中枢统计信息

        Returns:
            统计信息
        """
        stats = super().get_stats()
        stats["sensor_types"] = {sensor_type: len(sensors) for sensor_type, sensors in self.sensor_types.items()}
        return stats


class MotorCortex(CortexBase):
    """运动中枢 - 管理所有运动神经元"""

    def __init__(self, synaptic_network: SynapticNetwork):
        """初始化运动中枢

        Args:
            synaptic_network: 神经突触网络
        """
        super().__init__(synaptic_network)
        self.actuator_types: Dict[str, Set[Actuator]] = defaultdict(set)

    async def register_neuron(self, neuron: Neuron) -> None:
        """注册运动神经元

        Args:
            neuron: 要注册的运动神经元
        """
        if not isinstance(neuron, Actuator):
            logger.error(f"只能在运动中枢注册Actuator类型的神经元，收到: {neuron.__class__.__name__}")
            return

        await super().register_neuron(neuron)

        # 将执行器按类型分类
        actuator_type = neuron.__class__.__name__
        self.actuator_types[actuator_type].add(neuron)

    async def unregister_neuron(self, neuron: Neuron) -> None:
        """取消注册运动神经元

        Args:
            neuron: 要取消注册的运动神经元
        """
        if not isinstance(neuron, Actuator):
            logger.error(f"只能在运动中枢取消注册Actuator类型的神经元，收到: {neuron.__class__.__name__}")
            return

        await super().unregister_neuron(neuron)

        # 从类型分类中移除
        actuator_type = neuron.__class__.__name__
        if neuron in self.actuator_types[actuator_type]:
            self.actuator_types[actuator_type].remove(neuron)

        # 如果类型为空，移除键
        if not self.actuator_types[actuator_type]:
            del self.actuator_types[actuator_type]

    def get_actuators_by_type(self, actuator_type: str) -> List[Actuator]:
        """获取特定类型的执行器列表

        Args:
            actuator_type: 执行器类型名称

        Returns:
            该类型的执行器列表
        """
        return list(self.actuator_types.get(actuator_type, set()))

    def get_stats(self) -> Dict[str, Any]:
        """获取运动中枢统计信息

        Returns:
            统计信息
        """
        stats = super().get_stats()
        stats["actuator_types"] = {
            actuator_type: len(actuators) for actuator_type, actuators in self.actuator_types.items()
        }
        return stats


class CentralCortex:
    """中央皮层 - 管理感觉中枢、运动中枢和联结神经元"""

    def __init__(self, synaptic_network: SynapticNetwork):
        """初始化中央皮层

        Args:
            synaptic_network: 神经突触网络
        """
        self.sensory_cortex = SensoryCortex(synaptic_network)
        self.motor_cortex = MotorCortex(synaptic_network)
        self.connectors = set()  # 存储连接器神经元
        self.active_connectors = set()  # 存储激活的连接器

    async def register_neuron(self, neuron: Neuron) -> None:
        """注册神经元

        Args:
            neuron: 要注册的神经元
        """
        if isinstance(neuron, Sensor):
            await self.sensory_cortex.register_neuron(neuron)
        elif isinstance(neuron, Actuator):
            await self.motor_cortex.register_neuron(neuron)
        elif isinstance(neuron, Connector):
            if neuron in self.connectors:
                logger.warning(f"连接器 {neuron.name} 已经注册")
                return
            self.connectors.add(neuron)
            logger.info(f"已注册连接器: {neuron.name}")
        else:
            logger.error(f"无法注册未知类型的神经元: {neuron.__class__.__name__}")

    async def unregister_neuron(self, neuron: Neuron) -> None:
        """取消注册神经元

        Args:
            neuron: 要取消注册的神经元
        """
        if isinstance(neuron, Sensor):
            await self.sensory_cortex.unregister_neuron(neuron)
        elif isinstance(neuron, Actuator):
            await self.motor_cortex.unregister_neuron(neuron)
        elif isinstance(neuron, Connector):
            if neuron not in self.connectors:
                logger.warning(f"连接器 {neuron.name} 未注册")
                return

            # 如果处于激活状态，先停用
            if neuron.is_active:
                await self.deactivate_connector(neuron)

            self.connectors.remove(neuron)
            self.active_connectors.discard(neuron)
            logger.info(f"已取消注册连接器: {neuron.name}")
        else:
            logger.warning(f"无法取消注册未知类型的神经元: {neuron.__class__.__name__}")

    async def activate_connector(self, connector: Connector) -> None:
        """激活连接器

        Args:
            connector: 要激活的连接器
        """
        if connector not in self.connectors:
            logger.error(f"无法激活未注册的连接器: {connector.name}")
            return

        if connector in self.active_connectors:
            logger.warning(f"连接器 {connector.name} 已经处于激活状态")
            return

        try:
            await connector.activate()
            self.active_connectors.add(connector)
            logger.info(f"已激活连接器: {connector.name}")
        except Exception as e:
            logger.error(f"激活连接器 {connector.name} 时出错: {e}")
            raise

    async def deactivate_connector(self, connector: Connector) -> None:
        """停用连接器

        Args:
            connector: 要停用的连接器
        """
        if connector not in self.connectors:
            logger.error(f"无法停用未注册的连接器: {connector.name}")
            return

        if connector not in self.active_connectors:
            logger.warning(f"连接器 {connector.name} 未处于激活状态")
            return

        try:
            await connector.deactivate()
            self.active_connectors.discard(connector)
            logger.info(f"已停用连接器: {connector.name}")
        except Exception as e:
            logger.error(f"停用连接器 {connector.name} 时出错: {e}")
            raise

    async def activate_all(self) -> None:
        """激活所有注册的神经元"""
        logger.info("正在激活所有神经元...")

        # 先激活感知神经元
        await self.sensory_cortex.activate_all()

        # 然后激活运动神经元
        await self.motor_cortex.activate_all()

        # 最后激活连接器
        logger.info(f"正在激活 {len(self.connectors)} 个连接器...")
        for connector in self.connectors:
            try:
                await self.activate_connector(connector)
            except Exception as e:
                logger.error(f"激活连接器 {connector.name} 时出错: {e}")

        logger.info(f"已激活 {len(self.active_connectors)}/{len(self.connectors)} 个连接器")

        logger.info("已激活所有神经元")

    async def deactivate_all(self) -> None:
        """停用所有激活的神经元"""
        logger.info("正在停用所有神经元...")

        # 先停用连接器
        logger.info(f"正在停用 {len(self.active_connectors)} 个连接器...")
        for connector in list(self.active_connectors):
            try:
                await self.deactivate_connector(connector)
            except Exception as e:
                logger.error(f"停用连接器 {connector.name} 时出错: {e}")

        logger.info(f"已停用所有连接器，还有 {len(self.active_connectors)} 个未能正常停用")

        # 然后停用运动神经元
        await self.motor_cortex.deactivate_all()

        # 最后停用感知神经元
        await self.sensory_cortex.deactivate_all()

        logger.info("已停用所有神经元")

    def get_neuron_by_name(self, name: str) -> Optional[Neuron]:
        """通过名称获取神经元

        Args:
            name: 神经元名称

        Returns:
            对应的神经元，如果不存在则返回None
        """
        # 优先从感觉中枢查找
        neuron = self.sensory_cortex.get_neuron_by_name(name)
        if neuron:
            return neuron

        # 其次从运动中枢查找
        neuron = self.motor_cortex.get_neuron_by_name(name)
        if neuron:
            return neuron

        # 最后从连接器查找
        for connector in self.connectors:
            if connector.name == name:
                return connector

        return None

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息

        Returns:
            统计信息
        """
        # 获取感觉中枢和运动中枢的统计信息
        sensory_stats = self.sensory_cortex.get_stats()
        motor_stats = self.motor_cortex.get_stats()

        # 构建连接器的统计信息
        connector_stats = {
            "total_connectors": len(self.connectors),
            "active_connectors": len(self.active_connectors),
            "connectors": {},
        }

        for connector in self.connectors:
            connector_stats["connectors"][connector.name] = {
                "active": connector in self.active_connectors,
                "type": connector.__class__.__name__,
            }

        # 合并统计信息
        return {
            "sensory_cortex": sensory_stats,
            "motor_cortex": motor_stats,
            "connectors": connector_stats,
            "total_neurons": sensory_stats["total_neurons"] + motor_stats["total_neurons"] + len(self.connectors),
            "active_neurons": sensory_stats["active_neurons"]
            + motor_stats["active_neurons"]
            + len(self.active_connectors),
        }
