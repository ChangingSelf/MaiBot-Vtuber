from pydantic import BaseModel


class Config(BaseModel):
    """Plugin Config Here"""

    Fastapi_url: str = "http://localhost:8000/api/message"  # maimcore的api地址
    bot_name: str = "麦麦"  # bot昵称
    user_name: str = "憧憬少"  # 直播间发弹幕的人，只是暂时配置在这里，后续会改
    platfrom: str = "vtube-studio"  # 平台
    port: int = 18004  # 端口


config = Config()
