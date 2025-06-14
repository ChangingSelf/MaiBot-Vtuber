# Command Processor 管道

## 概述
`CommandProcessorPipeline` 是一个消息处理管道，其唯一职责是在消息被发送到 MaiCore 之前，**清理和移除**消息文本中嵌入的命令标记（例如 `%{command:args}%`）。

这个管道确保了消费消息的下游插件（如 `TTSPlugin`）接收到的是干净、可读的文本，而无需关心其中可能包含的特殊指令。

**重要**: 此管道 **只负责移除标记**，不负责解析或执行命令。命令的执行是由 `ActionTriggerPlugin` 独立处理的。

## 工作原理

### 基本流程
1.  **启用与排序**: 管道需要在根 `config.toml` 的 `[pipelines]` 部分被启用，并赋予一个 `priority`（优先级）。推荐使用一个较小的 `priority` 值（如 `50`），以确保它在绝大多数处理插件（特别是 `TTSPlugin`）之前运行。
2.  **消息拦截**: 当一个消息通过 `core.send_to_maicore()` 发送时，`PipelineManager` 会将其传递给此管道的 `process_message` 方法。
3.  **文本清理**: 管道使用正则表达式查找并移除所有匹配 `command_pattern` 的命令标记。
4.  **消息传递**: 管道返回被清理后的消息对象，以便 `PipelineManager` 将其传递给下一个管道，或最终发送到 `MaiCore`。如果消息中没有找到命令，则原样返回。

## 配置

管道的配置位于其目录下的 `config.toml` 文件中。

- `enabled`: `true` 或 `false`。注意：即使此处为 `true`，管道也必须在根配置中设置 `priority` 才能被激活。
- `command_pattern`: 用于匹配命令的正则表达式。默认值能匹配 `%{...}%` 格式的标签。

#### `config.toml` 示例
```toml
# src/pipelines/command_processor/config.toml

enabled = true
command_pattern = "%\\{([^%{}]+)\\}"
```

## 如何启用

要启用此管道，请在 **项目根目录** 的 `config.toml` (或 `config-template.toml`) 文件中，找到 `[pipelines]` 部分，并添加如下配置：

```toml
# 根目录 config.toml

[pipelines]
  # ... 其他管道

  [pipelines.command_processor]
  priority = 50 # 必须项。定义优先级并启用管道。
  # command_pattern = "..." # 可选：在这里覆盖管道自己的配置
``` 