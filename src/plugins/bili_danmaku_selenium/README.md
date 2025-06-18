# Bilibili 弹幕插件 (Selenium版)

## 功能介绍

这个插件使用 Selenium WebDriver 直接从 Bilibili 直播间页面获取弹幕和礼物消息，相比 API 版本具有以下优势：

- **实时性更好**: 直接从页面获取，无需等待 API 更新
- **信息更全面**: 可以获取礼物、进入直播间等多种消息类型
- **更稳定**: 不依赖可能变化的 API 接口

## 新增功能

### 1. 跳过初始弹幕 ✨
- **功能**: 只发送新增弹幕，不发送第一次读取时已存在的弹幕
- **配置**: `skip_initial_danmaku = true`
- **说明**: 启用后，插件会等待页面完全加载，然后只处理之后出现的新弹幕，避免重复处理历史弹幕

### 2. 弹幕保存功能 💾
- **功能**: 自动将获取到的弹幕保存为JSONL格式文件
- **配置**: 
  - `enable_danmaku_save = true` - 启用保存功能
  - `danmaku_save_file = "danmaku_123456.jsonl"` - 指定保存文件名
- **保存位置**: 文件保存在 `src/plugins/bili_danmaku_selenium/data/` 目录下
- **文件格式**: 每行一个JSON对象，包含完整的MessageBase信息

### 3. 从文件读取弹幕 📄
- **功能**: 从之前保存的弹幕文件中读取并重新发送弹幕
- **配置**:
  - `enable_danmaku_load = true` - 启用读取功能
  - `danmaku_load_file = "danmaku_123456.jsonl"` - 指定要读取的文件名
- **读取位置**: 从 `src/plugins/bili_danmaku_selenium/data/` 目录读取
- **使用场景**: 
  - 测试和调试
  - 重放历史弹幕
  - 离线模式运行

### 4. 纯文件模式 ⚡
- **功能**: 当启用文件读取时，自动进入纯文件模式
- **特点**:
  - 不启动浏览器，完全离线运行
  - 按照文件中记录的时间轴精确重放弹幕
  - 保持原始弹幕的时间间隔
- **配置**: 
  ```toml
  enable_danmaku_load = true
  danmaku_load_file = "replay_data.jsonl"
  # enable_danmaku_save = true  # 可选，同时保存新生成的弹幕
  ```
- **优势**: 资源占用极低，重放时间精确，适合测试和演示

## 配置示例

```toml
[bili_danmaku_selenium]
# 基本设置
room_id = 123456
poll_interval = 1.0

# 弹幕处理设置
skip_initial_danmaku = true        # 跳过初始弹幕
enable_danmaku_save = true         # 启用弹幕保存
danmaku_save_file = "live_123456.jsonl"  # 保存文件名
enable_danmaku_load = false        # 不从文件读取
danmaku_load_file = ""             # 读取文件名（空表示不读取）
```

## 使用场景

### 场景1：录制弹幕用于后续分析
```toml
skip_initial_danmaku = true
enable_danmaku_save = true
danmaku_save_file = "analysis_data.jsonl"
enable_danmaku_load = false
```

### 场景2：重放历史弹幕进行测试
```toml
skip_initial_danmaku = false
enable_danmaku_save = false
enable_danmaku_load = true
danmaku_load_file = "test_data.jsonl"
```

### 场景3：同时录制和读取（混合模式）
```toml
skip_initial_danmaku = true
enable_danmaku_save = true
danmaku_save_file = "new_data.jsonl"
enable_danmaku_load = true
danmaku_load_file = "old_data.jsonl"
```

### 场景4：纯文件重放模式（离线测试）
```toml
skip_initial_danmaku = false  # 不跳过，因为是重放
enable_danmaku_save = false   # 不保存，纯重放
enable_danmaku_load = true    # 启用文件读取
danmaku_load_file = "test_replay.jsonl"
# 启用文件读取会自动进入纯文件模式，不启动浏览器
```

## 依赖安装

