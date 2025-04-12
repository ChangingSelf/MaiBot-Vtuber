# 连接器开发指南

## 概述

连接器(Connector)是系统中负责与外部系统(如MaiBot Core)通信的双向神经元。它既能将内部神经信号发送到外部系统，又能接收外部系统的响应并转换为内部信号。

## 连接器工作原理

连接器基本工作流程：

1. **初始化**: 加载连接配置
2. **激活**: 建立外部连接
3. **接收内部信号**: 接收神经突触网络的信号
4. **转发到外部**: 将内部信号发送到外部系统
5. **接收外部响应**: 接收外部系统的响应
6. **转发到内部**: 将外部响应转换为内部神经信号
7. **停用**: 关闭连接，释放资源

## 创建自定义连接器

所有连接器都应继承自`Connector`类：

```python
from src.connectors.base_connector import Connector
from src.signals.neural_signal import NeuralSignal, SignalType

class CustomConnector(Connector):
    """自定义连接器 - 连接特定的外部系统"""
    
    async def _initialize(self, config):
        """初始化连接器"""
        self.endpoint = config.get("endpoint", "ws://localhost:8080")
        self.auth_token = config.get("auth_token")
        self.reconnect_interval = config.get("reconnect_interval", 5.0)
        
        # 初始化连接状态
        self.connection = None
        self.connected = False
    
    async def _activate(self):
        """激活连接器，建立连接"""
        await super()._activate()
        await self._connect()
    
    async def _deactivate(self):
        """停用连接器，关闭连接"""
        if self.connection:
            await self._disconnect()
        await super()._deactivate()
    
    async def sense(self, external_data):
        """处理来自外部系统的输入"""
        # 更新统计信息
        self.stats["messages_received"] += 1
        
        # 转换为内部神经信号
        signal = self._external_to_signal(external_data)
        if signal:
            # 发送到神经突触网络
            await self.synaptic_network.transmit(signal)
    
    async def respond(self, signal):
        """响应内部神经信号，发送到外部系统"""
        if not self.connected:
            logger.warning(f"尝试发送信号但未连接到外部系统")
            return
        
        # 转换为外部系统格式
        external_message = self._signal_to_external(signal)
        if external_message:
            # 发送到外部系统
            await self._send_to_external(external_message)
            self.stats["messages_sent"] += 1
    
    def _external_to_signal(self, external_data):
        """将外部响应转换为内部神经信号"""
        # 实现特定的转换逻辑
        try:
            data = external_data
            if isinstance(data, str):
                data = json.loads(data)
                
            return NeuralSignal(
                source=self.name,
                type=self._determine_signal_type(data),
                content=data
            )
        except Exception as e:
            logger.error(f"转换外部数据时出错: {e}")
            return None
    
    def _signal_to_external(self, signal):
        """将内部神经信号转换为外部系统格式"""
        # 实现特定的转换逻辑
        return signal.content
```

## WebSocket连接器示例

WebSocket是连接器最常用的通信方式：

