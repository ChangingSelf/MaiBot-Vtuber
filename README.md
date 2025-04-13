# MaiBot-Vtuber

聊天机器人麦麦的[VTubeStudio](https://github.com/DenchiSoft/VTubeStudio)插件。其聊天核心为[麦麦Bot](https://github.com/MaiM-with-u/MaiBot)，一款专注于 群组聊天 的赛博网友 QQ BOT。

## 项目结构

```
.
├── src/                # 源代码目录
│   ├── actuator/      # 执行器模块
│   ├── neuro/         # 神经网络模块
│   ├── sensor/        # 传感器模块
│   └── utils/         # 工具函数模块
├── main.py            # 主程序入口
└── requirements.txt   # 项目依赖
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

跟着[麦麦的安装文档](https://docs.mai-mai.org/manual/deployment/mmc_deploy.html)，安装并运行麦麦。

5. 运行

开启VtubeStudio，在选项中允许安装插件，接着运行主程序：

```bash
python -m main
```


`vts_client.py`中是对连接VTubeStudio的pyvts库的封装，启动VTubeStudio之后，在设置中开启允许安装插件的选项，可使用如下命令运行这个文件进行简单测试：

```bash
python -m src.actuator.vts_client
```

会调用当前打开模型的第一个动画。
