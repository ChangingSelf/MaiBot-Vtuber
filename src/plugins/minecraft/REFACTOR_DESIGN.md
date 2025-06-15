# Minecraft插件智能体模式重构设计文档

## 1. 需求分析

### 1.1 核心需求
- **模式切换**：在现有MaiCore通信模式和新的智能体自主决策模式之间动态切换
- **智能体接口**：抽象智能体接口，支持多种智能体实现的热插拔
- **分层决策**：上层(MaiCore)负责高级策略，下层(智能体)负责具体执行
- **向后兼容**：不破坏现有功能，保持与MaiCore的完整兼容性

### 1.2 补充需求
- **运行时切换**：支持不重启插件的模式和智能体切换
- **状态同步**：确保模式切换时游戏状态的连续性
- **性能优化**：智能体模式的计算开销管理
- **配置热更新**：智能体参数的动态调整
- **错误恢复**：智能体异常时的fallback机制

### 1.3 智能体需求
- **Alex智能体适配**：集成MineLand的Alex智能体
- **简单智能体实现**：基于LLM的轻量级智能体
- **记忆和规划**：基础的上下文记忆和行动规划能力
- **指令接收**：可选地接收来自MaiCore的高级指令

## 2. 架构设计

### 2.1 整体架构图

```
MinecraftPlugin
├── mode_controller: ControllerStrategy      # 控制策略
├── agent_manager: AgentManager              # 智能体管理器
├── config_manager: ConfigManager            # 配置管理器
├── communication: CommunicationLayer        # 通信层
├── [现有组件复用]
│   ├── game_state: MinecraftGameState
│   ├── event_manager: MinecraftEventManager
│   ├── action_executor: MinecraftActionExecutor
│   └── message_builder: MinecraftMessageBuilder
└── [新增组件]
    ├── mode_switcher: ModeSwitcher          # 模式切换器
    └── state_synchronizer: StateSynchronizer # 状态同步器
```

### 2.2 核心接口设计

#### 2.2.1 控制策略接口
```python
class ControllerStrategy(ABC):
    @abstractmethod
    async def initialize(self, plugin_context: 'MinecraftPlugin') -> None:
        """初始化控制器"""
        pass
    
    @abstractmethod
    async def start_control_loop(self) -> None:
        """启动控制循环"""
        pass
    
    @abstractmethod
    async def handle_external_message(self, message: MessageBase) -> None:
        """处理外部消息"""
        pass
    
    @abstractmethod
    async def cleanup(self) -> None:
        """清理资源"""
        pass
    
    @abstractmethod
    def get_mode_name(self) -> str:
        """获取模式名称"""
        pass
```

#### 2.2.2 智能体接口
```python
class BaseAgent(ABC):
    @abstractmethod
    async def initialize(self, config: Dict[str, Any]) -> None:
        """初始化智能体"""
        pass
    
    @abstractmethod
    async def run(self, 
                  obs: Dict[str, Any], 
                  code_info: Optional[Dict] = None,
                  done: Optional[bool] = None, 
                  task_info: Optional[Dict] = None,
                  maicore_command: Optional[str] = None) -> Optional[Action]:
        """执行一步决策"""
        pass
    
    @abstractmethod
    async def reset(self) -> None:
        """重置智能体状态"""
        pass
    
    @abstractmethod
    async def receive_command(self, command: str, priority: str = "normal") -> None:
        """接收上层指令"""
        pass
    
    @abstractmethod
    async def get_status(self) -> Dict[str, Any]:
        """获取智能体状态"""
        pass
    
    @abstractmethod
    def get_agent_type(self) -> str:
        """获取智能体类型"""
        pass
```

#### 2.2.3 智能体管理器接口
```python
class AgentManager:
    async def initialize(self, config: Dict[str, Any]) -> None
    async def register_agent_type(self, name: str, agent_class: Type[BaseAgent]) -> None
    async def create_agent(self, agent_type: str, config: Dict[str, Any]) -> BaseAgent
    async def switch_agent(self, agent_type: str, config: Optional[Dict] = None) -> None
    async def get_current_agent(self) -> Optional[BaseAgent]
    async def get_available_agents(self) -> List[str]
    async def cleanup(self) -> None
```

## 3. 详细实施步骤

### Phase 1: 架构重构准备 (1-2天)

#### 3.1.1 创建基础接口文件
```bash
mkdir -p src/plugins/minecraft/controllers
mkdir -p src/plugins/minecraft/agents
mkdir -p src/plugins/minecraft/core
```

