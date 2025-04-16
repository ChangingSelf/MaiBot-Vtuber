# src/plugins/bili_danmaku/plugin.py

import asyncio
import logging
import tomllib
import os
import time
from typing import Any, Dict, Optional, List
from maim_message import MessageBase, UserInfo, BaseMessageInfo, GroupInfo, FormatInfo, Seg
from maim_message.message_base import TemplateInfo  # 假设可以这样导入

# 尝试导入 aiohttp
try:
    import aiohttp
except ImportError:
    aiohttp = None  # 标记不可用

from core.plugin_manager import BasePlugin
from core.vup_next_core import VupNextCore
from maim_message import MessageBase, UserInfo, GroupInfo, FormatInfo, Seg


# --- Helper Function ---
def load_plugin_config() -> Dict[str, Any]:
    # (Config loading logic - similar to other plugins)
    config_path = os.path.join(os.path.dirname(__file__), "config.toml")
    try:
        with open(config_path, "rb") as f:
            if hasattr(tomllib, "load"):
                return tomllib.load(f)
            else:
                try:
                    import toml

                    with open(config_path, "r", encoding="utf-8") as rf:
                        return toml.load(rf)
                except ImportError:
                    logging.error("toml package needed for Python < 3.11.")
                    return {}
                except FileNotFoundError:
                    logging.warning(f"Config file not found: {config_path}")
                    return {}
    except Exception as e:
        logging.error(f"Error loading config: {config_path}: {e}", exc_info=True)
        return {}


