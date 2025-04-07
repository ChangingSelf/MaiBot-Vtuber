from fastapi import FastAPI, Request
import uvicorn
from util import logger
import asyncio
from typing import Optional, Dict, Any
import json
from config import Config

fastapi = FastAPI()
config = Config()


@fastapi.post("/api/message")
async def handle_request(request: Request):
    try:
        # 接收并解析JSON数据
        json_data = await request.json()
        logger.info(f"收到请求数据: {json_data}")

        # 提取消息内容
        message_segment = json_data.get("message_segment", {})

        message_content = ""

        if message_segment.get("type") == "text":
            message_content = str(message_segment.get("data", ""))

        print(f"【{config.bot_name}】{message_content}")

        # 返回响应
        return {"status": "success", "message": "消息已处理"}

    except Exception as e:
        logger.error(f"处理请求时出错: {str(e)}")
        return {"status": "error", "message": str(e)}
