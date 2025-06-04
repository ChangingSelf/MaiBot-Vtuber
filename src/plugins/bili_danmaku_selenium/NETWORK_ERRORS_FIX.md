# Chrome网络错误解决方案配置

这些错误信息是由于Chrome浏览器尝试连接B站的STUN服务器导致的，属于正常现象，可以通过以下方式解决：

## 方法1：添加Chrome启动参数（推荐）

在plugin.py的Chrome选项中添加以下参数：

```python
# 禁用WebRTC相关功能
options.add_argument("--disable-webrtc")
options.add_argument("--disable-webrtc-hw-decoding") 
options.add_argument("--disable-webrtc-hw-encoding")
options.add_argument("--disable-webrtc-multiple-routes")

# 禁用后台网络活动
options.add_argument("--disable-background-networking")
options.add_argument("--disable-background-timer-throttling")

# 设置日志级别
options.add_argument("--log-level=3")  # 只显示致命错误
options.add_experimental_option('excludeSwitches', ['enable-logging'])
```

## 方法2：启用无头模式

无头模式下这些错误通常不会出现：

```python
options.add_argument("--headless")
```

## 方法3：忽略这些错误

这些错误不影响弹幕捕获功能，可以安全忽略。

## 当前错误分析

错误信息 `Failed to resolve address for stun6.chat.bilibili.com., errorcode: -105` 表示：
- Chrome尝试解析B站的STUN服务器地址失败
- 错误代码-105表示域名解析失败（DNS_ERROR）
- 这是WebRTC功能导致的，不影响页面正常访问和弹幕捕获

## 建议解决方案

立即应用方法1和方法2，在配置文件中启用无头模式：

```toml
[bili_danmaku_selenium]
headless = true  # 启用无头模式
```

这样既能消除错误信息，又能减少资源占用。
