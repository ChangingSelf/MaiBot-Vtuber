"""
对maicore的mock

启用一个ws服务端和一个控制台输入任务，便于模拟麦麦的回应来测试插件功能

使用方法：

```bash
python mock_maicore.py
```
"""

import asyncio
import json
import uuid
import time
import os
import random
import base64
from typing import Set, Dict, Callable, List, Any, Optional
from enum import Enum

from maim_message.message_base import BaseMessageInfo, FormatInfo, Seg, UserInfo
from maim_message import MessageBase
import tomllib
from aiohttp import web, WSMsgType
from src.utils.logger import get_logger

logger = get_logger("mock_maicore")


# ANSI 颜色代码
COLOR_RESET = "\033[0m"
COLOR_RED = "\033[91m"
COLOR_GREEN = "\033[92m"
COLOR_YELLOW = "\033[93m"
COLOR_BLUE = "\033[94m"
COLOR_MAGENTA = "\033[95m"
COLOR_CYAN = "\033[96m"


CONFIG_FILE_PATH = "config.toml"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000
EMOJI_PATH = "data/emoji"

# 存储所有连接的 WebSocket 客户端
clients: Set[web.WebSocketResponse] = set()

# 自定义命令系统
commands: Dict[str, Dict[str, Any]] = {}


def command(name: str, description: str, usage: str = None):
    """命令注册装饰器"""

    def decorator(func: Callable):
        commands[name] = {
            "callback": func,
            "description": description,
            "usage": usage or f"/{name}",
        }
        return func

    return decorator


# Minecraft动作类型枚举
class MinecraftActionType(Enum):
    """Minecraft动作类型枚举，与插件内部使用的动作类型保持一致"""

    NO_OP = "NO_OP"  # 不执行任何操作
    NEW = "NEW"  # 提交新代码
    RESUME = "RESUME"  # 恢复执行
    CHAT = "CHAT"  # 聊天消息（与CHAT_OP相同）
    CHAT_OP = "CHAT_OP"  # 聊天消息

    @classmethod
    def get_name(cls, action_type):
        """获取动作类型的名称"""
        return action_type.value


