# Minecraft插件重构技术规范

## 重构目标
将现有minecraft插件重构为支持双模式切换：
- **maicore模式**：现有MaiCore通信控制模式（保持向后兼容）
- **agent模式**：智能体自主决策模式，支持Alex和Simple智能体

## 架构设计问题修复

### 发现的问题
1. **异步兼容性问题**：Alex.run()是同步方法，需要在异步环境中正确调用
2. **Action类型处理**：不同版本MineLand的Action定义可能不同
3. **状态传递错误**：游戏状态属性访问可能不存在
4. **导入依赖缺失**：需要处理可选依赖的导入错误
5. **消息格式解析**：原plugin.py中的消息处理逻辑需要完整移植

## 核心接口（修正版）

### ControllerStrategy
```python
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Optional
import logging

if TYPE_CHECKING:
    from ..plugin import MinecraftPlugin
    from maim_message import MessageBase

class ControllerStrategy(ABC):
    def __init__(self):
        self.plugin: Optional['MinecraftPlugin'] = None
        self.logger = logging.getLogger(self.__class__.__name__)
    
    @abstractmethod
    async def initialize(self, plugin_context: 'MinecraftPlugin') -> None:
        self.plugin = plugin_context
    
    @abstractmethod
    async def start_control_loop(self) -> None:
        pass
    
    @abstractmethod
    async def handle_external_message(self, message: 'MessageBase') -> None:
        pass
    
    @abstractmethod
    async def cleanup(self) -> None:
        pass
    
    @abstractmethod
    def get_mode_name(self) -> str:
        pass
```

### BaseAgent
```python
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
import logging

try:
    from mineland import Action
except ImportError:
    Action = Any

class BaseAgent(ABC):
    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)
        self.is_initialized = False
    
    @abstractmethod
    async def initialize(self, config: Dict[str, Any]) -> None:
        self.is_initialized = True
    
    @abstractmethod
    async def run(self, obs: Dict[str, Any], **kwargs) -> Optional[Action]:
        if not self.is_initialized:
            raise RuntimeError(f"{self.__class__.__name__} not initialized")
    
    @abstractmethod
    async def reset(self) -> None:
        pass
    
    @abstractmethod
    async def receive_command(self, command: str, priority: str = "normal") -> None:
        pass
    
    @abstractmethod
    def get_agent_type(self) -> str:
        pass
    
    async def cleanup(self) -> None:
        self.is_initialized = False
```

## 实施方案

### 1. 目录结构创建
```bash
mkdir -p controllers agents core
touch controllers/__init__.py agents/__init__.py core/__init__.py
```

