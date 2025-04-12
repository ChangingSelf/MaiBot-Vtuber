from typing import Dict, Any, Optional, List, Union, Callable
import logging
import asyncio
import time
import json
import websockets
from websockets.exceptions import ConnectionClosed, InvalidStatusCode

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

        self.ws_url = None
        self.ws_connection = None
        self.message_task = None
        self.message_queue = asyncio.Queue()
        self.heartbeat_task = None
        self.heartbeat_interval = 30  # 心跳间隔（秒）
        self.signal_adapter = SignalAdapter()

        # 扩展统计信息
        self.stats.update(
            {
                "messages_processed": 0,
                "last_message_time": None,
                "connection_drops": 0,
                "heartbeats_sent": 0,
                "heartbeats_missed": 0,
            }
        )

    async def _init_connection(self, config: Dict[str, Any]) -> None:
        """初始化WebSocket连接配置

        Args:
            config: 连接配置
        """
        # 设置WebSocket URL
        if "ws_url" not in config:
            raise ValueError("MaiBot Core连接器配置必须包含 'ws_url'")

        self.ws_url = config["ws_url"]

        # 设置心跳间隔
        if "heartbeat_interval" in config:
            self.heartbeat_interval = config["heartbeat_interval"]

        logger.info(f"MaiBot Core连接器初始化完成: {self.name}, URL: {self.ws_url}")

    async def _connect(self) -> bool:
        """建立与MaiBot Core的WebSocket连接

        Returns:
            连接是否成功
        """
        if not self.ws_url:
            logger.error(f"未设置WebSocket URL，无法连接: {self.name}")
            self._update_connection_state("error")
            return False

        self._update_connection_state("connecting")

        try:
            # 建立WebSocket连接
            self.ws_connection = await websockets.connect(
                self.ws_url,
                ping_interval=None,  # 禁用内置心跳，使用自定义心跳
                close_timeout=5,
            )

            # 启动消息处理任务
            self.message_task = asyncio.create_task(self._message_loop())

            # 启动心跳任务
            self.heartbeat_task = asyncio.create_task(self._heartbeat_loop())

            self._update_connection_state("connected")
            logger.info(f"已连接到MaiBot Core: {self.name}, URL: {self.ws_url}")
            return True
        except (ConnectionRefusedError, InvalidStatusCode) as e:
            logger.error(f"连接到MaiBot Core失败: {self.name}, 错误: {e}")
            self._update_connection_state("error")
            return False
        except Exception as e:
            logger.error(f"连接到MaiBot Core过程中出现未知错误: {self.name}, 错误: {e}")
            self._update_connection_state("error")
            return False

    async def _disconnect(self) -> None:
        """断开与MaiBot Core的WebSocket连接"""
        # 停止消息处理任务
        if self.message_task:
            self.message_task.cancel()
            try:
                await self.message_task
            except asyncio.CancelledError:
                pass
            self.message_task = None

        # 停止心跳任务
        if self.heartbeat_task:
            self.heartbeat_task.cancel()
            try:
                await self.heartbeat_task
            except asyncio.CancelledError:
                pass
            self.heartbeat_task = None

        # 关闭WebSocket连接
        if self.ws_connection:
            try:
                await self.ws_connection.close()
            except Exception as e:
                logger.error(f"关闭WebSocket连接时出错: {self.name}, 错误: {e}")
            finally:
                self.ws_connection = None

        self._update_connection_state("disconnected")
        logger.info(f"已断开与MaiBot Core的连接: {self.name}")

    async def _message_loop(self) -> None:
        """处理WebSocket消息的循环任务"""
        try:
            while self.is_active and self.ws_connection:
                try:
                    # 接收消息
                    message = await self.ws_connection.recv()
                    await self._handle_message(message)
                except ConnectionClosed:
                    logger.warning(f"WebSocket连接已关闭: {self.name}")
                    self._update_connection_state("disconnected")
                    self.stats["connection_drops"] += 1
                    break
                except Exception as e:
                    logger.error(f"处理WebSocket消息时出错: {self.name}, 错误: {e}")
                    self.stats["errors"] += 1
                    # 不终止循环，继续尝试处理下一条消息
        except asyncio.CancelledError:
            logger.info(f"消息处理任务被取消: {self.name}")
            raise
        except Exception as e:
            logger.error(f"消息处理循环出现严重错误: {self.name}, 错误: {e}")
            self._update_connection_state("error")
            self.stats["errors"] += 1

    async def _handle_message(self, message: str) -> None:
        """处理接收到的WebSocket消息

        Args:
            message: 接收到的消息
        """
        try:
            # 解析消息
            data = json.loads(message)

            # 更新统计信息
            self.stats["messages_received"] += 1
            self.stats["last_message_time"] = time.time()

            # 处理特殊消息类型
            if data.get("type") == "heartbeat":
                # 心跳响应，不需要进一步处理
                logger.debug(f"收到心跳响应: {self.name}")
                return
            elif data.get("type") == "system":
                # 系统消息，记录但不处理
                logger.info(f"收到系统消息: {data.get('message')}")
                return

            # 将消息转换为神经信号并传递
            await self.sense(data)

        except json.JSONDecodeError as e:
            logger.error(f"解析消息JSON时出错: {self.name}, 错误: {e}, 消息: {message[:100]}")
            self.stats["errors"] += 1
        except Exception as e:
            logger.error(f"处理消息时出错: {self.name}, 错误: {e}")
            self.stats["errors"] += 1

    async def _heartbeat_loop(self) -> None:
        """发送心跳的循环任务"""
        consecutive_fails = 0

        try:
            while self.is_active and self.ws_connection:
                try:
                    # 发送心跳
                    heartbeat = {"type": "heartbeat", "timestamp": time.time()}
                    await self.ws_connection.send(json.dumps(heartbeat))
                    self.stats["heartbeats_sent"] += 1
                    consecutive_fails = 0
                except Exception as e:
                    logger.error(f"发送心跳时出错: {self.name}, 错误: {e}")
                    self.stats["errors"] += 1
                    self.stats["heartbeats_missed"] += 1
                    consecutive_fails += 1

                    # 如果连续三次心跳失败，认为连接已断开
                    if consecutive_fails >= 3:
                        logger.warning(f"连续{consecutive_fails}次心跳失败，连接可能已断开: {self.name}")
                        self._update_connection_state("disconnected")
                        self.stats["connection_drops"] += 1
                        break

                # 等待下一次心跳
                await asyncio.sleep(self.heartbeat_interval)
        except asyncio.CancelledError:
            logger.info(f"心跳任务被取消: {self.name}")
            raise
        except Exception as e:
            logger.error(f"心跳循环出现严重错误: {self.name}, 错误: {e}")
            self._update_connection_state("error")
            self.stats["errors"] += 1

    async def sense(self, input_data: Dict[str, Any]) -> None:
        """处理从MaiBot Core接收到的消息

        Args:
            input_data: 接收到的消息数据
        """
        if not self.is_active:
            return

        try:
            # 将消息转换为神经信号
            signal = self.signal_adapter.to_neural_signal(input_data)

            if signal:
                # 将信号传递到神经突触网络
                await self._transmit_signal(signal)
                logger.debug(f"从MaiBot Core接收到消息并转换为信号: {signal.id}, 类型: {signal.signal_type.name}")
                self.stats["messages_processed"] += 1
            else:
                logger.warning(f"无法将消息转换为神经信号: {input_data}")
        except Exception as e:
            logger.error(f"处理接收到的消息时出错: {self.name}, 错误: {e}")
            self.stats["errors"] += 1

    async def respond(self, signal: NeuralSignal) -> None:
        """响应神经信号，将信号转换为消息并发送到MaiBot Core

        Args:
            signal: 接收到的神经信号
        """
        if not self.is_active or not self.ws_connection or self.connection_state != "connected":
            logger.warning(f"尝试发送消息但连接未就绪: {self.name}, 信号ID: {signal.id}")
            return

        try:
            # 检查是否需要处理该信号，排除不需要发送的信号类型
            if signal.signal_type not in self.accepted_signal_types:
                return

            # 将神经信号转换为消息
            message = self.signal_adapter.to_maim_message(signal)

            if message:
                # 发送消息 - 将MessageBase对象转换为字典再序列化
                await self.ws_connection.send(json.dumps(message.to_dict()))
                logger.debug(f"将信号转换为消息并发送到MaiBot Core: {signal.id}, 类型: {signal.signal_type.name}")
                self.stats["messages_sent"] += 1
            else:
                logger.warning(f"无法将信号转换为消息: {signal.id}")
        except Exception as e:
            logger.error(f"响应信号时出错: {self.name}, 错误: {e}, 信号ID: {signal.id}")
            self.stats["errors"] += 1
