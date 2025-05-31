# VTube Studio Plugin

VTube Studio插件是一个用于连接[VTube Studio](https://denchisoft.com/)的Amaidesu组件，允许虚拟形象与聊天机器人交互，实现表情、动作和热键触发等功能。

## 🎯 功能概述

### 核心功能
- 自动连接到VTube Studio API
- 自动处理认证流程
- 提供面部参数控制（微笑、眨眼等）
- 支持加载/卸载挂件

### ✨ 新功能：智能语义匹配 (v2.0+)
- **基于embedding的智能热键匹配**：根据文本语义自动选择合适的表情热键
- **双重匹配策略**：预设表情词汇 + 直接热键名称匹配
- **可配置的相似度阈值**：精确控制匹配敏感度
- **预设表情映射库**：内置常用中文表情词汇

### 传统功能（保持兼容）
- 从聊天消息中解析和触发热键标记
- 获取并注册可用热键到提示上下文

## 📦 依赖

- Python 3.11+（推荐，内置`tomllib`）或Python 3.8+（需额外安装`toml`）
- [pyvts](https://github.com/Genteki/pyvts)库
- **新增**：[openai](https://github.com/openai/openai-python)库（用于embedding功能）
- **新增**：[numpy](https://numpy.org/)库（用于相似度计算）

## 🛠 安装

1. 确保安装了必要的依赖：

   ```bash
   pip install pyvts openai numpy
   ```

2. 将插件目录复制到`src/plugins/`下

3. 从模板创建配置文件：

   ```bash
   cp src/plugins/vtube_studio/config-template.toml src/plugins/vtube_studio/config.toml
   ```

4. 编辑配置文件，根据需要调整参数（特别是API密钥配置）

## 🔧 配置说明

配置文件位于`src/plugins/vtube_studio/config.toml`，包含以下主要选项：

### 基础配置

```toml
[vtube_studio]
enabled = true  # 是否启用插件
plugin_name = "Amaidesu_VTS_Connector"  # 在VTS中显示的插件名称
developer = "mai-devs"  # 开发者名称
authentication_token_path = "./src/plugins/vtube_studio/vts_token.txt"  # 令牌存储路径
vts_host = "localhost"  # VTS API主机
vts_port = 8001  # VTS API端口
```

### 🧠 Embedding智能匹配配置（推荐）

```toml
# Embedding 智能热键匹配功能配置
embedding_enabled = true                # 是否启用基于embedding的智能热键匹配
openai_api_key = "sk-your-api-key"     # OpenAI API密钥（必填）
openai_base_url = "https://api.siliconflow.cn/v1"  # API基础URL（硅基流动推荐）
embedding_model = "BAAI/bge-large-zh-v1.5"         # embedding模型名称
similarity_threshold = 0.7              # 相似度阈值，超过此值才会触发热键

# 预设表情/热键映射配置
[vtube_studio.emotion_hotkey_mapping]
开心 = ["微笑", "笑", "开心", "高兴", "愉快", "喜悦", "欢乐", "兴奋"]
惊讶 = ["惊讶", "吃惊", "震惊", "意外", "诧异", "惊奇"]
难过 = ["难过", "伤心", "悲伤", "沮丧", "失落", "忧郁", "哭泣"]
生气 = ["生气", "愤怒", "不满", "恼火", "气愤", "暴怒"]
害羞 = ["害羞", "脸红", "羞涩", "不好意思", "羞耻", "腼腆"]
眨眼 = ["眨眼", "wink", "眨眨眼", "眨眼睛", "抛媚眼"]
```

### 传统配置（向后兼容）

```toml
# 提示上下文相关设置（已弃用，建议使用embedding功能）
register_hotkeys_context = false  # 是否注册热键到提示
hotkeys_context_priority = 50  # 上下文优先级
```

详细配置说明请查看 [CONFIG_GUIDE.md](./CONFIG_GUIDE.md)。

## 📱 使用方法

### 🆕 智能语义匹配（推荐）

发送包含 `vtb_text` 类型的消息段，插件会自动分析文本语义并触发相应热键：

```python
# 示例：自动根据文本内容触发表情
message_segment = MessageSegment(type="vtb_text", data="我今天真的很开心！")
# 插件会自动分析"开心"的语义，找到最匹配的热键并触发
```

工作原理：
1. 分析文本的语义向量
2. 与预设表情词汇进行相似度比较
3. 找到最匹配的表情类别
4. 在VTube Studio热键中查找对应的热键
5. 自动触发最佳匹配的热键

### 传统标记方式（兼容）

在消息中使用特定标记格式来触发热键：

```
%{vts_trigger_hotkey:热键名称}%
```

例如：

```
这是一个测试消息，我很高兴能帮助你！%{vts_trigger_hotkey:微笑}%
```

## 💬 消息处理流程

### 新版本流程（Embedding模式）

```mermaid
sequenceDiagram
    participant User
    participant Core as Amaidesu Core
    participant Plugin as VTubeStudio Plugin
    participant VTS as VTube Studio API
    participant API as OpenAI API

    Plugin->>VTS: 连接&认证
    Plugin->>VTS: 获取热键列表
    Plugin->>API: 预计算热键embedding
    Plugin->>API: 预计算表情词汇embedding
    
    User->>Core: 发送vtb_text消息
    Core->>Plugin: 传递消息
    Plugin->>API: 获取文本embedding
    Note over Plugin: 计算相似度并找到最佳匹配
    Plugin->>VTS: 触发匹配的热键
    VTS-->>Plugin: 热键触发响应
```

## 核心代码讲解

### 初始化和连接

```python
def __init__(self, core: AmaidesuCore, plugin_config: Dict[str, Any]):
    # 初始化插件并加载配置
    self.vts = pyvts.vts(plugin_info=plugin_info, vts_api_info=vts_api_info)

async def _connect_and_auth(self):
    # 连接到VTS并处理认证流程
    await self.vts.connect()
    await self.vts.request_authenticate_token()
    authenticated = await self.vts.request_authenticate()
```

### 热键处理

```python
async def handle_maicore_message(self, message: MessageBase):
    # 从消息中解析热键触发标记
    hotkey_pattern = r"%\{vts_trigger_hotkey:([^}]+)\}%"
    hotkey_matches = re.findall(hotkey_pattern, original_text)
    
    # 触发所有匹配到的热键
    for hotkey_name in hotkey_matches:
        await self.trigger_hotkey(hotkey_name)
```

### 参数控制

插件提供几个简化的参数控制方法：

```python
async def close_eyes(self) -> bool:
    # 闭眼动作
    await self.set_parameter_value("EyeOpenLeft", 0)
    await self.set_parameter_value("EyeOpenRight", 0)

async def smile(self, value: float = 1) -> bool:
    # 微笑控制
    return await self.set_parameter_value("MouthSmile", value)
```

## 服务使用示例

该插件注册了`vts_control`服务，可以被其他插件调用：

```python
# 在其他插件中获取VTS控制服务
vts_service = core.get_service("vts_control")
if vts_service:
    # 触发表情热键
    await vts_service.trigger_hotkey("微笑")
    
    # 控制面部参数
    await vts_service.smile(0.8)  # 80%的微笑
    await vts_service.close_eyes()  # 闭眼
    
    # 加载自定义挂件
    item_id = await vts_service.load_item(
        file_name="heart.png",
        position_x=0.5,
        position_y=0.5,
        size=0.3
    )
    
    # 稍后卸载挂件
    await vts_service.unload_item(item_instance_id_list=[item_id])
```

## AI提示格式

向大语言模型发送的消息中可以包含以下格式的标记来触发VTube Studio热键：

```
%{vts_trigger_hotkey:热键名称}%
```

例如：

```
这是一个测试消息，我很高兴能帮助你！%{vts_trigger_hotkey:微笑}%
```

上面的消息会触发VTube Studio中名为"微笑"的热键。

## 开发注意事项

1. 在开发调试过程中，确保VTube Studio正在运行，并已启用API
2. 第一次连接时，VTube Studio会弹出窗口要求授权
3. 认证令牌将保存在指定路径，以便后续使用
4. 对于复杂的动画序列，建议在VTube Studio中设置好热键，然后通过插件触发

## 错误处理

常见错误及解决方案：

- 连接拒绝：确保VTube Studio已启动并已启用API（端口8001）
- 认证失败：检查认证令牌文件，可能需要删除并重新授权
- 热键未找到：确保热键名称完全匹配（区分大小写） 