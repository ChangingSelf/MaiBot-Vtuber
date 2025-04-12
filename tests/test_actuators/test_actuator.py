"""
测试运动神经元基类模块。
"""

import pytest
import asyncio
from unittest.mock import MagicMock
from src.actuators.base_actuator import Actuator
from src.signals.neural_signal import NeuralSignal, SignalType


class TestActuatorImpl(Actuator):
    """用于测试的运动神经元实现类"""

    async def _initialize(self, config):
        self.test_config = config
        self.initialized = True

    async def _process_action_queue(self):
        """处理动作队列"""
        self.processing_active = True
        try:
            while self.is_active:
                action = await self.action_queue.get()
                try:
                    await self._execute_action(action)
                except Exception:
                    self.stats["errors"] += 1
                finally:
                    self.action_queue.task_done()
        except asyncio.CancelledError:
            pass
        finally:
            self.processing_active = False

    async def _execute_action(self, action):
        """执行具体动作"""
        self.stats["actions_performed"] += 1
        self.stats["last_action_time"] = asyncio.get_event_loop().time()
        self.last_executed_action = action

        # 这里在实际实现中会包含特定的执行逻辑
        # 对于测试，我们只记录被执行的动作

    async def _handle_signal(self, signal):
        """处理接收到的神经信号"""
        self.stats["signals_processed"] += 1
        action = {"type": signal.signal_type.name, "content": signal.content}
        self.stats["pending_actions"] += 1
        await self.action_queue.put(action)


class TestActuator:
    """测试运动神经元基类"""

    @pytest.fixture
    def mock_synaptic_network(self):
        """创建模拟的神经突触网络"""
        network = MagicMock()
        network.register_receptor = MagicMock(return_value="test-receptor-id")
        network.unregister_receptor = MagicMock(return_value=True)
        return network

    @pytest.fixture
    def test_actuator(self, mock_synaptic_network):
        """创建测试运动神经元实例"""
        return TestActuatorImpl(mock_synaptic_network, "TestActuator")

    @pytest.fixture
    def test_config(self):
        """创建测试配置"""
        return {"actuator_type": "test", "output_mode": "sync"}

    @pytest.fixture
    def test_signal(self):
        """创建测试信号"""
        return NeuralSignal(
            source="test_source",
            type=SignalType.MOTOR,
            content={"action": "test_action", "parameters": {"param1": "value1"}},
        )

    @pytest.mark.asyncio
    async def test_actuator_initialization(self, test_actuator, test_config):
        """测试运动神经元初始化"""
        await test_actuator.initialize(test_config)
        assert test_actuator.initialized is True
        assert test_actuator.test_config == test_config
        assert test_actuator.name == "TestActuator"
        assert test_actuator.is_active is False
        assert "actions_performed" in test_actuator.stats
        assert "last_action_time" in test_actuator.stats
        assert "pending_actions" in test_actuator.stats

    @pytest.mark.asyncio
    async def test_actuator_activation(self, test_actuator, test_config):
        """测试运动神经元激活"""
        # 初始化神经元
        await test_actuator.initialize(test_config)

        # 激活神经元
        await test_actuator.activate()

        # 检查状态
        assert test_actuator.is_active is True
        assert test_actuator.action_task is not None

        # 检查接收器注册
        test_actuator.synaptic_network.register_receptor.assert_called_once()

    @pytest.mark.asyncio
    async def test_actuator_deactivation(self, test_actuator, test_config):
        """测试运动神经元停用"""
        # 初始化并激活神经元
        await test_actuator.initialize(test_config)
        await test_actuator.activate()

        # 保存任务引用用于检查
        action_task = test_actuator.action_task

        # 停用神经元
        await test_actuator.deactivate()

        # 检查状态
        assert test_actuator.is_active is False
        assert test_actuator.action_task is None
        assert action_task.cancelled() or action_task.done()

        # 检查接收器取消注册
        test_actuator.synaptic_network.unregister_receptor.assert_called_once_with("test-receptor-id")

    @pytest.mark.asyncio
    async def test_signal_handling(self, test_actuator, test_config, test_signal):
        """测试信号处理"""
        # 初始化神经元
        await test_actuator.initialize(test_config)

        # 调用信号处理方法
        await test_actuator._handle_signal(test_signal)

        # 检查统计信息更新
        assert test_actuator.stats["signals_processed"] == 1
        assert test_actuator.stats["pending_actions"] == 1

        # 检查动作是否添加到队列
        assert test_actuator.action_queue.qsize() == 1

    @pytest.mark.asyncio
    async def test_action_execution(self, test_actuator, test_config):
        """测试动作执行"""
        # 初始化神经元
        await test_actuator.initialize(test_config)

        # 创建测试动作
        test_action = {"type": "MOTOR", "content": {"action": "test_action"}}

        # 直接调用执行方法
        await test_actuator._execute_action(test_action)

        # 检查结果
        assert test_actuator.last_executed_action == test_action
        assert test_actuator.stats["actions_performed"] == 1
        assert test_actuator.stats["last_action_time"] is not None

    @pytest.mark.asyncio
    async def test_action_queue_processing(self, test_actuator, test_config):
        """测试动作队列处理"""
        # 初始化并激活运动神经元
        await test_actuator.initialize(test_config)
        await test_actuator.activate()

        # 向队列添加动作
        test_action = {"type": "MOTOR", "content": {"action": "test_action"}}
        await test_actuator.action_queue.put(test_action)

        # 等待处理完成
        await asyncio.sleep(0.1)

        # 检查结果
        assert test_actuator.last_executed_action == test_action
        assert test_actuator.stats["actions_performed"] == 1

        # 停用神经元
        await test_actuator.deactivate()
