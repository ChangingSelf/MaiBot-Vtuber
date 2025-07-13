# Remote Stream 集成测试配置指南

## 1. 插件配置概述

### STT 插件 (src/plugins/stt/config.toml)
- 已配置 `use_remote_stream = false` (测试时设为 true)
- 音频格式: 16kHz, 单声道, int16

### read_pingmu 插件 (src/plugins/read_pingmu/config.toml)  
- 已配置 `use_remote_stream = false` (测试时设为 true)
- 支持远程图像输入

### gptsovits_tts 插件 (src/plugins/gptsovits_tts/config.toml)
- 已配置 `use_remote_stream = false` (测试时设为 true)
- 支持远程音频输出

### remote_stream 插件 (src/plugins/remote_stream/config.toml)
- 服务端模式，监听端口 8765
- 音频: 16kHz, 单声道, int16
- 图像: 1280x720, JPEG, 质量85

## 2. 测试步骤

### 准备阶段
1. 确保所有必要依赖已安装:
   ```bash
   pip install websockets numpy sounddevice soundfile opencv-python Pillow
   ```

2. 启动 Amaidesu 主程序（确保 remote_stream 插件已加载）

### 测试模式 1：本地测试（不使用 remote_stream）
1. 保持所有插件的 `use_remote_stream = false`
2. 验证各插件的基本功能正常

### 测试模式 2：remote_stream 集成测试
1. 修改插件配置启用 remote_stream：
   - STT: `use_remote_stream = true`
   - read_pingmu: `use_remote_stream = true`
   - gptsovits_tts: `use_remote_stream = true`

2. 启动测试客户端：
   ```bash
   cd src/plugins/remote_stream
   python test_client.py --host localhost --port 8765 --mode audio,image
   ```

3. 测试功能：
   - 音频输入：通过测试客户端的麦克风输入，验证 STT 识别
   - 图像输入：通过测试客户端的摄像头，验证 read_pingmu 描述
   - 音频输出：触发 TTS，验证音频是否发送到测试客户端播放

## 3. 验证检查点

### STT 功能验证
- [ ] 本地麦克风模式正常工作
- [ ] 远程音频模式正常接收和识别
- [ ] 远程模式下的 VAD 检测正常
- [ ] 音频格式转换正确

### read_pingmu 功能验证  
- [ ] 本地截图模式正常工作
- [ ] 远程图像模式正常接收和处理
- [ ] 图像请求机制正常
- [ ] 图像格式解析正确

### gptsovits_tts 功能验证
- [ ] 本地音频播放模式正常工作
- [ ] 远程音频发送模式正常
- [ ] 音频数据格式正确
- [ ] 回退机制正常（远程失败时自动本地播放）

### remote_stream 服务验证
- [ ] WebSocket 服务器正常启动
- [ ] 客户端连接正常
- [ ] 音频数据传输稳定
- [ ] 图像数据传输稳定
- [ ] TTS 音频下发正常

## 4. 故障排除

### 常见问题
1. **连接失败**：检查防火墙设置，确保端口 8765 开放
2. **音频不同步**：检查音频格式配置是否一致
3. **图像质量差**：调整 JPEG 质量设置
4. **性能问题**：调整传输频率和缓冲区大小

### 调试工具
- 使用 `test_client.py` 模拟边缘设备
- 检查 Amaidesu 日志输出
- 监控网络连接状态
- 验证音频/图像数据完整性

## 5. 配置文件快速切换

为了方便测试，可以创建两套配置：

### 本地模式配置
- 所有插件的 `use_remote_stream = false`

### 远程模式配置  
- 所有插件的 `use_remote_stream = true`
- 确保 remote_stream 插件配置正确
