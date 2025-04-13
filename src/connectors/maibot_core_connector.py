from typing import Dict, Any, Optional
import logging
import asyncio
import time
import json
from maim_message import Router, RouteConfig, TargetConfig
from maim_message.message_base import BaseMessageInfo, GroupInfo, MessageBase, Seg, UserInfo

from src.core.synaptic_network import SynapticNetwork
from src.signals.neural_signal import NeuralSignal, SignalType
from src.signals.signal_adapter import SignalAdapter
from src.connectors.base_connector import Connector

logger = logging.getLogger(__name__)


class MaiBotCoreConnector(Connector):
    """MaiBot Core连接器 - 负责与MaiBot Core通信"""

    def __init__(self, synaptic_network: SynapticNetwork, name: Optional[str] = None):
        super().__init__(
            synaptic_network,
            name or "MaiBot Core连接器",
            # 接收所有可能需要传递给MaiBot Core的信号
            input_signal_types=[SignalType.SENSORY, SignalType.SYSTEM],
            # 输出不同类型的信号根据MaiBot Core的响应
            output_signal_types=[SignalType.MOTOR, SignalType.CORE],
        )

        self.router = None
        self.platform = None
        self.core_host = None
        self.core_port = None
        self.signal_adapter = SignalAdapter()

        # 扩展统计信息
        self.stats.update(
            {
                "messages_processed": 0,
                "last_message_time": None,
                "connection_drops": 0,
                "messages_sent": 0,
            }
        )

    async def _init_connection(self, config: Dict[str, Any]) -> None:
        """初始化Router连接配置

        Args:
            config: 连接配置
        """
        logger.info(f"初始化MaiBot Core连接器: {config}")
        # 检查必要配置
        if "ws_url" not in config:
            raise ValueError("MaiBot Core连接器配置必须包含 'ws_url'")
        if "platform" not in config:
            raise ValueError("MaiBot Core连接器配置必须包含 'platform'")

        self.ws_url = config["ws_url"]
        self.platform = config["platform"]

        # 创建Router配置
        route_config = RouteConfig(
            route_config={
                self.platform: TargetConfig(
                    url=self.ws_url,
                    token=config.get("token"),
                )
            }
        )
        self.router = Router(route_config)

        logger.info(f"MaiBot Core连接器初始化完成: {self.name}, URL: {self.ws_url}")

    async def _connect(self) -> bool:
        """建立与MaiBot Core的连接

        Returns:
            连接是否成功
        """
        if not self.router:
            logger.error(f"未初始化Router，无法连接: {self.name}")
            self._update_connection_state("error")
            return False

        self._update_connection_state("connecting")

        try:
            # 注册消息处理器
            self.router.register_class_handler(self._process_message)

            # 运行Router
            asyncio.create_task(self.router.run())

            self._update_connection_state("connected")
            logger.info(f"已连接到MaiBot Core: {self.name}, URL: ws://{self.core_host}:{self.core_port}/ws")
            return True
        except Exception as e:
            logger.error(f"连接到MaiBot Core过程中出现错误: {self.name}, 错误: {e}")
            self._update_connection_state("error")
            return False

    async def _disconnect(self) -> None:
        """断开与MaiBot Core的连接"""
        if self.router:
            try:
                await self.router.stop()
                logger.info(f"已断开与MaiBot Core的连接: {self.name}")
            except Exception as e:
                logger.error(f"断开与MaiBot Core的连接时出错: {self.name}, 错误: {e}")
                self.stats["errors"] += 1

        self._update_connection_state("disconnected")

    async def _process_message(self, raw_message_base_str: str) -> None:
        """处理接收到的消息

        Args:
            raw_message_base_str: 接收到的原始消息
        """
        try:
            # 安全地记录日志，避免切片错误
            try:
                log_message = (
                    str(raw_message_base_str)[:100] + "..."
                    if len(str(raw_message_base_str)) > 100
                    else str(raw_message_base_str)
                )
                logger.debug(f"从MaiBot Core接收到消息: {log_message}")
            except Exception as e:
                logger.debug(f"记录消息日志时出错: {type(e).__name__}, 消息类型: {type(raw_message_base_str)}")

            # 解析消息
            raw_message_base: MessageBase = MessageBase.from_dict(raw_message_base_str)

            # 更新统计信息
            self.stats["messages_received"] += 1
            self.stats["last_message_time"] = time.time()

            # 直接使用SignalAdapter将MessageBase转换为神经信号
            signal = self.signal_adapter.to_neural_signal(raw_message_base)

            if signal:
                # 将信号传递到神经突触网络
                await self._transmit_signal(signal)
                logger.debug(f"从MaiBot Core接收到消息并转换为信号: {signal.id}, 类型: {signal.signal_type.name}")
                self.stats["messages_processed"] += 1
            else:
                # 安全地记录警告日志
                logger.warning("无法将消息转换为神经信号")

        except Exception as e:
            # 记录错误信息，但不尝试打印raw_message_base_str
            logger.error(f"处理消息时出错: {self.name}, 错误类型: {type(e).__name__}, 错误信息: {str(e)}")
            self.stats["errors"] += 1

    async def sense(self, input_data: Dict[str, Any]) -> None:
        """实现抽象方法以符合Connector接口

        注意：在MaiBotCoreConnector中，实际处理消息的是_process_message方法，
        sense方法仅作为接口实现，通常不会被直接调用。
        TODO 之后修

        Args:
            input_data: 接收到的消息数据
        """
        pass
        # # 所有实际处理已在_process_message中完成
        # # 此方法保留以满足Connector接口要求
        # logger.debug(f"sense方法被调用，但不是MaiBotCore的主要处理路径: {self.name}")

        # if not self.is_active:
        #     return

        # try:
        #     # 将消息转换为神经信号
        #     signal = self.signal_adapter.to_neural_signal(input_data)

        #     if signal:
        #         # 将信号传递到神经突触网络
        #         await self._transmit_signal(signal)
        #         logger.debug(f"通过sense方法处理消息: {signal.id}, 类型: {signal.signal_type.name}")
        #         self.stats["messages_processed"] += 1
        # except Exception as e:
        #     logger.error(f"sense方法处理消息时出错: {self.name}, 错误: {e}")
        #     self.stats["errors"] += 1

    async def respond(self, signal: NeuralSignal) -> None:
        """响应神经信号，将信号转换为消息并发送到MaiBot Core

        Args:
            signal: 接收到的神经信号
        """
        if not self.is_active or not self.router or self.connection_state != "connected":
            logger.warning(f"尝试发送消息但连接未就绪: {self.name}, 信号ID: {signal.id}")
            return

        try:
            # 检查是否需要处理该信号，排除不需要发送的信号类型
            if signal.signal_type not in self.accepted_signal_types:
                return

            # 使用SignalAdapter将神经信号转换为MaiM消息格式
            message_base = self.signal_adapter.to_maim_message(signal)

            if message_base:
                # 确保消息使用正确的平台
                if message_base.message_info.platform != self.platform:
                    message_base.message_info.platform = self.platform

                # 发送消息
                await self.router.send_message(message_base)
                logger.debug(
                    f"将信号转换为消息并发送到MaiBot Core: {signal.id}, 内容: {message_base.raw_message[:50] if message_base.raw_message else ''}..."
                )
                self.stats["messages_sent"] += 1
            else:
                logger.warning(f"无法将信号转换为消息: {signal.id}")
        except Exception as e:
            logger.error(f"响应信号时出错: {self.name}, 错误: {e}, 信号ID: {signal.id}")
            self.stats["errors"] += 1