### 2. MaiCoreController（完整移植原逻辑）
```python
# controllers/maicore_controller.py
import asyncio
import contextlib
import time
from typing import Optional
from .base_controller import ControllerStrategy

class MaiCoreController(ControllerStrategy):
    def __init__(self):
        super().__init__()
        self._auto_send_task: Optional[asyncio.Task] = None
        self._last_response_time: float = 0.0
    
    async def initialize(self, plugin_context) -> None:
        await super().initialize(plugin_context)
        await self.start_control_loop()
    
    async def start_control_loop(self) -> None:
        if self._auto_send_task is None:
            self._auto_send_task = asyncio.create_task(
                self._auto_send_loop(), name="MaiCoreAutoSend"
            )
    
    async def _auto_send_loop(self):
        # 完全复制原plugin.py中的_auto_send_loop逻辑
        while True:
            try:
                await asyncio.sleep(self.plugin.auto_send_interval)
                current_time = time.time()
                if current_time - self._last_response_time > self.plugin.auto_send_interval:
                    await self.plugin.action_executor.execute_no_op()
                    if self.plugin.game_state.is_ready_for_next_action():
                        await self._send_state_to_maicore()
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"自动发送错误: {e}")
                await asyncio.sleep(1)
    
    async def _send_state_to_maicore(self):
        # 完全复制原plugin.py中的_send_state_to_maicore逻辑
        try:
            msg_to_maicore = self.plugin.message_builder.build_state_message(
                self.plugin.game_state, self.plugin.event_manager, self.plugin.agents_config
            )
            if not msg_to_maicore:
                await self.plugin.action_executor.execute_no_op()
                return
            await self.plugin.core.send_to_maicore(msg_to_maicore)
        except Exception as e:
            self.logger.error(f"发送状态错误: {e}")
            raise
    
    async def handle_external_message(self, message) -> None:
        # 完全复制原plugin.py中的handle_maicore_response逻辑
        self._last_response_time = time.time()
        
        if not self.plugin.mland:
            self.logger.error("MineLand环境未初始化")
            return
        
        if message.message_segment.type not in ["text", "seglist"]:
            self.logger.warning(f"不支持的消息类型: {message.message_segment.type}")
            return
        
        # 提取消息文本
        if message.message_segment.type == "seglist":
            message_json_str = None
            for seg in message.message_segment.data:
                if seg.type == "text":
                    message_json_str = seg.data.strip()
                    break
            if not message_json_str:
                return
        else:
            message_json_str = message.message_segment.data.strip()
        
        try:
            await self.plugin.action_executor.execute_maicore_action(message_json_str)
            await self._send_state_to_maicore()
        except Exception as e:
            self.logger.exception(f"执行动作错误: {e}")
    
    async def cleanup(self) -> None:
        if self._auto_send_task:
            self._auto_send_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._auto_send_task
    
    def get_mode_name(self) -> str:
        return "maicore"
```

### 3. AgentController（智能体决策循环）
```python
# controllers/agent_controller.py
import asyncio
from typing import Optional
from .base_controller import ControllerStrategy

class AgentController(ControllerStrategy):
    def __init__(self):
        super().__init__()
        self._decision_loop_task: Optional[asyncio.Task] = None
        self._report_interval = 30  # 状态报告间隔
    
    async def initialize(self, plugin_context) -> None:
        await super().initialize(plugin_context)
        await self.start_control_loop()
    
    async def start_control_loop(self) -> None:
        if self._decision_loop_task is None:
            self._decision_loop_task = asyncio.create_task(
                self._agent_decision_loop(), name="AgentDecisionLoop"
            )
    
    async def _agent_decision_loop(self):
        last_report_time = 0
        while True:
            try:
                agent = await self.plugin.agent_manager.get_current_agent()
                if not agent:
                    await asyncio.sleep(1)
                    continue
                
                if not self.plugin.game_state.is_ready_for_next_action():
                    await asyncio.sleep(0.1)
                    continue
                
                # 构建观察
                obs = self._build_observation()
                if not obs:
                    await asyncio.sleep(0.1)
                    continue
                
                # 智能体决策
                action = await agent.run(
                    obs=obs,
                    code_info=getattr(self.plugin.game_state, 'current_code_info', None),
                    done=self.plugin.game_state.current_done,
                    task_info=self._get_task_info()
                )
                
                if action:
                    await self._execute_agent_action(action)
                
                # 定期报告状态给MaiCore
                current_time = asyncio.get_event_loop().time()
                if current_time - last_report_time > self._report_interval:
                    await self._report_to_maicore()
                    last_report_time = current_time
                
                await asyncio.sleep(0.1)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"智能体决策循环错误: {e}")
                await asyncio.sleep(1)
    
    def _build_observation(self):
        if not self.plugin.game_state.current_obs:
            return None
        # 单智能体模式，取第一个观察
        return self.plugin.game_state.current_obs[0] if self.plugin.game_state.current_obs else None
    
    def _get_task_info(self):
        return {
            'goal': getattr(self.plugin.game_state, 'goal', '探索世界'),
            'step': getattr(self.plugin.game_state, 'current_step_num', 0),
            'done': getattr(self.plugin.game_state, 'current_done', False)
        }
    
    async def _execute_agent_action(self, action):
        try:
            # 转换Action为字符串格式
            if hasattr(action, 'type') and hasattr(action, 'code'):
                action_str = f'{{"type": "{action.type}", "code": "{action.code}"}}'
            else:
                action_str = str(action)
            
            await self.plugin.action_executor.execute_maicore_action(action_str)
        except Exception as e:
            self.logger.error(f"执行智能体动作失败: {e}")
    
    async def _report_to_maicore(self):
        try:
            msg = self.plugin.message_builder.build_state_message(
                self.plugin.game_state, self.plugin.event_manager, self.plugin.agents_config
            )
            if msg:
                await self.plugin.core.send_to_maicore(msg)
        except Exception as e:
            self.logger.error(f"报告状态失败: {e}")
    
    async def handle_external_message(self, message) -> None:
        # 将MaiCore指令转发给智能体
        agent = await self.plugin.agent_manager.get_current_agent()
        if not agent:
            return
        
        # 提取消息内容
        content = None
        if message.message_segment.type == "text":
            content = message.message_segment.data.strip()
        elif message.message_segment.type == "seglist":
            for seg in message.message_segment.data:
                if seg.type == "text":
                    content = seg.data.strip()
                    break
        
        if content:
            await agent.receive_command(content, priority="high")
    
    async def cleanup(self) -> None:
        if self._decision_loop_task:
            self._decision_loop_task.cancel()
            try:
                await self._decision_loop_task
            except asyncio.CancelledError:
                pass
    
    def get_mode_name(self) -> str:
        return "agent"
```