async def handle_websocket(request: web.Request):
    """处理新的 WebSocket 连接。"""
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    logger.info(f"客户端已连接: {request.remote}")
    clients.add(ws)

    try:
        async for msg in ws:
            if msg.type == WSMsgType.TEXT:
                try:
                    data = json.loads(msg.data)
                    logger.debug(json.dumps(data, indent=2, ensure_ascii=False))

                    message_base = MessageBase.from_dict(data)
                    timestamp = time.strftime("%H:%M:%S", time.localtime(message_base.message_info.time))
                    user_info = message_base.message_info.user_info
                    user_display = f"{user_info.user_nickname}"
                    if message_base.message_segment.type == "text":
                        print(
                            f"{COLOR_GREEN}{message_base.message_info.platform}{COLOR_RESET} [{timestamp}] {COLOR_YELLOW}{user_display}{COLOR_RESET} > {message_base.message_segment.data}"
                        )
                    else:
                        print(
                            f"{COLOR_GREEN}{message_base.message_info.platform}{COLOR_RESET} [{timestamp}] {COLOR_YELLOW}{user_display}{COLOR_RESET} > [{message_base.message_segment.type}类型的消息]"
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


def get_random_emoji() -> str:
    """从表情包目录中随机选择一个表情包并转换为base64"""
    try:
        emoji_files = [f for f in os.listdir(EMOJI_PATH) if f.lower().endswith((".png", ".jpg", ".jpeg", ".gif"))]
        if not emoji_files:
            logger.warning("表情包目录为空")
            return None

        random_emoji = random.choice(emoji_files)
        emoji_path = os.path.join(EMOJI_PATH, random_emoji)

        with open(emoji_path, "rb") as f:
            image_data = f.read()
            base64_data = base64.b64encode(image_data).decode("utf-8")
            return base64_data
    except Exception as e:
        logger.error(f"处理表情包时出错: {e}")
        return None


def build_message(content: str, message_type: str = "text") -> MessageBase:
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
        content_format=["text", "emoji"],
        accept_format=["text", "emoji"],
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

    if message_type == "emoji":
        message_segment = Seg(type="emoji", data=content)
    else:
        message_segment = Seg(type="text", data=content)

    return MessageBase(message_info=message_info, message_segment=message_segment, raw_message=content)


# 命令处理函数
@command("help", "显示所有可用命令", "/help")
async def cmd_help(args: List[str]) -> Optional[MessageBase]:
    """显示所有可用命令的帮助信息"""
    help_text = f"\n{COLOR_CYAN}===== 可用命令列表 ====={COLOR_RESET}\n"

    for cmd_name, cmd_info in sorted(commands.items()):
        help_text += f"{COLOR_YELLOW}{cmd_info['usage']}{COLOR_RESET} - {cmd_info['description']}\n"

    print(help_text)
    return None  # 不发送任何消息到websocket


@command("sendRandomEmoji", "发送随机表情包", "/sendRandomEmoji")
async def cmd_sendRandomEmoji(args: List[str]) -> Optional[MessageBase]:
    """发送随机表情包"""
    emoji_data = get_random_emoji()
    if emoji_data:
        return build_message(emoji_data, "emoji")
    else:
        print(f"{COLOR_RED}无法发送表情消息：没有可用的表情包{COLOR_RESET}")
        return None


@command("mc_help", "显示Minecraft相关命令帮助", "/mc_help")
async def cmd_mc_help(args: List[str]) -> Optional[MessageBase]:
    """显示Minecraft相关命令的帮助信息"""
    help_text = f"\n{COLOR_CYAN}===== Minecraft命令帮助 ====={COLOR_RESET}\n"

    # 筛选所有mc_前缀的命令
    mc_commands = {name: info for name, info in commands.items() if name.startswith("mc_")}

    for cmd_name, cmd_info in sorted(mc_commands.items()):
        help_text += f"{COLOR_YELLOW}{cmd_info['usage']}{COLOR_RESET} - {cmd_info['description']}\n"

    print(help_text)
    return None  # 不发送任何消息到websocket


@command("mc_new", "发送Minecraft NEW动作 - 提交新的JavaScript代码", "/mc_new [代码]")
async def cmd_mc_new(args: List[str]) -> Optional[MessageBase]:
    """发送Minecraft NEW动作"""
    # 默认代码
    default_code = """
def run(api):
    api.chat("Hello, Minecraft world!")
    api.step_forward()
    """

    # 如果提供了自定义代码，使用用户提供的代码
    code = " ".join(args) if args else default_code

    action = {"action_type_name": MinecraftActionType.get_name(MinecraftActionType.NEW), "code": code}

    return build_message(json.dumps(action))


@command("mc_chat", "发送Minecraft CHAT动作 - 发送聊天消息", "/mc_chat [消息]")
async def cmd_mc_chat(args: List[str]) -> Optional[MessageBase]:
    """发送Minecraft CHAT动作"""
    # 默认消息
    message = " ".join(args) if args else "Hello, world!"

    action = {"action_type_name": MinecraftActionType.get_name(MinecraftActionType.CHAT_OP), "message": message}

    return build_message(json.dumps(action))


@command("mc_low_level", "发送自定义低级动作", "/mc_low_level [val1] [val2] [val3] [val4] [val5] [val6] [val7] [val8]")
async def cmd_mc_low_level(args: List[str]) -> Optional[MessageBase]:
    """发送Minecraft低级动作

    用法: /mc_low_level <val1> <val2> <val3> <val4> <val5> <val6> <val7> <val8>
    默认: 0 0 0 0 0 0 0 0 (空闲)
    示例动作:
    - 前进: 0 1 0 0 0 0 0 0
    - 后退: 0 -1 0 0 0 0 0 0
    - 向左: -1 0 0 0 0 0 0 0
    - 向右: 1 0 0 0 0 0 0 0
    - 跳跃: 0 0 0 1 0 0 0 0
    - 攻击: 0 0 0 0 1 0 0 0
    - 使用: 0 0 0 0 0 1 0 0
    """
    # 默认全为0的低级动作
    values = [0, 0, 0, 0, 0, 0, 0, 0]

    # 如果用户提供了参数，覆盖相应位置的值
    for i, arg in enumerate(args):
        if i < 8:  # 只处理前8个参数
            try:
                values[i] = int(arg)
            except ValueError:
                print(f"{COLOR_RED}警告: 参数 '{arg}' 不是有效整数，使用默认值0{COLOR_RESET}")

    action = {"values": values}

    return build_message(json.dumps(action))


# 命令描述工具函数
def get_action_description(action_type: MinecraftActionType) -> str:
    """获取动作类型的描述文本"""
    descriptions = {
        MinecraftActionType.NO_OP: "不执行任何操作",
        MinecraftActionType.NEW: "提交新的JavaScript代码",
        MinecraftActionType.RESUME: "恢复执行代码",
        MinecraftActionType.CHAT: "发送聊天消息",
        MinecraftActionType.CHAT_OP: "发送聊天消息",
    }
    return descriptions.get(action_type, f"未知动作类型 ({action_type.value})")


async def handle_command(cmd_line: str):
    """处理命令行输入，解析命令和参数"""
    if not cmd_line.startswith("/"):
        return None

    # 去除前导斜杠并分割命令和参数
    parts = cmd_line[1:].strip().split()
    if not parts:
        return None

    cmd_name = parts[0].lower()
    args = parts[1:]

    if cmd_name in commands:
        cmd_func = commands[cmd_name]["callback"]
        try:
            return await cmd_func(args)
        except Exception as e:
            logger.error(f"执行命令 '{cmd_name}' 时出错: {e}", exc_info=True)
            print(f"{COLOR_RED}执行命令 '{cmd_name}' 时出错: {e}{COLOR_RESET}")
            return None
    else:
        print(f"{COLOR_RED}未知命令: '{cmd_name}'. 输入 /help 查看可用命令。{COLOR_RESET}")
        return None


async def console_input_loop():
    """异步监听控制台输入并广播消息。"""
    loop = asyncio.get_running_loop()
    logger.info("启动控制台输入监听。输入 '/help' 查看可用命令，输入 'quit' 或 'exit' 退出。")

    # 启动时显示帮助信息
    await cmd_help([])

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

            # 处理命令
            if line.startswith("/"):
                message_to_send = await handle_command(line)
                if message_to_send:
                    await broadcast_message(message_to_send)
                continue

            # 处理普通消息
            message_to_send = build_message(line)
            logger.debug(f"准备从控制台发送消息: {message_to_send}")
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
    return {}


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
