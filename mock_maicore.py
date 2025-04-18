"""
对maicore的mock

启用一个ws服务端和一个控制台输入任务，便于模拟麦麦的回应来测试插件功能

使用方法：

```bash
python mock_maicore.py
```
"""

# ANSI 颜色代码
COLOR_RESET = "\033[0m"
COLOR_RED = "\033[91m"
COLOR_GREEN = "\033[92m"
COLOR_YELLOW = "\033[93m"
COLOR_BLUE = "\033[94m"
COLOR_MAGENTA = "\033[95m"
COLOR_CYAN = "\033[96m"

import asyncio
import json
import uuid
import time
from typing import Set

from maim_message.message_base import BaseMessageInfo, FormatInfo, Seg, UserInfo
from maim_message import MessageBase
from src.utils.logger import logger
import tomllib
from aiohttp import web, WSMsgType

CONFIG_FILE_PATH = "config.toml"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000

# 存储所有连接的 WebSocket 客户端
clients: Set[web.WebSocketResponse] = set()


async def handle_websocket(request: web.Request):
    """处理新的 WebSocket 连接。"""
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    logger.info(f"客户端已连接: {request.remote}")
    clients.add(ws)

    try:
        async for msg in ws:
            if msg.type == WSMsgType.TEXT:
                logger.info(f"收到来自 {request.remote} 的消息:")
                try:
                    data = json.loads(msg.data)
                    logger.info(json.dumps(data, indent=2, ensure_ascii=False))

                    message_base = MessageBase.from_dict(data)
                    if message_base.message_segment.type == "text":
                        print(
                            f"{COLOR_GREEN}{message_base.message_info.platform}{COLOR_RESET} > {message_base.message_segment.data}"
                        )
                    else:
                        print(
                            f"{COLOR_GREEN}{message_base.message_info.platform}{COLOR_RESET} > [{message_base.message_segment.type}类型的消息]"
                        )

                except Exception as e:
                    logger.error(f"处理接收到的消息时出错: {e}", exc_info=True)

            elif msg.type == WSMsgType.ERROR:
                logger.error(f"WebSocket 连接错误: {ws.exception()}")

    except asyncio.CancelledError:
        logger.info(f"WebSocket 任务被取消 ({request.remote})")
    except Exception as e:
        logger.error(f"WebSocket 连接异常 ({request.remote}): {e}", exc_info=True)
    finally:
        logger.info(f"客户端已断开连接: {request.remote}")
        clients.discard(ws)

    return ws


async def broadcast_message(message: MessageBase):
    """向所有连接的客户端广播消息。"""
    if not clients:
        logger.warning("没有连接的客户端，无法广播消息。")
        return
    # 转换为json
    message_json = json.dumps(message.to_dict())
    logger.info(f"准备广播消息给 {len(clients)} 个客户端: {str(message_json)[:100]}...")
    # 创建发送任务列表
    send_tasks = [asyncio.create_task(ws.send_str(message_json)) for ws in clients]
    # 等待所有发送完成，并处理可能出现的错误
    results = await asyncio.gather(*send_tasks, return_exceptions=True)
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            # 从 tasks 获取对应的 ws (这种方式有点脆弱，但可行)
            ws_list = list(clients)
            failed_ws = ws_list[i] if i < len(ws_list) else "Unknown WS"
            logger.error(
                f"向客户端 {failed_ws.remote if hasattr(failed_ws, 'remote') else failed_ws} 发送消息失败: {result}"
            )


def build_message(content: str) -> MessageBase:
    """构建MessageBase"""
    msg_id = str(uuid.uuid4())
    now = time.time()

    platform = "mock-maicore"

    user_info = UserInfo(
        platform=platform,
        user_id=123456,
        user_nickname="麦麦",
        user_cardname="麦麦",
    )

    group_info = None

    format_info = FormatInfo(
        content_format=["text"],
        accept_format=["text"],
    )

    message_info = BaseMessageInfo(
        platform=platform,
        message_id=msg_id,
        time=now,
        user_info=user_info,
        group_info=group_info,
        template_info=None,
        format_info=format_info,
        additional_config={},
    )

    message_segment = Seg(type="text", data=content)

    return MessageBase(message_info=message_info, message_segment=message_segment, raw_message=content)


async def console_input_loop():
    """异步监听控制台输入并广播消息。"""
    loop = asyncio.get_running_loop()
    logger.info("启动控制台输入监听。输入 'quit' 或 'exit' 退出。")
    while True:
        try:
            # 使用 run_in_executor 在单独的线程中运行阻塞的 input()
            line = await loop.run_in_executor(None, lambda: input(f"{COLOR_BLUE}mock_maicore{COLOR_RESET} > "))
            line = line.strip()
            if not line:
                continue
            if line.lower() in ["quit", "exit"]:
                logger.info("收到退出指令，正在停止...")
                # 可以触发应用的关闭逻辑
                tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
                [task.cancel() for task in tasks]
                break

            # 构造消息字典
            message_to_send = build_message(line)
            logger.debug(f"准备从控制台发送消息: {message_to_send}")

            # 广播消息
            await broadcast_message(message_to_send)

        except (EOFError, KeyboardInterrupt):
            logger.info("检测到 EOF 或中断信号，正在退出...")
            break
        except asyncio.CancelledError:
            logger.info("控制台输入任务被取消。")
            break
        except Exception as e:
            logger.error(f"控制台输入循环出错: {e}", exc_info=True)
            # 防止无限循环错误，稍微等待一下
            await asyncio.sleep(1)


def load_config() -> dict:
    """加载配置文件并返回配置。"""
    try:
        with open(CONFIG_FILE_PATH, "rb") as f:  # tomllib 需要二进制模式打开文件
            config = tomllib.load(f)  # 使用 tomllib.load
            return config
    except FileNotFoundError:
        logger.warning(f"配置文件 {CONFIG_FILE_PATH} 未找到，将使用默认配置: ws://{DEFAULT_HOST}:{DEFAULT_PORT}")
    except tomllib.TOMLDecodeError as e:  # 使用 tomllib 的特定异常
        logger.error(f"解析配置文件 {CONFIG_FILE_PATH} 时出错: {e}，将使用默认配置: ws://{DEFAULT_HOST}:{DEFAULT_PORT}")
    except Exception as e:
        logger.error(
            f"读取配置文件 {CONFIG_FILE_PATH} 时发生其他错误: {e}，将使用默认配置: ws://{DEFAULT_HOST}:{DEFAULT_PORT}"
        )


async def main():
    config = load_config()

    host = config.get("host", DEFAULT_HOST)
    port = config.get("port", DEFAULT_PORT)

    app = web.Application()
    app.router.add_get("/ws", handle_websocket)
    logger.info(f"模拟 MaiCore 启动，监听地址: ws://{host}:{port}/ws (从 {CONFIG_FILE_PATH} 读取)")

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)

    try:
        await site.start()
        logger.info("WebSocket 服务器已启动。")
        # 启动控制台输入任务
        console_task = asyncio.create_task(console_input_loop())
        # 等待控制台任务结束（表示用户想退出）或服务器被外部停止
        await console_task  # 等待控制台输入循环结束

    except asyncio.CancelledError:
        logger.info("主任务被取消。")
    except Exception as e:
        logger.error(f"启动或运行服务器时发生错误: {e}", exc_info=True)
    finally:
        logger.info("开始关闭服务器...")
        await runner.cleanup()
        logger.info("服务器已关闭。")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("通过 Ctrl+C 强制退出。")
    except Exception as e:
        logger.critical(f"程序意外终止: {e}", exc_info=True)
