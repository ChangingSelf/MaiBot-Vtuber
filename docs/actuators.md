# 运动神经元开发指南

## 概述

运动神经元(Actuator)是系统中负责将内部神经信号转换为外部行为的组件。它们是系统与外部世界交互的输出点，接收来自神经突触网络的信号，并执行相应的动作，如显示字幕、控制Live2D模型等。

## 运动神经元工作原理

运动神经元基于以下工作流程：

1. **初始化**: 加载配置，准备输出资源
2. **激活**: 开始监听神经信号
3. **接收**: 接收来自神经突触网络的信号
4. **处理**: 将神经信号转换为具体动作
5. **执行**: 执行外部行为
6. **停用**: 关闭输出资源，释放连接

## 创建自定义运动神经元

### 基本结构

所有运动神经元都应继承自`Actuator`基类，并实现其抽象方法：

```python
from src.actuators.base_actuator import Actuator
from src.signals.neural_signal import NeuralSignal, SignalType

class CustomActuator(Actuator):
    """自定义运动神经元 - 执行特定类型的外部行为"""
    
    async def _initialize(self, config):
        """初始化运动神经元
        
        Args:
            config: 神经元配置字典
        """
        # 保存配置
        self.custom_parameter = config.get("custom_parameter", "default_value")
        
        # 初始化输出资源
        # ...
    
    async def _activate(self):
        """激活运动神经元，开始处理动作"""
        # 调用父类激活方法（设置信号处理队列）
        await super()._activate()
        
        # 初始化输出连接或资源
        # ...
    
    async def _deactivate(self):
        """停用运动神经元，停止处理动作"""
        # 关闭输出连接或资源
        # ...
        
        # 调用父类停用方法
        await super()._deactivate()
    
    async def _handle_signal(self, signal):
        """处理接收到的神经信号
        
        Args:
            signal: 接收到的神经信号
        """
        # 更新统计信息
        self.stats["signals_processed"] += 1
        
        # 将信号转换为动作
        action = self._signal_to_action(signal)
        
        if action:
            # 增加待处理动作计数
            self.stats["pending_actions"] += 1
            
            # 将动作加入队列
            await self.action_queue.put(action)
    
    async def _process_action_queue(self):
        """处理动作队列"""
        while self.is_active:
            try:
                # 从队列中获取动作
                action = await self.action_queue.get()
                
                try:
                    # 执行动作
                    await self._execute_action(action)
                    
                    # 减少待处理动作计数
                    self.stats["pending_actions"] -= 1
                    
                    # 更新统计信息
                    self.stats["actions_performed"] += 1
                    self.stats["last_action_time"] = asyncio.get_event_loop().time()
                except Exception as e:
                    self.stats["errors"] += 1
                    logger.error(f"执行动作时出错: {e}", exc_info=True)
                
                # 标记任务完成
                self.action_queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.stats["errors"] += 1
                logger.error(f"处理动作队列时出错: {e}", exc_info=True)
    
    async def _execute_action(self, action):
        """执行具体动作
        
        Args:
            action: 要执行的动作
        """
        # 实现特定的动作执行逻辑
        action_type = action.get("type")
        
        if action_type == "display":
            await self._display_output(action.get("content"))
        elif action_type == "control":
            await self._control_device(action.get("parameters"))
        else:
            logger.warning(f"未知动作类型: {action_type}")
    
    def _signal_to_action(self, signal):
        """将神经信号转换为动作
        
        Args:
            signal: 神经信号
            
        Returns:
            dict: 动作字典，或None表示不需要执行动作
        """
        # 实现特定的信号转换逻辑
        if signal.signal_type != SignalType.MOTOR:
            return None
            
        content = signal.content
        
        # 检查信号内容是否适用于此执行器
        if not self._is_applicable_signal(content):
            return None
            
        # 构建动作
        return {
            "type": content.get("action_type", "display"),
            "content": content.get("message"),
            "parameters": content.get("parameters", {}),
            "timestamp": time.time()
        }
    
    def _is_applicable_signal(self, content):
        """检查信号内容是否适用于此执行器
        
        Args:
            content: 信号内容
            
        Returns:
            bool: 是否适用
        """
        # 判断信号是否应由此执行器处理
        target = content.get("target")
        if target and target != self.name and target != "all":
            return False
            
        return True
    
    async def _display_output(self, content):
        """显示输出内容
        
        Args:
            content: 要显示的内容
        """
        # 实现特定的显示逻辑
        pass
    
    async def _control_device(self, parameters):
        """控制设备
        
        Args:
            parameters: 控制参数
        """
        # 实现特定的设备控制逻辑
        pass
```

