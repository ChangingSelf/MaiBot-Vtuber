# 感觉神经元开发指南

## 概述

感觉神经元(Sensor)是系统中负责感知外部刺激并转换为内部神经信号的组件。它们是系统与外部世界交互的入口点，负责从各种来源(如直播平台弹幕、管理命令等)获取信息，并将其转换为标准化的内部信号格式。

## 感觉神经元工作原理

感觉神经元基于以下工作流程：

1. **初始化**: 加载配置，建立外部连接
2. **激活**: 开始接收外部输入
3. **感知**: 持续监听或轮询外部来源
4. **处理**: 将外部输入转换为神经信号
5. **传输**: 将神经信号发送到神经突触网络
6. **停用**: 关闭连接，释放资源

## 创建自定义感觉神经元

### 基本结构

所有感觉神经元都应继承自`Sensor`基类，并实现其抽象方法：

```python
from src.sensors.base_sensor import Sensor
from src.signals.neural_signal import NeuralSignal, SignalType, SignalPriority

class CustomSensor(Sensor):
    """自定义感觉神经元 - 处理特定类型的外部输入"""
    
    async def _initialize(self, config):
        """初始化感觉神经元
        
        Args:
            config: 神经元配置字典
        """
        # 保存配置
        self.custom_parameter = config.get("custom_parameter", "default_value")
        
        # 初始化外部连接或资源
        # ...
    
    async def _activate(self):
        """激活感觉神经元，开始处理输入"""
        # 调用父类激活方法
        await super()._activate()
        
        # 启动自定义输入处理逻辑
        # 例如，启动轮询任务或建立WebSocket连接
        # ...
    
    async def _deactivate(self):
        """停用感觉神经元，停止处理输入"""
        # 关闭外部连接或资源
        # ...
        
        # 调用父类停用方法
        await super()._deactivate()
    
    async def sense(self, input_data):
        """处理外部输入并转换为神经信号
        
        Args:
            input_data: 外部输入数据
            
        Returns:
            NeuralSignal: 生成的神经信号
        """
        # 更新统计信息
        self.stats["inputs_processed"] += 1
        self.stats["last_input_time"] = asyncio.get_event_loop().time()
        
        # 创建神经信号
        signal = NeuralSignal(
            source=self.name,
            type=SignalType.SENSORY,
            content=self._transform_input(input_data),
            priority=self._determine_priority(input_data)
        )
        
        # 传输信号到神经网络
        await self.synaptic_network.transmit(signal)
        self.stats["signals_transmitted"] += 1
        
        return signal
    
    def _transform_input(self, input_data):
        """转换输入数据为标准格式
        
        Args:
            input_data: 原始输入数据
            
        Returns:
            dict: 转换后的数据
        """
        # 实现特定的数据转换逻辑
        return {
            "type": "custom_input",
            "content": input_data,
            "timestamp": time.time()
        }
    
    def _determine_priority(self, input_data):
        """确定信号优先级
        
        Args:
            input_data: 原始输入数据
            
        Returns:
            SignalPriority: 信号优先级
        """
        # 实现特定的优先级确定逻辑
        return SignalPriority.NORMAL
```

### 输入处理方式

感觉神经元有两种常见的输入处理方式：

1. **推送模式(Push)**: 外部源主动发送数据，如WebSocket连接
2. **拉取模式(Pull)**: 定期轮询外部源获取数据，如API轮询

#### 示例：推送模式(WebSocket)

