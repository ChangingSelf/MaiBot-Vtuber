# 安装指南

## 依赖安装

### 1. 安装 Selenium

```bash
pip install selenium
```

### 2. 安装浏览器驱动

#### 方法一：自动管理（推荐）

```bash
pip install webdriver-manager
```

然后修改插件代码使用自动管理的驱动：

```python
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service

service = Service(ChromeDriverManager().install())
driver = webdriver.Chrome(service=service, options=options)
```

#### 方法二：手动安装

1. 下载 ChromeDriver
   - 访问：https://chromedriver.chromium.org/
   - 选择与你的 Chrome 浏览器版本匹配的 ChromeDriver
   - 下载并解压

2. 配置环境变量
   - 将 ChromeDriver 所在目录添加到系统 PATH
   - 或者直接放到项目目录中

### 3. 验证安装

运行测试脚本验证安装是否成功：

```bash
cd src/plugins/bili_danmaku_selenium
python test_selectors.py
```

## 常见问题

### ChromeDriver 版本不匹配

```
WebDriverException: This version of ChromeDriver only supports Chrome version XX
```

**解决方案：**
1. 检查你的 Chrome 浏览器版本（chrome://version/）
2. 下载对应版本的 ChromeDriver
3. 或使用 webdriver-manager 自动管理

### 权限问题

```
PermissionError: [Errno 13] Permission denied
```

**解决方案：**
1. 确保 ChromeDriver 有执行权限
2. 在 Linux/Mac 上运行：`chmod +x chromedriver`

### 无头模式问题

如果无头模式下获取不到元素，可以：
1. 暂时关闭无头模式进行调试
2. 增加等待时间
3. 检查选择器是否正确

## 性能优化建议

1. **使用无头模式**：生产环境中始终启用 `headless = true`
2. **调整检查间隔**：根据直播间活跃度调整 `poll_interval`
3. **限制处理数量**：设置合理的 `max_messages_per_check`
4. **定期重启**：长时间运行后可能需要重启浏览器实例
