from abc import ABC, abstractmethod
import importlib
import inspect
import os
import sys

from typing import Dict, List, Optional, Any, Type

from maim_message import MessageBase
from src.utils.logger import get_logger
from src.utils.config import load_component_specific_config, merge_component_configs


class MessagePipeline(ABC):
    """
    消息管道基类，用于在消息发送到 MaiCore 前进行处理。
    所有的管道都应该继承此类，并实现 process_message 方法。
    """

    # 默认优先级，数值越小优先级越高。实际优先级由配置决定。
    priority = 1000

    def __init__(self, config: Dict[str, Any]):
        """
        初始化管道。

        Args:
            config: 该管道的合并后配置字典。
        """
        self.config = config
        self.logger = get_logger(self.__class__.__name__)
        # 管道实现可以在这里从 self.config 中读取自己的配置项
        # 例如:
        # self.rate_limit = self.config.get("rate_limit", 60)
        # self.enabled_feature = self.config.get("feature_x_enabled", False)
        # self.logger.debug(f"管道 '{self.__class__.__name__}' 使用配置初始化: {self.config}")

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

    async def on_connect(self) -> None:
        """
        当 AmaidesuCore 成功连接到 MaiCore 时调用的钩子方法。
        子类可以重写此方法以在连接建立时执行初始化操作。

        默认实现为空操作。
        """
        self.logger.debug("管道已连接")

    async def on_disconnect(self) -> None:
        """
        当 AmaidesuCore 与 MaiCore 断开连接时调用的钩子方法。
        子类可以重写此方法以在连接断开时执行清理操作。

        默认实现为空操作。
        """
        self.logger.debug("管道已断开")


