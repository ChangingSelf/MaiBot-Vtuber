from maim_message.message_base import GroupInfo, UserInfo
from ..neuro.synapse import Neurotransmitter, Synapse, synapse
from .sensor import Sensor
from ..utils.logger import logger
import asyncio
import aiohttp
import time
import json
from ..utils.config import global_config
from collections import deque
import datetime


class DanmakuLiveSensor(Sensor):
    def __init__(self, synapse: Synapse):
        super().__init__(synapse)
        self.running = False
        self.room_id = global_config.bilibili_room_id
        self.api_url = f"https://api.live.bilibili.com/xlive/web-room/v1/dM/gethistory?roomid={self.room_id}"
        # 用于存储已处理弹幕的ID
        self.processed_ids = set()
        # 轮询间隔（秒）
        self.poll_interval = 5
        # 可选的Cookie字符串，可以在配置文件中设置
        self.cookies = getattr(global_config, "bilibili_cookies", "")
        # 最近一次获取到的弹幕原始数据，用于调试
        self.last_response = None
        # 弹幕获取任务
        self.fetch_task = None

    async def fetch_danmaku(self):
        """从B站API获取最新弹幕"""
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36",
                "Referer": f"https://live.bilibili.com/{self.room_id}",
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "zh-CN,zh;q=0.9",
                "Origin": "https://live.bilibili.com",
            }

            # 如果有配置Cookie，则添加到请求头中
            if self.cookies:
                headers["Cookie"] = self.cookies

            async with aiohttp.ClientSession() as session:
                async with session.get(self.api_url, headers=headers) as response:
                    if response.status == 200:
                        text = await response.text()
                        # 保存原始响应用于调试
                        logger.debug(f"API原始响应: {text[:200]}...")

                        data = json.loads(text)
                        self.last_response = data

                        if data.get("code") == 0 and "data" in data and "room" in data["data"]:
                            return data["data"]["room"]
                        else:
                            logger.error(f"API返回数据结构异常: {data}")
                    else:
                        logger.error(f"获取弹幕失败: {response.status}")
                        if response.status == 412:
                            logger.error("请求被拒绝，可能是请求过于频繁或缺少必要的请求头")
                            logger.error(f"请求头: {headers}")
        except Exception as e:
            logger.error(f"获取弹幕出错: {str(e)}")
        return []

    async def _fetch_danmaku_loop(self):
        """持续获取并处理弹幕的任务"""
        logger.info(f"开始获取弹幕, 直播间ID: {self.room_id}")

        # 启动时清空已处理ID集合
        self.processed_ids.clear()

        # 是否为第一次获取（用于跳过历史弹幕）
        first_fetch = True

        while self.running:
            try:
                danmaku_list = await self.fetch_danmaku()
                current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                # 记录获取到的弹幕数量
                logger.info(f"当前时间: {current_time}, 获取到 {len(danmaku_list)} 条弹幕")

                # 第一次获取只记录ID，不处理内容
                if first_fetch:
                    if danmaku_list:
                        for danmaku in danmaku_list:
                            danmaku_id = danmaku.get("id_str", "")
                            if danmaku_id:
                                self.processed_ids.add(danmaku_id)
                        logger.info(f"首次获取，已记录 {len(self.processed_ids)} 条弹幕ID，这些弹幕不会被处理")
                        first_fetch = False
                    else:
                        logger.warning("首次获取没有获取到弹幕，将在下次尝试")
                    await asyncio.sleep(self.poll_interval)
                    continue

                # 处理新弹幕
                new_danmaku_count = 0

                # 详细记录每条弹幕信息用于调试
                for i, danmaku in enumerate(danmaku_list):
                    danmaku_id = danmaku.get("id_str", "")
                    text = danmaku.get("text", "")
                    nickname = danmaku.get("user", {}).get("base", {}).get("name", "未知用户")
                    timeline = danmaku.get("timeline", "未知时间")

                    # 详细调试信息
                    logger.debug(f"弹幕[{i}]: ID={danmaku_id}, 时间={timeline}, 用户={nickname}, 内容={text}")

                    # 如果是新弹幕且有ID，则处理
                    if danmaku_id and danmaku_id not in self.processed_ids:
                        new_danmaku_count += 1
                        logger.info(f"处理新弹幕[{timeline}]: {nickname} 说: {text}")

                        # 添加到已处理集合
                        self.processed_ids.add(danmaku_id)

                        # 构造用户信息
                        user_info = UserInfo(
                            platform=global_config.platform,
                            user_id=str(danmaku.get("uid", "0")),
                            user_nickname=nickname,
                            user_cardname=nickname,
                        )

                        # 构造群组信息（B站直播间）
                        group_info = GroupInfo(
                            platform=global_config.platform,
                            group_id=self.room_id,
                            group_name=f"B站直播间-{self.room_id}",
                        )

                        # 发布弹幕到处理队列
                        try:
                            await self.synapse.publish_input(
                                Neurotransmitter(raw_message=text, user_info=user_info, group_info=group_info)
                            )
                        except Exception as e:
                            logger.error(f"发布弹幕到处理队列失败: {str(e)}")

                # 记录本次处理的弹幕数量
                logger.info(f"已处理 {new_danmaku_count} 条新弹幕，当前总共缓存了 {len(self.processed_ids)} 个弹幕ID")

                # 控制缓存大小，避免内存无限增长
                if len(self.processed_ids) > 1000:
                    logger.info("缓存ID数量超过1000，清理旧ID")
                    # 由于使用集合，无法精确控制保留哪些ID，只能整体重置
                    # 下次循环会重新收集新的弹幕ID
                    self.processed_ids.clear()
                    first_fetch = True
                    logger.info("已清空弹幕ID缓存，下次获取将作为首次获取处理")

            except Exception as e:
                logger.error(f"处理弹幕时发生错误: {str(e)}")
                import traceback

                logger.error(traceback.format_exc())

            # 等待下一次轮询
            await asyncio.sleep(self.poll_interval)

    async def connect(self):
        """连接到B站直播间并开始轮询获取弹幕"""
        await asyncio.sleep(2)  # 等待核心连接
        self.running = True
        logger.info(f"B站直播弹幕传感器已启动，直播间ID: {self.room_id}")

        # 在事件循环中创建弹幕获取任务，但不等待它完成
        # 这样connect函数可以立即返回，而弹幕获取任务会在后台继续运行
        self.fetch_task = asyncio.create_task(self._fetch_danmaku_loop())
        self.fetch_task.set_name("Danmaku_Fetcher")

        # 不要在这里await self.fetch_task，这样connect函数会立即返回
        logger.info("弹幕获取任务已创建并在后台运行")

    async def disconnect(self):
        """停止弹幕获取"""
        logger.info("正在关闭B站直播弹幕传感器...")
        self.running = False

        # 取消后台任务
        if self.fetch_task and not self.fetch_task.done():
            logger.info("正在取消弹幕获取任务...")
            self.fetch_task.cancel()
            try:
                # 等待任务取消，设置超时
                await asyncio.wait_for(self.fetch_task, timeout=2.0)
            except asyncio.TimeoutError:
                logger.warning("弹幕获取任务取消超时")
            except asyncio.CancelledError:
                logger.info("弹幕获取任务已成功取消")
            except Exception as e:
                logger.error(f"取消弹幕获取任务时出错: {str(e)}")


danmaku_live_sensor = DanmakuLiveSensor(synapse)