```bash
pip install selenium
```

还需要安装 Chrome 浏览器和对应版本的 ChromeDriver，或者配置使用其他浏览器。

## 配置说明

### 基本配置

- `room_id`: B站直播间号码
- `poll_interval`: 检查弹幕的间隔时间（秒），建议 1-2 秒
- `max_messages_per_check`: 每次检查最多处理的消息数量

### 弹幕文件处理配置

- `skip_initial_danmaku`: 是否跳过初始弹幕，只处理新增弹幕
- `enable_danmaku_save`: 是否自动保存弹幕到文件
- `danmaku_save_file`: 保存弹幕的文件名
- `enable_danmaku_load`: 是否从文件读取弹幕
- `danmaku_load_file`: 要读取的弹幕文件名

### Selenium 配置

- `headless`: 是否使用无头模式运行浏览器（建议 true）
- `webdriver_timeout`: WebDriver 操作超时时间
- `page_load_timeout`: 页面加载超时时间
- `implicit_wait`: 隐式等待时间
- `chromedriver_path`: ChromeDriver可执行文件的路径
  - 若指定，将优先使用此路径
  - 若不指定或路径无效，将尝试使用webdriver-manager或系统安装的ChromeDriver

### 选择器配置

可以根据 Bilibili 页面结构的变化调整这些 CSS 选择器：

- `danmaku_container_selector`: 弹幕容器的选择器
- `danmaku_item_selector`: 单条弹幕的选择器
- `danmaku_text_selector`: 弹幕文本的选择器
- `username_selector`: 用户名的选择器
- `gift_selector`: 礼物消息的选择器
- `gift_text_selector`: 礼物文本的选择器

## 特色功能

### 消息去重

插件会自动记录已处理的消息，防止重复处理同一条弹幕。

### 多类型消息支持

- **弹幕消息**: 普通的文字弹幕
- **礼物消息**: 观众送礼物的消息，包含礼物名称和数量

### 自动重连

当网络异常或页面问题时，插件会自动重试，确保持续监控。

### 内存优化

定期清理已处理消息的记录，防止长时间运行导致内存占用过大。

## 文件格式说明

保存的弹幕文件使用JSONL格式（JSON Lines），每行一个JSON对象：

```json
{"message_info": {"platform": "bili", "message_id": "bili_selenium_123456_1234567890_abc123", "time": 1234567890, "user_info": {"platform": "bili", "user_id": "bili_user", "user_nickname": "观众名字"}, "format_info": {"content_format": ["text"], "accept_format": ["text"]}, "additional_config": {"source": "bili_danmaku_selenium_plugin"}}, "message_segment": {"type": "text", "data": "弹幕内容"}, "raw_message": "弹幕内容"}
```

## 注意事项

1. **Chrome浏览器**: 确保系统安装了Chrome浏览器
2. **ChromeDriver**: 需要对应版本的ChromeDriver，建议使用webdriver-manager自动管理
3. **网络环境**: 需要能正常访问Bilibili直播间
4. **资源占用**: Selenium会消耗较多系统资源，建议在性能较好的机器上运行
5. **文件权限**: 确保插件有读写data目录的权限
6. **文件大小**: 长时间录制会产生较大文件，注意磁盘空间

## 故障排除

### 常见问题

1. **WebDriver启动失败**: 检查Chrome和ChromeDriver版本是否匹配
2. **页面加载超时**: 增加`page_load_timeout`的值
3. **弹幕获取不到**: 检查CSS选择器是否需要更新
4. **文件读写失败**: 检查data目录权限和磁盘空间

## 与 API 版本的对比

| 特性       | Selenium版 | API版 |
| ---------- | ---------- | ----- |
| 实时性     | 优秀       | 良好  |
| 稳定性     | 良好       | 优秀  |
| 资源占用   | 较高       | 低    |
| 消息类型   | 丰富       | 有限  |
| 配置复杂度 | 较高       | 低    |

根据具体需求选择合适的版本使用。