# --- Plugin Class ---
class BiliDanmakuPlugin(BasePlugin):
    """
    Fetches Danmaku from a Bilibili live room via HTTP polling
    and sends them to the VupNextCore.
    """

    _is_vup_next_plugin: bool = True

    def __init__(self, core: VupNextCore, plugin_config: Dict[str, Any]):
        super().__init__(core, plugin_config)
        self.logger = logging.getLogger(__name__)

        # --- 显式加载自己目录下的 config.toml ---
        loaded_config = load_plugin_config()
        # 从加载的配置中获取 bili_danmaku 段
        self.config = loaded_config.get("bili_danmaku", {})

        self.enabled = self.config.get("enabled", True)

        # --- 依赖和配置检查 (基于 self.config) ---
        if aiohttp is None:
            self.logger.error(
                "aiohttp library not found. Please install it (`pip install aiohttp`). BiliDanmakuPlugin disabled."
            )
            self.enabled = False
            return

        if not self.enabled:
            self.logger.warning("BiliDanmakuPlugin is disabled in the configuration.")
            return

        self.room_id = self.config.get("room_id")
        if not self.room_id or not isinstance(self.room_id, int) or self.room_id <= 0:
            self.logger.error(f"Invalid or missing 'room_id' in config: {self.room_id}. Plugin disabled.")
            self.enabled = False
            return

        self.poll_interval = max(1, self.config.get("poll_interval", 3))
        self.api_url = f"https://api.live.bilibili.com/xlive/web-room/v1/dM/gethistory?roomid={self.room_id}"

        # --- 状态变量 ---
        self._latest_timestamp: float = time.time()  # 初始化为当前时间
        self._session: Optional[aiohttp.ClientSession] = None
        self._stop_event = asyncio.Event()
        self._task: Optional[asyncio.Task] = None

        self.logger.info(f"BiliDanmakuPlugin 初始化完成 (房间: {self.room_id}, 间隔: {self.poll_interval}s)。")

    async def setup(self):
        await super().setup()
        if not self.enabled:
            return

        # 创建 aiohttp session
        # 可以添加 headers 模拟浏览器请求，如果需要的话
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Referer": f"https://live.bilibili.com/{self.room_id}",  # 添加 Referer 可能有帮助
            "Accept": "application/json",
        }
        self._session = aiohttp.ClientSession(headers=headers)
        self.logger.debug("创建了 aiohttp Session。")

        # 启动后台轮询任务
        self._task = asyncio.create_task(self._run_polling_loop(), name=f"BiliDanmakuPoll_{self.room_id}")
        self.logger.info(f"启动 Bilibili 弹幕轮询任务 (房间: {self.room_id})...")

    async def cleanup(self):
        self.logger.info(f"开始清理 BiliDanmakuPlugin (房间: {self.room_id})...")
        self._stop_event.set()
        if self._task and not self._task.done():
            self.logger.debug("正在取消弹幕轮询任务...")
            self._task.cancel()
            try:
                await asyncio.wait_for(self._task, timeout=self.poll_interval + 1)  # 等待一小段时间
            except asyncio.TimeoutError:
                self.logger.warning("弹幕轮询任务在超时后未结束。")
            except asyncio.CancelledError:
                self.logger.info("弹幕轮询任务已被取消。")  # 正常

        if self._session and not self._session.closed:
            await self._session.close()
            self.logger.debug("关闭了 aiohttp Session。")

        await super().cleanup()
        self.logger.info(f"BiliDanmakuPlugin 清理完成 (房间: {self.room_id})。")

    async def _run_polling_loop(self):
        """后台轮询循环"""
        while not self._stop_event.is_set():
            await self._fetch_and_process()
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self.poll_interval)
                break
            except asyncio.TimeoutError:
                pass  # 正常超时，继续循环
            except asyncio.CancelledError:
                self.logger.info("弹幕轮询循环被取消。")
                break
        self.logger.info("弹幕轮询循环已结束。")

    async def _fetch_and_process(self):
        """获取并处理弹幕"""
        if not self._session or self._session.closed:
            self.logger.warning("aiohttp session 未初始化或已关闭，跳过本次轮询。")
            # 可以在这里尝试重新创建 session，但更健壮的做法是在 setup 失败时禁用插件
            return

        new_max_timestamp = self._latest_timestamp
        try:
            self.logger.debug(f"轮询 Bilibili API: {self.api_url}")
            async with self._session.get(self.api_url, timeout=10) as response:
                # Bilibili API 即使出错也可能返回 200 OK，需要检查内容
                if response.status != 200:
                    self.logger.warning(f"Bilibili API 请求失败，状态码: {response.status}")
                    # 增加一点等待时间，避免在 IP 被临时阻止时快速重试
                    await asyncio.sleep(self.poll_interval * 2)
                    return

                data = await response.json()
                self.logger.debug(f"收到 API 响应: code={data.get('code')}")

                if data.get("code") == 0:
                    room_data = data.get("data", {}).get("room", [])
                    if not room_data:
                        self.logger.debug("API 返回的弹幕列表为空")
                        return

                    new_danmakus = []
                    for item in room_data:
                        # B站时间戳是秒级整数
                        timestamp = item.get("check_info", {}).get("ts")
                        # 尝试获取用户ID (uid)
                        uid = item.get("uid")

                        if timestamp and timestamp > self._latest_timestamp:
                            new_danmakus.append(item)
                            new_max_timestamp = max(new_max_timestamp, timestamp)

                    if new_danmakus:
                        new_danmakus.sort(key=lambda x: x.get("check_info", {}).get("ts", 0))
                        self.logger.info(f"收到 {len(new_danmakus)} 条新弹幕")
                        for item in new_danmakus:
                            try:
                                message = self._create_danmaku_message(item)
                                if message:
                                    await self.core.send_to_maicore(message)
                            except Exception as e:
                                self.logger.error(f"处理单条弹幕时出错: {item} - {e}", exc_info=True)
                    else:
                        self.logger.debug("没有新的弹幕")

                    self._latest_timestamp = new_max_timestamp

                else:
                    self.logger.warning(
                        f"Bilibili API 返回错误: code={data.get('code')}, message={data.get('message')}"
                    )

        except aiohttp.ClientError as e:
            self.logger.warning(f"轮询 Bilibili API 时发生网络错误: {e}")
        except asyncio.TimeoutError:
            self.logger.warning("轮询 Bilibili API 超时")
        except asyncio.CancelledError:
            raise  # 重新抛出 CancelledError 以便上层捕获
        except Exception as e:
            # 捕获更广泛的异常，例如 JSON 解码错误
            self.logger.exception(f"处理 Bilibili 弹幕时发生未知错误: {e}")  # 使用 exception 记录 traceback

    def _create_danmaku_message(self, item: Dict[str, Any]) -> Optional[MessageBase]:
        """根据弹幕数据和配置创建 MessageBase 对象"""
        text = item.get("text", "")
        nickname = item.get("nickname", "未知用户")
        timestamp = item.get("check_info", {}).get("ts", time.time())

        # 直接从 self.config 获取默认 user_id
        user_id = item.get("uid") or self.config.get("default_user_id", f"bili_{nickname}")

        if not text:  # 忽略空弹幕
            return None

        # --- User Info --- (使用 self.config 获取配置)
        user_info = UserInfo(
            platform=self.core.platform,
            user_id=str(user_id),
            user_nickname=nickname,
            user_cardname=self.config.get("user_cardname", ""),
        )

        # --- Group Info (Conditional) --- (使用 self.config 获取配置)
        group_info: Optional[GroupInfo] = None
        if self.config.get("enable_group_info", False):
            group_info = GroupInfo(
                platform=self.core.platform,
                group_id=self.config.get("group_id", self.room_id),
                group_name=self.config.get("group_name", f"bili_{self.room_id}"),
            )

        # --- Format Info --- (使用 self.config 获取配置)
        format_info = FormatInfo(
            content_format=self.config.get("content_format", ["text"]),
            accept_format=self.config.get("accept_format", ["text"]),
        )

        # --- Additional Config --- (使用 self.config 获取配置)
        additional_config = self.config.get("additional_config", {}).copy()
        # 保留或移动到 config
        additional_config["source"] = "bili_danmaku_plugin"
        additional_config["sender_name"] = nickname
        additional_config["bili_uid"] = str(user_id) if item.get("uid") else None
        additional_config["maimcore_reply_probability_gain"] = 0.5

        # --- Base Message Info ---
        final_template_info_value = None
        # 获取 prompt_context 服务并添加上下文
        prompt_ctx_service = self.core.get_service("prompt_context")
        if prompt_ctx_service:
            try:
                # 获取带有指定标签的上下文
                additional_context = prompt_ctx_service.get_formatted_context(
                    tags=["vts", "action", "hotkey", "instruction"]
                )
                if additional_context:
                    self.logger.debug(f"获取到VTS Prompt 上下文: '{additional_context[:100]}...'")
                    # 创建模板项
                    template_items = {"reasoning_prompt_main": additional_context}
                    final_template_info_value = TemplateInfo(
                        template_items=template_items,
                    )
            except Exception as e:
                self.logger.error(f"调用 prompt_context 服务时出错: {e}", exc_info=True)

        message_info = BaseMessageInfo(
            platform=self.core.platform,
            message_id=f"bili_{self.room_id}_{int(timestamp)}_{hash(text + str(user_id)) % 10000}",
            time=int(timestamp),
            user_info=user_info,
            group_info=group_info,
            template_info=final_template_info_value,
            format_info=format_info,
            additional_config=additional_config,
        )

        # --- Message Segment ---
        message_segment = Seg(type="text", data=text)

        # self.logger.info(f"[弹幕] {nickname}({user_id}): {text}")  # 记录日志

        # --- Final MessageBase ---
        return MessageBase(message_info=message_info, message_segment=message_segment, raw_message=text)


# --- Plugin Entry Point ---
plugin_entrypoint = BiliDanmakuPlugin
