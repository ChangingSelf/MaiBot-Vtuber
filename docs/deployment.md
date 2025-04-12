# MaiBot-Vtuber 部署指南

本文档提供了在不同环境中部署MaiBot-Vtuber系统的详细说明。

## 系统需求

### 硬件要求

- **最低配置**:
  - CPU: 双核处理器，2.0GHz以上
  - 内存: 4GB RAM
  - 磁盘空间: 500MB可用空间
  - 显卡: 支持OpenGL 3.3的集成显卡

- **推荐配置**:
  - CPU: 四核处理器，3.0GHz以上
  - 内存: 8GB RAM
  - 磁盘空间: 1GB可用空间
  - 显卡: 独立显卡，2GB显存

### 软件要求

- Python 3.8或更高版本
- FFmpeg (用于音频处理)
- Git (用于获取源代码)
- 直播平台API密钥 (根据需要)

## 标准部署

### 1. 准备环境

```bash
# 安装Python (如果尚未安装)
# Windows: 从python.org下载并安装
# Linux:
sudo apt update
sudo apt install python3 python3-pip python3-venv

# 安装FFmpeg
# Windows: 从ffmpeg.org下载并添加到PATH
# Linux:
sudo apt install ffmpeg
```

### 2. 克隆代码库

```bash
git clone https://github.com/yourusername/MaiBot-Vtuber.git
cd MaiBot-Vtuber
```

### 3. 创建虚拟环境

```bash
# 创建虚拟环境
python -m venv venv

# 激活虚拟环境
# Windows:
venv\Scripts\activate
# Linux/macOS:
source venv/bin/activate
```

### 4. 安装依赖

```bash
# 安装运行时依赖
pip install -r requirements.txt

# 安装开发依赖(可选)
pip install -r requirements-dev.txt
```

### 5. 配置系统

```bash
# 复制默认配置
cp config/default.yaml config/config.yaml

# 编辑配置文件
nano config/config.yaml
```

在配置文件中，您需要设置:
- 直播平台账号
- 弹幕房间ID
- 连接器端点
- 日志级别和路径
- 其他特定功能参数

### 6. 启动系统

```bash
# 直接启动
python src/main.py

# 使用自定义配置文件启动
python src/main.py --config path/to/config.yaml
```

## Docker部署

### 1. 安装Docker

