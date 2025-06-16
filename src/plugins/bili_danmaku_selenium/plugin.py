# src/plugins/bili_danmaku_selenium/plugin.py

import asyncio
import time
import hashlib
import signal
import threading
import json
import os
from pathlib import Path
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
from maim_message import MessageBase, UserInfo, BaseMessageInfo, GroupInfo, FormatInfo, Seg, TemplateInfo


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


class MessageCacheService:
    """消息缓存服务，用于存储和检索消息"""

    def __init__(self, max_cache_size: int = 1000):
        """
        初始化消息缓存服务

        Args:
            max_cache_size: 最大缓存消息数量
        """
        self.cache: Dict[str, MessageBase] = {}
        self.max_cache_size = max_cache_size
        self.access_order: List[str] = []  # 用于LRU淘汰

    def cache_message(self, message: MessageBase):
        """
        缓存消息

        Args:
            message: 要缓存的消息
        """
        message_id = message.message_info.message_id

        # 如果消息已存在，更新访问顺序
        if message_id in self.cache:
            self.access_order.remove(message_id)
            self.access_order.append(message_id)
            # 更新消息内容
            self.cache[message_id] = message
        else:
            # 如果缓存已满，删除最旧的消息
            if len(self.cache) >= self.max_cache_size:
                oldest_id = self.access_order.pop(0)
                del self.cache[oldest_id]

            # 添加新消息
            self.cache[message_id] = message
            self.access_order.append(message_id)

    def get_message(self, message_id: str) -> Optional[MessageBase]:
        """
        根据消息ID获取缓存的消息

        Args:
            message_id: 消息ID

        Returns:
            缓存的消息，如果不存在则返回None
        """
        if message_id in self.cache:
            # 更新访问顺序（LRU）
            self.access_order.remove(message_id)
            self.access_order.append(message_id)
            return self.cache[message_id]
        return None

    def clear_cache(self):
        """清空缓存"""
        self.cache.clear()
        self.access_order.clear()

    def get_cache_size(self) -> int:
        """获取当前缓存大小"""
        return len(self.cache)