### 4. AgentManager（智能体管理）
```python
# core/agent_manager.py
from typing import Dict, Any, Optional, Type, List
import logging

class AgentManager:
    def __init__(self):
        self._agent_registry = {}
        self._current_agent = None
        self._agent_configs = {}
        self.logger = logging.getLogger(__name__)
    
    async def initialize(self, config: Dict[str, Any]) -> None:
        await self._register_builtin_agents()
        self._agent_configs = config.get('agents', {})
        
        default_type = config.get('default_agent_type', 'simple')
        if default_type in self._agent_registry:
            await self.switch_agent(default_type)
    
    async def _register_builtin_agents(self):
        # 注册Alex智能体（处理导入错误）
        try:
            from ..agents.alex_adapter import AlexAgentAdapter
            self._agent_registry['alex'] = AlexAgentAdapter
            self.logger.info("已注册Alex智能体")
        except ImportError as e:
            self.logger.warning(f"Alex智能体不可用: {e}")
        
        # 注册Simple智能体
        try:
            from ..agents.simple_agent import SimpleAgent
            self._agent_registry['simple'] = SimpleAgent
            self.logger.info("已注册Simple智能体")
        except ImportError as e:
            self.logger.warning(f"Simple智能体不可用: {e}")
    
    async def switch_agent(self, agent_type: str, config: Optional[Dict] = None) -> None:
        if agent_type not in self._agent_registry:
            raise ValueError(f"未知智能体类型: {agent_type}")
        
        if self._current_agent:
            await self._current_agent.cleanup()
        
        agent_config = config or self._agent_configs.get(agent_type, {})
        agent_class = self._agent_registry[agent_type]
        self._current_agent = agent_class()
        await self._current_agent.initialize(agent_config)
        
        self.logger.info(f"已切换到智能体: {agent_type}")
    
    async def get_current_agent(self):
        return self._current_agent
    
    async def cleanup(self) -> None:
        if self._current_agent:
            await self._current_agent.cleanup()
```

