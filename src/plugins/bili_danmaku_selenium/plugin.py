# src/plugins/bili_danmaku_selenium/plugin.py

import asyncio
import time
import hashlib
from typing import Dict, Any, Optional, List, Set
from dataclasses import dataclass

# --- Dependency Check ---
try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.chrome.options import Options as ChromeOptions
    from selenium.webdriver.chrome.service import Service
    from selenium.common.exceptions import NoSuchElementException

    # 尝试导入 webdriver-manager（可选依赖）
    try:
        from webdriver_manager.chrome import ChromeDriverManager

        WEBDRIVER_MANAGER_AVAILABLE = True
    except ImportError:
        WEBDRIVER_MANAGER_AVAILABLE = False

except ImportError:
    webdriver = None
    WEBDRIVER_MANAGER_AVAILABLE = False

# --- Amaidesu Core Imports ---
from src.core.plugin_manager import BasePlugin
from src.core.amaidesu_core import AmaidesuCore
from maim_message import MessageBase, UserInfo, BaseMessageInfo, GroupInfo, FormatInfo, Seg


@dataclass
class DanmakuMessage:
    """弹幕消息数据类"""

    username: str
    text: str
    timestamp: float
    user_id: str = ""  # 添加用户ID字段
    element_id: str = ""
    message_type: str = "danmaku"  # danmaku, gift, etc.
    gift_name: str = ""
    gift_count: int = 0