```python
import asyncio
import websockets

class WebSocketSensor(Sensor):
    """WebSocket感觉神经元 - 通过WebSocket接收输入"""
    
    async def _initialize(self, config):
        """初始化WebSocket连接"""
        self.ws_url = config.get("ws_url", "ws://localhost:8080")
        self.ws_connection = None
        self.connected = False
    
    async def _activate(self):
        """激活感觉神经元，建立WebSocket连接"""
        await super()._activate()
        
        # 创建WebSocket接收任务
        self.ws_task = asyncio.create_task(self._ws_listener())
    
    async def _deactivate(self):
        """停用感觉神经元，关闭WebSocket连接"""
        if self.ws_connection:
            await self.ws_connection.close()
            self.connected = False
        
        if self.ws_task:
            self.ws_task.cancel()
            try:
                await self.ws_task
            except asyncio.CancelledError:
                pass
        
        await super()._deactivate()
    
    async def _ws_listener(self):
        """WebSocket监听器"""
        while self.is_active:
            try:
                async with websockets.connect(self.ws_url) as websocket:
                    self.ws_connection = websocket
                    self.connected = True
                    
                    # 持续接收消息
                    async for message in websocket:
                        # 处理接收到的消息
                        await self.sense(message)
                        
            except (websockets.exceptions.ConnectionClosed, 
                    websockets.exceptions.ConnectionError) as e:
                self.stats["errors"] += 1
                self.connected = False
                
                # 等待一段时间后重连
                await asyncio.sleep(5)
```

#### 示例：拉取模式(API轮询)

```python
import asyncio
import aiohttp
import time

class APIPollingSensor(Sensor):
    """API轮询感觉神经元 - 定期轮询API获取数据"""
    
    async def _initialize(self, config):
        """初始化API配置"""
        self.api_url = config.get("api_url", "http://localhost:8080/api/data")
        self.poll_interval = config.get("poll_interval", 5.0)  # 轮询间隔(秒)
        self.last_poll_time = 0
        self.session = None
    
    async def _activate(self):
        """激活感觉神经元，开始轮询"""
        await super()._activate()
        
        # 创建HTTP会话
        self.session = aiohttp.ClientSession()
        
        # 创建轮询任务
        self.polling_task = asyncio.create_task(self._polling_loop())
    
    async def _deactivate(self):
        """停用感觉神经元，停止轮询"""
        if self.polling_task:
            self.polling_task.cancel()
            try:
                await self.polling_task
            except asyncio.CancelledError:
                pass
        
        if self.session:
            await self.session.close()
            self.session = None
        
        await super()._deactivate()
    
    async def _polling_loop(self):
        """API轮询循环"""
        while self.is_active:
            try:
                # 执行API请求
                async with self.session.get(self.api_url) as response:
                    if response.status == 200:
                        data = await response.json()
                        self.last_poll_time = time.time()
                        
                        # 处理获取到的数据
                        if data:
                            await self.sense(data)
                    else:
                        self.stats["errors"] += 1
                        
            except Exception as e:
                self.stats["errors"] += 1
            
            # 等待下一次轮询
            await asyncio.sleep(self.poll_interval)
```

## 最佳实践

### 1. 异常处理

确保感觉神经元能够优雅地处理异常情况：

```python
try:
    # 执行可能出错的操作
    result = await some_operation()
    await self.sense(result)
except Exception as e:
    self.stats["errors"] += 1
    logger.error(f"处理输入时出错: {e}", exc_info=True)
    
    # 根据需要执行恢复操作
    await self._handle_error(e)
```

### 2. 重连机制

对于需要持久连接的感觉神经元，实现自动重连机制：

```python
async def _connect_with_retry(self):
    """带重试的连接逻辑"""
    retry_count = 0
    max_retries = self.config.get("max_retries", 5)
    retry_delay = self.config.get("retry_delay", 5)
    
    while self.is_active and retry_count < max_retries:
        try:
            # 尝试连接
            await self._connect()
            return True
        except Exception as e:
            retry_count += 1
            self.stats["reconnect_attempts"] += 1
            logger.warning(f"连接失败，第{retry_count}次重试，错误: {e}")
            
            # 等待一段时间后重试
            await asyncio.sleep(retry_delay)
    
    return False
```

### 3. 输入缓冲处理

对于高频率输入，使用队列和缓冲处理避免阻塞：

```python
async def _process_input_queue(self):
    """处理输入队列"""
    while self.is_active:
        try:
            # 从队列获取输入
            input_data = await self.input_queue.get()
            
            # 处理输入
            await self.sense(input_data)
            
            # 标记任务完成
            self.input_queue.task_done()
        except asyncio.CancelledError:
            break
        except Exception as e:
            self.stats["errors"] += 1
            logger.error(f"处理输入队列时出错: {e}", exc_info=True)
```

