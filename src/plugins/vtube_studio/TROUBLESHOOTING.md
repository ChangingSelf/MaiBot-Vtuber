# VTube Studio 插件故障排除指南

本文档提供VTube Studio插件常见问题的解决方案。

## 🔧 常见问题及解决方案

### 1. JSON序列化错误 (已修复)

**问题症状:**
```
ERROR: Object of type float32 is not JSON serializable
```

**问题原因:**
音频分析过程中产生的numpy.float32类型数值无法被JSON序列化，导致与VTube Studio API通信失败。

**解决方案:**
此问题已在最新版本中修复。插件现在会自动将所有numpy数值类型转换为Python原生float类型。

**修复内容:**
- `analyze_audio_chunk` 方法中的数值转换
- `_update_lip_sync_parameters` 方法中的参数处理
- `_analyze_vowel_features` 方法中的特征计算

### 2. 连接问题

**问题症状:**
- 无法连接到VTube Studio
- 认证失败

**解决步骤:**

1. **检查VTube Studio API设置:**
   ```
   VTube Studio → 设置 → API → 启用API
   ```

2. **检查端口配置:**
   ```toml
   [vtube_studio]
   vts_host = "localhost"
   vts_port = 8001
   ```

3. **检查防火墙设置:**
   确保端口8001未被防火墙阻止。

4. **重新认证:**
   删除认证令牌文件并重新启动插件：
   ```bash
   rm vts_token.txt
   ```

### 3. 口型同步不工作

**可能原因及解决方案:**

#### 3.1 依赖库缺失
```bash
pip install librosa scipy numpy
```

#### 3.2 口型同步被禁用
检查配置文件：
```toml
[vtube_studio.lip_sync]
enabled = true
```

#### 3.3 模型参数不支持
确认VTube Studio模型支持以下参数：
- VoiceVolume
- VoiceSilence  
- VoiceA, VoiceI, VoiceU, VoiceE, VoiceO

#### 3.4 音频阈值设置
调整音量阈值：
```toml
[vtube_studio.lip_sync]
volume_threshold = 0.01  # 降低阈值以提高敏感度
```

### 4. 性能问题

**优化建议:**

1. **调整缓冲区大小:**
   ```toml
   [vtube_studio.lip_sync]
   buffer_size = 512  # 减小以降低延迟
   sample_rate = 16000  # 降低采样率以减少计算量
   ```

2. **调整平滑系数:**
   ```toml
   [vtube_studio.lip_sync]
   smoothing_factor = 0.5  # 增加以减少抖动
   ```

### 5. LLM热键匹配问题

**问题症状:**
- LLM无法正确匹配热键
- API调用失败

**解决步骤:**

1. **检查API密钥:**
   ```toml
   [vtube_studio]
   llm_api_key = "your_api_key_here"
   ```

2. **检查模型配置:**
   ```toml
   [vtube_studio]
   llm_model = "deepseek-chat"
   llm_base_url = "https://api.siliconflow.cn/v1"
   ```

3. **禁用LLM匹配:**
   如果不需要智能热键匹配：
   ```toml
   [vtube_studio]
   llm_matching_enabled = false
   ```

## 🧪 测试和诊断

### 运行测试脚本
```bash
cd src/plugins/vtube_studio
python test_lip_sync.py
```

### 查看日志输出
启用调试日志以获取详细信息：
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

### 检查网络连接
```bash
telnet localhost 8001
```

## 📋 检查清单

使用此清单确保所有组件正常工作：

- [ ] VTube Studio已运行并启用API
- [ ] 所有Python依赖已安装 (`pyvts`, `librosa`, `scipy`, `numpy`)
- [ ] 配置文件正确设置
- [ ] 防火墙未阻止端口8001
- [ ] VTube Studio模型支持口型同步参数
- [ ] 认证令牌有效
- [ ] 测试脚本运行通过

## 🆘 获取帮助

如果问题仍然存在：

1. **收集信息:**
   - 运行测试脚本并保存输出
   - 检查应用程序日志
   - 记录错误消息和堆栈跟踪

2. **检查文档:**
   - README.md - 基本使用说明
   - QUICK_START.md - 快速开始指南
   - 配置文件注释

3. **联系支持:**
   提供以下信息：
   - 操作系统版本
   - Python版本
   - VTube Studio版本
   - 完整的错误日志
   - 配置文件（移除敏感信息）

## 📈 性能调优

### 延迟优化
```toml
[vtube_studio.lip_sync]
buffer_size = 256      # 减小缓冲区
sample_rate = 16000    # 降低采样率
smoothing_factor = 0.2 # 减少平滑以降低延迟
```

### 准确性优化
```toml
[vtube_studio.lip_sync]
buffer_size = 1024              # 增大缓冲区
sample_rate = 32000             # 提高采样率
vowel_detection_sensitivity = 0.8 # 提高敏感度
volume_threshold = 0.005        # 降低音量阈值
```

### CPU使用率优化
```toml
[vtube_studio.lip_sync]
sample_rate = 16000    # 降低采样率
buffer_size = 512      # 适中的缓冲区大小
```

---

**提示:** 修改配置后需要重启插件才能生效。 