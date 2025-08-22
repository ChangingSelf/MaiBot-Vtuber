## 重构方案（已完成）

### 1. 整体架构调整

**当前架构问题：**
- 自定义的LLMPlanner和AgentRunner过于复杂
- 工具调用逻辑分散在多个文件中
- 缺乏标准的Agent框架支持
- 未充分利用LCEL的优势

**重构目标：**
- 使用LangChain Agent替代自定义的LLMPlanner
- 充分利用LCEL (LangChain Expression Language) 构建执行链
- 将MCP工具转换为LangChain Tool，供LangChain Agent使用
- 简化代码结构，提高可维护性
- 使用LangChain内置的记忆管理机制
- 更新README

### 2. 核心组件重构

#### 2.1 MCP工具适配器
```python
# 新建: src/plugins/maicraft/mcp/mcp_tool_adapter.py
from typing import Dict, List, Any, Optional
from langchain.schema import BaseTool
from langchain.tools import tool
from pydantic import BaseModel, Field
from src.utils.logger import get_logger

class MCPToolAdapter:
    """将MCP工具转换为LangChain Tool"""
    
    def __init__(self, mcp_client):
        self.mcp_client = mcp_client
        self.logger = get_logger("MCPToolAdapter")
    
    async def create_langchain_tools(self) -> List[BaseTool]:
        """将MCP工具转换为LangChain Tool列表"""
        # 获取MCP工具元数据并转换为LangChain工具
        # 包含错误处理和日志记录
        pass
    
    def _create_langchain_tool(self, name: str, description: str, schema: Dict) -> BaseTool:
        """创建单个LangChain工具"""
        # 动态创建Pydantic模型和工具执行函数
        # 包含详细的错误处理和日志记录
        pass
    
    def _create_tool_model(self, name: str, schema: Dict) -> type:
        """根据MCP schema动态创建Pydantic模型"""
        # 根据JSON schema动态生成Pydantic模型
        pass
```

#### 2.2 主Agent（简化版，使用chains）
```python
# 新建: src/plugins/maicraft/agent/agent.py
from typing import Dict, List, Any, Optional
from langchain.agents import AgentExecutor, create_react_agent
from langchain_openai import ChatOpenAI
from langchain.schema import BaseTool
from langchain.memory import ConversationBufferMemory
from src.utils.logger import get_logger
from ..chains.base import BaseChain
from ..chains.task_planning_chain import TaskPlanningChain
from ..chains.goal_proposal_chain import GoalProposalChain
from ..chains.memory_chain import MemoryChain
from ..chains.error_handling_chain import ErrorHandlingChain

class MaicraftAgent:
    """基于LangChain Agent的Minecraft Agent（简化版）"""
    
    def __init__(self, config: Dict[str, Any], mcp_client):
        self.config = config
        self.mcp_client = mcp_client
        self.logger = get_logger("MaicraftAgent")
        
        # 初始化LLM和工具适配器
        self.llm = self._create_llm()
        self.tool_adapter = MCPToolAdapter(mcp_client)
        
        # 延迟初始化
        self.tools: Optional[List[BaseTool]] = None
        self.agent_executor: Optional[AgentExecutor] = None
        self.memory: Optional[ConversationBufferMemory] = None
        
        # LCEL链组件
        self.task_planning_chain: Optional[TaskPlanningChain] = None
        self.goal_proposal_chain: Optional[GoalProposalChain] = None
        self.memory_chain: Optional[MemoryChain] = None
        self.error_handling_chain: Optional[ErrorHandlingChain] = None
    
    def _create_llm(self) -> ChatOpenAI:
        """创建LLM实例"""
        # 根据配置创建ChatOpenAI实例
        pass
    
    async def initialize(self):
        """异步初始化"""
        # 获取工具、创建记忆、构建Agent和LCEL链
        pass
    
    async def plan_and_execute(self, user_input: str) -> Dict[str, Any]:
        """规划并执行任务（使用LCEL链）"""
        # 使用任务规划链执行任务
        pass
    
    async def propose_next_goal(self) -> Optional[str]:
        """提议下一个目标"""
        # 使用目标提议链生成目标
        pass
    
    def get_chat_history(self) -> List[str]:
        """获取聊天历史"""
        # 使用记忆链获取历史
        pass
    
    def clear_memory(self):
        """清除记忆"""
        # 使用记忆链清除记忆
        pass
```