### 信号处理流程

运动神经元处理神经信号的一般流程如下：

1. **接收信号**: 通过`_handle_signal`方法接收信号
2. **转换信号**: 将信号转换为具体动作
3. **队列处理**: 将动作放入队列进行异步处理
4. **执行动作**: 在`_execute_action`中执行具体动作

## 常见运动神经元实现模式

### 1. UI输出型执行器

```python
import asyncio
import tkinter as tk
from tkinter import ttk

class SubtitleActuator(Actuator):
    """字幕运动神经元 - 在界面上显示字幕"""
    
    async def _initialize(self, config):
        """初始化字幕执行器"""
        self.font_size = config.get("font_size", 20)
        self.font_family = config.get("font_family", "Microsoft YaHei")
        self.display_time = config.get("display_time", 5.0)  # 字幕显示时间(秒)
        self.max_width = config.get("max_width", 40)  # 最大宽度(字符数)
        
        # 创建字幕窗口（这里使用asyncio.to_thread在非阻塞线程中执行）
        await asyncio.to_thread(self._create_subtitle_window)
    
    def _create_subtitle_window(self):
        """创建字幕窗口"""
        self.root = tk.Tk()
        self.root.title("字幕显示")
        self.root.attributes("-topmost", True)
        
        # 配置窗口样式
        self.root.configure(bg="black")
        self.root.attributes("-alpha", 0.8)
        
        # 创建字幕标签
        self.subtitle_label = ttk.Label(
            self.root, 
            font=(self.font_family, self.font_size),
            foreground="white",
            background="black",
            anchor="center",
            wraplength=self.font_size * self.max_width
        )
        self.subtitle_label.pack(padx=20, pady=20, fill="both", expand=True)
        
        # 居中显示
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        window_width = int(screen_width * 0.8)
        window_height = int(screen_height * 0.2)
        x = (screen_width - window_width) // 2
        y = screen_height - window_height - 50
        self.root.geometry(f"{window_width}x{window_height}+{x}+{y}")
        
        # 不显示窗口，等待显示字幕时再显示
        self.root.withdraw()
        
        # 启动事件循环
        self.tk_task = asyncio.create_task(self._tk_loop())
    
    async def _tk_loop(self):
        """Tkinter事件循环"""
        while self.is_active:
            # 使用asyncio.to_thread在非阻塞线程中更新UI
            await asyncio.to_thread(self.root.update)
            await asyncio.sleep(0.01)  # 避免占用过多CPU
    
    async def _deactivate(self):
        """停用字幕执行器"""
        # 取消Tkinter事件循环任务
        if hasattr(self, 'tk_task') and self.tk_task:
            self.tk_task.cancel()
            try:
                await self.tk_task
            except asyncio.CancelledError:
                pass
        
        # 关闭Tkinter窗口
        if hasattr(self, 'root'):
            await asyncio.to_thread(self.root.destroy)
        
        await super()._deactivate()
    
    async def _execute_action(self, action):
        """执行字幕显示动作"""
        if action["type"] != "display":
            return
            
        text = action.get("content", "")
        if not text:
            return
            
        # 使用asyncio.to_thread在非阻塞线程中更新UI
        await asyncio.to_thread(self._update_subtitle, text)
        
        # 设置自动消失计时器
        self.hide_timer = asyncio.create_task(self._auto_hide(self.display_time))
    
    def _update_subtitle(self, text):
        """更新字幕文本"""
        self.subtitle_label.config(text=text)
        self.root.deiconify()  # 显示窗口
        
    async def _auto_hide(self, delay):
        """自动隐藏字幕"""
        await asyncio.sleep(delay)
        
        # 使用asyncio.to_thread在非阻塞线程中更新UI
        await asyncio.to_thread(self.root.withdraw)  # 隐藏窗口
```

### 2. 设备控制型执行器