class BiliDanmakuSeleniumPlugin(BasePlugin):
    """Bilibili 直播弹幕插件（Selenium版），使用浏览器直接获取弹幕和礼物。"""

    def __init__(self, core: AmaidesuCore, plugin_config: Dict[str, Any]):
        super().__init__(core, plugin_config)

        # --- 显式加载自己目录下的 config.toml ---
        self.config = self.plugin_config
        self.enabled = self.config.get("enabled", True)  # --- 依赖检查 ---
        if webdriver is None:
            self.logger.error(
                "selenium library not found. Please install it (`pip install selenium`). BiliDanmakuSeleniumPlugin disabled."
            )
            self.enabled = False
            return

        if not self.enabled:
            self.logger.warning("BiliDanmakuSeleniumPlugin is disabled in the configuration.")
            return

        # --- 基本配置 ---
        self.room_id = self.config.get("room_id")
        if not self.room_id or not isinstance(self.room_id, int) or self.room_id <= 0:
            self.logger.error(f"Invalid or missing 'room_id' in config: {self.room_id}. Plugin disabled.")
            self.enabled = False
            return

        self.poll_interval = max(0.5, self.config.get("poll_interval", 1.0))
        self.max_messages_per_check = max(1, self.config.get("max_messages_per_check", 10))

        # --- Selenium 配置 ---
        self.headless = self.config.get("headless", True)
        self.webdriver_timeout = self.config.get("webdriver_timeout", 30)
        self.page_load_timeout = self.config.get("page_load_timeout", 30)
        self.implicit_wait = self.config.get("implicit_wait", 10)  # --- 选择器配置 ---
        self.danmaku_container_selector = self.config.get("danmaku_container_selector", "#chat-items")
        self.danmaku_item_selector = self.config.get("danmaku_item_selector", ".chat-item.danmaku-item")
        self.danmaku_text_selector = self.config.get("danmaku_text_selector", ".danmaku-item-right")
        self.username_selector = self.config.get("username_selector", ".user-name")
        self.gift_selector = self.config.get("gift_selector", ".gift-item")
        self.gift_text_selector = self.config.get("gift_text_selector", ".gift-item-text")

        # --- Prompt Context Tags ---
        self.context_tags: Optional[List[str]] = self.config.get("context_tags")
        if not isinstance(self.context_tags, list):
            if self.context_tags is not None:
                self.logger.warning(
                    f"Config 'context_tags' is not a list ({type(self.context_tags)}), will fetch all context."
                )
            self.context_tags = None
        elif not self.context_tags:
            self.logger.info("'context_tags' is empty, will fetch all context.")
            self.context_tags = None
        else:
            self.logger.info(f"Will fetch context with tags: {self.context_tags}")  # --- 状态变量 ---
        self.driver = None  # 类型：Optional[webdriver.Chrome]
        self._stop_event = asyncio.Event()
        self._task: Optional[asyncio.Task] = None
        self._processed_messages: Set[str] = set()  # 已处理的消息ID，防止重复
        self._last_cleanup_time = time.time()

        # --- Load Template Items ---
        self.template_items = None
        if self.config.get("enable_template_info", False):
            self.template_items = self.config.get("template_items", {})
            if not self.template_items:
                self.logger.warning(
                    "BiliDanmakuSelenium 配置启用了 template_info，但在 config.toml 中未找到 template_items。"
                )

        # --- 直播间URL ---
        self.live_url = f"https://live.bilibili.com/{self.room_id}"

    async def setup(self):
        await super().setup()
        if not self.enabled:
            return

        try:
            # 创建 WebDriver
            await self._create_webdriver()

            # 启动后台监控任务
            self._task = asyncio.create_task(self._run_monitoring_loop(), name=f"BiliDanmakuSelenium_{self.room_id}")
            self.logger.info(f"启动 Bilibili Selenium 弹幕监控任务 (房间: {self.room_id})...")

        except Exception as e:
            self.logger.error(f"设置 BiliDanmakuSeleniumPlugin 时发生错误: {e}", exc_info=True)
            self.enabled = False

    async def cleanup(self):
        self.logger.info(f"开始清理 BiliDanmakuSeleniumPlugin (房间: {self.room_id})...")
        self._stop_event.set()

        if self._task and not self._task.done():
            self.logger.info("正在取消弹幕监控任务...")
            self._task.cancel()
            try:
                await asyncio.wait_for(self._task, timeout=self.poll_interval + 2)
            except asyncio.TimeoutError:
                self.logger.warning("弹幕监控任务在超时后未结束。")
            except asyncio.CancelledError:
                self.logger.info("弹幕监控任务已被取消。")  # 关闭 WebDriver
        if self.driver:
            try:
                await asyncio.get_event_loop().run_in_executor(None, self.driver.quit)
                self.logger.info("关闭了 WebDriver。")
            except Exception as e:
                self.logger.warning(f"关闭 WebDriver 时出错: {e}")
                await super().cleanup()
        self.logger.info(f"BiliDanmakuSeleniumPlugin 清理完成 (房间: {self.room_id})。")

    async def _create_webdriver(self):
        """创建 WebDriver"""

        def _create_driver():
            options = ChromeOptions()
            # if self.headless:
            #     options.add_argument("--headless")

            # 基础安全和性能参数
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--disable-gpu")
            options.add_argument("--disable-web-security")
            options.add_argument("--disable-features=VizDisplayCompositor")

            # # 禁用WebRTC和网络相关功能，避免STUN服务器连接错误
            # options.add_argument("--disable-webrtc")
            # options.add_argument("--disable-webrtc-hw-decoding")
            # options.add_argument("--disable-webrtc-hw-encoding")
            # options.add_argument("--disable-webrtc-multiple-routes")
            # options.add_argument("--disable-webrtc-hw-vp8-encoding")
            # options.add_argument("--disable-webrtc-hw-vp9-encoding")

            # # 禁用其他可能产生网络请求的功能
            # options.add_argument("--disable-background-networking")
            # options.add_argument("--disable-background-timer-throttling")
            # options.add_argument("--disable-client-side-phishing-detection")
            # options.add_argument("--disable-default-apps")
            # options.add_argument("--disable-extensions")
            # options.add_argument("--disable-hang-monitor")
            # options.add_argument("--disable-popup-blocking")
            # options.add_argument("--disable-prompt-on-repost")
            # options.add_argument("--disable-sync")

            # 设置用户代理
            options.add_argument(
                "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            )

            # 设置日志级别，屏蔽网络错误日志
            options.add_argument("--log-level=3")  # 只显示致命错误
            options.add_experimental_option("excludeSwitches", ["enable-logging"])
            options.add_experimental_option("useAutomationExtension", False)

            # 禁用信息栏
            options.add_experimental_option(
                "prefs",
                {
                    "profile.default_content_setting_values.notifications": 2,
                    "profile.default_content_settings.popups": 0,
                    # "profile.managed_default_content_settings.images": 2,  # 禁用图片加载以提高性能
                },
            )

            # 尝试使用 webdriver-manager 自动管理 ChromeDriver
            if WEBDRIVER_MANAGER_AVAILABLE:
                try:
                    service = Service(ChromeDriverManager().install())
                    driver = webdriver.Chrome(service=service, options=options)
                    self.logger.info("使用 webdriver-manager 创建 ChromeDriver")
                except Exception as e:
                    self.logger.warning(f"webdriver-manager 创建失败，尝试系统 ChromeDriver: {e}")
                    driver = webdriver.Chrome(options=options)
            else:
                driver = webdriver.Chrome(options=options)

            driver.set_page_load_timeout(self.page_load_timeout)
            driver.implicitly_wait(self.implicit_wait)
            return driver

        try:
            self.driver = await asyncio.get_event_loop().run_in_executor(None, _create_driver)

            # 导航到直播间
            await asyncio.get_event_loop().run_in_executor(None, self.driver.get, self.live_url)
            self.logger.info(f"成功打开直播间: {self.live_url}")

            # 等待页面加载完成
            await asyncio.sleep(10)

        except Exception as e:
            self.logger.error(f"创建 WebDriver 失败: {e}", exc_info=True)
            raise

    async def _run_monitoring_loop(self):
        """后台监控循环"""
        while not self._stop_event.is_set():
            try:
                await self._fetch_and_process_messages()

                # 定期清理已处理消息记录
                current_time = time.time()
                if current_time - self._last_cleanup_time > 300:  # 5分钟清理一次
                    self._cleanup_processed_messages()
                    self._last_cleanup_time = current_time

            except Exception as e:
                self.logger.error(f"监控弹幕时发生错误: {e}", exc_info=True)
                await asyncio.sleep(self.poll_interval * 2)  # 出错时延长等待

            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self.poll_interval)
                break
            except asyncio.TimeoutError:
                pass  # 正常超时，继续循环
            except asyncio.CancelledError:
                self.logger.info("弹幕监控循环被取消。")
                break

        self.logger.info("弹幕监控循环已结束。")

    async def _fetch_and_process_messages(self):
        """获取并处理弹幕消息"""
        fetch_start_time = time.time()
        self.logger.info(f"[计时] 开始获取弹幕消息 - {fetch_start_time:.3f}")

        if not self.driver:
            self.logger.warning("WebDriver 未初始化，跳过本次检查。")
            return

        def _get_messages():
            get_msg_start_time = time.time()
            self.logger.info(f"[计时] 开始执行 _get_messages - {get_msg_start_time:.3f}")

            messages = []
            try:
                # 计时：获取弹幕元素
                danmaku_search_start = time.time()
                danmaku_elements = self.driver.find_elements(By.CSS_SELECTOR, self.danmaku_item_selector)
                danmaku_search_end = time.time()
                self.logger.info(
                    f"[计时] 查找弹幕元素耗时: {(danmaku_search_end - danmaku_search_start) * 1000:.1f}ms, 找到 {len(danmaku_elements)} 个元素"
                )

                pre_max = (
                    self.max_messages_per_check
                    if len(danmaku_elements) > self.max_messages_per_check
                    else len(danmaku_elements)
                )
                self.logger.info(f"[计时] 准备处理最新的 {pre_max} 条弹幕")  # 计时：处理弹幕元素
                process_danmaku_start = time.time()
                processed_count = 0
                for element in danmaku_elements[-pre_max:]:  # 只处理最新的几条
                    try:
                        # 生成元素ID
                        element_id = self._generate_element_id(element)
                        if element_id in self._processed_messages:
                            self.logger.info(f"[计时] 跳过已处理的元素: {element_id}")
                            continue

                        # 提取弹幕数据（从 data 属性获取）
                        username_search_start = time.time()
                        try:
                            # 从 data-* 属性中提取信息
                            text = element.get_attribute("data-danmaku") or ""
                            username = element.get_attribute("data-uname") or "未知用户"
                            user_id = element.get_attribute("data-uid") or ""

                            self.logger.info(f"提取到弹幕信息: 用户={username}, ID={user_id}, 内容={text}")
                            if not text:
                                self.logger.warning(f"弹幕内容为空，跳过处理: {element_id}")
                                continue
                            elif not username:
                                self.logger.warning(f"用户名为空，使用默认值: {element_id}")
                                continue
                            elif not user_id:
                                self.logger.warning(f"用户ID为空，使用默认值: {element_id}")
                                continue
                        except Exception as e:
                            self.logger.warning(f"提取弹幕属性失败: {e}")
                            continue

                        username_search_end = time.time()
                        self.logger.info(
                            f"[计时] 提取用户信息耗时: {(username_search_end - username_search_start) * 1000:.1f}ms"
                        )

                        message = DanmakuMessage(
                            username=username,
                            text=text,
                            timestamp=time.time(),
                            user_id=user_id,
                            element_id=element_id,
                            message_type="danmaku",
                        )
                        messages.append(message)
                        self._processed_messages.add(element_id)
                        processed_count += 1

                    except NoSuchElementException:
                        self.logger.info("[计时] 弹幕元素结构变化，跳过")
                        continue  # 元素结构可能变化，跳过
                    except Exception as e:
                        self.logger.info(f"[计时] 处理单个弹幕元素时出错: {e}")
                        continue

                process_danmaku_end = time.time()
                self.logger.info(
                    f"[计时] 处理 {processed_count} 条弹幕耗时: {(process_danmaku_end - process_danmaku_start) * 1000:.1f}ms"
                )

                # 计时：获取礼物消息
                gift_search_start = time.time()
                gift_elements = self.driver.find_elements(By.CSS_SELECTOR, self.gift_selector)
                gift_search_end = time.time()
                self.logger.info(
                    f"[计时] 查找礼物元素耗时: {(gift_search_end - gift_search_start) * 1000:.1f}ms, 找到 {len(gift_elements)} 个元素"
                )
                # 注释：礼物处理暂时禁用
                # print(f"gift {gift_elements}")
                # for element in gift_elements[-self.max_messages_per_check :]:
                #     gift_element_start = time.time()
                #     try:
                #         element_id = self._generate_element_id(element)
                #         if element_id in self._processed_messages:
                #             continue

                #         gift_text_elem = element.find_element(By.CSS_SELECTOR, self.gift_text_selector)
                #         gift_text = gift_text_elem.text.strip() if gift_text_elem else ""
                #         print(gift_text)
                #         if gift_text:
                #             # 解析礼物信息

                #             username, gift_name, gift_count = self._parse_gift_text(gift_text)

                #             message = DanmakuMessage(
                #                 username=username,
                #                 text=gift_text,
                #                 timestamp=time.time(),
                #                 element_id=element_id,
                #                 message_type="gift",
                #                 gift_name=gift_name,
                #                 gift_count=gift_count,
                #             )
                #             messages.append(message)
                #             self._processed_messages.add(element_id)
                #             gift_processed_count += 1

                #             gift_element_end = time.time()
                #             self.logger.info(
                #                 f"[计时] 处理礼物元素耗时: {(gift_element_end - gift_element_start) * 1000:.1f}ms - {username}: {gift_name}x{gift_count}"
                #             )

                #     except NoSuchElementException:
                #         continue
                #     except Exception as e:
                #         self.logger.info(f"[计时] 处理单个礼物元素时出错: {e}")
                #         continue

            except Exception as e:
                self.logger.warning(f"[计时] 获取页面元素时出错: {e}")

            get_msg_end_time = time.time()
            self.logger.info(
                f"[计时] _get_messages 总耗时: {(get_msg_end_time - get_msg_start_time) * 1000:.1f}ms, 获得 {len(messages)} 条消息"
            )
            return messages

        try:
            # 计时：线程池执行
            executor_start_time = time.time()
            messages = await asyncio.get_event_loop().run_in_executor(None, _get_messages)
            executor_end_time = time.time()
            self.logger.info(f"[计时] 线程池执行耗时: {(executor_end_time - executor_start_time) * 1000:.1f}ms")

            if messages:
                # 计时：消息处理
                msg_process_start = time.time()
                self.logger.info(f"收到 {len(messages)} 条新消息")
                for message in messages:
                    try:
                        msg_create_start = time.time()
                        message_base = await self._create_message_base(message)
                        msg_create_end = time.time()
                        self.logger.info(
                            f"[计时] 创建 MessageBase 耗时: {(msg_create_end - msg_create_start) * 1000:.1f}ms"
                        )
                        if message_base:
                            self.logger.debug(f"成功创建消息: {message.username}: {message.text}")
                            # await self.core.send_to_maicore(message_base)  # 取消注释以启用消息发送
                    except Exception as e:
                        self.logger.error(f"处理消息时出错: {message} - {e}", exc_info=True)

                msg_process_end = time.time()
                self.logger.info(
                    f"[计时] 处理 {len(messages)} 条消息耗时: {(msg_process_end - msg_process_start) * 1000:.1f}ms"
                )
            else:
                self.logger.info("[计时] 没有新的消息")

        except Exception as e:
            self.logger.warning(f"获取弹幕时发生错误: {e}")

        fetch_end_time = time.time()
        self.logger.info(f"[计时] 整个获取弹幕流程耗时: {(fetch_end_time - fetch_start_time) * 1000:.1f}ms")

    def _generate_element_id(self, element) -> str:
        """为元素生成唯一ID"""
        try:  # 使用元素的位置和文本内容生成ID
            location = element.location
            size = element.size
            text = element.text
            content = f"{location['x']},{location['y']},{size['width']},{size['height']},{text}"
            return hashlib.md5(content.encode()).hexdigest()[:12]
        except Exception:
            return f"elem_{int(time.time() * 1000) % 100000}"

    def _parse_gift_text(self, gift_text: str) -> tuple[str, str, int]:
        """解析礼物文本，提取用户名、礼物名称和数量"""
        try:
            # 简单的礼物文本解析逻辑，可根据实际页面结构调整
            # 示例: "用户名 投喂了 1个 辣条"
            parts = gift_text.split()
            username = parts[0] if parts else "未知用户"
            gift_name = "礼物"
            gift_count = 1  # 尝试提取礼物名称和数量
            for i, part in enumerate(parts):
                if "个" in part and i > 0:
                    try:
                        gift_count = int(part.replace("个", ""))
                        if i + 1 < len(parts):
                            gift_name = parts[i + 1]
                    except ValueError:
                        pass
                    break

            return username, gift_name, gift_count
        except Exception:
            return "未知用户", "礼物", 1

    def _cleanup_processed_messages(self):
        """清理过期的已处理消息记录"""
        # 保留最近的1000条记录，防止内存占用过多
        if len(self._processed_messages) > 1000:
            # 转换为列表，保留后500条
            messages_list = list(self._processed_messages)
            self._processed_messages = set(messages_list[-500:])
            self.logger.info(f"清理已处理消息记录，保留 {len(self._processed_messages)} 条")

    async def _create_message_base(self, message: DanmakuMessage) -> Optional[MessageBase]:
        """根据弹幕数据创建 MessageBase 对象"""
        if not message.text:
            return None

        # 用户ID生成
        user_id = self.config.get("default_user_id", f"bili_{message.username}")

        # --- User Info ---
        user_info = UserInfo(
            platform=self.core.platform,
            user_id=str(user_id),
            user_nickname=message.username,
            user_cardname=self.config.get("user_cardname", ""),
        )

        # --- Group Info (Conditional) ---
        group_info: Optional[GroupInfo] = None
        if self.config.get("enable_group_info", False):
            group_info = GroupInfo(
                platform=self.core.platform,
                group_id=self.config.get("group_id", self.room_id),
                group_name=self.config.get("group_name", f"bili_{self.room_id}"),
            )

        # --- Format Info ---
        format_info = FormatInfo(
            content_format=self.config.get("content_format", ["text"]),
            accept_format=self.config.get("accept_format", ["text"]),
        )

        # --- Additional Config ---
        additional_config = self.config.get("additional_config", {}).copy()
        additional_config.update(
            {
                "source": "bili_danmaku_selenium_plugin",
                "sender_name": message.username,
                "message_type": message.message_type,
                "maimcore_reply_probability_gain": 1,
            }
        )

        if message.message_type == "gift":
            additional_config.update({"gift_name": message.gift_name, "gift_count": message.gift_count})

        # --- Template Info (Conditional & Modification) ---
        final_template_info_value = None
        if self.config.get("enable_template_info", False) and self.template_items:
            # 获取原始模板项 (创建副本)
            modified_template_items = (self.template_items or {}).copy()

            # 获取并追加 Prompt 上下文
            additional_context = ""
            prompt_ctx_service = self.core.get_service("prompt_context")
            if prompt_ctx_service:
                try:
                    additional_context = await prompt_ctx_service.get_formatted_context(tags=self.context_tags)
                    if additional_context:
                        self.logger.info(f"获取到聚合 Prompt 上下文: '{additional_context[:100]}...'")
                except Exception as e:
                    self.logger.error(f"调用 prompt_context 服务时出错: {e}", exc_info=True)

            # 修改主 Prompt (如果上下文非空且主 Prompt 存在)
            main_prompt_key = "reasoning_prompt_main"
            if additional_context and main_prompt_key in modified_template_items:
                original_prompt = modified_template_items[main_prompt_key]
                modified_template_items[main_prompt_key] = original_prompt + "\n" + additional_context
                self.logger.info(f"已将聚合上下文追加到 '{main_prompt_key}'。")

            # 使用修改后的模板项构建最终结构
            final_template_info_value = {"template_items": modified_template_items}

        # --- Base Message Info ---
        message_info = BaseMessageInfo(
            platform=self.core.platform,
            message_id=f"bili_selenium_{self.room_id}_{int(message.timestamp)}_{message.element_id}",
            time=int(message.timestamp),
            user_info=user_info,
            group_info=group_info,
            template_info=final_template_info_value,
            format_info=format_info,
            additional_config=additional_config,
        )

        # --- Message Segment ---
        message_segment = Seg(type="text", data=message.text)

        # --- Final MessageBase ---
        return MessageBase(message_info=message_info, message_segment=message_segment, raw_message=message.text)


# --- Plugin Entry Point ---
plugin_entrypoint = BiliDanmakuSeleniumPlugin
