# Minecraft 插件 for AmaidesuCore

## 目录

- [Minecraft 插件 for AmaidesuCore](#minecraft-插件-for-amaidesucore)
  - [目录](#目录)
  - [概述](#概述)
  - [核心功能](#核心功能)
  - [使用流程](#使用流程)
  - [与 AmaidesuCore 的消息交互](#与-amaidesucore-的消息交互)
    - [插件 -\> AmaidesuCore (状态同步)](#插件---amaidesucore-状态同步)
    - [AmaidesuCore -\> 插件 (动作指令)](#amaidesucore---插件-动作指令)
  - [Mineland 核心概念](#mineland-核心概念)
  - [插件代码结构简述](#插件代码结构简述)

## 概述

本插件旨在将 [MineLand](https://deepwiki.com/cocacola-lab/MineLand/) 模拟器集成到 AmaidesuCore 中。它允许 AmaidesuCore 控制在 MineLand 环境中运行的 Minecraft 智能体，接收来自模拟器的观察和事件，并向其发送动作指令。

MineLand 是一个为研究大规模互动、有限多模态感知和物理需求的 AI 智能体而设计的多智能体 Minecraft 模拟器。

## 核心功能

*   **环境管理**: 初始化和管理 MineLand 模拟环境，包括任务加载、智能体配置等。
*   **状态同步**: 将 MineLand 环境的当前状态 (如观察数据、代码执行信息、事件、任务完成状态等) 序列化后发送给 AmaidesuCore。
*   **动作执行**: 接收来自 AmaidesuCore 的动作指令，并在 MineLand 环境中为指定的智能体执行这些动作。
*   **动作类型支持**:
    *   **高级动作**: 以 JavaScript 代码字符串的形式定义复杂行为。
    *   **低级动作**: 以数值数组的形式定义基础操作，适用于强化学习场景。
    *   **聊天动作**: 允许智能体在 Minecraft 环境中发送聊天消息。
*   **自定义序列化**: 使用自定义 JSON 编码器处理 MineLand 特有的数据类型 (如 NumPy 数组)。

## 使用流程

1. clone [mineland项目](https://github.com/cocacola-lab/MineLand)，按照它的README安装好依赖
2. 在本项目所使用的虚拟环境中使用`pip install -e <mineland所在路径>`进行本地安装
3. 按根目录的README启动本项目


## 与 AmaidesuCore 的消息交互

插件通过 `maim_message.MessageBase` 格式与 AmaidesuCore 进行通信。

### 插件 -> AmaidesuCore (状态同步)

*   **触发时机**:
    1.  插件启动并成功初始化/重置 MineLand 环境后。
    2.  在 MineLand 中执行一个动作并获得新的环境状态后。
    3.  当任务完成并自动重置环境后。
*   **`MessageBase` 结构**:
    *   `message_info`:
        *   `platform`: 从 `self.core.platform` 获取。
        *   `message_id`: 动态生成，格式类似 `f"mc_direct_{timestamp}_{hash_value}"`。
        *   `time`: 当前的 Unix 时间戳 (整数)。
        *   `user_info` (`UserInfo`):
            *   `platform`: 从 `self.core.platform` 获取。
            *   `user_id`: 配置文件中的 `user_id`。
            *   `user_nickname`: 配置文件中的 `nickname`。
        *   `group_info` (`GroupInfo`, 可选):
            *   `platform`: 从 `self.core.platform` 获取。
            *   `group_id`: 配置文件中的 `group_id` (转换为整数)。如果 `group_id` 无效或未提供，则此字段为 `None`。
        *   `format_info` (`FormatInfo`):
            *   `content_format`: `"text"`
            *   `accept_format`: `"text"`
        *   `additional_config` (`Dict[str, Any]`):
            *   `source_plugin`: `"minecraft"`
            *   `low_level_action_enabled`: 当前插件配置的 `mineland_enable_low_level_action` (布尔值)。
        *   `template_info`: `None`
    *   `message_segment` (`Seg`):
        *   `type`: `"text"`
        *   `data`: 一个 JSON 字符串。该字符串由配置文件中的 `json_prompt_prefix` 和一个代表当前 MineLand 状态的 JSON 对象拼接而成。其内部 JSON 对象结构如下：
            ```json
            {
                "step": "<int>", // 当前环境的步数
                "observations": "<List[Any]>", // 来自 MineLand 的观察数据。通常是每个智能体的观察对象的列表。内部复杂类型 (如 NumPy 数组) 已被转换为 JSON 兼容格式。
                "code_infos": "<List[Any]>", // 来自 MineLand 的代码执行信息 (例如，对于高级动作的执行状态)。
                "events": "<List[List[Any]]>", // 来自 MineLand 的事件列表，每个智能体一个事件列表。
                "is_done": "<bool>" or "<List[bool]>", // 指示当前任务是否完成。对于单智能体环境，通常是一个布尔值；对于多智能体，可能是一个布尔值列表。插件目前主要按单智能体逻辑处理 `is_done[0]`。
                "task_info": "<Dict[str, Any]>", // 来自 MineLand 的当前任务相关信息。
                "low_level_action_enabled": "<bool>" // 指示当前 MineLand 环境是否配置为接受低级动作。
            }
            ```
    *   `raw_message`: 与 `message_segment.data` 相同。

### AmaidesuCore -> 插件 (动作指令)

*   **触发时机**: AmaidesuCore 在分析了插件发送的环境状态后，决定需要执行的动作。
*   **`MessageBase` 结构 (插件从 `handle_maicore_response` 方法接收到的 `message` 参数)**:
    *   `message_segment`:
        *   `type`: 插件期望为 `"text"`。
        *   `data`: 一个 JSON 字符串，其具体结构取决于当前插件配置的动作模式 (`mineland_enable_low_level_action`)。

    *   **1. 高级动作模式 (`mineland_enable_low_level_action: false`)**
        AmaidesuCore 应发送包含以下结构的 JSON 字符串：
        ```json
        {
            "action_type_name": "<ActionTypeNameString>",
            // 根据 action_type_name 可能需要的其他字段:
            "code": "<javascript_code_string>", // 当 action_type_name 为 "NEW" 时
            "message": "<chat_message_string>"  // 当 action_type_name 为 "CHAT" 或 "CHAT_OP" 时
        }
        ```
        `action_type_name` 可以是以下字符串之一 (对应 `MinecraftActionType` 枚举):
        *   `"NO_OP"`: 不执行任何操作。MineLand 智能体将执行一个空操作。
        *   `"NEW"`: 执行新的 JavaScript 代码。`code` 字段必须提供。
        *   `"RESUME"`: 继续执行先前暂停的 JavaScript 代码。
        *   `"CHAT"` 或 `"CHAT_OP"`: 发送聊天消息。`message` 字段必须提供。该消息将在 Minecraft 环境中以智能体的身份发出。

    *   **2. 低级动作模式 (`mineland_enable_low_level_action: true`)**
        AmaidesuCore 应发送包含以下结构的 JSON 字符串：
        ```json
        {
            "values": [
                <int>, <int>, <int>, <int>,
                <int>, <int>, <int>, <int>
            ]
        }
        ```
        `values`: 一个包含8个整数的列表。这些值对应 `mineland.LowLevelAction` 的8个维度，用于控制智能体的基本移动和交互。
        *   如果 `values` 字段缺失、不是列表、或列表长度不为8，插件会记录警告并执行一个 `no_op` (无操作) 动作。

## Mineland 核心概念

(参考自 [MineLand DeepWiki](https://deepwiki.com/cocacola-lab/MineLand/))

*   **Gym 式接口**: MineLand 提供了一个类似 OpenAI Gym 的接口，主要通过 `mineland.make()` 创建环境，`reset()` 重置环境并获取初始观察，`step(action)` 执行动作并获取下一状态。插件中的 `setup()` 和 `handle_maicore_response()` 方法分别使用了这些接口。
*   **动作系统**:
    *   **高级动作 (High-Level Actions)**: 以 JavaScript 代码形式提供，由 Mineflayer bots 执行，允许复杂的行为和与 Minecraft 世界的交互。对应插件中 `enable_low_level_action: false` 的情况。
    *   **低级动作 (Low-Level Actions)**: 数值动作，用于基本移动和交互，适合强化学习智能体。对应插件中 `enable_low_level_action: true` 的情况。
*   **观察空间 (Observation Space)**: MineLand 的观察空间包括视觉信息 (第一人称视角图像)、实体信息 (附近实体)、库存状态、健康和饥饿度、环境数据以及声音事件等。这些信息是插件发送给 AmaidesuCore 的 `observations` 字段的主要内容。
*   **多智能体支持**: MineLand 支持多个智能体在同一世界中并发运行。当前插件实现主要针对单智能体 (`agents_count` 硬编码为1) 进行动作解析和状态处理，但 MineLand 本身具备多智能体能力。

## 插件代码结构简述

*   `plugin.py`:
    *   `MinecraftPlugin(BasePlugin)`: 插件的主类。
        *   `__init__`: 加载配置，初始化 MineLand 相关参数。
        *   `setup()`: 初始化 MineLand 环境 (`mineland.make()`, `mland.reset()`)，注册到 AmaidesuCore 的 WebSocket 处理器，并发送初始状态。
        *   `_send_state_to_maicore()`: 封装了将当前 MineLand 状态构建为 `MessageBase` 对象并发送给 AmaidesuCore 的逻辑。
        *   `handle_maicore_response(message: MessageBase)`: 核心回调函数，处理来自 AmaidesuCore 的动作指令。它解析接收到的 JSON 动作，转换为 MineLand 动作对象，通过 `mland.step()` 在模拟器中执行，然后发送更新后的状态。
        *   `cleanup()`: 关闭 MineLand 环境 (`mland.close()`)。
    *   `MinecraftActionType(Enum)`: 定义了插件内部使用的高级动作类型 (NO_OP, NEW, RESUME, CHAT, CHAT_OP)。
    *   `MinelandJSONEncoder(json.JSONEncoder)`: 自定义 JSON 编码器，用于处理 MineLand 返回数据中可能包含的 NumPy 数组等非标准 JSON 类型，确保它们能被正确序列化。
    *   `json_serialize_mineland(obj)`: 使用 `MinelandJSONEncoder` 序列化对象的辅助函数。
    *   `load_plugin_config()`: 加载 `config.toml` 文件的辅助函数。