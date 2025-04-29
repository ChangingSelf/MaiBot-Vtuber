# Amaidesu TTS 插件

TTS（语音合成）插件是 Amaidesu VTuber 项目的核心组件，负责将文本消息转换为语音并播放给用户。插件使用 Microsoft Edge TTS 引擎实现高质量语音合成，并支持与其他插件如文本清理服务和字幕服务的集成。

## 功能特点

- 接收并处理 WebSocket 文本消息
- 使用 Edge TTS 进行语音合成
- 支持选择不同语音角色和输出音频设备
- 支持通过 UDP 广播 TTS 内容（用于外部监听）
- 集成文本清理服务（可选）
- 发送播放信息到字幕服务（可选）
- 智能错误处理和资源管理

## 依赖

### 必需依赖

- `edge-tts`: Microsoft Edge TTS 引擎
- `sounddevice`: 音频播放
- `soundfile`: 音频文件处理
- `numpy`: 用于音频数据处理

### 可选服务依赖

- `text_cleanup`: 用于优化 TTS 的文本（由 LLM Text Processor 插件提供）
- `subtitle_service`: 用于显示正在播放的文本（由 Subtitle 插件提供）

## 消息处理流程

TTS 插件处理流程如下：

1. **消息接收**：监听来自 MaiCore 的所有 WebSocket 消息，过滤出文本类型消息
2. **文本清理**（可选）：通过 `text_cleanup` 服务优化文本内容
3. **UDP 广播**（可选）：将最终文本通过 UDP 广播到外部监听者
4. **语音合成**：使用 Edge TTS 将文本合成为语音并保存为临时文件
5. **播放前处理**：计算音频时长并通知字幕服务
6. **音频播放**：通过 sounddevice 播放音频
7. **资源清理**：播放完成后删除临时文件

## 时序图

```mermaid
sequenceDiagram
    participant MaiCore as MaiCore WebSocket
    participant TTS as TTS插件
    participant Cleanup as 文本清理服务
    participant Subtitle as 字幕服务
    participant UDP as UDP监听器
    participant EdgeTTS as Edge TTS引擎
    participant Audio as 音频设备

    MaiCore->>TTS: 发送文本消息
    
    alt 文本清理服务可用
        TTS->>Cleanup: 请求清理文本
        Cleanup-->>TTS: 返回优化后文本
    end
    
    alt UDP广播已启用
        TTS->>UDP: 广播最终文本
    end
    
    TTS->>EdgeTTS: 请求语音合成
    EdgeTTS-->>TTS: 返回音频数据
    
    TTS->>TTS: 计算音频时长
    
    alt 字幕服务可用
        TTS->>Subtitle: 发送文本和时长 (record_speech)
    end
    
    TTS->>Audio: 播放音频
    Audio-->>TTS: 播放完成
    
    TTS->>TTS: 清理临时文件
```

## 核心服务使用

### 文本清理服务使用示例

TTS 插件通过`text_cleanup`服务来优化文本以获得更好的语音效果：

```python
# 获取文本清理服务
cleanup_service = self.core.get_service("text_cleanup")
if cleanup_service:
    # 尝试清理文本
    cleaned = await cleanup_service.clean_text(original_text)
    if cleaned:
        # 使用清理后的文本
        final_text = cleaned
```

### 字幕服务通知示例

TTS 插件在播放音频前会通知字幕服务展示对应文本：

```python
# 通知字幕服务
if duration_seconds is not None and duration_seconds > 0:
    subtitle_service = self.core.get_service("subtitle_service")
    if subtitle_service:
        # 异步调用，不阻塞播放
        asyncio.create_task(subtitle_service.record_speech(text, duration_seconds))
```

## 核心代码解析

### 1. 消息处理函数

```python
async def handle_maicore_message(self, message: MessageBase):
    """处理从 MaiCore 收到的消息，如果是文本类型，则进行 TTS 处理。"""
    # 检查消息段是否存在且类型为 'text'
    if message.message_segment and message.message_segment.type == "text":
        original_text = message.message_segment.data
        if not isinstance(original_text, str) or not original_text.strip():
            return

        original_text = original_text.strip()
        final_text = original_text

        # 1. (可选) 清理文本 - 通过服务调用
        cleanup_service = self.core.get_service("text_cleanup")
        if cleanup_service:
            cleaned = await cleanup_service.clean_text(original_text)
            if cleaned:
                final_text = cleaned

        # 2. (可选) UDP 广播
        if self.udp_enabled and self.udp_socket and self.udp_dest:
            self._broadcast_text(final_text)

        # 3. 执行 TTS
        await self._speak(final_text)
```

### 2. TTS 执行函数

```python
async def _speak(self, text: str):
    """执行 Edge TTS 合成和播放，并通知 Subtitle Service。"""
    async with self.tts_lock:
        try:
            # --- TTS 合成 ---
            communicate = edge_tts.Communicate(text, self.voice)
            with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp_file:
                tmp_filename = tmp_file.name
            await asyncio.to_thread(communicate.save_sync, tmp_filename)
            
            # --- 读取音频并计算时长 ---
            audio_data, samplerate = await asyncio.to_thread(sf.read, tmp_filename, dtype="float32")
            if samplerate > 0 and isinstance(audio_data, np.ndarray):
                duration_seconds = len(audio_data) / samplerate
                
                # --- 通知 Subtitle Service ---
                if duration_seconds > 0:
                    subtitle_service = self.core.get_service("subtitle_service")
                    if subtitle_service:
                        asyncio.create_task(subtitle_service.record_speech(text, duration_seconds))
            
            # --- 播放音频 ---
            await asyncio.to_thread(
                sd.play, audio_data, samplerate=samplerate, 
                device=self.output_device_index, blocking=True
            )
        finally:
            # --- 清理临时文件 ---
            if tmp_filename and os.path.exists(tmp_filename):
                os.remove(tmp_filename)
```

### 3. 广播机制

```python
def _broadcast_text(self, text: str):
    """通过 UDP 发送文本 (用于外部监听)。"""
    if self.udp_socket and self.udp_dest:
        try:
            message_bytes = text.encode("utf-8")
            self.udp_socket.sendto(message_bytes, self.udp_dest)
        except Exception as e:
            self.logger.warning(f"发送 TTS 内容到 UDP 监听器失败: {e}")
```

## 配置说明

插件通过 `config.toml` 文件进行配置，主要配置项包括：

```toml
[tts]
# 使用的 Edge TTS 语音模型
voice = "zh-CN-XiaoxiaoNeural"
# 指定输出音频设备名称 (留空或注释掉以使用系统默认设备)
output_device_name = ""

[udp_broadcast]
# 是否将最终要播报的文本通过 UDP 广播出去
enable = false
# 广播的目标主机地址
host = "127.0.0.1"
# 广播的目标 UDP 端口
port = 9998
```

## 优化与扩展

1. **多语言支持**：可通过配置不同的 `voice` 值支持多种语言
2. **高级音频控制**：可添加音量、语速等参数配置
3. **并发处理**：当前使用互斥锁确保单个 TTS 任务执行，可扩展为队列机制
4. **缓存机制**：对常用语句进行缓存以减少 TTS 调用
5. **情感分析**：集成情感分析插件以自动选择合适的语音风格

## 开发注意事项

1. 确保正确安装所有依赖项
2. 注意音频设备兼容性，特别是在跨平台场景
3. 优先处理 `edge-tts` 和音频播放库的异常，确保程序稳定
4. 考虑长文本的分段处理以提高响应速度
5. 确保临时文件的正确清理，避免磁盘空间占用 