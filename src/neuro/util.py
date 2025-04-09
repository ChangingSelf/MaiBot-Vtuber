from maim_message import UserInfo, Seg, MessageBase, BaseMessageInfo
import aiohttp
from ..utils.config import config
from ..utils.logger import get_logger
import time

# 创建logger
logger = get_logger("util")


class chat:
    def __init__(self) -> None:
        self.session = None

    async def get_session(self):
        if self.session is None:
            self.session = aiohttp.ClientSession()
        return self.session

    async def easy_to_send(self, text: str):
        user_info = UserInfo(
            platform=config.platfrom,
            user_id=0,  # 反正得有
            user_nickname=config.user_name,
            user_cardname=config.user_name,
        )

        message_info = BaseMessageInfo(
            platform=config.platfrom,
            message_id=None,
            time=int(time.time()),
            group_info=None,
            user_info=user_info,
            additional_config={"maimcore_reply_probability_gain": 1},
        )
        message_seg = Seg(
            type="text",
            data=text,
        )

        message_base = MessageBase(message_info, message_seg, raw_message=text)

        payload = message_base.to_dict()
        # logger.info(payload)
        logger.info("消息发送成功")

        session = await self.get_session()
        async with session.post(
            config.core_url,
            json=payload,
            headers={"Content-Type": "application/json"},
        ) as response:
            # 检查响应状态
            if response.status != 200:
                logger.error(f"FastAPI返回错误状态码: {response.status}")
                response_text = await response.text()
                logger.debug(f"响应内容: {response_text}")
            else:
                response_data = await response.json()
                logger.info(f"收到服务端响应: {response_data}")
                logger.debug(f"响应内容: {response_data}")

    async def close(self):
        if self.session is not None:
            await self.session.close()
            self.session = None


chat_util = chat()
