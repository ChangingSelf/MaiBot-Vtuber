"""
基因表达系统 - 负责MaiBot的配置管理和环境变量处理
支持配置文件、环境变量、加密存储和热加载
"""

import os
import json
import time
import logging
from typing import Dict, Any, Optional, List, Callable, Union, Set
from pathlib import Path
import yaml

from src.genetics.dna_storage import DNAStorage
from src.genetics.neuron_config import NeuronConfig


class GeneticExpression:
    """
    基因表达配置管理系统

    负责管理MaiBot的所有配置，包括：
    - 全局配置管理（配置文件和环境变量）
    - 敏感信息的加密存储
    - 神经元配置（感觉神经元和运动神经元）
    - 配置的验证、热加载和变更通知
    """

    def __init__(
        self, config_path: Optional[str] = None, env_prefix: str = "MAIBOT_", dna_storage_path: Optional[str] = None
    ):
        """
        初始化配置管理系统

        Args:
            config_path: 配置文件路径，默认为'config/config.yaml'
            env_prefix: 环境变量前缀，默认为'MAIBOT_'
            dna_storage_path: 加密存储路径，默认为'data/dna_storage'
        """
        self.logger = logging.getLogger("GeneticExpression")

        # 基本配置
        self.config_path = config_path or os.environ.get(f"{env_prefix}CONFIG", "config/config.yaml")
        self.env_prefix = env_prefix
        self.config: Dict[str, Any] = {}
        self.config_timestamp = 0
        self.last_check_time = 0
        self.reload_interval = 30  # 热加载检查间隔（秒）
        self.change_callbacks: Dict[str, List[Callable]] = {}

        # 神经元配置
        self.neuron_config = NeuronConfig(parent_config=self)

        # 加密存储
        self.dna_storage = DNAStorage(
            storage_path=dna_storage_path or os.environ.get(f"{env_prefix}DNA_STORAGE", "data/dna_storage"),
            env_key_name=f"{env_prefix}DNA_KEY",
        )

        # 加载配置
        self.load_config()

    def load_config(self) -> None:
        """加载配置文件"""
        config_path = Path(self.config_path)

        if not config_path.exists():
            self.logger.warning(f"配置文件不存在: {config_path}，创建默认配置")
            self._create_default_config()
            return

        try:
            # 记录文件修改时间用于热加载检测
            self.config_timestamp = config_path.stat().st_mtime

            # 根据文件扩展名选择加载方式
            extension = config_path.suffix.lower()
            if extension == ".yaml" or extension == ".yml":
                with open(config_path, "r", encoding="utf-8") as f:
                    self.config = yaml.safe_load(f) or {}
            elif extension == ".json":
                with open(config_path, "r", encoding="utf-8") as f:
                    self.config = json.load(f)
            else:
                self.logger.error(f"不支持的配置文件格式: {extension}")
                self._create_default_config()
                return

            # 加载配置后处理
            self._post_load_processing()

        except Exception as e:
            self.logger.error(f"加载配置文件失败: {e}")
            self._create_default_config()

    def _create_default_config(self) -> None:
        """创建默认配置"""
        self.config = {
            "app": {
                "name": "MaiBot",
                "version": "0.1.0",
                "debug": False,
                "log_level": "info",
                "language": "zh-CN",
                "timezone": "Asia/Shanghai",
                "hot_reload": True,
            },
            "brain": {
                "model_provider": "openai",
                "model_name": "gpt-4",
                "memory": {
                    "enabled": True,
                    "storage_type": "sqlite",
                    "sqlite_path": "data/memory.db",
                    "max_memory_items": 1000,
                },
            },
            "sensory_neurons": {
                "vision": {
                    "enabled": True,
                    "description": "视觉处理模块",
                    "frame_rate": 15,
                    "resolution": [640, 480],
                    "use_gpu": True,
                },
                "audio": {
                    "enabled": True,
                    "description": "音频处理模块",
                    "sample_rate": 16000,
                    "channels": 1,
                    "chunk_size": 1024,
                },
                "text": {"enabled": True, "description": "文本输入处理模块"},
            },
            "motor_neurons": {
                "speech": {
                    "enabled": True,
                    "description": "语音合成模块",
                    "voice": "zh-CN-XiaoxiaoNeural",
                    "rate": 1.0,
                    "volume": 1.0,
                },
                "expression": {"enabled": True, "description": "表情动画模块", "model_path": "models/live2d/default"},
                "movement": {"enabled": False, "description": "肢体动作模块"},
            },
        }

        # 保存默认配置
        self.save_config()

        # 处理默认配置
        self._post_load_processing()

    def _post_load_processing(self) -> None:
        """配置加载后的处理"""
        # 处理环境变量覆盖
        self._apply_env_overrides()

        # 加载神经元配置
        self._load_neuron_config()

        # 发送配置变更通知
        self._notify_change("all", None)

    def _apply_env_overrides(self) -> None:
        """应用环境变量覆盖配置"""
        # 扫描环境变量
        for env_name, env_value in os.environ.items():
            # 仅处理指定前缀的环境变量
            if not env_name.startswith(self.env_prefix):
                continue

            # 移除前缀，转换为配置路径
            config_path = env_name[len(self.env_prefix) :].lower().replace("_", ".")

            try:
                # 尝试解析环境变量值（支持数值、布尔值、JSON）
                parsed_value = self._parse_env_value(env_value)

                # 应用到配置
                self._set_config_value(config_path, parsed_value)

            except Exception as e:
                self.logger.warning(f"处理环境变量覆盖失败 [{env_name}]: {e}")

    def _parse_env_value(self, value: str) -> Any:
        """
        解析环境变量值

        Args:
            value: 环境变量值字符串

        Returns:
            解析后的值（可能是字符串、数值、布尔值或字典）
        """
        # 尝试解析为JSON
        if value.startswith("{") or value.startswith("["):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                pass

        # 尝试解析为布尔值
        if value.lower() in ("true", "yes", "1"):
            return True
        if value.lower() in ("false", "no", "0"):
            return False

        # 尝试解析为数值
        try:
            if "." in value:
                return float(value)
            else:
                return int(value)
        except ValueError:
            pass

        # 默认为字符串
        return value

    def _set_config_value(self, path: str, value: Any) -> None:
        """
        根据路径设置配置值

        Args:
            path: 配置路径（点分隔，如'app.debug'）
            value: 要设置的值
        """
        # 拆分路径
        parts = path.split(".")
        target = self.config

        # 导航到最后一层
        for i, part in enumerate(parts[:-1]):
            if part not in target:
                target[part] = {}
            elif not isinstance(target[part], dict):
                # 如果路径中的某一部分不是字典，则覆盖为字典
                target[part] = {}
            target = target[part]

        # 设置值
        target[parts[-1]] = value

    def _load_neuron_config(self) -> None:
        """加载神经元配置"""
        neuron_data = {
            "sensory_neurons": self.config.get("sensory_neurons", {}),
            "motor_neurons": self.config.get("motor_neurons", {}),
        }
        self.neuron_config.load_config(neuron_data)

    def save_config(self) -> None:
        """保存配置到文件"""
        config_path = Path(self.config_path)

        # 确保目录存在
        config_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            # 更新神经元配置
            self.config["sensory_neurons"] = self.neuron_config.sensory_neurons
            self.config["motor_neurons"] = self.neuron_config.motor_neurons

            # 根据文件扩展名选择保存格式
            extension = config_path.suffix.lower()
            if extension == ".yaml" or extension == ".yml":
                with open(config_path, "w", encoding="utf-8") as f:
                    yaml.dump(self.config, f, sort_keys=False, allow_unicode=True)
            elif extension == ".json":
                with open(config_path, "w", encoding="utf-8") as f:
                    json.dump(self.config, f, indent=2, ensure_ascii=False)
            else:
                self.logger.error(f"不支持的配置文件格式: {extension}")
                return

            # 更新时间戳
            self.config_timestamp = config_path.stat().st_mtime

        except Exception as e:
            self.logger.error(f"保存配置文件失败: {e}")

    def get(self, key: str, default: Any = None) -> Any:
        """
        获取配置值

        Args:
            key: 配置键路径（点分隔，如'app.debug'）
            default: 如果配置不存在时的默认值

        Returns:
            配置值或默认值
        """
        parts = key.split(".")
        value = self.config

        for part in parts:
            if not isinstance(value, dict) or part not in value:
                return default
            value = value[part]

        return value

    def set(self, key: str, value: Any, save: bool = True) -> None:
        """
        设置配置值

        Args:
            key: 配置键路径（点分隔，如'app.debug'）
            value: 要设置的值
            save: 是否立即保存配置
        """
        self._set_config_value(key, value)

        # 特殊处理神经元配置
        if key.startswith("sensory_neurons.") or key.startswith("motor_neurons."):
            self._load_neuron_config()

        # 发送变更通知
        self._notify_change(key.split(".")[0], key)

        # 如果需要，保存配置
        if save:
            self.save_config()

    def register_change_callback(self, section: str, callback: Callable) -> None:
        """
        注册配置变更回调

        Args:
            section: 配置区域（如'app', 'brain', 'sensory_neurons'等，或'all'表示所有区域）
            callback: 回调函数，接收变更的配置键作为参数
        """
        if section not in self.change_callbacks:
            self.change_callbacks[section] = []

        if callback not in self.change_callbacks[section]:
            self.change_callbacks[section].append(callback)

    def unregister_change_callback(self, section: str, callback: Callable) -> None:
        """
        注销配置变更回调

        Args:
            section: 配置区域
            callback: 已注册的回调函数
        """
        if section in self.change_callbacks and callback in self.change_callbacks[section]:
            self.change_callbacks[section].remove(callback)

    def _notify_change(self, section: str, key: Optional[str]) -> None:
        """
        通知配置变更

        Args:
            section: 变更的配置区域
            key: 变更的配置键
        """
        # 触发特定区域的回调
        self._trigger_callbacks(section, key)

        # 触发通用回调
        if section != "all":
            self._trigger_callbacks("all", key)

    def _trigger_callbacks(self, section: str, key: Optional[str]) -> None:
        """
        触发特定区域的回调

        Args:
            section: 配置区域
            key: 变更的配置键
        """
        if section in self.change_callbacks:
            for callback in self.change_callbacks[section]:
                try:
                    callback(key)
                except Exception as e:
                    self.logger.error(f"执行配置变更回调时出错: {e}")

    def check_hot_reload(self) -> bool:
        """
        检查配置是否需要热加载

        Returns:
            如果配置已重新加载则返回True，否则返回False
        """
        # 如果未启用热加载，直接返回False
        if not self.get("app.hot_reload", False):
            return False

        # 控制检查频率，避免频繁IO操作
        current_time = time.time()
        if current_time - self.last_check_time < self.reload_interval:
            return False

        self.last_check_time = current_time

        # 检查文件是否被修改
        config_path = Path(self.config_path)
        if not config_path.exists():
            return False

        file_mtime = config_path.stat().st_mtime

        # 如果文件修改时间更新，则重新加载
        if file_mtime > self.config_timestamp:
            old_config = self.config.copy()
            self.load_config()

            # 变更已在load_config中通知
            return True

        return False

    def store_secret(self, key: str, value: str) -> bool:
        """
        安全存储敏感信息

        Args:
            key: 密钥名称
            value: 敏感信息值

        Returns:
            是否成功存储
        """
        return self.dna_storage.store(key, value)

    def get_secret(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """
        获取敏感信息

        Args:
            key: 密钥名称
            default: 默认值

        Returns:
            解密后的敏感信息或默认值
        """
        value = self.dna_storage.retrieve(key)
        return value if value is not None else default

    def delete_secret(self, key: str) -> bool:
        """
        删除敏感信息

        Args:
            key: 密钥名称

        Returns:
            是否成功删除
        """
        return self.dna_storage.delete(key)

    def has_secret(self, key: str) -> bool:
        """
        检查敏感信息是否存在

        Args:
            key: 密钥名称

        Returns:
            敏感信息是否存在
        """
        return self.dna_storage.has_key(key)

    def validate_config(self) -> List[str]:
        """
        验证配置是否有效

        Returns:
            错误信息列表，如果为空则表示配置有效
        """
        errors = []

        # 验证必需的配置字段
        required_fields = [
            "app.name",
            "app.version",
        ]

        for field in required_fields:
            if self.get(field) is None:
                errors.append(f"缺少必需配置: {field}")

        # TODO: 添加更多复杂的验证逻辑

        return errors
