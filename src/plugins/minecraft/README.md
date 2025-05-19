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
    *   **统一的动作字段**: 使用单一的 `actions` 字段，根据内容类型区分不同动作:
        *   **高级动作**: 当 `actions` 字段为字符串时，表示 JavaScript 代码。
        *   **低级动作**: 当 `actions` 字段为8元素整数数组时，表示基础数值动作。
    *   **提示词优化**: 基于配置的 `mineland_enable_low_level_action` 值，生成偏向高级或低级动作的提示词，减少使用的 tokens。
*   **自定义序列化**: 使用自定义 JSON 编码器处理 MineLand 特有的数据类型 (如 NumPy 数组)。

## 使用流程

1. clone [mineland项目](https://github.com/cocacola-lab/MineLand)，按照它的README安装好依赖
2. 在本项目所使用的虚拟环境中使用`pip install -e <mineland所在路径>`进行本地安装
3. 按根目录的README启动本项目

## 配置说明

插件使用以下配置项（位于 `src/plugins/minecraft/config.toml`）：

```toml
[minecraft]
# MineLand 任务ID
mineland_task_id = "playground"

# 是否启用无头模式（不显示图形界面）
mineland_headless = true

# 图像大小 [高度, 宽度]
mineland_image_size = [180, 320]

# 每步的游戏刻数
mineland_ticks_per_step = 20

# 偏好使用低级别动作的提示词，但仍可解析两种类型的动作
# true: 偏好低级动作提示词，false: 偏好高级动作提示词
mineland_enable_low_level_action = false

# 插件发送消息时使用的用户ID
user_id = "minecraft_bot"

# 插件发送消息时使用的昵称
nickname = "Minecraft Observer"

# 插件发送消息时使用的群组ID（可选）
# group_id = "12345678"
```

**注意**: `mineland_enable_low_level_action` 配置仅影响发送给 AmaidesuCore 的提示词类型，不限制实际可执行的动作类型。无论该值如何设置，插件都能解析和执行高级和低级两种动作，只是提示词会偏向配置的类型，以节省 tokens。

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
        *   `data`: 一个 JSON 字符串，其具体结构如下。

    *   **动作JSON结构**
        AmaidesuCore 应发送包含以下字段的 JSON 字符串:
        ```json
        {
            "actions": "<javascript_code_string>" // 或 [<int>, <int>, <int>, <int>, <int>, <int>, <int>, <int>]
        }
        ```
        
        **字段说明:**
        *   `actions`: 可以是以下两种类型之一:
            * **字符串**: 包含要执行的 JavaScript 代码，触发高级动作模式。
            * **数组**: 包含8个整数，触发低级动作模式，用于控制智能体的基本移动和交互。整数含义如下:
             *   索引 0: 前进/后退 (0=无, 1=前进, 2=后退), 范围: [0, 2]
             *   索引 1: 左移/右移 (0=无, 1=左移, 2=右移), 范围: [0, 2]
             *   索引 2: 跳跃/下蹲 (0=无, 1=跳跃, 2=下蹲), 范围: [0, 3]
             *   索引 3: 摄像头水平旋转 (0-24, 12=无变化), 范围: [0, 24]
             *   索引 4: 摄像头垂直旋转 (0-24, 12=无变化), 范围: [0, 24]
             *   索引 5: 交互类型 (0=无, 1=攻击, 2=使用等), 范围: [0, 9]
             *   索引 6: 方块/物品选择 (代表快捷栏和物品), 范围: [0, 243]
             *   索引 7: 库存管理, 范围: [0, 45]
        
        **注意:**
        *   如果 `actions` 字段未提供或格式不正确，插件将执行 `no_op` (无操作) 动作。
        *   高级和低级动作是互斥的，由 `actions` 字段的类型决定使用哪种动作。
        *   插件会根据 `mineland_enable_low_level_action` 配置值发送偏向高级或低级动作的提示词，但 AmaidesuCore 可以返回任意一种类型的动作，插件都能正确解析和执行。

        **示例:**
        ```json
        {
            "actions": "bot.chat('Hello'); bot.jump();"
        }
        ```
        或
        ```json
        {
            "actions": [0, 1, 0, 0, 12, 0, 0, 0]
        }
        ```

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
    *   `MinelandJSONEncoder(json.JSONEncoder)`: 自定义 JSON 编码器，用于处理 MineLand 返回数据中可能包含的 NumPy 数组等非标准 JSON 类型，确保它们能被正确序列化。
    *   `json_serialize_mineland(obj)`: 使用 `MinelandJSONEncoder` 序列化对象的辅助函数。
    *   `load_plugin_config()`: 加载 `config.toml` 文件的辅助函数。