class PipelineManager:
    """
    管道管理器，负责加载、排序和执行双向消息管道。
    """

    def __init__(self):
        self._inbound_pipelines: List[MessagePipeline] = []
        self._outbound_pipelines: List[MessagePipeline] = []
        self._inbound_sorted: bool = True
        self._outbound_sorted: bool = True
        self.logger = get_logger("PipelineManager")

    def _register_pipeline(self, pipeline: MessagePipeline, direction: str) -> None:
        """
        根据方向注册一个消息管道。

        Args:
            pipeline: MessagePipeline 的实例。
            direction: 管道方向 ("inbound" 或 "outbound")。
        """
        if direction == "inbound":
            self._inbound_pipelines.append(pipeline)
            self._inbound_sorted = False
        else: # 默认 "outbound"
            self._outbound_pipelines.append(pipeline)
            self._outbound_sorted = False
        
        self.logger.info(f"管道已注册: {pipeline.__class__.__name__} (方向: {direction}, 优先级: {pipeline.priority})")

    def _ensure_sorted(self) -> None:
        """确保管道列表按优先级排序 (此方法已废弃，请使用带有方向的方法)"""
        pass # 保留为空以防万一，但不应再被调用

    def _ensure_outbound_sorted(self) -> None:
        """确保出站管道列表按优先级排序"""
        if not self._outbound_sorted:
            self._outbound_pipelines.sort(key=lambda x: x.priority)
            self._outbound_sorted = True
            pipe_info = ", ".join([f"{p.__class__.__name__}({p.priority})" for p in self._outbound_pipelines])
            self.logger.debug(f"出站管道已排序: {pipe_info}")

    def _ensure_inbound_sorted(self) -> None:
        """确保入站管道列表按优先级排序"""
        if not self._inbound_sorted:
            self._inbound_pipelines.sort(key=lambda x: x.priority)
            self._inbound_sorted = True
            pipe_info = ", ".join([f"{p.__class__.__name__}({p.priority})" for p in self._inbound_pipelines])
            self.logger.debug(f"入站管道已排序: {pipe_info}")

    async def process_outbound_message(self, message: MessageBase) -> Optional[MessageBase]:
        """
        按优先级顺序通过所有出站管道处理消息。

        Args:
            message: 要处理的 MessageBase 对象

        Returns:
            处理后的 MessageBase 对象，如果任何管道返回 None 则返回 None
        """
        self._ensure_outbound_sorted()

        current_message = message
        for pipeline in self._outbound_pipelines:
            if current_message is None:
                self.logger.info(f"消息被前序管道丢弃，终止于出站管道 {pipeline.__class__.__name__} 之前")
                return None

            try:
                self.logger.debug(f"出站管道 {pipeline.__class__.__name__} 开始处理消息: {message.message_info.message_id}")
                current_message = await pipeline.process_message(current_message)
                if current_message is None:
                    self.logger.info(f"消息 {message.message_info.message_id} 被出站管道 {pipeline.__class__.__name__} 丢弃")
                    return None
            except Exception as e:
                self.logger.error(f"出站管道 {pipeline.__class__.__name__} 处理消息时出错: {e}", exc_info=True)
        
        return current_message

    async def process_inbound_message(self, message: MessageBase) -> Optional[MessageBase]:
        """
        按优先级顺序通过所有入站管道处理消息。

        Args:
            message: 要处理的 MessageBase 对象

        Returns:
            处理后的 MessageBase 对象，如果任何管道返回 None 则返回 None
        """
        self._ensure_inbound_sorted()

        current_message = message
        for pipeline in self._inbound_pipelines:
            if current_message is None:
                self.logger.info(f"消息被前序管道丢弃，终止于入站管道 {pipeline.__class__.__name__} 之前")
                return None

            try:
                self.logger.debug(f"入站管道 {pipeline.__class__.__name__} 开始处理消息: {message.message_info.message_id}")
                current_message = await pipeline.process_message(current_message)
                if current_message is None:
                    self.logger.info(f"消息 {message.message_info.message_id} 被入站管道 {pipeline.__class__.__name__} 丢弃")
                    return None
            except Exception as e:
                self.logger.error(f"入站管道 {pipeline.__class__.__name__} 处理消息时出错: {e}", exc_info=True)

        return current_message

    async def load_pipelines(
        self, pipeline_base_dir: str = "src/pipelines", root_config_pipelines_section: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        扫描并加载指定目录下的所有管道。
        采用新的配置结构，从根配置的 [pipelines.pipeline_name_snake] 获取优先级和全局覆盖。

        Args:
            pipeline_base_dir: 管道包的基础目录，默认为 "src/pipelines"
            root_config_pipelines_section: 根配置文件中 'pipelines' 部分的字典。
                                           例如：config.get('pipelines', {})
        """
        self.logger.info(f"开始从目录加载管道: {pipeline_base_dir}")
        pipeline_dir_abs = os.path.abspath(pipeline_base_dir)

        if not os.path.isdir(pipeline_dir_abs):
            self.logger.warning(f"管道目录不存在: {pipeline_dir_abs}，跳过管道加载。")
            return

        # 将 src 目录（通常是管道目录的父目录）添加到 sys.path
        src_dir = os.path.dirname(pipeline_dir_abs)
        if src_dir not in sys.path:
            sys.path.insert(0, src_dir)
            self.logger.debug(f"已将目录添加到 sys.path: {src_dir}")

        if root_config_pipelines_section is None:
            root_config_pipelines_section = {}
            self.logger.warning("未提供根配置中的 'pipelines' 部分，所有管道将无法加载。")
            return

        loaded_pipeline_count = 0

        # 遍历根配置中定义的管道
        for pipeline_name_snake, pipeline_global_settings in root_config_pipelines_section.items():
            if not isinstance(pipeline_global_settings, dict):
                self.logger.warning(f"管道 '{pipeline_name_snake}' 在根配置中的条目格式不正确 (应为字典), 跳过。")
                continue

            priority = pipeline_global_settings.get("priority")
            if not isinstance(priority, int):
                self.logger.info(  # 使用info级别，因为这可能是用户故意禁用管道的方式
                    f"管道 '{pipeline_name_snake}' 在根配置中 'priority' 缺失或无效，视为禁用，跳过加载。"
                )
                continue

            # --- 新增：确定管道方向 ---
            # 默认为 "outbound" 以保持向后兼容
            direction = pipeline_global_settings.get("direction", "outbound").lower()
            if direction not in ["inbound", "outbound"]:
                self.logger.warning(
                    f"管道 '{pipeline_name_snake}' 的方向配置 '{direction}' 无效，将默认为 'outbound'。"
                )
                direction = "outbound"
            
            self.logger.debug(f"管道 '{pipeline_name_snake}' 方向设置为: {direction}")

            pipeline_package_path = os.path.join(pipeline_dir_abs, pipeline_name_snake)

            # 检查预期的管道目录和文件是否存在
            if not (
                os.path.isdir(pipeline_package_path)
                and os.path.exists(os.path.join(pipeline_package_path, "__init__.py"))
                and os.path.exists(os.path.join(pipeline_package_path, "pipeline.py"))
            ):
                self.logger.warning(
                    f"管道 '{pipeline_name_snake}' 在根配置中已启用 (priority={priority})，"
                    f"但在 '{pipeline_package_path}' 未找到有效的包结构 (需要 __init__.py 和 pipeline.py)，跳过。"
                )
                continue

            # 1. 提取全局覆盖配置 (排除 'priority' 和 'direction' 键)
            global_override_config = {
                k: v for k, v in pipeline_global_settings.items() if k not in ["priority", "direction"]
            }
            self.logger.debug(f"管道 '{pipeline_name_snake}' 的全局覆盖配置: {global_override_config}")

            # 2. 加载管道自身的独立配置
            pipeline_specific_config = load_component_specific_config(
                pipeline_package_path, pipeline_name_snake, "管道"
            )

            # 3. 合并配置：全局覆盖配置优先
            final_pipeline_config = merge_component_configs(
                pipeline_specific_config, global_override_config, pipeline_name_snake, "管道"
            )
            # self.logger.debug(f"管道 '{pipeline_name_snake}' 合并后的最终配置: {final_pipeline_config}") # 此日志现在由 merge_component_configs 处理

            # 4. 导入并实例化管道
            try:
                module_import_path = f"pipelines.{pipeline_name_snake}.pipeline"
                self.logger.debug(f"尝试导入管道模块: {module_import_path}")
                module = importlib.import_module(module_import_path)

                expected_class_name = "".join(word.title() for word in pipeline_name_snake.split("_")) + "Pipeline"
                pipeline_class: Optional[Type[MessagePipeline]] = None

                for name, obj in inspect.getmembers(module):
                    if inspect.isclass(obj) and issubclass(obj, MessagePipeline) and obj != MessagePipeline:
                        if name == expected_class_name:
                            pipeline_class = obj
                            break
                        # 记录找到但不匹配期望名称的MessagePipeline子类
                        self.logger.debug(
                            f"在 {module_import_path} 中找到MessagePipeline子类 '{name}'，但期望的是 '{expected_class_name}'。"
                        )

                if pipeline_class:
                    # 直接在实例上设置优先级，因为基类构造函数不处理它
                    # 而 MessagePipeline 类本身的 priority 是默认值
                    pipeline_instance = pipeline_class(config=final_pipeline_config)
                    pipeline_instance.priority = priority  # 设置实例的优先级，用于排序

                    self._register_pipeline(pipeline_instance, direction) # 使用新的注册方法
                    loaded_pipeline_count += 1
                    # self.logger.info(f"成功加载并设置管道: {pipeline_class.__name__} (来自 {pipeline_name_snake}/pipeline.py, 优先级: {priority})") # register_pipeline 已记录
                else:
                    self.logger.error(f"在模块 '{module_import_path}' 中未找到预期的管道类 '{expected_class_name}'。")

            except ImportError as e:
                self.logger.error(f"导入管道模块 '{module_import_path}' 失败: {e}", exc_info=True)
            except Exception as e:
                self.logger.error(f"加载或实例化管道 '{pipeline_name_snake}' 时发生错误: {e}", exc_info=True)

        if loaded_pipeline_count > 0:
            self.logger.info(f"管道加载完成，共加载 {loaded_pipeline_count} 个启用的管道。")
        else:
            self.logger.warning("未加载任何启用的管道。请检查根配置文件 [pipelines] 部分和管道目录结构。")

        self._ensure_inbound_sorted()
        self._ensure_outbound_sorted()

    async def notify_connect(self) -> None:
        """当 AmaidesuCore 连接时通知所有管道。"""
        all_pipelines = self._inbound_pipelines + self._outbound_pipelines
        if not all_pipelines:
            return
            
        self.logger.debug(f"通知 {len(all_pipelines)} 个管道连接已建立...")
        for pipeline in all_pipelines:
            try:
                await pipeline.on_connect()
            except Exception as e:
                self.logger.error(f"通知管道 {pipeline.__class__.__name__} 连接事件时出错: {e}", exc_info=True)

    async def notify_disconnect(self) -> None:
        """当 AmaidesuCore 断开连接时通知所有管道。"""
        all_pipelines = self._inbound_pipelines + self._outbound_pipelines
        if not all_pipelines:
            return

        self.logger.debug(f"通知 {len(all_pipelines)} 个管道连接已断开...")
        for pipeline in all_pipelines:
            try:
                await pipeline.on_disconnect()
            except Exception as e:
                self.logger.error(f"通知管道 {pipeline.__class__.__name__} 断开连接事件时出错: {e}", exc_info=True)