### 5. AlexAdapter（处理同步/异步兼容）
```python
# agents/alex_adapter.py
import asyncio
from typing import Dict, Any, Optional
from .base_agent import BaseAgent

try:
    from mineland.alex import Alex
    from mineland import Action
    ALEX_AVAILABLE = True
except ImportError:
    ALEX_AVAILABLE = False
    Alex = None
    Action = Any

class AlexAgentAdapter(BaseAgent):
    def __init__(self):
        super().__init__()
        if not ALEX_AVAILABLE:
            raise ImportError("mineland.alex不可用")
        self.alex = None
        self.maicore_command = None
        self.command_priority = "normal"
    
    async def initialize(self, config: Dict[str, Any]) -> None:
        alex_config = {
            'personality': config.get('personality', 'explorer'),
            'llm_model_name': config.get('llm_model', 'gpt-4-turbo'),
            'vlm_model_name': config.get('vlm_model', 'gpt-4-turbo'),
            'bot_name': config.get('bot_name', 'Mai'),
            'temperature': config.get('temperature', 0.1),
            'save_path': config.get('save_path', './storage/alex'),
            'load_path': config.get('load_path', './load/alex'),
        }
        self.alex = Alex(**alex_config)
        await super().initialize(config)
    
    async def run(self, obs: Dict[str, Any], **kwargs) -> Optional[Action]:
        await super().run(obs, **kwargs)
        
        # 增强task_info
        task_info = kwargs.get('task_info', {})
        if self.maicore_command:
            task_info['maicore_instruction'] = self.maicore_command
            task_info['instruction_priority'] = self.command_priority
        
        # 在线程池中运行同步的Alex.run方法
        loop = asyncio.get_event_loop()
        try:
            action = await loop.run_in_executor(
                None, 
                lambda: self.alex.run(
                    obs,
                    kwargs.get('code_info'),
                    kwargs.get('done'),
                    task_info,
                    verbose=False
                )
            )
            
            # 清理高优先级指令
            if self.command_priority == "high":
                self.maicore_command = None
                
            return action
        except Exception as e:
            self.logger.error(f"Alex执行错误: {e}")
            return None
    
    async def reset(self) -> None:
        self.maicore_command = None
        self.command_priority = "normal"
    
    async def receive_command(self, command: str, priority: str = "normal") -> None:
        self.maicore_command = command
        self.command_priority = priority
    
    def get_agent_type(self) -> str:
        return "alex"
```

### 6. SimpleAgent（轻量级实现）
```python
# agents/simple_agent.py
from typing import Dict, Any, Optional, List
from .base_agent import BaseAgent

try:
    from langchain_openai import ChatOpenAI
    from langchain_core.messages import HumanMessage, SystemMessage
    from mineland import Action
    LANGCHAIN_AVAILABLE = True
except ImportError:
    LANGCHAIN_AVAILABLE = False
    ChatOpenAI = None
    Action = Any

class SimpleAgent(BaseAgent):
    def __init__(self):
        super().__init__()
        if not LANGCHAIN_AVAILABLE:
            raise ImportError("langchain不可用")
        self.llm = None
        self.memory = []
        self.maicore_command = None
        self.max_memory = 5
    
    async def initialize(self, config: Dict[str, Any]) -> None:
        self.llm = ChatOpenAI(
            model=config.get('model', 'gpt-3.5-turbo'),
            temperature=config.get('temperature', 0.7),
            max_tokens=config.get('max_tokens', 512)
        )
        self.max_memory = config.get('max_memory', 5)
        await super().initialize(config)
    
    async def run(self, obs: Dict[str, Any], **kwargs) -> Optional[Action]:
        await super().run(obs, **kwargs)
        
        try:
            context = self._build_context(obs, kwargs)
            messages = [
                SystemMessage(content=self._get_system_prompt()),
                HumanMessage(content=context)
            ]
            
            response = await self.llm.ainvoke(messages)
            action_code = self._parse_action(response.content)
            
            # 更新记忆
            self.memory.append({'obs': str(obs)[:100], 'action': action_code})
            if len(self.memory) > self.max_memory:
                self.memory.pop(0)
            
            return Action(type="NEW", code=action_code)
            
        except Exception as e:
            self.logger.error(f"Simple智能体错误: {e}")
            return Action(type="NEW", code="await bot.no_op()")
    
    def _build_context(self, obs: Dict, kwargs: Dict) -> str:
        parts = [f"观察: {obs}"]
        
        if self.memory:
            parts.append(f"记忆: {self.memory[-2:]}")
        
        if self.maicore_command:
            parts.append(f"指令: {self.maicore_command}")
        
        task_info = kwargs.get('task_info')
        if task_info:
            parts.append(f"任务: {task_info}")
        
        return "\n".join(parts)
    
    def _get_system_prompt(self) -> str:
        return """你是Minecraft智能体。根据观察生成动作代码。
动作格式：await bot.方法名(参数)
例如：await bot.move_forward(1)、await bot.dig_down()、await bot.no_op()
只返回一行代码，不要解释。"""
    
    def _parse_action(self, response: str) -> str:
        for line in response.strip().split('\n'):
            line = line.strip()
            if line.startswith('await bot.'):
                return line
        return "await bot.no_op()"
    
    async def reset(self) -> None:
        self.memory.clear()
        self.maicore_command = None
    
    async def receive_command(self, command: str, priority: str = "normal") -> None:
        self.maicore_command = command
    
    def get_agent_type(self) -> str:
        return "simple"
```

