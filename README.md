# MaiBot-Vtuber

聊天机器人麦麦的[VTubeStudio](https://github.com/DenchiSoft/VTubeStudio)插件。其聊天核心为[麦麦Bot](https://github.com/MaiM-with-u/MaiBot)，一款专注于 群组聊天 的赛博网友 QQ BOT。

## 项目结构

```
.
├── main.py          # 主程序入口
├── api.py           # API接口定义
├── config.py        # 配置文件
├── util.py          # 工具函数
├── requirements.txt # 项目依赖
└── token.txt        # 认证令牌
```

## 安装步骤

1. 克隆项目到本地：
```bash
git clone git@github.com:ChangingSelf/MaiBot-Vtuber.git
cd MaiBot-Vtuber
```

2. 创建并激活虚拟环境（推荐）：
```bash
python -m venv venv
# Windows
.\venv\Scripts\activate
# Linux/Mac
source venv/bin/activate
```

3. 安装依赖：
```bash
pip install -r requirements.txt
```

4. 配置并启动麦麦

在麦麦的配置文件`bot_config.toml`的`platforms`配置中添加以下内容：

```toml
[platforms] # 必填项目，填写每个平台适配器提供的链接
nonebot-qq="http://127.0.0.1:18002/api/message" # 原有默认配置
vtube-studio="http://127.0.0.1:18004/api/message" # 新增加的本项目配置
```

跟着[麦麦的安装文档](https://docs.mai-mai.org/manual/deployment/mmc_deploy.html)，安装并运行麦麦。

5. 运行

```bash
python main.py
```

目前`main.py`中是一个测试用的控制台程序，实现了和MaiBot Core的简单交互，后续会完善。

`vts_test.py`中是连接VTubeStudio的测试程序，启动VTubeStudio之后，在设置中开启允许安装插件的选项，使用如下命令运行插件：

```bash
python vts_test.py
```

会调用当前打开模型的第一个动画。
