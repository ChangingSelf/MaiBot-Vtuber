# Bilibili Selenium 弹幕插件完整安装指南

## 快速开始

### 1. 安装依赖

```bash
# 安装 Selenium
pip install selenium

# 安装 ChromeDriver (选择以下任一方式)
# 方式 1: 使用 webdriver-manager (推荐)
pip install webdriver-manager

# 方式 2: 手动下载 ChromeDriver
# 从 https://chromedriver.chromium.org/ 下载对应版本
# 放置到 PATH 环境变量中的目录
```

### 2. 配置插件

1. 复制配置模板：
```bash
cd f:\Amaidesu\src\plugins\bili_danmaku_selenium
cp config-template.toml config.toml
```

2. 修改 `config.toml`：
```toml
[bili_danmaku_selenium]
room_id = 22603245  # 修改为目标直播间ID
poll_interval = 1.0  # 检查间隔(秒)
headless = true  # 是否无头模式运行
```

### 3. 启动测试

```bash
# 测试选择器有效性
cd f:\Amaidesu\src\plugins\bili_danmaku_selenium
python test_selectors.py

# 测试插件功能
python test_plugin.py
```

## 详细配置说明

### Selenium 配置
- `headless`: 是否以无头模式运行浏览器（推荐 true）
- `webdriver_timeout`: WebDriver 超时时间
- `page_load_timeout`: 页面加载超时时间
- `implicit_wait`: 隐式等待时间

### 选择器配置
选择器用于定位页面元素，可能需要根据B站页面更新进行调整：

```toml
# 弹幕相关选择器
danmaku_container_selector = "#chat-items"
danmaku_item_selector = ".chat-item"
danmaku_text_selector = ".danmaku-item-right"
username_selector = ".danmaku-item-left .username"

# 礼物相关选择器
gift_selector = ".gift-item"
gift_text_selector = ".gift-item-text"
```

### 性能调优
```toml
poll_interval = 1.0  # 检查频率，太频繁会消耗更多CPU
max_messages_per_check = 10  # 每次检查处理的最大消息数
```

## 故障排除

### 常见问题

#### 1. ChromeDriver 版本不匹配
```
selenium.common.exceptions.SessionNotCreatedException: Message: session not created: This version of ChromeDriver only supports Chrome version XX
```

**解决方案**：
```bash
# 使用 webdriver-manager 自动管理
pip install webdriver-manager
```

然后修改 `plugin.py` 中的 WebDriver 创建代码：
```python
from webdriver_manager.chrome import ChromeDriverManager

driver = webdriver.Chrome(
    service=Service(ChromeDriverManager().install()),
    options=options
)
```

#### 2. 页面元素找不到
```
selenium.common.exceptions.NoSuchElementException: Message: no such element
```

**解决方案**：
1. 运行选择器测试脚本更新选择器
2. 检查直播间是否正在直播
3. 增加页面加载等待时间

#### 3. 内存占用过高
**解决方案**：
- 启用无头模式 `headless = true`
- 增加 `poll_interval` 减少检查频率
- 减少 `max_messages_per_check`

#### 4. 弹幕获取不到
**可能原因**：
- 直播间没有弹幕
- 选择器已过期
- 页面加载未完成

**排查步骤**：
1. 手动访问直播间确认有弹幕
2. 运行 `test_selectors.py` 验证选择器
3. 检查控制台日志输出

## 高级配置

### 自定义选择器
如果默认选择器失效，可以通过以下方式更新：

1. 运行交互式测试：
```bash
python test_selectors.py
```

2. 使用浏览器开发者工具：
   - F12 打开开发者工具
   - 右键点击弹幕元素 → 检查
   - 复制 CSS 选择器

### 集成到 Amaidesu
确保在 Amaidesu 主配置中启用插件：

```toml
# config.toml (主配置)
[plugin_manager]
enabled_plugins = [
    "bili_danmaku_selenium",
    # 其他插件...
]
```

## 性能监控

插件运行时会输出关键日志：

```
INFO: 启动 Bilibili Selenium 弹幕监控任务 (房间: 22603245)
INFO: 收到 3 条新消息
DEBUG: 清理已处理消息记录，保留 500 条
```

监控要点：
- 消息获取频率是否正常
- 内存使用是否稳定
- CPU 占用是否合理

## WebDriver 替代方案

如果 Chrome 有问题，可以尝试其他浏览器：

### Firefox
```python
from selenium.webdriver.firefox.options import Options as FirefoxOptions

options = FirefoxOptions()
if self.headless:
    options.add_argument("--headless")
driver = webdriver.Firefox(options=options)
```

### Edge
```python
from selenium.webdriver.edge.options import Options as EdgeOptions

options = EdgeOptions()
if self.headless:
    options.add_argument("--headless")
driver = webdriver.Edge(options=options)
```

## 更新和维护

### 定期维护任务
1. 更新 ChromeDriver 版本
2. 验证选择器有效性
3. 检查B站页面结构变化
4. 优化性能参数

### 备份重要配置
建议备份 `config.toml` 文件，特别是自定义的选择器配置。

## 联系支持

如遇到问题，请提供：
1. 完整的错误日志
2. 使用的 Chrome 版本
3. 测试的直播间ID
4. 配置文件内容（删除敏感信息）