### 4. 输入过滤和限流

实现过滤和限流机制，避免无用输入和过载：

```python
def _should_process(self, input_data):
    """判断是否应该处理输入
    
    Args:
        input_data: 原始输入数据
        
    Returns:
        bool: 是否处理该输入
    """
    # 过滤无效输入
    if not input_data:
        return False
    
    # 检查速率限制
    current_time = time.time()
    if current_time - self.last_processed_time < self.rate_limit:
        self.stats["rate_limited"] += 1
        return False
    
    # 检查输入是否匹配过滤条件
    if not self._matches_filter(input_data):
        self.stats["filtered"] += 1
        return False
    
    return True
```

## 常见感觉神经元类型

- **DanmakuSensor**: 接收直播平台弹幕
- **CommandSensor**: 接收管理命令
- **WebhookSensor**: 接收Webhook回调
- **FileSensor**: 监控文件变化
- **APISensor**: 调用外部API
- **MQTTSensor**: 订阅MQTT消息
- **TimedSensor**: 定时生成信号
- **KeyboardSensor**: 接收键盘输入

## 配置示例

```yaml
sensors:
  DanmakuSensor:
    enabled: true
    platforms:
      - type: bilibili
        room_id: 12345
        poll_interval: 1.0  # 秒
      - type: youtube
        channel_id: "UCxxxxxxxxxxxxxxx"
        api_key: "your-api-key"
  
  WebhookSensor:
    enabled: true
    host: "0.0.0.0"
    port: 8080
    endpoints:
      - path: "/webhook/github"
        secret: "your-webhook-secret"
      - path: "/webhook/custom"
```

## 调试技巧

1. **启用详细日志**:
   ```python
   import logging
   logger = logging.getLogger(__name__)
   logger.setLevel(logging.DEBUG)
   ```

2. **记录重要事件**:
   ```python
   logger.info(f"接收到输入: {input_data}")
   logger.debug(f"转换后的信号: {signal}")
   ```

3. **使用测试模式**:
   ```python
   if self.config.get("test_mode", False):
       # 以测试模式运行，可能会模拟输入或跳过某些操作
   ```

4. **检查状态统计**:
   ```python
   def get_status(self):
       """获取详细状态信息用于调试"""
       return {
           "name": self.name,
           "active": self.is_active,
           "stats": self.stats,
           "config": self.config,
           "connections": {
               "connected": self.connected,
               "last_connect_time": self.last_connect_time
           }
       }
   ```

## 测试感觉神经元

为感觉神经元编写测试，确保其正常工作：

```python
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from src.signals.neural_signal import NeuralSignal, SignalType

class TestCustomSensor:
    @pytest.fixture
    def mock_synaptic_network(self):
        network = MagicMock()
        network.transmit = AsyncMock()
        return network
    
    @pytest.fixture
    def test_sensor(self, mock_synaptic_network):
        from src.sensors.custom_sensor import CustomSensor
        return CustomSensor(mock_synaptic_network, "TestCustomSensor")
    
    @pytest.mark.asyncio
    async def test_initialization(self, test_sensor):
        config = {"custom_parameter": "test_value"}
        await test_sensor.initialize(config)
        
        assert test_sensor.custom_parameter == "test_value"
    
    @pytest.mark.asyncio
    async def test_sensing(self, test_sensor, mock_synaptic_network):
        config = {}
        await test_sensor.initialize(config)
        
        test_input = {"data": "test_data"}
        await test_sensor.sense(test_input)
        
        # 检查信号是否正确传输
        mock_synaptic_network.transmit.assert_called_once()
        signal = mock_synaptic_network.transmit.call_args[0][0]
        
        assert isinstance(signal, NeuralSignal)
        assert signal.source == "TestCustomSensor"
        assert signal.signal_type == SignalType.SENSORY
```