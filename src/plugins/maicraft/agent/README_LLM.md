# MaiAgent LLM客户端使用说明

本文档说明如何在MaiAgent中使用集成的LLM客户端。

## 功能概述

MaiAgent现在集成了精简的LLM客户端，支持：
- 异步LLM调用
- 工具调用（Function Calling）
- 自动配置管理
- 错误处理和日志记录

## 初始化

LLM客户端会在MaiAgent初始化时自动创建：

```python
# 创建MaiAgent实例
agent = MaiAgent(config, mcp_client)

# 初始化（包括LLM客户端）
await agent.initialize()
```

## 使用方法

### 1. 简单聊天

```python
# 与LLM进行简单对话
response = await agent.chat_with_llm(
    "你好，请介绍一下自己",
    system_message="你是一个有用的AI助手。"
)
print(response)
```

### 2. 工具调用

```python
# 定义工具
tools = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "获取天气信息",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {"type": "string", "description": "城市名称"}
                },
                "required": ["location"]
            }
        }
    }
]

# 使用工具调用LLM
result = await agent.call_llm_with_tools(
    "北京今天天气怎么样？",
    tools=tools,
    system_message="你是一个天气助手，可以使用工具来获取天气信息。"
)
```

### 3. 获取配置信息

```python
# 获取LLM配置信息
config_info = agent.get_llm_config_info()
print(f"模型: {config_info['model']}")
print(f"温度: {config_info['temperature']}")
print(f"最大Token: {config_info['max_tokens']}")
```

## API参考

### chat_with_llm()
```python
async def chat_with_llm(
    self, 
    prompt: str, 
    system_message: Optional[str] = None
) -> str
```

与LLM进行简单对话，返回响应文本。

**参数：**
- `prompt`: 用户输入的提示
- `system_message`: 可选的系统消息

**返回：**
- LLM的响应文本

### call_llm_with_tools()
```python
async def call_llm_with_tools(
    self, 
    prompt: str, 
    tools: List[Dict[str, Any]], 
    system_message: Optional[str] = None
) -> Dict[str, Any]
```

使用工具调用LLM，支持Function Calling。

**参数：**
- `prompt`: 用户输入的提示
- `tools`: 工具列表（OpenAI工具格式）
- `system_message`: 可选的系统消息

**返回：**
- 包含工具调用结果的字典

### get_llm_config_info()
```python
def get_llm_config_info(self) -> Dict[str, Any]
```

获取LLM客户端的配置信息。

**返回：**
- 配置信息字典

## 配置

LLM客户端使用MaiAgent的配置对象，支持以下配置项：

```toml
[llm]
model = "qwen-plus"
temperature = 0.3
api_key = "your-api-key"
base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"

[langchain]
max_token_limit = 4000
```

## 错误处理

- 如果LLM客户端未初始化，会抛出`RuntimeError`
- API调用失败时会返回错误信息
- 所有错误都会记录到日志中

## 测试

运行测试文件验证功能：

```bash
cd src/plugins/maicraft/agent
python test_mai_agent_llm.py
```

## 注意事项

1. 确保在调用LLM方法前已经调用了`initialize()`
2. 工具定义需要遵循OpenAI的Function Calling格式
3. 网络异常会自动处理并记录日志
4. 建议在生产环境中设置适当的超时时间

## 示例场景

### 场景1：智能对话
```python
# 让AI根据当前环境状态给出建议
response = await agent.chat_with_llm(
    f"当前环境状态：{agent.environment_updater.get_current_state()}，请给出下一步建议",
    system_message="你是一个Minecraft游戏AI助手，擅长分析环境并给出建议。"
)
```

### 场景2：工具增强
```python
# 使用MCP工具增强AI能力
tools = agent.mcp_client.get_available_tools()
result = await agent.call_llm_with_tools(
    "请帮我分析当前游戏状态并制定行动计划",
    tools=tools,
    system_message="你是一个Minecraft策略AI，可以使用各种工具来帮助玩家。"
)
```

### 场景3：配置管理
```python
# 动态调整LLM参数
config_info = agent.get_llm_config_info()
if config_info.get('temperature', 0) > 0.5:
    print("当前温度设置较高，可能影响输出稳定性")
```