```python
import asyncio
import aiohttp

class Live2DActuator(Actuator):
    """Live2D运动神经元 - 控制Live2D模型表情和动作"""
    
    async def _initialize(self, config):
        """初始化Live2D执行器"""
        self.api_base_url = config.get("api_url", "http://localhost:8080/api")
        self.model_id = config.get("model_id", "default")
        self.session = None
        self.connected = False
        
        # 表情映射
        self.expression_map = {
            "happy": "expression_happy",
            "sad": "expression_sad",
            "angry": "expression_angry",
            "surprised": "expression_surprised",
            "neutral": "expression_neutral"
        }
        
        # 动作映射
        self.motion_map = {
            "wave": "motion_wave",
            "bow": "motion_bow",
            "jump": "motion_jump",
            "idle": "motion_idle"
        }
    
    async def _activate(self):
        """激活Live2D执行器"""
        await super()._activate()
        
        # 创建HTTP会话
        self.session = aiohttp.ClientSession()
        
        # 尝试连接并检查状态
        try:
            async with self.session.get(f"{self.api_base_url}/status") as response:
                if response.status == 200:
                    self.connected = True
                    logger.info("成功连接到Live2D API")
                else:
                    logger.error(f"无法连接到Live2D API，状态码: {response.status}")
        except Exception as e:
            logger.error(f"连接Live2D API时出错: {e}")
    
    async def _deactivate(self):
        """停用Live2D执行器"""
        # 关闭HTTP会话
        if self.session:
            await self.session.close()
            self.session = None
            
        self.connected = False
        
        await super()._deactivate()
    
    async def _execute_action(self, action):
        """执行Live2D控制动作"""
        if not self.connected or not self.session:
            logger.error("Live2D API未连接，无法执行动作")
            return
            
        action_type = action.get("type")
        parameters = action.get("parameters", {})
        
        try:
            if action_type == "expression":
                # 设置表情
                expression = parameters.get("name", "neutral")
                await self._set_expression(expression)
                
            elif action_type == "motion":
                # 执行动作
                motion = parameters.get("name", "idle")
                await self._play_motion(motion)
                
            elif action_type == "parameter":
                # 设置模型参数
                param_name = parameters.get("name")
                param_value = parameters.get("value")
                if param_name and param_value is not None:
                    await self._set_parameter(param_name, param_value)
                    
            elif action_type == "composite":
                # 组合动作（同时设置表情和动作）
                expression = parameters.get("expression")
                motion = parameters.get("motion")
                
                if expression:
                    await self._set_expression(expression)
                if motion:
                    await self._play_motion(motion)
        except Exception as e:
            self.stats["errors"] += 1
            logger.error(f"执行Live2D动作时出错: {e}")
    
    async def _set_expression(self, expression_name):
        """设置Live2D模型表情
        
        Args:
            expression_name: 表情名称
        """
        # 映射表情名称到API使用的ID
        expression_id = self.expression_map.get(expression_name.lower(), expression_name)
        
        # 发送API请求
        url = f"{self.api_base_url}/expression"
        payload = {
            "model": self.model_id,
            "expression": expression_id
        }
        
        async with self.session.post(url, json=payload) as response:
            if response.status != 200:
                logger.error(f"设置表情失败，状态码: {response.status}")
                return False
                
        return True
    
    async def _play_motion(self, motion_name):
        """播放Live2D模型动作
        
        Args:
            motion_name: 动作名称
        """
        # 映射动作名称到API使用的ID
        motion_id = self.motion_map.get(motion_name.lower(), motion_name)
        
        # 发送API请求
        url = f"{self.api_base_url}/motion"
        payload = {
            "model": self.model_id,
            "motion": motion_id
        }
        
        async with self.session.post(url, json=payload) as response:
            if response.status != 200:
                logger.error(f"播放动作失败，状态码: {response.status}")
                return False
                
        return True
    
    async def _set_parameter(self, param_name, param_value):
        """设置Live2D模型参数
        
        Args:
            param_name: 参数名称
            param_value: 参数值
        """
        # 发送API请求
        url = f"{self.api_base_url}/parameter"
        payload = {
            "model": self.model_id,
            "name": param_name,
            "value": param_value
        }
        
        async with self.session.post(url, json=payload) as response:
            if response.status != 200:
                logger.error(f"设置参数失败，状态码: {response.status}")
                return False
                
        return True
```

### 3. 文件输出型执行器

