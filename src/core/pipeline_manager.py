from abc import ABC, abstractmethod
import asyncio
import importlib
import inspect
import os
import sys

# 尝试导入 tomllib (Python 3.11+), 否则使用 toml
try:
    import tomllib
except ModuleNotFoundError:
    try:
        import toml as tomllib  # type: ignore
    except ModuleNotFoundError:
        print("错误：需要安装 TOML 解析库。请运行 'pip install toml'", file=sys.stderr)
        sys.exit(1)
from typing import Dict, List, Optional, Any, Type, TypeVar, Set, Callable

from maim_message import MessageBase
from src.utils.logger import logger


class MessagePipeline(ABC):
    """
    消息管道基类，用于在消息发送到 MaiCore 前进行处理。
    所有的管道都应该继承此类，并实现 process_message 方法。
    """

    # 默认优先级，数值越小优先级越高
    priority = 1000

    @abstractmethod
    async def process_message(self, message: MessageBase) -> Optional[MessageBase]:
        """
        处理消息的抽象方法，子类必须实现此方法。

        Args:
            message: 要处理的 MessageBase 对象

        Returns:
            处理后的 MessageBase 对象，如果返回 None 则表示该消息应被丢弃（不再继续处理）
        """
        pass


class PipelineManager:
    """
    管道管理器，负责注册、排序和执行消息管道。
    """

    def __init__(self):
        self._pipelines: List[MessagePipeline] = []
        self._sorted: bool = True  # 标记管道列表是否已排序
        self.logger = logger

    def register_pipeline(self, pipeline: MessagePipeline) -> None:
        """
        注册一个消息管道。

        Args:
            pipeline: MessagePipeline 的实例
        """
        self._pipelines.append(pipeline)
        self._sorted = False
        self.logger.info(f"管道已注册: {pipeline.__class__.__name__} (优先级: {pipeline.priority})")

    def _ensure_sorted(self) -> None:
        """确保管道列表按优先级排序"""
        if not self._sorted:
            self._pipelines.sort(key=lambda x: x.priority)
            self._sorted = True
            pipe_info = ", ".join([f"{p.__class__.__name__}({p.priority})" for p in self._pipelines])
            self.logger.debug(f"管道已排序: {pipe_info}")

    async def process_message(self, message: MessageBase) -> Optional[MessageBase]:
        """
        按优先级顺序通过所有注册的管道处理消息。

        Args:
            message: 要处理的 MessageBase 对象

        Returns:
            处理后的 MessageBase 对象，如果任何管道返回 None 则返回 None
        """
        self._ensure_sorted()

        current_message = message
        for pipeline in self._pipelines:
            if current_message is None:
                # 如果消息被某个管道丢弃，则终止处理
                self.logger.info(f"消息被管道 {pipeline.__class__.__name__} 丢弃，终止处理")
                return None

            try:
                self.logger.debug(f"管道 {pipeline.__class__.__name__} 开始处理消息: {message.message_info.message_id}")
                current_message = await pipeline.process_message(current_message)
                if current_message is None:
                    self.logger.info(
                        f"消息 {message.message_info.message_id} 被管道 {pipeline.__class__.__name__} 丢弃"
                    )
                    return None
            except Exception as e:
                self.logger.error(f"管道 {pipeline.__class__.__name__} 处理消息时出错: {e}", exc_info=True)
                # 在出错时可以选择继续处理或终止
                # 这里选择继续，但在生产环境中可能需要更谨慎的策略

        return current_message

    def _load_pipeline_config(self, pipeline_dir: str, pipeline_name: str) -> Dict[str, Any]:
        """
        加载管道的配置文件。

        Args:
            pipeline_dir: 管道目录的绝对路径
            pipeline_name: 管道名称

        Returns:
            配置字典，若配置文件不存在或加载失败则返回空字典
        """
        config_path = os.path.join(pipeline_dir, pipeline_name, "config.toml")

        if os.path.exists(config_path):
            try:
                # 加载并返回管道的配置
                pipeline_config = tomllib.load(open(config_path, "rb"))
                section_name = pipeline_name.replace("-", "_")

                # 如果配置中有对应段落，则返回该段落
                if section_name in pipeline_config:
                    self.logger.debug(f"已加载管道 '{pipeline_name}' 特定配置: {pipeline_config[section_name]}")
                    return pipeline_config[section_name]
                else:
                    self.logger.warning(f"管道 '{pipeline_name}' 配置文件中未找到 [{section_name}] 段落")
                    return {}
            except Exception as e:
                self.logger.error(f"加载管道 '{pipeline_name}' 配置文件失败: {e}")
                return {}
        else:
            self.logger.debug(f"管道 '{pipeline_name}' 无配置文件")
            return {}

    async def load_pipelines(
        self, pipeline_dir: str = "src/pipelines", config: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        扫描并加载指定目录下的所有管道。
        使用简化的配置格式，未配置的管道默认不启用。

        Args:
            pipeline_dir: 管道目录的路径，默认为 "src/pipelines"
            config: 可选的配置字典，用于初始化管道
        """
        self.logger.info(f"开始从目录加载管道: {pipeline_dir}")
        pipeline_dir_abs = os.path.abspath(pipeline_dir)

        if not os.path.isdir(pipeline_dir_abs):
            self.logger.warning(f"管道目录不存在: {pipeline_dir_abs}，跳过管道加载。")
            return

        # 将 src 目录添加到 sys.path，以便导入管道模块
        src_dir = os.path.dirname(pipeline_dir_abs)
        if src_dir not in sys.path:
            sys.path.insert(0, src_dir)
            self.logger.debug(f"已将目录添加到 sys.path: {src_dir}")

        # 使用配置或初始化空字典
        if config is None:
            config = {}

        # 获取已启用的管道及其优先级
        # 配置中未明确列出的管道默认不启用
        enabled_pipelines = {}
        for key, value in config.items():
            if isinstance(value, (int, float)):
                # 转换蛇形命名为驼峰命名 (如 danmu_throttle -> DanmuThrottlePipeline)
                class_name = "".join(word.title() for word in key.split("_")) + "Pipeline"
                enabled_pipelines[class_name] = value

        self.logger.debug(f"已启用的管道配置: {enabled_pipelines}")
        if not enabled_pipelines:
            self.logger.warning("未找到任何已启用的管道配置，管道系统将不加载任何管道。")
            return

        # 遍历管道目录下的所有子目录和Python文件
        loaded_pipeline_count = 0
        for item in os.listdir(pipeline_dir_abs):
            if item == "__init__.py" or item == "__pycache__" or item == "README.md":
                continue

            item_path = os.path.join(pipeline_dir_abs, item)

            if os.path.isdir(item_path):
                # 处理作为包的管道
                package_name = item
                pipeline_module_path = os.path.join(item_path, "pipeline.py")

                if os.path.exists(pipeline_module_path):
                    try:
                        # 加载管道配置
                        pipeline_config = self._load_pipeline_config(pipeline_dir_abs, package_name)

                        # 导入管道模块
                        module_import_path = f"pipelines.{package_name}.pipeline"
                        self.logger.debug(f"尝试导入管道模块: {module_import_path}")
                        module = importlib.import_module(module_import_path)

                        # 处理模块中的管道类
                        loaded_pipeline_count = self._process_pipeline_module(
                            module, enabled_pipelines, loaded_pipeline_count, pipeline_config
                        )
                    except ImportError as e:
                        self.logger.error(f"导入管道包 '{package_name}' 失败: {e}", exc_info=True)
                    except Exception as e:
                        self.logger.error(f"处理管道包 '{package_name}' 时出错: {e}", exc_info=True)

            elif item.endswith(".py"):
                # 处理单文件管道
                module_name = item[:-3]  # 去掉 .py 后缀
                try:
                    # 加载管道配置 (单文件管道不会有独立配置文件)
                    pipeline_config = {}

                    # 导入管道模块
                    module_import_path = f"pipelines.{module_name}"
                    self.logger.debug(f"尝试导入单文件管道模块: {module_import_path}")
                    module = importlib.import_module(module_import_path)

                    # 处理模块中的管道类
                    loaded_pipeline_count = self._process_pipeline_module(
                        module, enabled_pipelines, loaded_pipeline_count, pipeline_config
                    )
                except ImportError as e:
                    self.logger.error(f"导入管道模块 '{module_name}' 失败: {e}", exc_info=True)
                except Exception as e:
                    self.logger.error(f"处理管道模块 '{module_name}' 时出错: {e}", exc_info=True)

        if loaded_pipeline_count > 0:
            self.logger.info(f"管道加载完成，共加载 {loaded_pipeline_count} 个管道。")
        else:
            self.logger.warning("未找到任何匹配的管道可以加载。")

        # 确保按优先级排序
        self._ensure_sorted()

    def _process_pipeline_module(self, module, enabled_pipelines, loaded_count, pipeline_config=None):
        """
        处理一个包含管道类的模块，查找并注册符合条件的管道。

        Args:
            module: 导入的模块对象
            enabled_pipelines: 已启用的管道配置字典
            loaded_count: 当前已加载的管道计数
            pipeline_config: 管道特定配置，用于初始化管道实例

        Returns:
            更新后的已加载管道计数
        """
        count = loaded_count

        if pipeline_config is None:
            pipeline_config = {}

        # 查找模块中的所有管道类（继承自 MessagePipeline 的类）
        for name, obj in inspect.getmembers(module):
            if inspect.isclass(obj) and issubclass(obj, MessagePipeline) and obj != MessagePipeline:  # 排除基类
                # 检查配置中是否启用该管道
                if name not in enabled_pipelines:
                    self.logger.debug(f"管道 '{name}' 未在配置中启用，跳过加载。")
                    continue

                priority = enabled_pipelines[name]

                # 设置优先级
                obj.priority = priority
                self.logger.debug(f"为管道 '{name}' 设置优先级: {priority}")

                # 初始化管道实例（使用管道特定配置）
                try:
                    # 尝试使用配置初始化管道
                    init_signature = inspect.signature(obj.__init__)
                    init_params = {}

                    # 过滤配置，只传递__init__方法能接受的参数
                    for param_name in init_signature.parameters:
                        if param_name != "self" and param_name in pipeline_config:
                            init_params[param_name] = pipeline_config[param_name]

                    # 创建管道实例
                    if init_params:
                        self.logger.debug(f"使用自定义配置初始化管道 '{name}': {init_params}")
                        pipeline_instance = obj(**init_params)
                    else:
                        self.logger.debug(f"使用默认配置初始化管道 '{name}'")
                        pipeline_instance = obj()

                    self.register_pipeline(pipeline_instance)
                    self.logger.info(f"成功加载管道: {name} (优先级: {priority})")
                    count += 1
                except Exception as e:
                    self.logger.error(f"初始化管道 '{name}' 时出错: {e}", exc_info=True)

        return count
