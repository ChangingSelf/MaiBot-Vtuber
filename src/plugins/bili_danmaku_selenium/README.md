# Bilibili 弹幕插件 (Selenium版)

## 功能介绍

这个插件使用 Selenium WebDriver 直接从 Bilibili 直播间页面获取弹幕和礼物消息，相比 API 版本具有以下优势：

- **实时性更好**: 直接从页面获取，无需等待 API 更新
- **信息更全面**: 可以获取礼物、进入直播间等多种消息类型
- **更稳定**: 不依赖可能变化的 API 接口

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

### Selenium 配置

- `headless`: 是否使用无头模式运行浏览器（建议 true）
- `webdriver_timeout`: WebDriver 操作超时时间
- `page_load_timeout`: 页面加载超时时间
- `implicit_wait`: 隐式等待时间

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

## 注意事项

1. **浏览器驱动**: 确保 ChromeDriver 版本与 Chrome 浏览器版本匹配
2. **页面结构**: Bilibili 可能会更新页面结构，导致选择器失效，需要及时调整配置
3. **资源占用**: Selenium 会占用一定的系统资源，建议在服务器环境中使用无头模式
4. **访问频率**: 避免设置过于频繁的检查间隔，以免给 Bilibili 服务器造成压力

## 故障排除

### WebDriver 相关问题

1. 确保已安装 Chrome 浏览器
2. 下载对应版本的 ChromeDriver 并添加到 PATH
3. 或者使用 `webdriver-manager` 自动管理驱动

### 元素定位问题

1. 检查 Bilibili 页面结构是否发生变化
2. 使用浏览器开发者工具重新确认 CSS 选择器
3. 更新配置文件中的选择器设置

### 性能问题

1. 增加 `poll_interval` 减少检查频率
2. 减少 `max_messages_per_check` 限制单次处理量
3. 启用无头模式减少资源占用

## 与 API 版本的对比

| 特性       | Selenium版 | API版 |
| ---------- | ---------- | ----- |
| 实时性     | 优秀       | 良好  |
| 稳定性     | 良好       | 优秀  |
| 资源占用   | 较高       | 低    |
| 消息类型   | 丰富       | 有限  |
| 配置复杂度 | 较高       | 低    |

根据具体需求选择合适的版本使用。