```python
import asyncio
import aiofiles
import json
import os
import time

class LogActuator(Actuator):
    """日志运动神经元 - 将神经信号写入日志文件"""
    
    async def _initialize(self, config):
        """初始化日志执行器"""
        self.log_dir = config.get("log_dir", "logs")
        self.log_prefix = config.get("log_prefix", "neural_")
        self.rotate_size = config.get("rotate_size", 10 * 1024 * 1024)  # 10MB
        self.current_log_file = None
        self.current_size = 0
        
        # 创建日志目录
        os.makedirs(self.log_dir, exist_ok=True)
        
        # 创建新的日志文件
        await self._create_new_log_file()
    
    async def _create_new_log_file(self):
        """创建新的日志文件"""
        timestamp = int(time.time())
        filename = f"{self.log_prefix}{timestamp}.log"
        self.current_log_file = os.path.join(self.log_dir, filename)
        self.current_size = 0
        
        # 创建空文件
        async with aiofiles.open(self.current_log_file, "w") as f:
            await f.write("")
    
    async def _check_rotate(self):
        """检查是否需要轮转日志文件"""
        if self.current_size >= self.rotate_size:
            await self._create_new_log_file()
    
    async def _execute_action(self, action):
        """执行日志记录动作"""
        if action["type"] != "log":
            return
            
        # 准备日志内容
        log_entry = {
            "timestamp": time.time(),
            "content": action.get("content"),
            "metadata": action.get("parameters", {})
        }
        
        log_line = json.dumps(log_entry) + "\n"
        
        # 写入日志文件
        try:
            async with aiofiles.open(self.current_log_file, "a") as f:
                await f.write(log_line)
                
            # 更新当前文件大小
            self.current_size += len(log_line)
            
            # 检查是否需要轮转
            await self._check_rotate()
                
        except Exception as e:
            self.stats["errors"] += 1
            logger.error(f"写入日志文件时出错: {e}")
    
    def _signal_to_action(self, signal):
        """将神经信号转换为日志动作"""
        # 检查信号类型
        if signal.signal_type not in [SignalType.MOTOR, SignalType.SENSORY, SignalType.CORE]:
            return None
            
        # 构建日志动作
        return {
            "type": "log",
            "content": signal.content,
            "parameters": {
                "signal_type": signal.signal_type.name,
                "source": signal.source,
                "priority": signal.priority.name
            },
            "timestamp": time.time()
        }
```

## 最佳实践

### 1. 异常处理和恢复

确保运动神经元能够处理各种异常情况，并适当恢复：

```python
try:
    await self._execute_external_action(action)
except ConnectionError as e:
    # 连接失败处理
    self.stats["connection_errors"] += 1
    logger.error(f"执行动作时连接失败: {e}")
    
    # 尝试重新连接
    await self._reconnect()
except Exception as e:
    # 一般错误处理
    self.stats["errors"] += 1
    logger.error(f"执行动作时出错: {e}", exc_info=True)
```

### 2. 资源管理

确保资源在停用时正确释放：

```python
async def _deactivate(self):
    """停用运动神经元"""
    # 关闭外部连接
    if self.connection:
        await self.connection.close()
    
    # 释放资源
    if self.resource:
        self.resource.release()
    
    # 调用父类停用方法
    await super()._deactivate()
```

### 3. 信号过滤和优先级处理

实现信号过滤和优先级处理机制：

```python
async def _handle_signal(self, signal):
    """处理接收到的神经信号"""
    # 检查信号是否适用于此执行器
    if not self._is_applicable_signal(signal):
        return
    
    # 检查信号优先级
    if signal.priority == SignalPriority.HIGH:
        # 对于高优先级信号，清空当前队列
        while not self.action_queue.empty():
            try:
                self.action_queue.get_nowait()
                self.action_queue.task_done()
            except asyncio.QueueEmpty:
                break
                
        # 减少待处理动作计数
        self.stats["pending_actions"] = 0
    
    # 转换为动作并加入队列
    action = self._signal_to_action(signal)
    if action:
        self.stats["pending_actions"] += 1
        await self.action_queue.put(action)
```

### 4. 行为节流

对于高频率输出，实现节流机制避免过载：

```python
def _should_execute(self, action):
    """判断是否应该执行动作
    
    Args:
        action: 动作数据
        
    Returns:
        bool: 是否执行
    """
    # 检查节流设置
    current_time = time.time()
    if action["type"] in self.throttle_settings:
        last_time = self.last_execution_times.get(action["type"], 0)
        min_interval = self.throttle_settings[action["type"]]
        
        if current_time - last_time < min_interval:
            self.stats["throttled"] += 1
            return False
            
    # 更新最后执行时间
    self.last_execution_times[action["type"]] = current_time
    return True
```

## 常见运动神经元类型

- **SubtitleActuator**: 显示字幕
- **Live2DActuator**: 控制Live2D模型
- **AudioActuator**: 播放声音或语音
- **LightActuator**: 控制灯光
- **NotificationActuator**: 发送通知
- **FileActuator**: 写入文件
- **LogActuator**: A那些日志记录
- **APIActuator**: 调用外部API

## 配置示例