```python
import asyncio
import json
import websockets

class WebSocketConnector(Connector):
    """WebSocket连接器示例"""
    
    async def _connect(self):
        """建立WebSocket连接"""
        try:
            headers = {}
            if self.auth_token:
                headers["Authorization"] = f"Bearer {self.auth_token}"
                
            self.connection = await websockets.connect(
                self.endpoint,
                extra_headers=headers
            )
            self.connected = True
            
            # 启动接收任务
            self.receive_task = asyncio.create_task(self._receive_loop())
            logger.info(f"已连接到WebSocket: {self.endpoint}")
        except Exception as e:
            self.connected = False
            logger.error(f"连接WebSocket失败: {e}")
            self._schedule_reconnect()
    
    async def _disconnect(self):
        """关闭WebSocket连接"""
        try:
            if self.receive_task:
                self.receive_task.cancel()
                try:
                    await self.receive_task
                except asyncio.CancelledError:
                    pass
                
            if self.connection:
                await self.connection.close()
                
            self.connected = False
            logger.info("已断开WebSocket连接")
        except Exception as e:
            logger.error(f"断开WebSocket连接时出错: {e}")
    
    async def _receive_loop(self):
        """接收WebSocket消息循环"""
        try:
            while self.connected and self.is_active:
                message = await self.connection.recv()
                await self.sense(message)
        except websockets.exceptions.ConnectionClosed:
            logger.warning("WebSocket连接已关闭")
            if self.is_active:
                self.connected = False
                self._schedule_reconnect()
        except Exception as e:
            logger.error(f"接收WebSocket消息时出错: {e}")
            if self.is_active:
                self.connected = False
                self._schedule_reconnect()
    
    async def _send_to_external(self, message):
        """通过WebSocket发送消息"""
        if isinstance(message, dict):
            message = json.dumps(message)
            
        await self.connection.send(message)
    
    def _schedule_reconnect(self):
        """计划重连任务"""
        if not self.is_active or self.connected:
            return
            
        logger.info(f"计划在{self.reconnect_interval}秒后重连")
        asyncio.create_task(self._reconnect_after_delay())
    
    async def _reconnect_after_delay(self):
        """延迟后重连"""
        await asyncio.sleep(self.reconnect_interval)
        if self.is_active and not self.connected:
            await self._connect()
```

## MaiBot Core连接器

MaiBot Core连接器是系统的核心连接器，负责与MaiBot Core通信：

```python
class MaiBotCoreConnector(WebSocketConnector):
    """MaiBot Core连接器 - 连接MaiBot Core AI系统"""
    
    def _external_to_signal(self, external_data):
        """将MaiBot Core响应转换为内部神经信号"""
        try:
            # 解析响应
            if isinstance(external_data, str):
                data = json.loads(external_data)
            else:
                data = external_data
                
            # 判断响应类型
            if "action" in data:
                # 动作响应 -> 运动信号
                signal_type = SignalType.MOTOR
            else:
                # 文本响应 -> 感知信号
                signal_type = SignalType.SENSORY
                
            return NeuralSignal(
                source="MaiBotCore",
                type=signal_type,
                content=data
            )
        except Exception as e:
            logger.error(f"转换MaiBot Core响应时出错: {e}")
            return None
    
    def _signal_to_external(self, signal):
        """将内部神经信号转换为MaiBot Core请求格式"""
        # 只转发感知信号到MaiBot Core
        if signal.signal_type != SignalType.SENSORY:
            return None
            
        # 构建请求
        return {
            "type": "user_message",
            "content": signal.content,
            "source": signal.source,
            "timestamp": time.time()
        }
```

## 最佳实践

### 1. 健壮的错误处理

确保连接器能够处理各种错误情况：

```python
try:
    await self._send_to_external(message)
except ConnectionError as e:
    logger.error(f"发送消息时连接断开: {e}")
    self.connected = False
    self._schedule_reconnect()
except Exception as e:
    logger.error(f"发送消息时出错: {e}")
```

### 2. 自动重连机制

实现自动重连确保连接可靠性：

```python
async def _connect_with_retry(self, max_attempts=5):
    """带重试的连接"""
    for attempt in range(1, max_attempts + 1):
        try:
            await self._connect()
            return True
        except Exception as e:
            logger.warning(f"连接失败，尝试 {attempt}/{max_attempts}，错误: {e}")
            if attempt < max_attempts:
                await asyncio.sleep(self.reconnect_interval)
    
    return False
```

### 3. 心跳检测

实现心跳检测确保连接活跃：

```python
async def _start_heartbeat(self, interval=30):
    """启动心跳检测"""
    while self.connected and self.is_active:
        try:
            await self._send_to_external({"type": "heartbeat"})
        except Exception as e:
            logger.error(f"发送心跳时出错: {e}")
            break
        
        await asyncio.sleep(interval)
```

## 配置示例

```yaml
connectors:
  MaiBotCoreConnector:
    enabled: true
    endpoint: "ws://localhost:8080/connect"
    auth_token: "${MAIBOT_CORE_TOKEN}"
    reconnect_interval: 5.0
    max_reconnect_attempts: 10
``` 