按照[Docker官方文档](https://docs.docker.com/get-docker/)安装Docker。

### 2. 构建Docker镜像

在项目根目录创建`Dockerfile`:

```dockerfile
FROM python:3.9-slim

# 设置工作目录
WORKDIR /app

# 安装FFmpeg
RUN apt-get update && apt-get install -y \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件
COPY requirements.txt .

# 安装依赖
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY . .

# 设置环境变量
ENV PYTHONUNBUFFERED=1

# 设置容器启动命令
CMD ["python", "src/main.py"]
```

构建镜像:

```bash
docker build -t maibot-vtuber .
```

### 3. 运行Docker容器

```bash
# 创建配置目录
mkdir -p $HOME/maibot-config

# 复制默认配置到本地目录
cp config/default.yaml $HOME/maibot-config/config.yaml

# 编辑配置文件
nano $HOME/maibot-config/config.yaml

# 运行Docker容器
docker run -d \
  --name maibot \
  -v $HOME/maibot-config:/app/config \
  -v $HOME/maibot-logs:/app/logs \
  --restart unless-stopped \
  maibot-vtuber
```

## 系统服务部署 (Linux)

### 1. 创建系统服务文件

```bash
sudo nano /etc/systemd/system/maibot.service
```

添加以下内容:

```ini
[Unit]
Description=MaiBot Vtuber Service
After=network.target

[Service]
User=yourusername
WorkingDirectory=/path/to/MaiBot-Vtuber
ExecStart=/path/to/MaiBot-Vtuber/venv/bin/python src/main.py
Restart=on-failure
RestartSec=5
StandardOutput=syslog
StandardError=syslog
SyslogIdentifier=maibot

[Install]
WantedBy=multi-user.target
```

### 2. 启用并启动服务

```bash
# 重新加载systemd管理器配置
sudo systemctl daemon-reload

# 启用服务(开机自启)
sudo systemctl enable maibot

# 启动服务
sudo systemctl start maibot

# 检查服务状态
sudo systemctl status maibot
```

## 云端部署

### 部署到Heroku

1. 在项目根目录创建`Procfile`:

```
worker: python src/main.py
```

2. 安装Heroku CLI并登录:

```bash
# 安装Heroku CLI
# 按照 https://devcenter.heroku.com/articles/heroku-cli 的说明安装

# 登录Heroku
heroku login

# 创建应用
heroku create maibot-vtuber

# 设置环境变量
heroku config:set MAIBOT_CONFIG_BASE64="$(base64 -w 0 config/config.yaml)"

# 部署应用
git push heroku main

# 查看日志
heroku logs --tail
```

### 部署到AWS EC2

1. 启动EC2实例，选择Ubuntu Server
2. 配置安全组，开放必要端口
3. 使用SSH连接到实例
4. 按照标准部署步骤部署应用
5. 设置系统服务实现自动启动

```bash
# 设置自动重启
sudo systemctl enable maibot
```

## 多实例部署

对于需要运行多个MaiBot-Vtuber实例的情况，可以通过以下方法实现:

### 使用不同配置文件

```bash
# 复制配置文件
cp config/default.yaml config/instance1.yaml
cp config/default.yaml config/instance2.yaml

# 修改配置文件中的端口和其他特定配置

# 启动不同实例
python src/main.py --config config/instance1.yaml
python src/main.py --config config/instance2.yaml
```

### 使用Docker Compose

创建`docker-compose.yml`:

```yaml
version: '3'

services:
  maibot-instance1:
    build: .
    volumes:
      - ./config/instance1.yaml:/app/config/config.yaml
      - ./logs/instance1:/app/logs
    restart: unless-stopped

  maibot-instance2:
    build: .
    volumes:
      - ./config/instance2.yaml:/app/config/config.yaml
      - ./logs/instance2:/app/logs
    restart: unless-stopped
```

启动服务:

```bash
docker-compose up -d
```

## 升级指南

### 标准升级

```bash
# 进入项目目录
cd MaiBot-Vtuber

# 获取最新代码
git pull

# 激活虚拟环境
source venv/bin/activate

# 更新依赖
pip install -r requirements.txt

# 重启服务(如果作为系统服务运行)
sudo systemctl restart maibot
```

### Docker升级

```bash
# 进入项目目录
cd MaiBot-Vtuber

# 获取最新代码
git pull

# 重新构建镜像
docker build -t maibot-vtuber .

# 停止并删除旧容器
docker stop maibot
docker rm maibot

# 启动新容器
docker run -d \
  --name maibot \
  -v $HOME/maibot-config:/app/config \
  -v $HOME/maibot-logs:/app/logs \
  --restart unless-stopped \
  maibot-vtuber
```

## 故障排除

### 常见问题

1. **系统无法启动**
   - 检查Python版本是否兼容
   - 验证所有依赖是否安装正确
   - 检查配置文件语法

2. **无法连接到直播平台**
   - 验证API密钥是否有效
   - 检查网络连接和防火墙设置
   - 确认平台API是否有变更

3. **内存使用过高**
   - 调整配置中的最大缓冲区大小
   - 减少并发处理的信号数量
   - 考虑增加系统内存

### 日志分析

日志文件位于`logs/`目录，可以通过以下命令查看:

```bash
# 查看最新日志
tail -f logs/maibot.log

# 查找错误信息
grep ERROR logs/maibot.log

# 分析特定组件日志
grep "SynapticNetwork" logs/maibot.log
```

## 性能优化

1. **增加资源配置**
   - 增加系统内存和CPU核心
   - 使用更快的存储设备

2. **调整系统参数**
   - 增大信号处理队列容量
   - 启用信号过滤和优先级处理
   - 调整批处理大小

3. **减少日志输出**
   - 在生产环境将日志级别设置为WARNING
   - 仅在需要调试时使用INFO或DEBUG级别

## 安全建议

1. **保护API密钥**
   - 不要直接在代码中硬编码密钥
   - 使用环境变量或加密存储

2. **网络隔离**
   - 将系统运行在内部网络
   - 使用防火墙限制对外连接

3. **定期更新**
   - 及时更新系统和依赖
   - 关注安全公告