#### 2.3 LCEL链设计
```python
# 新建: src/plugins/maicraft/chains/base.py
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from langchain_core.runnables import Runnable

class BaseChain(ABC):
    """LCEL链基类"""
    
    @abstractmethod
    def build(self) -> Runnable:
        """构建LCEL链"""
        pass
    
    @abstractmethod
    async def execute(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """执行链"""
        pass

# 新建: src/plugins/maicraft/chains/task_planning_chain.py
class TaskPlanningChain(BaseChain):
    """任务规划链：输入预处理 -> Agent执行 -> 输出后处理"""
    def build(self) -> Runnable:
        # 构建任务规划LCEL链
        pass
    
    async def execute(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        # 执行任务规划
        pass

# 新建: src/plugins/maicraft/chains/goal_proposal_chain.py
class GoalProposalChain(BaseChain):
    """目标提议链：分析上下文 -> 生成目标 -> 验证可行性"""
    def build(self) -> Runnable:
        # 构建目标提议LCEL链
        pass
    
    async def execute(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        # 执行目标提议
        pass

# 新建: src/plugins/maicraft/chains/memory_chain.py
class MemoryChain(BaseChain):
    """记忆管理链：加载记忆 -> 更新记忆 -> 保存记忆"""
    def build(self) -> Runnable:
        # 构建记忆管理LCEL链
        pass
    
    async def execute(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        # 执行记忆管理
        pass

# 新建: src/plugins/maicraft/chains/error_handling_chain.py
class ErrorHandlingChain(BaseChain):
    """错误处理链：错误检测 -> 错误恢复 -> 错误报告"""
    def build(self) -> Runnable:
        # 构建错误处理LCEL链
        pass
    
    async def execute(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        # 执行错误处理
        pass
```

#### 2.3 简化的AgentRunner
```python
# 修改: src/plugins/maicraft/agent/runner.py
from typing import Dict, Any, Optional
import asyncio
from src.utils.logger import get_logger

class AgentRunner:
    """简化的Agent运行器，专注于任务调度"""
    
    def __init__(self, core, mcp_client, agent, agent_cfg: Dict[str, Any]):
        self.core = core
        self.mcp_client = mcp_client
        self.agent = agent
        self.agent_cfg = agent_cfg
        self.logger = get_logger("AgentRunner")
        
        # 任务队列和运行状态
        self.task_queue = asyncio.Queue()
        self.running = False
        self._task = None
        
        # 配置参数
        self.tick_seconds = float(agent_cfg.get("tick_seconds", 8.0))
        self.report_each_step = bool(agent_cfg.get("report_each_step", True))
    
    async def start(self):
        """启动Agent运行器"""
        # 启动运行循环
        pass
    
    async def stop(self):
        """停止Agent运行器"""
        # 停止运行循环
        pass
    
    async def _run_loop(self):
        """主运行循环"""
        # 处理任务队列和自主目标提议
        pass
    
    async def _process_task(self, task: Dict[str, Any]):
        """处理任务"""
        # 使用Agent执行任务并报告结果
        pass
    
    async def _propose_and_execute_goal(self):
        """提议并执行目标"""
        # 使用Agent提议目标并执行
        pass
    
    async def _report_result(self, result: Dict[str, Any], source: str):
        """报告执行结果"""
        # 格式化并发送结果到核心系统
        pass
    
    async def handle_message(self, message: Dict[str, Any]):
        """处理外部消息"""
        # 提取用户输入并添加到任务队列
        pass
    
    def _extract_user_input(self, message: Dict[str, Any]) -> Optional[str]:
        """从消息中提取用户输入"""
        # 根据消息类型提取输入内容
        pass
```

### 3. 文件结构调整

```
src/plugins/maicraft/
├── plugin.py                    # 主插件文件（简化）
├── config.py                   # 配置验证模块（新增）
├── mcp/
│   ├── client.py               # 保持不变
│   └── mcp_tool_adapter.py     # MCP工具适配器
├── agent/                     
│   ├── __init__.py
│   ├── agent.py               # 主Agent（简化版）
│   ├── runner.py              # 简化的任务调度器
│   └── task_queue.py          # 保持不变
├── chains/                    # LCEL链模块
│   ├── __init__.py
│   ├── base.py                # 基础链类
│   ├── task_planning_chain.py # 任务规划链
│   ├── goal_proposal_chain.py # 目标提议链
│   ├── memory_chain.py        # 记忆管理链
│   └── error_handling_chain.py # 错误处理链
└── config-template.toml       # 更新配置
```

**chains目录设计说明：**
- **base.py**: 定义基础链类和通用接口
- **task_planning_chain.py**: 任务规划和执行链
- **goal_proposal_chain.py**: 目标提议和生成链  
- **memory_chain.py**: 记忆管理和上下文链
- **error_handling_chain.py**: 错误处理和恢复链

### 4. 配置优化

#### 4.1 配置结构
```toml
# 优化后的配置结构
[llm]
model = "gpt-4o-mini"
api_key = ""
base_url = "https://api.siliconflow.cn/v1"
temperature = 0.2

[agent]
enabled = true
session_id = "maicraft_default"
max_steps = 50
tick_seconds = 8.0
report_each_step = true

# LangChain特定配置
[langchain]
max_token_limit = 4000
verbose = false
early_stopping_method = "generate"
handle_parsing_errors = true
```

