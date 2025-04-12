from pydantic import BaseModel


class Config(BaseModel):
    """Plugin Config Here"""

    plugin_name: str = "MaiBot-Vtuber"  # 插件名称
    developer: str = "ChangingSelf"  # 插件开发者
    core_url: str = "http://localhost:8000/api/message"  # maimcore的api地址
    bot_name: str = "麦麦"  # bot昵称
    sender_name: str = "憧憬少"  # 直播间发弹幕的人，只是暂时配置在这里，后续会改
    platform: str = "maibot-vtuber"  # 平台
    port: int = 18004  # 端口
    token_path: str = "./token.txt"  # 认证token文件路径

    core_host: str = "127.0.0.1"
    core_port: int = 8000


global_config = Config()
