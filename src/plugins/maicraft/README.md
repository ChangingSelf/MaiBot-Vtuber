# Maicraft 插件

基于 Model Context Protocol (MCP) 的 Minecraft 智能代理插件。通过 LangChain Agent 和 LCEL (LangChain Expression Language) 进行自然语言理解和任务规划，实现 Minecraft 游戏的自动化控制。

## 🎯 核心特性

- **LangChain Agent**：使用标准的 LangChain Agent 框架，提供更好的可扩展性和稳定性
- **LCEL 链模块化**：基于 LangChain Expression Language 的模块化链设计，支持灵活组合
- **MCP 工具适配器**：自动将 MCP 工具转换为 LangChain Tool，支持动态 Pydantic 模型生成
- **智能规划**：LLM 动态分析任务并选择合适的工具执行
- **自主代理**：支持自主循环，从聊天历史推断并执行目标
- **异步架构**：基于 asyncio 的高性能异步处理
- **类型安全配置**：使用 Pydantic V2 进行配置验证和类型安全
- **错误处理链**：完善的错误检测、恢复和报告机制
- **消息打断功能**：支持用户消息打断正在执行的任务，实现实时响应
- **任务优先级管理**：用户消息具有高优先级，可以打断低优先级的自主任务

## 🏗️ 系统架构

```mermaid
graph TB
    subgraph "Amaidesu Core"
        Core[AmaidesuCore]
        WS[WebSocket Handler]
    end
    
    subgraph "Maicraft Plugin"
        Plugin[MaicraftPlugin]
        
        subgraph "MCP Layer"
            MCPClient[MCPClient]
            ToolAdapter[MCPToolAdapter]
            MCPServers[MCP Servers<br/>JSON Config]
        end
        
        subgraph "Agent Layer"
            Runner[AgentRunner]
            Agent[MaicraftAgent]
            TaskQueue[TaskQueue]
        end
        
        subgraph "LCEL Chains"
            TaskChain[TaskPlanningChain]
            GoalChain[GoalProposalChain]
            MemoryChain[MemoryChain]
            ErrorChain[ErrorHandlingChain]
        end
        
        subgraph "External Services"
            LLM[LLM Service<br/>GPT-4/DeepSeek]
            MinecraftServer[Minecraft Server<br/>via MCP]
        end
    end
    
    Core --> Plugin
    WS --> Runner
    Plugin --> MCPClient
    Plugin --> Agent
    Plugin --> Runner
    
    Runner --> TaskQueue
    Runner --> Agent
    
    Agent --> ToolAdapter
    Agent --> TaskChain
    Agent --> GoalChain
    Agent --> MemoryChain
    Agent --> ErrorChain
    
    ToolAdapter --> MCPClient
    MCPClient --> MCPServers
    MCPClient --> MinecraftServer
    
    TaskChain --> LLM
    GoalChain --> LLM
    MemoryChain --> LLM
    ErrorChain --> LLM
    
    Runner --> Core
    
    classDef core fill:#e1f5fe
    classDef plugin fill:#f3e5f5
    classDef mcp fill:#e8f5e8
    classDef agent fill:#fff3e0
    classDef chains fill:#fce4ec
    classDef external fill:#ffebee
    
    class Core,WS core
    class Plugin plugin
    class MCPClient,ToolAdapter,MCPServers mcp
    class Runner,Agent,TaskQueue agent
    class TaskChain,GoalChain,MemoryChain,ErrorChain chains
    class LLM,MinecraftServer external
```

### 组件说明

| 组件 | 职责 |
|------|------|
| **MaicraftPlugin** | 插件主入口，负责组件装配和生命周期管理 |
| **MCPClient** | MCP 协议客户端，连接和调用 Minecraft 工具 |
| **MCPToolAdapter** | MCP 工具适配器，将 MCP 工具转换为 LangChain Tool |
| **MaicraftAgent** | 基于 LangChain Agent 的主代理，协调各个 LCEL 链 |
| **AgentRunner** | 代理执行器，处理任务调度和消息响应 |
| **TaskPlanningChain** | 任务规划链，负责任务分解和执行 |
| **GoalProposalChain** | 目标提议链，生成自主目标 |
| **MemoryChain** | 记忆管理链，处理上下文和聊天历史 |
| **ErrorHandlingChain** | 错误处理链，检测和恢复错误 |
| **TaskQueue** | 任务队列管理器，支持优先级调度和任务打断 |

## 📊 工作流程

