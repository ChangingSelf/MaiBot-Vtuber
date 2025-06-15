# Minecraft插件智能体模式重构实现

## 概述

本次重构成功实现了Minecraft插件的智能体模式，允许在现有MaiCore通信模式和新的智能体自主决策模式之间动态切换。重构完全向后兼容，不会破坏现有功能。

## 主要功能

### 1. 双模式支持
- **MaiCore模式**：保持原有的MaiCore通信逻辑
- **智能体模式**：智能体自主决策，可选接收MaiCore指令

### 2. 智能体热插拔
- 支持简单智能体（基于LLM）
- 运行时切换智能体类型
- 抽象智能体接口，易于扩展

### 3. 模式动态切换
- 不重启插件即可切换控制模式
- 状态保持和恢复机制

## 架构说明

### 目录结构
```
src/plugins/minecraft/
├── controllers/           # 控制器模块
│   ├── __init__.py
│   ├── base_controller.py      # 控制策略基类
│   ├── maicore_controller.py   # MaiCore控制器
│   └── agent_controller.py     # 智能体控制器
├── agents/               # 智能体模块
│   ├── __init__.py
│   ├── base_agent.py          # 智能体基类
│   └── simple_agent.py        # 简单智能体
├── core/                 # 核心组件
│   ├── __init__.py
│   ├── agent_manager.py       # 智能体管理器
│   ├── mode_switcher.py       # 模式切换器
│   └── config_manager.py      # 配置管理器
└── [现有目录保持不变]
```

### 核心组件

#### 控制器 (Controllers)
- **MaiCoreController**: 实现原有的MaiCore通信模式
- **AgentController**: 实现智能体自主决策模式

#### 智能体 (Agents)
- **SimpleAgent**: 基于LLM的轻量级智能体

#### 核心管理 (Core)
- **AgentManager**: 智能体的注册、创建和切换管理
- **ModeSwitcher**: 控制模式之间的切换
- **ConfigManager**: 统一的配置管理

## 配置说明

### 基本配置
```toml
[minecraft]
# 控制模式: maicore | agent  
control_mode = "maicore"
# 是否允许运行时切换模式
allow_mode_switching = true
```

### 智能体管理配置
```toml
[minecraft.agent_manager]
default_agent_type = "simple"
agent_switch_timeout = 30
```

### MaiCore集成配置
```toml
[minecraft.maicore_integration]
accept_commands = true
status_report_interval = 60
default_command_priority = "normal"
```

### 简单智能体配置
```toml
[minecraft.agents.simple]
model = "Pro/deepseek-ai/DeepSeek-V3"
temperature = 0.1
max_tokens = 1024
max_memory = 10
# API配置
api_key = "your_api_key_here"
base_url = "https://api.deepseek.com"
# 或使用环境变量（推荐）
# api_key_env = "DEEPSEEK_API_KEY"
# base_url_env = "DEEPSEEK_BASE_URL"
```

### LLM API配置说明

支持两种配置方式：

1. **直接配置**（不推荐，安全性较低）：
   ```toml
   api_key = "your_actual_api_key"
   base_url = "https://api.provider.com"
   ```

2. **环境变量配置**（推荐）：
   ```toml
   api_key_env = "YOUR_API_KEY_ENV_NAME"
   base_url_env = "YOUR_BASE_URL_ENV_NAME"
   ```

   然后设置环境变量：
   ```bash
   # Windows (PowerShell)
   $env:DEEPSEEK_API_KEY="your_key_here"
   
   # Linux/macOS
   export DEEPSEEK_API_KEY="your_key_here"
   ```

## 使用方法

### 1. 基本使用
默认情况下，插件以原有的MaiCore模式运行，无需任何更改。

### 2. 启用智能体模式
修改配置文件：
```toml
[minecraft]
control_mode = "agent"
```

### 3. 运行时模式切换
```python
# 切换到智能体模式
await plugin.switch_mode("agent")

# 切换回MaiCore模式
await plugin.switch_mode("maicore")

# 查看当前模式
current_mode = await plugin.get_current_mode()
```

## 智能体开发

### 创建自定义智能体
```python
from agents.base_agent import BaseAgent
from mineland import Action

class MyCustomAgent(BaseAgent):
    async def initialize(self, config):
        # 初始化逻辑
        pass
    
    async def run(self, obs, **kwargs):
        # 决策逻辑
        return Action(type=Action.NEW, code="await bot.move_forward(1)")
    
    # 实现其他必要方法...
```

### 注册自定义智能体
```python
await plugin.agent_manager.register_agent_type("custom", MyCustomAgent)
```

## 支持的API提供商

- **OpenAI**: gpt-4-turbo, gpt-3.5-turbo
- **DeepSeek**: Pro/deepseek-ai/DeepSeek-V3
- **SiliconFlow**: Pro/deepseek-ai/DeepSeek-V3
- 任何兼容OpenAI API的提供商

## 故障排除

### 常见问题

1. **API密钥错误**
   - 检查API密钥是否正确设置
   - 确认环境变量名称匹配

2. **模型不支持**
   - 确认使用的模型名称正确
   - 检查API提供商是否支持该模型

3. **网络连接问题**
   - 检查base_url是否正确
   - 确认网络连接正常

### 日志调试
插件会输出详细的日志信息，可以通过日志来诊断问题：
```
智能体管理器初始化完成，可用智能体: ['simple']
简单智能体初始化完成
已切换到智能体: simple
```

## 向后兼容性

- 现有配置文件无需修改即可正常工作
- 默认使用MaiCore模式，保持原有行为
- 所有现有API和功能保持不变

## 性能考虑

- 智能体模式会增加LLM API调用开销
- 建议根据使用场景调整决策频率
- 可通过配置调整智能体的响应速度和质量平衡 