#### 4.2 配置验证
```python
# 新建: src/plugins/maicraft/config.py
from pydantic import BaseModel, Field, validator
from typing import Optional

class LLMConfig(BaseModel):
    model: str = Field(default="gpt-4o-mini")
    api_key: Optional[str] = Field(default=None)
    base_url: Optional[str] = Field(default=None)
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)

class AgentConfig(BaseModel):
    enabled: bool = Field(default=True)
    session_id: str = Field(default="maicraft_default")
    max_steps: int = Field(default=50, ge=1, le=100)
    tick_seconds: float = Field(default=8.0, ge=1.0, le=60.0)
    report_each_step: bool = Field(default=True)

class LangChainConfig(BaseModel):
    max_token_limit: int = Field(default=4000, ge=1000, le=8000)
    verbose: bool = Field(default=False)
    early_stopping_method: str = Field(default="generate")
    handle_parsing_errors: bool = Field(default=True)

class MaicraftConfig(BaseModel):
    llm: LLMConfig = Field(default_factory=LLMConfig)
    agent: AgentConfig = Field(default_factory=AgentConfig)
    langchain: LangChainConfig = Field(default_factory=LangChainConfig)
    
    @validator('agent')
    def validate_agent_config(cls, v):
        if v.max_steps > 100:
            raise ValueError("max_steps不能超过100")
        return v
```

### 5. 主要改进点

#### 5.1 LCEL链模块化
- **chains目录设计**：将LCEL链分离到独立模块，避免单个文件过大
- **模块化架构**：每个链负责特定功能，便于维护和扩展
- **统一接口**：通过BaseChain基类提供统一的链接口
- **可组合性**：链之间可以灵活组合和重用
- **职责分离**：任务规划、目标提议、记忆管理、错误处理各司其职

#### 5.2 工具适配器优化
- **动态Pydantic模型**：根据MCP schema自动生成工具参数模型
- **类型安全**：确保工具调用的类型正确性
- **详细日志**：完整的工具调用日志记录
- **错误处理**：分级的错误处理和报告机制

#### 5.3 记忆管理优化
- **使用ConversationBufferMemory**：LangChain内置的记忆组件
- **自动token限制**：防止记忆过大
- **消息格式标准化**：使用LangChain标准的消息格式

#### 5.4 AgentRunner简化
- **专注任务调度**：移除复杂的LLM调用逻辑
- **队列管理**：使用asyncio.Queue管理任务
- **结果报告**：标准化的结果报告机制

### 6. 实施步骤

1. **第一阶段：核心组件**
   - 实现MCPToolAdapter（优化版，包含详细日志）
   - 创建chains目录和基础链类
   - 实现MaicraftAgent（简化版，使用chains）
   - 简化AgentRunner
   - 添加配置验证模块

2. **第二阶段：集成测试**
   - 更新plugin.py
   - 测试工具转换和日志记录
   - 验证chains模块和LCEL链执行
   - 测试配置验证功能

3. **第三阶段：配置优化**
   - 更新配置文件
   - 测试记忆管理
   - 验证错误处理和恢复机制
   - 测试配置验证和类型安全

4. **第四阶段：文档更新**
   - 更新README
   - 添加使用示例
   - 完善配置说明

### 7. 优势总结

#### ✅ **技术优势**
- **LCEL链模块化**：chains目录设计，避免单个文件过大
- **动态工具模型**：类型安全的工具调用
- **内置记忆管理**：标准化的上下文管理
- **错误处理**：完善的错误处理和恢复机制
- **配置验证**：类型安全的配置管理
- **简化架构**：减少约70%的自定义代码

#### ✅ **开发优势**
- **标准化**：使用LangChain最佳实践
- **可维护性**：清晰的代码结构和模块化设计
- **可扩展性**：易于添加新的LCEL链和功能
- **调试友好**：更好的错误信息和日志记录
- **配置安全**：类型安全的配置验证

#### ✅ **性能优势**
- **LCEL优化**：利用LangChain的内置优化
- **记忆优化**：自动token管理
- **并发支持**：更好的异步处理

### 8. 迁移策略

#### 渐进式迁移
```python
class MaicraftPlugin(BasePlugin):
    async def setup(self):
        # ... MCP连接代码 ...
        
        if self.connected:
            # 尝试使用新的LCEL Agent
            try:
                self.agent = MaicraftAgent(self.plugin_config, self.mcp_client)
                await self.agent.initialize()
                self.use_lcel = True
                self.logger.info("[插件初始化] 使用LCEL Agent")
            except Exception as e:
                self.logger.warning(f"[插件初始化] LCEL Agent初始化失败，回退到原方案: {e}")
                # 回退到原有的LLMPlanner
                self.use_lcel = False
```

### 9. 最终评估

#### ✅ **强烈推荐实施**
- **技术风险低**：使用成熟的LangChain框架
- **收益显著**：大幅简化代码，提高可维护性
- **LCEL优势**：更好的可组合性和扩展性
- **渐进迁移**：可以分阶段实施，降低风险

这个优化版重构方案在保持简洁的同时，充分利用了LangChain的LCEL和内置功能，提供了更好的架构设计和开发体验。