**文件创建清单：**
- `controllers/__init__.py` - 控制器模块
- `controllers/base_controller.py` - 控制策略基类
- `controllers/maicore_controller.py` - MaiCore控制器
- `controllers/agent_controller.py` - 智能体控制器
- `agents/__init__.py` - 智能体模块  
- `agents/base_agent.py` - 智能体基类
- `agents/alex_adapter.py` - Alex适配器
- `agents/simple_agent.py` - 简单智能体
- `core/agent_manager.py` - 智能体管理器
- `core/mode_switcher.py` - 模式切换器
- `core/config_manager.py` - 配置管理器

#### 3.1.2 重构现有plugin.py
1. 提取现有逻辑到MaiCoreController
2. 修改MinecraftPlugin构造函数支持策略注入
3. 添加模式切换相关方法

### Phase 2: 控制器实现 (2-3天)

#### 3.2.1 实现MaiCoreController
```python
# controllers/maicore_controller.py
class MaiCoreController(ControllerStrategy):
    def __init__(self):
        self.plugin: Optional['MinecraftPlugin'] = None
        self._auto_send_task: Optional[asyncio.Task] = None
        self._last_response_time: float = 0.0
    
    async def initialize(self, plugin_context: 'MinecraftPlugin') -> None:
        self.plugin = plugin_context
        # 启动自动发送任务
        self._auto_send_task = asyncio.create_task(
            self._auto_send_loop(), 
            name="MaiCoreAutoSend"
        )
    
    async def _auto_send_loop(self):
        # 移植原有的自动发送循环逻辑
        pass
    
    async def handle_external_message(self, message: MessageBase) -> None:
        # 移植原有的MaiCore响应处理逻辑
        pass
```

#### 3.2.2 实现AgentController
```python
# controllers/agent_controller.py
class AgentController(ControllerStrategy):
    def __init__(self):
        self.plugin: Optional['MinecraftPlugin'] = None
        self.agent_manager: Optional[AgentManager] = None
        self._decision_loop_task: Optional[asyncio.Task] = None
        self._maicore_integration_enabled: bool = True
    
    async def initialize(self, plugin_context: 'MinecraftPlugin') -> None:
        self.plugin = plugin_context
        self.agent_manager = plugin_context.agent_manager
        
        # 启动智能体决策循环
        self._decision_loop_task = asyncio.create_task(
            self._agent_decision_loop(),
            name="AgentDecisionLoop"
        )
    
    async def _agent_decision_loop(self):
        while True:
            try:
                # 获取当前智能体
                agent = await self.agent_manager.get_current_agent()
                if not agent:
                    await asyncio.sleep(1)
                    continue
                
                # 获取游戏状态
                if not self.plugin.game_state.is_ready_for_next_action():
                    await asyncio.sleep(0.1)
                    continue
                
                # 构建观察数据
                obs = self._build_observation()
                
                # 智能体决策
                action = await agent.run(
                    obs,
                    code_info=self.plugin.game_state.get_latest_code_info(),
                    done=self.plugin.game_state.current_done,
                    task_info=self.plugin.game_state.get_task_info()
                )
                
                if action:
                    # 执行动作
                    await self.plugin.action_executor.execute_action(action)
                
                # 可选：向MaiCore报告状态
                if self._maicore_integration_enabled:
                    await self._report_to_maicore()
                
                await asyncio.sleep(0.1)
                
            except Exception as e:
                self.plugin.logger.error(f"智能体决策循环错误: {e}")
                await asyncio.sleep(1)
```

### Phase 3: 智能体管理器实现 (2-3天)

#### 3.3.1 实现AgentManager
```python
# core/agent_manager.py
class AgentManager:
    def __init__(self):
        self._agent_registry: Dict[str, Type[BaseAgent]] = {}
        self._current_agent: Optional[BaseAgent] = None
        self._agent_configs: Dict[str, Dict[str, Any]] = {}
        self.logger = logging.getLogger(__name__)
    
    async def initialize(self, config: Dict[str, Any]) -> None:
        # 注册内置智能体类型
        await self._register_builtin_agents()
        
        # 加载配置
        self._agent_configs = config.get('agents', {})
        
        # 创建默认智能体
        default_agent_type = config.get('default_agent_type', 'alex')
        if default_agent_type in self._agent_registry:
            await self.switch_agent(default_agent_type)
    
    async def _register_builtin_agents(self):
        from ..agents.alex_adapter import AlexAgentAdapter
        from ..agents.simple_agent import SimpleAgent
        
        await self.register_agent_type('alex', AlexAgentAdapter)
        await self.register_agent_type('simple', SimpleAgent)
    
    async def switch_agent(self, agent_type: str, config: Optional[Dict] = None) -> None:
        if agent_type not in self._agent_registry:
            raise ValueError(f"未知的智能体类型: {agent_type}")
        
        # 清理当前智能体
        if self._current_agent:
            await self._current_agent.cleanup()
        
        # 创建新智能体
        agent_config = config or self._agent_configs.get(agent_type, {})
        self._current_agent = await self.create_agent(agent_type, agent_config)
        
        self.logger.info(f"已切换到智能体: {agent_type}")
```