class BiliDanmakuSeleniumPlugin(BasePlugin):
    """Bilibili 直播弹幕插件（Selenium版），使用浏览器直接获取弹幕和礼物。"""

    def __init__(self, core: AmaidesuCore, config: Dict[str, Any]):
        super().__init__(core, config)

        # --- 显式加载自己目录下的 config.toml ---
        self.config = self.plugin_config
        self.enabled = self.config.get("enabled", True)

        # --- 依赖检查 ---
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

        # --- 弹幕文件保存与读取配置 ---
        self.enable_danmaku_save = self.config.get("enable_danmaku_save", False)
        self.danmaku_save_file = self.config.get("danmaku_save_file", f"danmaku_{self.room_id}.jsonl")
        self.enable_danmaku_load = self.config.get("enable_danmaku_load", False)
        self.danmaku_load_file = self.config.get("danmaku_load_file", "")
        self.skip_initial_danmaku = self.config.get("skip_initial_danmaku", True)

        # --- 创建data目录 ---
        self.data_dir = Path(__file__).parent / "data"
        self.data_dir.mkdir(exist_ok=True)

        # --- 弹幕文件路径设置 ---
        if self.enable_danmaku_save and self.danmaku_save_file:
            self.save_file_path = self.data_dir / self.danmaku_save_file
        else:
            self.save_file_path = None

        if self.enable_danmaku_load and self.danmaku_load_file:
            self.load_file_path = self.data_dir / self.danmaku_load_file
        else:
            self.load_file_path = None

        # --- Selenium 配置 ---
        self.headless = self.config.get("headless", True)
        self.webdriver_timeout = self.config.get("webdriver_timeout", 30)
        self.page_load_timeout = self.config.get("page_load_timeout", 30)
        self.implicit_wait = self.config.get("implicit_wait", 10)

        # --- 选择器配置 ---
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
            self.logger.info(f"Will fetch context with tags: {self.context_tags}")

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

        # --- 状态变量 ---
        self.driver = None
        self.monitoring_task = None
        self.stop_event = asyncio.Event()
        self.processed_messages: Set[str] = set()
        self.last_cleanup_time = time.time()

        # --- 新增状态变量 ---
        self.is_initial_load = True  # 标记是否为初始加载
        self.initial_load_complete = False  # 标记初始加载是否完成
        self.loaded_danmaku_queue = []  # 从文件读取的弹幕队列
        self.loaded_danmaku_index = 0  # 当前发送的弹幕索引

        # --- 纯文件模式判断 ---
        # 如果启用了文件读取，则进入纯文件模式（不启动浏览器，按时间轴重放）
        self.file_only_mode = self.enable_danmaku_load
        if self.file_only_mode:
            self.logger.info("进入纯文件模式：将按时间轴重放文件中的弹幕，不启动浏览器")

        # --- 初始化消息缓存服务 ---
        cache_size = self.config.get("message_cache_size", 1000)
        self.message_cache_service = MessageCacheService(max_cache_size=cache_size)

        # --- 日志记录配置信息 ---
        if self.enable_danmaku_save:
            self.logger.info(f"弹幕保存已启用，文件: {self.save_file_path}")
        if self.enable_danmaku_load:
            self.logger.info(f"弹幕读取已启用，文件: {self.load_file_path}")
        if self.skip_initial_danmaku:
            self.logger.info("跳过初始弹幕已启用")

        # --- 添加退出机制相关属性 ---
        self.shutdown_timeout = self.config.get("shutdown_timeout", 30)  # 30秒超时
        self.cleanup_lock = threading.Lock()
        self.is_shutting_down = False

        # --- 注册信号处理器 ---
        self._setup_signal_handlers()

    def _setup_signal_handlers(self):
        """设置信号处理器以实现优雅退出"""

        def signal_handler(signum, frame):
            self.logger.info(f"接收到信号 {signum}，开始优雅关闭...")
            asyncio.create_task(self._graceful_shutdown())

        # 注册常见的退出信号
        try:
            signal.signal(signal.SIGINT, signal_handler)  # Ctrl+C
            signal.signal(signal.SIGTERM, signal_handler)  # 终止信号
            if hasattr(signal, "SIGBREAK"):  # Windows
                signal.signal(signal.SIGBREAK, signal_handler)
        except Exception as e:
            self.logger.warning(f"设置信号处理器失败: {e}")

    async def _graceful_shutdown(self):
        """优雅关闭流程"""
        if self.is_shutting_down:
            return

        self.is_shutting_down = True
        self.logger.info("开始优雅关闭流程...")

        try:
            # 设置停止事件
            self.stop_event.set()

            # 等待监控任务完成
            if self.monitoring_task and not self.monitoring_task.done():
                self.logger.info("等待监控任务完成...")
                try:
                    await asyncio.wait_for(self.monitoring_task, timeout=self.shutdown_timeout)
                except asyncio.TimeoutError:
                    self.logger.warning(f"监控任务在 {self.shutdown_timeout} 秒内未完成，强制取消")
                    self.monitoring_task.cancel()
                    try:
                        await self.monitoring_task
                    except asyncio.CancelledError:
                        pass

            # 执行清理
            await self.cleanup()
            self.logger.info("优雅关闭完成")

        except Exception as e:
            self.logger.error(f"优雅关闭过程中发生错误: {e}")
        finally:
            self.is_shutting_down = False

    async def setup(self):
        await super().setup()
        if not self.enabled:
            return

        try:
            # 注册消息缓存服务到 core
            self.core.register_service("message_cache", self.message_cache_service)
            self.logger.info("消息缓存服务已注册到 AmaidesuCore")

            # 如果启用了从文件读取弹幕，加载弹幕数据
            if self.enable_danmaku_load and self.load_file_path:
                await self._load_danmaku_from_file()

            # 只有在非纯文件模式下才创建 WebDriver
            if not self.file_only_mode:
                # 创建 WebDriver
                await self._create_webdriver()
            else:
                self.logger.info("纯文件模式：跳过 WebDriver 创建")

            # 启动后台监控任务
            self.monitoring_task = asyncio.create_task(
                self._run_monitoring_loop(), name=f"BiliDanmakuSelenium_{self.room_id}"
            )

            if self.file_only_mode:
                self.logger.info(
                    f"启动弹幕文件重放任务 (文件: {self.load_file_path.name if self.load_file_path else 'N/A'})..."
                )
            else:
                self.logger.info(f"启动 Bilibili Selenium 弹幕监控任务 (房间: {self.room_id})...")

        except Exception as e:
            self.logger.error(f"设置 BiliDanmakuSeleniumPlugin 时发生错误: {e}", exc_info=True)
            self.enabled = False

    async def cleanup(self):
        """清理资源"""
        with self.cleanup_lock:
            if self.is_shutting_down and hasattr(self, "_cleanup_done"):
                return  # 避免重复清理

            self.logger.info("开始清理 BiliDanmakuSelenium 插件资源...")

            try:
                # 设置停止事件
                self.stop_event.set()

                # 取消监控任务
                if self.monitoring_task and not self.monitoring_task.done():
                    self.logger.info("取消监控任务...")
                    self.monitoring_task.cancel()
                    try:
                        await asyncio.wait_for(self.monitoring_task, timeout=10)
                    except (asyncio.CancelledError, asyncio.TimeoutError):
                        self.logger.info("监控任务已取消或超时")

                # 清理 WebDriver
                if self.driver:
                    self.logger.info("关闭 WebDriver...")
                    try:
                        # 设置较短的超时时间
                        def quit_driver():
                            try:
                                self.driver.quit()
                            except Exception as e:
                                self.logger.warning(f"关闭 WebDriver 时出错: {e}")

                        # 在单独线程中执行 WebDriver 关闭，避免阻塞
                        quit_thread = threading.Thread(target=quit_driver)
                        quit_thread.daemon = True
                        quit_thread.start()
                        quit_thread.join(timeout=5)  # 5秒超时

                        if quit_thread.is_alive():
                            self.logger.warning("WebDriver 关闭超时，可能存在僵尸进程")
                        else:
                            self.logger.info("WebDriver 已成功关闭")

                    except Exception as e:
                        self.logger.error(f"关闭 WebDriver 时发生异常: {e}")
                    finally:
                        self.driver = None

                # 清理缓存服务
                if self.message_cache_service:
                    try:
                        self.message_cache_service.clear_cache()
                        self.logger.info("消息缓存已清理")
                    except Exception as e:
                        self.logger.warning(f"清理消息缓存时出错: {e}")

                # 清理处理过的消息集合
                self.processed_messages.clear()

                self.logger.info("BiliDanmakuSelenium 插件资源清理完成")
                self._cleanup_done = True

            except Exception as e:
                self.logger.error(f"清理过程中发生错误: {e}")

    async def _create_webdriver(self):
        """创建 WebDriver"""

        def _create_driver():
            options = ChromeOptions()
            # 根据配置设置headless模式
            if self.headless:
                self.logger.info("使用无头模式运行浏览器")
                options.add_argument("--headless")
            else:
                self.logger.info("使用有界面模式运行浏览器")

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
            if self.config.get("chromedriver_path"):
                try:
                    chromedriver_path = self.config.get("chromedriver_path")
                    self.logger.info(f"使用配置的 ChromeDriver 路径: {chromedriver_path}")
                    service = Service(executable_path=chromedriver_path)
                    driver = webdriver.Chrome(service=service, options=options)
                except Exception as e:
                    self.logger.warning(f"使用配置的 ChromeDriver 路径失败: {e}，尝试其他方式")
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
            elif WEBDRIVER_MANAGER_AVAILABLE:
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
            # 确保在失败时清理已创建的driver
            if self.driver:
                try:
                    await asyncio.get_event_loop().run_in_executor(None, self.driver.quit)
                    self.logger.info("已清理失败的 WebDriver")
                except Exception as cleanup_error:
                    self.logger.warning(f"清理失败的 WebDriver 时出错: {cleanup_error}")
                finally:
                    self.driver = None
            raise

    async def _run_monitoring_loop(self):
        """运行监控循环"""
        if self.file_only_mode:
            self.logger.info(f"开始按时间轴重放弹幕文件: {self.load_file_path}")
            await self._run_file_replay_loop()
        else:
            self.logger.info(f"开始监控 Bilibili 直播间 {self.room_id} 的弹幕...")
            await self._run_live_monitoring_loop()

    async def _run_file_replay_loop(self):
        """运行文件重放循环"""
        if not self.loaded_danmaku_queue:
            self.logger.warning("没有加载到弹幕数据，重放任务结束")
            return

        self.logger.info(f"开始重放 {len(self.loaded_danmaku_queue)} 条弹幕")

        try:
            # 获取第一条弹幕的时间作为起始时间
            first_message_time = self.loaded_danmaku_queue[0].message_info.time if self.loaded_danmaku_queue else 0
            replay_start_time = time.time()

            for i, message_base in enumerate(self.loaded_danmaku_queue):
                if self.stop_event.is_set() or self.is_shutting_down:
                    self.logger.info("重放被中断")
                    break

                try:
                    # 计算应该等待的时间
                    message_time = message_base.message_info.time
                    expected_elapsed = message_time - first_message_time
                    actual_elapsed = time.time() - replay_start_time

                    wait_time = expected_elapsed - actual_elapsed
                    if wait_time > 0:
                        self.logger.debug(f"等待 {wait_time:.2f} 秒后发送第 {i + 1} 条弹幕")
                        try:
                            await asyncio.wait_for(self.stop_event.wait(), timeout=wait_time)
                            break  # 如果收到停止信号，退出循环
                        except asyncio.TimeoutError:
                            pass  # 超时继续

                    # 发送弹幕
                    self.message_cache_service.cache_message(message_base)
                    await self.core.send_to_maicore(message_base)

                    self.logger.debug(
                        f"重放弹幕 ({i + 1}/{len(self.loaded_danmaku_queue)}): {message_base.raw_message[:50] if message_base.raw_message else '(无内容)'}"
                    )

                except Exception as e:
                    self.logger.error(f"重放第 {i + 1} 条弹幕时出错: {e}")
                    continue

            self.logger.info("弹幕文件重放完成")

        except asyncio.CancelledError:
            self.logger.info("文件重放循环被取消")
        except Exception as e:
            self.logger.error(f"文件重放循环发生错误: {e}", exc_info=True)
        finally:
            self.logger.info("文件重放循环已结束")

    async def _run_live_monitoring_loop(self):
        """运行实时监控循环"""
        consecutive_errors = 0
        max_consecutive_errors = 5

        # 等待一段时间以让页面完全加载，然后标记初始加载完成
        if self.skip_initial_danmaku:
            await asyncio.sleep(5)  # 等待5秒让页面加载完成
            self.initial_load_complete = True
            self.logger.info("初始加载完成，开始处理新弹幕")
        else:
            self.initial_load_complete = True

        try:
            while not self.stop_event.is_set():
                try:
                    # 检查是否正在关闭
                    if self.is_shutting_down:
                        self.logger.info("检测到关闭信号，退出监控循环")
                        break

                    # 如果启用了从文件读取弹幕，优先发送文件中的弹幕
                    if self.enable_danmaku_load and self.loaded_danmaku_queue:
                        await self._send_loaded_danmaku()

                    await self._fetch_and_process_messages()
                    consecutive_errors = 0  # 重置错误计数

                    # 定期清理已处理消息记录
                    current_time = time.time()
                    if current_time - self.last_cleanup_time > 300:  # 5分钟清理一次
                        self._cleanup_processed_messages()
                        self.last_cleanup_time = current_time

                except Exception as e:
                    consecutive_errors += 1
                    self.logger.error(f"监控循环中发生错误 ({consecutive_errors}/{max_consecutive_errors}): {e}")

                    # 如果连续错误过多，尝试重新创建 WebDriver
                    if consecutive_errors >= max_consecutive_errors:
                        self.logger.warning("连续错误过多，尝试重新创建 WebDriver...")
                        try:
                            await self._recreate_webdriver()
                            consecutive_errors = 0
                        except Exception as recreate_error:
                            self.logger.error(f"重新创建 WebDriver 失败: {recreate_error}")
                            # 等待更长时间后再试
                            await asyncio.sleep(30)

                # 使用可中断的等待
                try:
                    await asyncio.wait_for(self.stop_event.wait(), timeout=self.poll_interval)
                    break  # 收到停止信号
                except asyncio.TimeoutError:
                    continue  # 超时，继续循环
                except asyncio.CancelledError:
                    self.logger.info("监控任务被取消")
                    break

        except asyncio.CancelledError:
            self.logger.info("监控循环被取消")
        except Exception as e:
            self.logger.error(f"监控循环发生未预期的错误: {e}", exc_info=True)
        finally:
            self.logger.info("监控循环已结束")

    async def _recreate_webdriver(self):
        """重新创建WebDriver"""
        try:
            # 先清理现有的driver
            if self.driver:
                try:
                    await asyncio.get_event_loop().run_in_executor(None, self.driver.quit)
                except Exception:
                    pass  # 忽略清理时的错误
                finally:
                    self.driver = None

            # 重新创建
            await self._create_webdriver()
            self.logger.info("WebDriver 重新创建成功")

        except Exception as e:
            self.logger.error(f"重新创建 WebDriver 失败: {e}", exc_info=True)
            # 标记为禁用，避免继续尝试
            self.enabled = False

    async def _fetch_and_process_messages(self):
        """获取并处理弹幕消息"""
        # 在纯文件模式下跳过实时弹幕获取
        if self.file_only_mode:
            return

        fetch_start_time = time.time()
        self.logger.debug(f"[计时] 开始获取弹幕消息 - {fetch_start_time:.3f}")

        if not self.driver:
            self.logger.warning("WebDriver 未初始化，跳过本次检查。")
            return

        def _get_messages():
            get_msg_start_time = time.time()
            self.logger.debug(f"[计时] 开始执行 _get_messages - {get_msg_start_time:.3f}")

            messages = []
            try:
                # 计时：获取弹幕元素
                danmaku_search_start = time.time()
                danmaku_elements = self.driver.find_elements(By.CSS_SELECTOR, self.danmaku_item_selector)
                danmaku_search_end = time.time()
                self.logger.debug(
                    f"[计时] 查找弹幕元素耗时: {(danmaku_search_end - danmaku_search_start) * 1000:.1f}ms, 找到 {len(danmaku_elements)} 个元素"
                )

                pre_max = (
                    self.max_messages_per_check
                    if len(danmaku_elements) > self.max_messages_per_check
                    else len(danmaku_elements)
                )
                self.logger.debug(f"[计时] 准备处理最新的 {pre_max} 条弹幕")

                # 计时：处理弹幕元素
                process_danmaku_start = time.time()
                processed_count = 0
                for element in danmaku_elements[-pre_max:]:  # 只处理最新的几条
                    try:
                        # 生成元素ID
                        element_id = self._generate_element_id(element)
                        if element_id in self.processed_messages:
                            # self.logger.debug(f"[计时] 跳过已处理的元素: {element_id}")
                            continue

                        # 提取弹幕数据（从 data 属性获取）
                        username_search_start = time.time()
                        try:
                            # 从 data-* 属性中提取信息
                            text = element.get_attribute("data-danmaku") or ""
                            username = element.get_attribute("data-uname") or "未知用户"
                            user_id = element.get_attribute("data-uid") or ""

                            self.logger.debug(f"提取到弹幕信息: 用户={username}, ID={user_id}, 内容={text}")
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
                        self.logger.debug(
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
                        self.processed_messages.add(element_id)
                        processed_count += 1

                    except NoSuchElementException:
                        self.logger.debug("[计时] 弹幕元素结构变化，跳过")
                        continue  # 元素结构可能变化，跳过
                    except Exception as e:
                        self.logger.warning(f"[计时] 处理单个弹幕元素时出错: {e}")
                        continue

                process_danmaku_end = time.time()
                self.logger.debug(
                    f"[计时] 处理 {processed_count} 条弹幕耗时: {(process_danmaku_end - process_danmaku_start) * 1000:.1f}ms"
                )

            except Exception as e:
                self.logger.warning(f"[计时] 获取页面元素时出错: {e}")

            get_msg_end_time = time.time()
            self.logger.debug(
                f"[计时] _get_messages 总耗时: {(get_msg_end_time - get_msg_start_time) * 1000:.1f}ms, 获得 {len(messages)} 条消息"
            )
            return messages

        try:
            # 计时：线程池执行
            executor_start_time = time.time()
            messages = await asyncio.get_event_loop().run_in_executor(None, _get_messages)
            executor_end_time = time.time()
            self.logger.debug(f"[计时] 线程池执行耗时: {(executor_end_time - executor_start_time) * 1000:.1f}ms")

            if messages:
                # 如果启用了跳过初始弹幕且还未完成初始加载，则跳过这些消息
                if self.skip_initial_danmaku and not self.initial_load_complete:
                    self.logger.info(f"跳过初始加载的 {len(messages)} 条弹幕")
                    return

                # 计时：消息处理
                msg_process_start = time.time()
                self.logger.info(f"收到 {len(messages)} 条新消息")
                for message in messages:
                    try:
                        msg_create_start = time.time()
                        message_base = await self._create_message_base(message)
                        msg_create_end = time.time()
                        self.logger.debug(
                            f"[计时] 创建 MessageBase 耗时: {(msg_create_end - msg_create_start) * 1000:.1f}ms"
                        )
                        if message_base:
                            self.logger.debug(f"成功创建消息: {message.username}: {message.text}")

                            # 将消息缓存到消息缓存服务中
                            self.message_cache_service.cache_message(message_base)
                            self.logger.debug(f"消息已缓存: {message_base.message_info.message_id}")

                            # 发送消息
                            # await self.core.send_to_maicore(message_base)

                            # 如果启用了弹幕保存，将消息保存到文件
                            if self.enable_danmaku_save and self.save_file_path:
                                await self._save_danmaku_to_file(message_base)

                    except Exception as e:
                        self.logger.error(f"处理消息时出错: {message} - {e}", exc_info=True)

                msg_process_end = time.time()
                self.logger.debug(
                    f"[计时] 处理 {len(messages)} 条消息耗时: {(msg_process_end - msg_process_start) * 1000:.1f}ms"
                )
            else:
                self.logger.debug("[计时] 没有新的消息")

        except Exception as e:
            self.logger.warning(f"获取弹幕时发生错误: {e}")

        fetch_end_time = time.time()
        self.logger.debug(f"[计时] 整个获取弹幕流程耗时: {(fetch_end_time - fetch_start_time) * 1000:.1f}ms")

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

    def _cleanup_processed_messages(self):
        """清理过期的已处理消息记录"""
        # 保留最近的1000条记录，防止内存占用过多
        if len(self.processed_messages) > 1000:
            # 转换为列表，保留后500条
            messages_list = list(self.processed_messages)
            self.processed_messages = set(messages_list[-500:])
            self.logger.info(f"清理已处理消息记录，保留 {len(self.processed_messages)} 条")

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
            final_template_info_value = TemplateInfo(
                template_items=modified_template_items,
                template_name=self.config.get("template_name", f"bili_{self.room_id}"),
                template_default=False,
            )

        # --- Base Message Info ---
        message_info = BaseMessageInfo(
            platform=self.core.platform,
            message_id=f"bili_selenium_{self.room_id}_{int(message.timestamp)}_{message.element_id}",
            time=message.timestamp,
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

    async def _load_danmaku_from_file(self):
        """从文件加载弹幕数据"""
        if not self.load_file_path or not self.load_file_path.exists():
            self.logger.warning(f"弹幕文件不存在: {self.load_file_path}")
            return

        try:
            with open(self.load_file_path, "r", encoding="utf-8") as file:
                for line_num, line in enumerate(file, 1):
                    if not line.strip():
                        continue
                    try:
                        # 解析JSON行
                        danmaku_data = json.loads(line.strip())

                        # 将字典转换为MessageBase对象
                        from maim_message import MessageBase

                        message_base = MessageBase.from_dict(danmaku_data)
                        self.loaded_danmaku_queue.append(message_base)

                    except json.JSONDecodeError as e:
                        self.logger.warning(f"解析第{line_num}行JSON失败: {e}")
                    except Exception as e:
                        self.logger.warning(f"处理第{line_num}行数据失败: {e}")

            self.logger.info(f"成功从文件加载 {len(self.loaded_danmaku_queue)} 条弹幕")

        except Exception as e:
            self.logger.error(f"读取弹幕文件失败: {e}")

    async def _save_danmaku_to_file(self, message_base: MessageBase):
        """将弹幕保存到文件"""
        if not self.save_file_path:
            return

        try:
            # 将MessageBase转换为字典
            message_dict = message_base.to_dict()

            # 异步写入文件
            def write_to_file():
                with open(self.save_file_path, "a", encoding="utf-8") as file:
                    json.dump(message_dict, file, ensure_ascii=False)
                    file.write("\n")

            await asyncio.get_event_loop().run_in_executor(None, write_to_file)
            self.logger.debug(f"弹幕已保存到文件: {message_base.message_info.message_id}")

        except Exception as e:
            self.logger.error(f"保存弹幕到文件失败: {e}")

    async def _send_loaded_danmaku(self):
        """发送从文件读取的弹幕"""
        if self.loaded_danmaku_index >= len(self.loaded_danmaku_queue):
            return

        try:
            # 获取当前要发送的弹幕
            message_base = self.loaded_danmaku_queue[self.loaded_danmaku_index]
            self.loaded_danmaku_index += 1

            # 缓存消息
            self.message_cache_service.cache_message(message_base)

            # 发送消息
            await self.core.send_to_maicore(message_base)

            self.logger.debug(
                f"发送文件弹幕: {message_base.raw_message[:50] if message_base.raw_message else '(无内容)'}"
            )

        except Exception as e:
            self.logger.error(f"发送文件弹幕失败: {e}")


# --- Plugin Entry Point ---
plugin_entrypoint = BiliDanmakuSeleniumPlugin
