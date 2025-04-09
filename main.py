import threading
import uvicorn
import asyncio
import aiohttp
from src.neuro.api import fastapi
from src.neuro.util import chat_util
from src.utils.logger import get_logger
import sys
from src.utils.config import config

logger = get_logger("main")


def run_fastapi():
    uvicorn.run(fastapi, host="0.0.0.0", port=config.port)


async def check_for_messages():
    """定期检查是否有新消息"""
    async with aiohttp.ClientSession() as client:
        try:
            while True:
                try:
                    # 每2秒检查一次新消息
                    await asyncio.sleep(2)

                    # 获取消息
                    async with client.get(f"http://localhost:{config.port}/api/messages") as response:
                        if response.status == 200:
                            data = await response.json()
                            messages = data.get("messages", [])

                            # 显示新消息
                            for message in messages:
                                sender = message.get("sender", "未知用户")
                                content = message.get("content", "")
                                logger.info(f"收到来自 {sender} 的消息: {content}")

                except Exception as e:
                    logger.error(f"检查消息时出错: {str(e)}")
                    await asyncio.sleep(5)  # 出错后等待更长时间

        except asyncio.CancelledError:
            logger.info("消息检查任务已取消")


async def console_interaction():
    """控制台交互功能，用于发送和接收消息"""
    logger.info("控制台交互已启动，输入消息并按回车发送，输入'exit'退出")

    # 启动消息检查任务
    message_check_task = asyncio.create_task(check_for_messages())

    try:
        while True:
            # 获取用户输入
            user_input = input("请输入消息: ")

            # 检查是否退出
            if user_input.lower() == "exit":
                logger.info("正在退出控制台交互...")
                break

            # 发送消息
            await chat_util.easy_to_send(user_input)

    except KeyboardInterrupt:
        logger.info("检测到Ctrl+C，正在退出控制台交互...")
    except Exception as e:
        logger.error(f"控制台交互出错: {str(e)}")
    finally:
        # 取消消息检查任务
        message_check_task.cancel()
        try:
            await message_check_task
        except asyncio.CancelledError:
            pass

        # 关闭 aiohttp 会话
        await chat_util.close()


def run_console_interaction():
    """在新线程中运行控制台交互"""
    asyncio.run(console_interaction())


if __name__ == "__main__":
    # 启动 FastAPI 线程
    api_thread = threading.Thread(target=run_fastapi, daemon=True)
    api_thread.start()

    # 启动控制台交互线程
    console_thread = threading.Thread(target=run_console_interaction)
    console_thread.start()

    # 等待控制台交互线程结束
    console_thread.join()

    # 程序退出
    logger.info("程序已退出")
    sys.exit(0)