#### 3.3.2 实现ModeSwitcher
```python
# core/mode_switcher.py
class ModeSwitcher:
    def __init__(self, plugin: 'MinecraftPlugin'):
        self.plugin = plugin
        self.logger = logging.getLogger(__name__)
    
    async def switch_mode(self, new_mode: str, **kwargs) -> bool:
        """切换控制模式"""
        try:
            current_mode = self.plugin.mode_controller.get_mode_name()
            if current_mode == new_mode:
                self.logger.info(f"已经处于{new_mode}模式")
                return True
            
            # 保存当前状态
            current_state = await self._save_current_state()
            
            # 清理当前控制器
            await self.plugin.mode_controller.cleanup()
            
            # 创建新控制器
            if new_mode == "maicore":
                new_controller = MaiCoreController()
            elif new_mode == "agent":
                new_controller = AgentController()
            else:
                raise ValueError(f"不支持的模式: {new_mode}")
            
            # 初始化新控制器
            await new_controller.initialize(self.plugin)
            
            # 恢复状态
            await self._restore_state(current_state)
            
            # 更新插件引用
            self.plugin.mode_controller = new_controller
            
            self.logger.info(f"成功从{current_mode}模式切换到{new_mode}模式")
            return True
            
        except Exception as e:
            self.logger.error(f"模式切换失败: {e}")
            return False
```

### Phase 4: 智能体实现 (3-4天)

#### 3.4.1 实现AlexAgentAdapter
```python
# agents/alex_adapter.py
from mineland.alex import Alex
from mineland import Action

class AlexAgentAdapter(BaseAgent):
    def __init__(self):
        self.alex: Optional[Alex] = None
        self.config: Dict[str, Any] = {}
        self.maicore_command: Optional[str] = None
        self.command_priority: str = "normal"
        self.logger = logging.getLogger(__name__)
    
    async def initialize(self, config: Dict[str, Any]) -> None:
        self.config = config
        
        # 初始化Alex智能体
        alex_config = {
            'personality': config.get('personality', 'None'),
            'llm_model_name': config.get('llm_model', 'gpt-4-turbo'),
            'vlm_model_name': config.get('vlm_model', 'gpt-4-turbo'),
            'bot_name': config.get('bot_name', 'Mai'),
            'temperature': config.get('temperature', 0.1),
            'save_path': config.get('save_path', './storage'),
            'load_path': config.get('load_path', './load'),
        }
        
        self.alex = Alex(**alex_config)
        self.logger.info("Alex智能体适配器初始化完成")
    
    async def run(self, obs: Dict[str, Any], **kwargs) -> Optional[Action]:
        if not self.alex:
            raise RuntimeError("Alex智能体未初始化")
        
        # 增强task_info以包含MaiCore指令
        task_info = kwargs.get('task_info', {})
        if self.maicore_command and self.command_priority == "high":
            task_info['maicore_instruction'] = self.maicore_command
            task_info['instruction_priority'] = self.command_priority
        
        # 调用Alex的run方法
        try:
            action = self.alex.run(
                obs,
                kwargs.get('code_info'),
                kwargs.get('done'),
                task_info,
                verbose=self.config.get('verbose', False)
            )
            
            # 清理已处理的指令
            if self.maicore_command and self.command_priority == "high":
                self.maicore_command = None
                
            return action
            
        except Exception as e:
            self.logger.error(f"Alex智能体执行错误: {e}")
            return None
    
    async def receive_command(self, command: str, priority: str = "normal") -> None:
        self.maicore_command = command
        self.command_priority = priority
        self.logger.info(f"收到MaiCore指令[{priority}]: {command}")
```