```yaml
actuators:
  SubtitleActuator:
    enabled: true
    font_size: 24
    font_family: "Microsoft YaHei"
    display_time: 5.0
    max_width: 40
    
  Live2DActuator:
    enabled: true
    api_url: "http://localhost:8080/api"
    model_id: "hiyori"
    expression_map:
      happy: "expression_01"
      sad: "expression_02"
      angry: "expression_03"
    motion_map:
      wave: "motion_01"
      bow: "motion_02"
      jump: "motion_03"
```

## 调试技巧

1. **可视化动作队列**:
   ```python
   def get_queue_status(self):
       """获取队列状态信息"""
       return {
           "queue_size": self.action_queue.qsize(),
           "pending_actions": self.stats["pending_actions"],
           "actions_performed": self.stats["actions_performed"]
       }
   ```

2. **跟踪动作执行**:
   ```python
   async def _execute_action(self, action):
       """执行动作并记录详细日志"""
       logger.debug(f"开始执行动作: {action}")
       start_time = time.time()
       
       try:
           result = await self._do_execute(action)
           execution_time = time.time() - start_time
           logger.debug(f"动作执行完成，耗时: {execution_time:.3f}秒，结果: {result}")
           return result
       except Exception as e:
           execution_time = time.time() - start_time
           logger.error(f"动作执行失败，耗时: {execution_time:.3f}秒，错误: {e}")
           raise
   ```

3. **模拟模式**:
   ```python
   async def _execute_action(self, action):
       """执行动作（支持模拟模式）"""
       if self.config.get("simulation_mode", False):
           # 在模拟模式下，只记录动作而不实际执行
           logger.info(f"[模拟] 执行动作: {action}")
           return True
           
       # 实际执行动作
       return await self._do_execute(action)
   ```

## 测试运动神经元

为运动神经元编写测试，确保其正常工作：

```python
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from src.signals.neural_signal import NeuralSignal, SignalType, SignalPriority

class TestCustomActuator:
    @pytest.fixture
    def mock_synaptic_network(self):
        network = MagicMock()
        network.register_receptor = MagicMock(return_value="test-receptor-id")
        return network
    
    @pytest.fixture
    def test_actuator(self, mock_synaptic_network):
        from src.actuators.custom_actuator import CustomActuator
        return CustomActuator(mock_synaptic_network, "TestCustomActuator")
    
    @pytest.fixture
    def test_signal(self):
        return NeuralSignal(
            source="test_source",
            type=SignalType.MOTOR,
            content={"action_type": "display", "message": "测试消息"},
            priority=SignalPriority.NORMAL
        )
    
    @pytest.mark.asyncio
    async def test_initialization(self, test_actuator):
        config = {"custom_parameter": "test_value"}
        await test_actuator.initialize(config)
        
        assert test_actuator.custom_parameter == "test_value"
    
    @pytest.mark.asyncio
    async def test_signal_handling(self, test_actuator, test_signal):
        # 初始化执行器
        config = {}
        await test_actuator.initialize(config)
        
        # 模拟signal_to_action方法
        with patch.object(test_actuator, '_signal_to_action') as mock_signal_to_action:
            # 设置mock返回值
            mock_action = {"type": "test", "content": "test_content"}
            mock_signal_to_action.return_value = mock_action
            
            # 模拟action_queue
            test_actuator.action_queue = AsyncMock()
            test_actuator.action_queue.put = AsyncMock()
            
            # 调用信号处理方法
            await test_actuator._handle_signal(test_signal)
            
            # 验证signal_to_action被调用
            mock_signal_to_action.assert_called_once_with(test_signal)
            
            # 验证动作被加入队列
            test_actuator.action_queue.put.assert_called_once_with(mock_action)
    
    @pytest.mark.asyncio
    async def test_action_execution(self, test_actuator):
        # 初始化执行器
        config = {}
        await test_actuator.initialize(config)
        
        # 创建测试动作
        test_action = {"type": "display", "content": "测试内容"}
        
        # 模拟execute_action方法
        with patch.object(test_actuator, '_execute_action', new_callable=AsyncMock) as mock_execute:
            # 模拟action_queue
            test_actuator.action_queue = MagicMock()
            test_actuator.action_queue.get = AsyncMock(return_value=test_action)
            test_actuator.action_queue.task_done = MagicMock()
            
            # 设置active状态
            test_actuator.is_active = True
            
            # 调用处理队列方法一次（通常在循环中运行）
            await test_actuator._process_action_queue.__wrapped__(test_actuator)
            
            # 验证execute_action被调用
            mock_execute.assert_called_once_with(test_action)
            
            # 验证队列任务被标记为完成
            test_actuator.action_queue.task_done.assert_called_once()
``` 