```mermaid
sequenceDiagram
    participant User as 用户/直播间
    participant Core as AmaidesuCore
    participant Runner as AgentRunner
    participant Agent as MaicraftAgent
    participant TaskChain as TaskPlanningChain
    participant ToolAdapter as MCPToolAdapter
    participant MCP as MCPClient
    participant MC as Minecraft Server
    participant LLM as LLM Service
    
    Note over User,LLM: 消息处理流程
    
    User->>Core: 发送消息<br/>"帮我挖10个石头"
    Core->>Runner: 转发WebSocket消息
    Runner->>Runner: 检查是否需要打断当前任务
    alt 有正在执行的任务
        Runner->>Runner: 取消当前任务
        Runner->>Runner: 报告任务取消
    end
    Runner->>Agent: 处理用户输入
    Agent->>TaskChain: 任务规划与分解
    TaskChain->>LLM: 调用LLM分析任务
    LLM-->>TaskChain: 返回执行计划
    TaskChain->>ToolAdapter: 获取可用工具
    ToolAdapter->>MCP: 调用MCP工具
    MCP->>MC: 执行Minecraft操作
    MC-->>MCP: 返回操作结果
    MCP-->>ToolAdapter: 工具调用结果
    ToolAdapter-->>TaskChain: 执行结果
    TaskChain-->>Agent: 任务完成
    Agent-->>Runner: 返回结果
    Runner->>Core: 报告执行进度
    Core->>User: 反馈执行状态
```

## 🚀 快速开始

### 1. 环境准备

```bash
# 安装依赖
pip install fastmcp langchain langchain-openai

# 启动 Minecraft 1.21.5（仅支持1.21.5及以下版本）
# 创建世界并开启局域网模式（端口25565）
```

### 2. 部署 MCP 服务器