#### 3.4.2 实现SimpleAgent
```python
# agents/simple_agent.py  
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from mineland import Action

class SimpleAgent(BaseAgent):
    def __init__(self):
        self.llm: Optional[ChatOpenAI] = None
        self.config: Dict[str, Any] = {}
        self.memory: List[Dict] = []
        self.current_goal: Optional[str] = None
        self.maicore_command: Optional[str] = None
        self.max_memory_size: int = 10
        self.logger = logging.getLogger(__name__)
    
    async def initialize(self, config: Dict[str, Any]) -> None:
        self.config = config
        self.max_memory_size = config.get('max_memory', 10)
        
        # 初始化LLM
        self.llm = ChatOpenAI(
            model=config.get('model', 'gpt-3.5-turbo'),
            temperature=config.get('temperature', 0.7),
            max_tokens=config.get('max_tokens', 512)
        )
        
        self.logger.info("简单智能体初始化完成")
    
    async def run(self, obs: Dict[str, Any], **kwargs) -> Optional[Action]:
        try:
            # 构建上下文
            context = self._build_context(obs, kwargs)
            
            # LLM推理
            messages = [
                SystemMessage(content=self._get_system_prompt()),
                HumanMessage(content=context)
            ]
            
            response = await self.llm.ainvoke(messages)
            
            # 解析动作
            action_code = self._parse_action_from_response(response.content)
            
            # 更新记忆
            self._update_memory(obs, action_code)
            
            return Action(type=Action.NEW, code=action_code)
            
        except Exception as e:
            self.logger.error(f"简单智能体执行错误: {e}")
            return Action(type=Action.NEW, code="await bot.no_op()")
    
    def _build_context(self, obs: Dict, kwargs: Dict) -> str:
        context_parts = []
        
        # 当前观察
        context_parts.append(f"当前观察: {obs}")
        
        # 历史记忆
        if self.memory:
            recent_memory = self.memory[-3:]  # 最近3次记忆
            context_parts.append(f"最近记忆: {recent_memory}")
        
        # MaiCore指令
        if self.maicore_command:
            context_parts.append(f"上层指令: {self.maicore_command}")
        
        # 当前目标
        if self.current_goal:
            context_parts.append(f"当前目标: {self.current_goal}")
        
        return "\n\n".join(context_parts)
    
    def _get_system_prompt(self) -> str:
        return """你是一个Minecraft智能体。根据当前观察和上下文，生成合适的动作代码。
        
动作代码应该是Python异步函数调用，例如：
- await bot.move_forward(1)
- await bot.dig_down()  
- await bot.place_block("dirt")
- await bot.no_op()

请直接返回一行动作代码，不要解释。"""
```

### Phase 5: 插件集成 (2-3天)

#### 3.5.1 重构plugin.py主类
```python
# plugin.py (重构后的关键部分)
class MinecraftPlugin(BasePlugin):
    def __init__(self, core: AmaidesuCore, plugin_config: Dict[str, Any]):
        super().__init__(core, plugin_config)
        # ... 现有配置保持不变 ...
        
        # 新增组件
        self.config_manager = ConfigManager(plugin_config)
        self.agent_manager = AgentManager()
        self.mode_switcher = ModeSwitcher(self)
        
        # 控制策略 (根据配置初始化)
        control_mode = self.config_manager.get_control_mode()
        if control_mode == "maicore":
            self.mode_controller = MaiCoreController()
        elif control_mode == "agent":
            self.mode_controller = AgentController()
        else:
            raise ValueError(f"不支持的控制模式: {control_mode}")
    
    async def setup(self):
        """重构后的初始化方法"""
        await super().setup()
        
        # 初始化MineLand环境 (保持现有逻辑)
        await self._initialize_mineland()
        
        # 初始化智能体管理器
        await self.agent_manager.initialize(
            self.config_manager.get_agent_config()
        )
        
        # 初始化控制器
        await self.mode_controller.initialize(self)
        
        # 注册消息处理器
        self.core.register_websocket_handler("*", self.handle_external_message)
        
        # 注册模式切换API
        self._register_mode_switch_handlers()
    
    async def handle_external_message(self, message: MessageBase):
        """委托给当前控制器处理"""
        await self.mode_controller.handle_external_message(message)
    
    def _register_mode_switch_handlers(self):
        """注册模式切换相关的API处理器"""
        # 通过MaiCore的API系统注册切换接口
        pass
```

#### 3.5.2 配置文件扩展
```python
# 在config.toml中添加新的配置节
[minecraft]
# 控制模式: maicore | agent  
control_mode = "agent"
# 是否允许运行时切换模式
allow_mode_switching = true

# 智能体管理配置
[minecraft.agent_manager]
default_agent_type = "alex"
agent_switch_timeout = 30  # 秒

# MaiCore集成配置 (在agent模式下)
[minecraft.maicore_integration]
# 是否在agent模式下接受maicore指令
accept_commands = true
# 状态报告间隔
status_report_interval = 60  # 秒
# 指令优先级: high | normal | low
default_command_priority = "normal"

# Alex智能体配置
[minecraft.agents.alex]
personality = "explorer"
llm_model = "gpt-4-turbo"
vlm_model = "gpt-4-turbo"
bot_name = "Mai"
temperature = 0.1
verbose = false
save_path = "./storage/alex"
load_path = "./load/alex"

# 简单智能体配置
[minecraft.agents.simple]
model = "gpt-3.5-turbo"
temperature = 0.7
max_tokens = 512
max_memory = 10
```