### 7. plugin.py重构要点
```python
# 关键修改点
class MinecraftPlugin(BasePlugin):
    def __init__(self, core: AmaidesuCore, plugin_config: Dict[str, Any]):
        super().__init__(core, plugin_config)
        # 保持所有现有配置...
        
        # 新增组件
        from .core.agent_manager import AgentManager
        from .controllers.maicore_controller import MaiCoreController
        from .controllers.agent_controller import AgentController
        
        self.agent_manager = AgentManager()
        
        # 根据配置选择控制器
        control_mode = plugin_config.get('control_mode', 'maicore')
        if control_mode == "maicore":
            self.mode_controller = MaiCoreController()
        elif control_mode == "agent":
            self.mode_controller = AgentController()
        else:
            raise ValueError(f"不支持的控制模式: {control_mode}")
        
        # 移除原有的自动发送任务相关属性
        # self._auto_send_task = None
        # self._last_response_time = 0.0
    
    async def setup(self):
        # 保持MineLand初始化逻辑不变...
        
        # 初始化智能体管理器
        agent_config = {
            'default_agent_type': self.plugin_config.get('current_agent', 'simple'),
            'agents': self.plugin_config.get('agents', {})
        }
        await self.agent_manager.initialize(agent_config)
        
        # 初始化控制器
        await self.mode_controller.initialize(self)
        
        # 注册消息处理器
        self.core.register_websocket_handler("*", self.handle_external_message)
    
    async def handle_external_message(self, message):
        """委托给控制器处理"""
        await self.mode_controller.handle_external_message(message)
    
    # 移除原有的handle_maicore_response和_auto_send_loop方法
    
    async def cleanup(self):
        # 清理控制器和智能体管理器
        if hasattr(self, 'mode_controller'):
            await self.mode_controller.cleanup()
        if hasattr(self, 'agent_manager'):
            await self.agent_manager.cleanup()
        # 保持MineLand清理逻辑...
```

## 配置文件示例
```toml
[minecraft]
# 现有配置保持不变...
control_mode = "maicore"  # 或 "agent"
current_agent = "simple"  # 或 "alex"

[minecraft.agents.alex]
personality = "explorer"
llm_model = "gpt-4-turbo"

[minecraft.agents.simple]
model = "gpt-3.5-turbo"
max_memory = 5
```

## 执行注意事项
1. 先创建所有目录和__init__.py文件
2. 按顺序实现：base_controller → controllers → base_agent → agents → agent_manager → plugin重构
3. 测试时先用maicore模式验证现有功能完整性
4. Alex智能体需要额外依赖，Simple智能体作为fallback
5. 注意异步/同步方法的正确调用方式 