**推荐使用 [ChangingSelf/Maicraft](https://github.com/ChangingSelf/Maicraft) 作为 Minecraft MCP 服务器**

这是一个专门为 MaiBot 开发的 Minecraft MCP 服务器，具有以下优势：

- ✅ **专门优化**：为 MaiBot 场景专门设计和优化
- ✅ **功能丰富**：支持多种 Minecraft 操作和查询
- ✅ **稳定可靠**：经过充分测试，生产环境可用
- ✅ **易于配置**：提供详细的配置文档和示例
- ✅ **活跃维护**：持续更新和改进

#### 方式一：使用 npx（推荐）

```bash
# 直接使用 npx 运行，无需本地安装
npx maicraft --help
```

#### 方式二：源码安装

```bash
# 1. 克隆项目到本地
git clone https://github.com/ChangingSelf/Maicraft.git
cd Maicraft

# 2. 安装依赖
pnpm install

# 3. 构建项目
pnpm build

# 4. 创建配置文件
cp config-template.yaml config.yaml
# 编辑 config.yaml 配置 Minecraft 服务器连接信息
```

#### 配置 Maicraft MCP 服务器

创建配置文件 `config.yaml`：

```yaml
minecraft:
  host: 127.0.0.1        # Minecraft 服务器地址
  port: 25565            # 端口
  username: MaiBot       # 机器人用户名
  auth: offline          # 认证方式：offline | microsoft | mojang
  version: "1.19.0"      # 游戏版本

enabledEvents:
  - chat                 # 聊天事件
  - playerJoin           # 玩家加入
  - playerLeave          # 玩家离开
  - blockBreak           # 方块破坏
  - blockPlace           # 方块放置

maxMessageHistory: 100   # 事件历史缓存数量

logging:
  level: INFO            # DEBUG | INFO | WARN | ERROR
  enableFileLog: true    # 是否启用文件日志
  useStderr: true        # 是否使用 stderr 输出（MCP 模式建议保持 true）
```

#### 验证部署

```bash
# 使用 npx 测试
npx maicraft --host 127.0.0.1 --port 25565 --username MaiBot

# 或使用源码运行
pnpm start
```

### 3. 备选方案

如果无法使用 Maicraft，也可以使用 [yuniko-software/minecraft-mcp-server](https://github.com/yuniko-software/minecraft-mcp-server) 作为备选方案。

> ⚠️ **重要提示**: yuniko-software/minecraft-mcp-server 仅支持 Minecraft 1.21.5 及以下版本

### 3. 配置插件

创建配置文件 `config/maicraft.toml`：

```toml
[llm]
model = "gpt-4o-mini"
api_key = ""                    # 留空使用环境变量 OPENAI_API_KEY
base_url = ""                   # 可选：自定义API地址
temperature = 0.2

[agent]
enabled = true                  # 启用自主代理
session_id = "maicraft_default" # 会话ID
max_steps = 50                  # 任务最大执行步数
tick_seconds = 8.0              # 自主循环间隔
report_each_step = true         # 是否报告每个步骤

[langchain]
max_token_limit = 4000          # 最大token限制
verbose = false                 # 是否启用详细日志
early_stopping_method = "generate" # 早期停止方法
handle_parsing_errors = true    # 是否处理解析错误

[error_detection]
mode = "full_json"              # 错误检测模式: full_json 或 custom_keys
error_keys = {success = false, ok = false, error = true, failed = true}
error_message_keys = ["error_message", "error", "message", "reason"]
error_code_keys = ["error_code", "code", "status_code"]
```

### 4. 配置 MCP 服务器

编辑 `mcp/mcp_servers.json`，配置 Maicraft MCP 服务器：

#### 方式一：使用 npx（推荐）

```json
{
  "mcpServers": {
    "maicraft": {
      "type": "stdio",
      "command": "npx",
      "args": ["-y", "maicraft", "./config.yaml"]
    }
  }
}
```

或者使用命令行参数覆盖配置：

```json
{
  "mcpServers": {
    "maicraft": {
      "type": "stdio",
      "command": "npx",
      "args": ["-y", "maicraft", "--host", "127.0.0.1", "--port", "25565", "--username", "MaiBot", "--auth", "offline"]
    }
  }
}
```

#### 方式二：源码安装

```json
{
  "mcpServers": {
    "maicraft": {
      "type": "stdio",
      "command": "node",
      "args": ["/path/to/maicraft/dist/main.js", "/path/to/maicraft/config.yaml"]
    }
  }
}
```

开发阶段也可以直接运行 TypeScript 源码：

```json
{
  "mcpServers": {
    "maicraft": {
      "type": "stdio",
      "command": "tsx",
      "args": ["/path/to/maicraft/src/main.ts", "/path/to/maicraft/config.yaml"]
    }
  }
}
```

### 5. 启动使用

启动 Amaidesu 后，插件会自动：
- 连接到 Maicraft MCP 服务器
- MCP 服务器连接到 Minecraft 游戏
- 监听直播间消息
- 执行 Minecraft 相关指令
- 进行自主探索和建造

#### 启动检查清单

确保以下条件都满足：
- ✅ Minecraft 游戏正在运行（支持多个版本）
- ✅ 游戏世界已开启局域网模式（端口25565）
- ✅ Maicraft MCP 服务器已正确配置
- ✅ mcp_servers.json 中的配置正确
- ✅ Amaidesu 主程序已启动

#### 可用的 MCP 工具

Maicraft 提供丰富的 MCP 工具：

**查询工具：**
- `query_state` - 查询游戏状态
- `query_events` - 查询事件历史

**动作工具：**
- `chat` - 发送聊天消息
- `mine_block` - 挖掘方块
- `place_block` - 放置方块
- `craft_item` - 合成物品
- `smelt_item` - 熔炼物品
- `use_chest` - 使用箱子
- `swim_to_land` - 游向陆地
- `kill_mob` - 击杀生物
- `follow_player` - 跟随玩家

## 🔧 配置说明

### LLM 配置

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `model` | string | "gpt-4o-mini" | LLM 模型名称 |
| `api_key` | string | None | API 密钥（留空使用环境变量） |
| `base_url` | string | None | 自定义 API 地址 |
| `temperature` | float | 0.2 | 温度参数 (0.0-2.0) |

### Agent 配置

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `enabled` | boolean | true | 是否启用自主代理 |
| `session_id` | string | "maicraft_default" | 会话标识符 |
| `max_steps` | integer | 50 | 任务最大执行步数 (1-100) |
| `tick_seconds` | float | 8.0 | 自主循环间隔 (1.0-60.0) |
| `report_each_step` | boolean | true | 是否报告每个步骤 |

### LangChain 配置

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `max_token_limit` | integer | 4000 | 最大 token 限制 (1000-8000) |
| `verbose` | boolean | false | 是否启用详细日志 |
| `early_stopping_method` | string | "generate" | 早期停止方法 |
| `handle_parsing_errors` | boolean | true | 是否处理解析错误 |

### 错误检测配置

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `mode` | string | "full_json" | 错误检测模式 |
| `error_keys` | object | {...} | 错误检测字段映射 |
| `error_message_keys` | array | [...] | 错误消息字段列表 |
| `error_code_keys` | array | [...] | 错误代码字段列表 |

## 🔄 LCEL 链架构

### 链模块设计

```
chains/
├── base.py                    # 基础链类
├── task_planning_chain.py     # 任务规划链
├── goal_proposal_chain.py     # 目标提议链
├── memory_chain.py            # 记忆管理链
└── error_handling_chain.py    # 错误处理链
```

### 链功能说明

#### TaskPlanningChain（任务规划链）
- **输入预处理**：分析用户输入，提取任务目标和参数
- **任务执行**：选择合适的工具并执行任务
- **输出后处理**：格式化执行结果，生成用户友好的响应

#### GoalProposalChain（目标提议链）
- **上下文分析**：分析聊天历史和当前状态
- **目标生成**：基于上下文生成潜在目标
- **可行性验证**：验证目标的可行性和优先级

#### MemoryChain（记忆管理链）
- **记忆加载**：从存储中加载历史记忆
- **记忆更新**：更新当前对话和状态信息
- **记忆保存**：将更新后的记忆保存到存储

#### ErrorHandlingChain（错误处理链）
- **错误检测**：检测工具调用和LLM响应中的错误
- **错误恢复**：尝试自动恢复或提供替代方案
- **错误报告**：生成详细的错误报告和日志

## 🎯 消息打断功能

### 功能说明
重构后的 AgentRunner 支持用户消息打断正在执行的任务，实现实时响应：

1. **优先级管理**：
   - 用户消息：高优先级（PRIORITY_MAICORE = 0）
   - 自主任务：低优先级（PRIORITY_NORMAL = 10）

2. **打断机制**：
   - 检测到新用户消息时，自动取消当前正在执行的任务
   - 立即开始处理用户的新指令
   - 向用户报告任务取消状态

3. **任务队列**：
   - 使用 TaskQueue 进行优先级调度
   - 支持任务拆分和组合
   - 提供任务状态监控

### 使用示例

```python
# 用户发送消息时，系统会自动：
# 1. 检查是否有正在执行的任务
# 2. 如果有，取消当前任务
# 3. 将用户消息作为高优先级任务加入队列
# 4. 立即开始处理用户指令

# 日志示例：
# [AgentRunner] 收到消息: chat
# [AgentRunner] 检测到新消息，准备打断当前任务
# [AgentRunner] 正在打断当前任务
# [AgentRunner] 当前任务已成功取消
# [AgentRunner] 用户任务已添加到队列: 帮我挖10个石头
```

## 🛠️ 开发指南

### 添加新的 LCEL 链

1. 在 `chains/` 目录下创建新的链文件
2. 继承 `BaseChain` 类并实现必要的方法
3. 在 `MaicraftAgent` 中集成新链

```python
from .base import BaseChain

class CustomChain(BaseChain):
    def __init__(self, name: str):
        super().__init__(name)
    
    def build(self) -> Runnable:
        # 构建LCEL链
        pass
    
    async def execute(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        # 执行链逻辑
        pass
```

### 扩展 MCP 工具支持

工具适配器会自动处理新的 MCP 工具，无需额外配置。工具会：
- 自动生成 Pydantic 模型
- 提供类型安全的参数验证
- 包含详细的错误处理
- 支持异步调用

### 配置验证

使用 Pydantic V2 进行配置验证：

```python
from src.plugins.maicraft.config import MaicraftConfig

# 创建配置实例
config = MaicraftConfig(
    llm=LLMConfig(model="gpt-4o-mini"),
    agent=AgentConfig(enabled=True)
)

# 验证配置
config.validate_and_log()
```

## 🐛 故障排除

### 常见问题

1. **MCP 连接失败**
   - 检查 Minecraft 服务器是否运行
   - 验证 Maicraft MCP 服务器配置
   - 确认端口和地址设置
   - 检查 `config.yaml` 配置是否正确

2. **Maicraft 服务器启动失败**
   - 确保已安装 Node.js 和 pnpm
   - 检查 Minecraft 服务器版本兼容性
   - 验证认证方式配置（offline/microsoft/mojang）
   - 查看 Maicraft 日志文件排查问题

3. **LLM 调用失败**
   - 检查 API 密钥配置
   - 验证网络连接
   - 确认模型名称正确

4. **工具调用错误**
   - 查看错误处理链日志
   - 检查 MCP 工具状态
   - 验证参数格式
   - 确认 Maicraft 工具是否可用

### 日志调试

启用详细日志：

```toml
[langchain]
verbose = true
```

查看关键日志：
- `[MCP工具适配器]` - MCP 工具转换日志
- `[MaicraftAgent]` - Agent 执行日志
- `[TaskPlanningChain]` - 任务规划日志
- `[ErrorHandlingChain]` - 错误处理日志

## 📝 更新日志

### v2.0.0 (重构版本)
- ✅ 使用 LangChain Agent 替代自定义 LLMPlanner
- ✅ 实现 LCEL 链模块化架构
- ✅ 添加 MCP 工具适配器
- ✅ 升级到 Pydantic V2
- ✅ 完善错误处理和恢复机制
- ✅ 优化配置验证和类型安全
- ✅ 简化代码结构，提高可维护性
- ✅ 集成 TaskQueue 优先级管理
- ✅ 实现消息打断功能，支持实时响应
- ✅ 优先推荐使用 [ChangingSelf/Maicraft](https://github.com/ChangingSelf/Maicraft) 作为 MCP 服务器

### v0.x.x (原版本)
- 基础 MCP 集成
- 自定义 LLM 规划器
- 简单的任务队列管理
