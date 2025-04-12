"""
神经元配置管理 - 负责管理所有感觉和运动神经元的配置
支持神经元的动态启用/禁用和运行时配置更新
"""

import logging
from typing import Dict, List, Any, Set, Optional, Callable
from pathlib import Path
import json


class NeuronConfig:
    """
    神经元配置管理器

    管理所有感觉神经元和运动神经元的配置，支持：
    - 动态启用/禁用神经元
    - 运行时热加载配置
    - 神经元配置验证
    - 订阅配置变更通知
    """

    def __init__(self, parent_config=None):
        """
        初始化神经元配置管理器

        Args:
            parent_config: 父配置对象，通常是GeneticExpression实例
        """
        self.logger = logging.getLogger("NeuronConfig")
        self.parent_config = parent_config

        # 神经元配置
        self.sensory_neurons: Dict[str, Dict[str, Any]] = {}
        self.motor_neurons: Dict[str, Dict[str, Any]] = {}

        # 已启用的神经元
        self.enabled_sensory: Set[str] = set()
        self.enabled_motor: Set[str] = set()

        # 配置变更回调
        self._change_callbacks: Dict[str, List[Callable]] = {
            "sensory": [],
            "motor": [],
        }

    def load_config(self, config_data: Dict[str, Any]) -> None:
        """
        从配置数据加载神经元配置

        Args:
            config_data: 包含神经元配置的字典
        """
        # 加载感觉神经元配置
        if "sensory_neurons" in config_data:
            self.sensory_neurons = config_data["sensory_neurons"]
            self._update_enabled_neurons("sensory")

        # 加载运动神经元配置
        if "motor_neurons" in config_data:
            self.motor_neurons = config_data["motor_neurons"]
            self._update_enabled_neurons("motor")

    def _update_enabled_neurons(self, neuron_type: str) -> None:
        """
        更新启用的神经元列表

        Args:
            neuron_type: 神经元类型 ('sensory' 或 'motor')
        """
        if neuron_type == "sensory":
            self.enabled_sensory = {
                name for name, config in self.sensory_neurons.items() if config.get("enabled", True)
            }
        elif neuron_type == "motor":
            self.enabled_motor = {name for name, config in self.motor_neurons.items() if config.get("enabled", True)}

    def is_sensory_neuron_enabled(self, neuron_name: str) -> bool:
        """
        检查感觉神经元是否启用

        Args:
            neuron_name: 神经元名称

        Returns:
            是否启用
        """
        return neuron_name in self.enabled_sensory

    def is_motor_neuron_enabled(self, neuron_name: str) -> bool:
        """
        检查运动神经元是否启用

        Args:
            neuron_name: 神经元名称

        Returns:
            是否启用
        """
        return neuron_name in self.enabled_motor

    def enable_sensory_neuron(self, neuron_name: str) -> bool:
        """
        启用感觉神经元

        Args:
            neuron_name: 神经元名称

        Returns:
            是否成功启用
        """
        if neuron_name not in self.sensory_neurons:
            self.logger.warning(f"尝试启用不存在的感觉神经元: {neuron_name}")
            return False

        self.sensory_neurons[neuron_name]["enabled"] = True
        self.enabled_sensory.add(neuron_name)
        self._notify_change("sensory", neuron_name)
        return True

    def disable_sensory_neuron(self, neuron_name: str) -> bool:
        """
        禁用感觉神经元

        Args:
            neuron_name: 神经元名称

        Returns:
            是否成功禁用
        """
        if neuron_name not in self.sensory_neurons:
            self.logger.warning(f"尝试禁用不存在的感觉神经元: {neuron_name}")
            return False

        self.sensory_neurons[neuron_name]["enabled"] = False
        self.enabled_sensory.discard(neuron_name)
        self._notify_change("sensory", neuron_name)
        return True

    def enable_motor_neuron(self, neuron_name: str) -> bool:
        """
        启用运动神经元

        Args:
            neuron_name: 神经元名称

        Returns:
            是否成功启用
        """
        if neuron_name not in self.motor_neurons:
            self.logger.warning(f"尝试启用不存在的运动神经元: {neuron_name}")
            return False

        self.motor_neurons[neuron_name]["enabled"] = True
        self.enabled_motor.add(neuron_name)
        self._notify_change("motor", neuron_name)
        return True

    def disable_motor_neuron(self, neuron_name: str) -> bool:
        """
        禁用运动神经元

        Args:
            neuron_name: 神经元名称

        Returns:
            是否成功禁用
        """
        if neuron_name not in self.motor_neurons:
            self.logger.warning(f"尝试禁用不存在的运动神经元: {neuron_name}")
            return False

        self.motor_neurons[neuron_name]["enabled"] = False
        self.enabled_motor.discard(neuron_name)
        self._notify_change("motor", neuron_name)
        return True

    def get_sensory_neuron_config(self, neuron_name: str, default: Any = None) -> Dict[str, Any]:
        """
        获取感觉神经元配置

        Args:
            neuron_name: 神经元名称
            default: 默认值，如果神经元不存在则返回此值

        Returns:
            神经元配置或默认值
        """
        return self.sensory_neurons.get(neuron_name, default)

    def get_motor_neuron_config(self, neuron_name: str, default: Any = None) -> Dict[str, Any]:
        """
        获取运动神经元配置

        Args:
            neuron_name: 神经元名称
            default: 默认值，如果神经元不存在则返回此值

        Returns:
            神经元配置或默认值
        """
        return self.motor_neurons.get(neuron_name, default)

    def set_sensory_neuron_config(self, neuron_name: str, config: Dict[str, Any]) -> None:
        """
        设置感觉神经元配置

        Args:
            neuron_name: 神经元名称
            config: 神经元配置
        """
        self.sensory_neurons[neuron_name] = config
        if config.get("enabled", True):
            self.enabled_sensory.add(neuron_name)
        else:
            self.enabled_sensory.discard(neuron_name)
        self._notify_change("sensory", neuron_name)

    def set_motor_neuron_config(self, neuron_name: str, config: Dict[str, Any]) -> None:
        """
        设置运动神经元配置

        Args:
            neuron_name: 神经元名称
            config: 神经元配置
        """
        self.motor_neurons[neuron_name] = config
        if config.get("enabled", True):
            self.enabled_motor.add(neuron_name)
        else:
            self.enabled_motor.discard(neuron_name)
        self._notify_change("motor", neuron_name)

    def update_sensory_neuron_config(self, neuron_name: str, updates: Dict[str, Any]) -> bool:
        """
        更新感觉神经元配置

        Args:
            neuron_name: 神经元名称
            updates: 配置更新

        Returns:
            是否成功更新
        """
        if neuron_name not in self.sensory_neurons:
            self.logger.warning(f"尝试更新不存在的感觉神经元: {neuron_name}")
            return False

        current_config = self.sensory_neurons[neuron_name]
        current_config.update(updates)

        # 如果更新包含enabled字段，则更新启用状态
        if "enabled" in updates:
            if updates["enabled"]:
                self.enabled_sensory.add(neuron_name)
            else:
                self.enabled_sensory.discard(neuron_name)

        self._notify_change("sensory", neuron_name)
        return True

    def update_motor_neuron_config(self, neuron_name: str, updates: Dict[str, Any]) -> bool:
        """
        更新运动神经元配置

        Args:
            neuron_name: 神经元名称
            updates: 配置更新

        Returns:
            是否成功更新
        """
        if neuron_name not in self.motor_neurons:
            self.logger.warning(f"尝试更新不存在的运动神经元: {neuron_name}")
            return False

        current_config = self.motor_neurons[neuron_name]
        current_config.update(updates)

        # 如果更新包含enabled字段，则更新启用状态
        if "enabled" in updates:
            if updates["enabled"]:
                self.enabled_motor.add(neuron_name)
            else:
                self.enabled_motor.discard(neuron_name)

        self._notify_change("motor", neuron_name)
        return True

    def get_all_sensory_neurons(self) -> List[str]:
        """
        获取所有感觉神经元名称

        Returns:
            感觉神经元名称列表
        """
        return list(self.sensory_neurons.keys())

    def get_all_motor_neurons(self) -> List[str]:
        """
        获取所有运动神经元名称

        Returns:
            运动神经元名称列表
        """
        return list(self.motor_neurons.keys())

    def get_enabled_sensory_neurons(self) -> List[str]:
        """
        获取已启用的感觉神经元名称

        Returns:
            已启用的感觉神经元名称列表
        """
        return list(self.enabled_sensory)

    def get_enabled_motor_neurons(self) -> List[str]:
        """
        获取已启用的运动神经元名称

        Returns:
            已启用的运动神经元名称列表
        """
        return list(self.enabled_motor)

    def register_change_callback(self, neuron_type: str, callback: Callable) -> None:
        """
        注册配置变更回调

        Args:
            neuron_type: 神经元类型 ('sensory' 或 'motor')
            callback: 回调函数，接收神经元名称作为参数
        """
        if neuron_type in self._change_callbacks:
            self._change_callbacks[neuron_type].append(callback)

    def _notify_change(self, neuron_type: str, neuron_name: str) -> None:
        """
        通知配置变更

        Args:
            neuron_type: 神经元类型 ('sensory' 或 'motor')
            neuron_name: 神经元名称
        """
        if neuron_type in self._change_callbacks:
            for callback in self._change_callbacks[neuron_type]:
                try:
                    callback(neuron_name)
                except Exception as e:
                    self.logger.error(f"执行配置变更回调时出错: {e}")

    def to_dict(self) -> Dict[str, Any]:
        """
        将配置转换为字典

        Returns:
            配置字典
        """
        return {"sensory_neurons": self.sensory_neurons, "motor_neurons": self.motor_neurons}

    def validate_neuron_config(self, neuron_type: str, neuron_name: str, config: Dict[str, Any]) -> bool:
        """
        验证神经元配置

        Args:
            neuron_type: 神经元类型 ('sensory' 或 'motor')
            neuron_name: 神经元名称
            config: 神经元配置

        Returns:
            配置是否有效
        """
        # 基本验证
        if not isinstance(config, dict):
            self.logger.error(f"神经元配置必须是字典: {neuron_name}")
            return False

        # 检查必需字段
        required_fields = ["description"]
        for field in required_fields:
            if field not in config:
                self.logger.error(f"神经元配置缺少必需字段 '{field}': {neuron_name}")
                return False

        # TODO: 根据神经元类型进行更具体的验证

        return True
