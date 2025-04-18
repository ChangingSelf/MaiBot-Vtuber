import asyncio

# import logging # 移除标准logging导入
import tomllib
import os
import time
import base64
from io import BytesIO
from typing import Any, Dict, Optional

# 导入全局logger
from src.utils.logger import logger

# --- 依赖检查 ---
try:
    import mss
    import mss.tools
except ImportError:
    mss = None

try:
    # 导入 openai 库
    import openai
    from openai import AsyncOpenAI  # 明确导入 AsyncOpenAI
except ImportError:
    openai = None
    AsyncOpenAI = None  # type: ignore

try:
    from PIL import Image
except ImportError:
    Image = None

from core.plugin_manager import BasePlugin
from core.amaidesu_core import AmaidesuCore


# --- Helper Function ---
def load_plugin_config() -> Dict[str, Any]:
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
                    logger.error("toml package needed for Python < 3.11.")
                    return {}
                except FileNotFoundError:
                    logger.warning(f"Config file not found: {config_path}")
                    return {}
    except Exception as e:
        logger.error(f"Error loading config: {config_path}: {e}", exc_info=True)
        return {}


# --- Plugin Class ---
class ScreenMonitorPlugin(BasePlugin):
    """
    定期截屏，通过 OpenAI 兼容接口调用 VL 模型获取描述，
    并将最新描述注册为 Prompt 上下文。
    !!! 警告：存在隐私风险和 API 成本 !!!
    """

    _is_vup_next_plugin: bool = True

    def __init__(self, core: VupNextCore, plugin_config: Dict[str, Any]):
        super().__init__(core, plugin_config)
        # 移除 self.logger 的初始化

        loaded_config = load_plugin_config()
        self.config = loaded_config.get("screen_monitor", {})
        self.enabled = self.config.get("enabled", True)

        # --- 检查核心依赖 ---
        # 更新依赖检查，需要 openai
        if mss is None or openai is None or Image is None:
            missing = [lib for lib, name in [(mss, "mss"), (openai, "openai"), (Image, "Pillow")] if lib is None]
            logger.error(
                f"缺少必要的库: {', '.join(missing)}。请运行 `pip install mss openai Pillow`。ScreenMonitorPlugin 已禁用。"
            )
            self.enabled = False
            return

        if not self.enabled:
            logger.warning("ScreenMonitorPlugin 在配置中被禁用。")
            return

        # --- 加载配置 (使用新配置项) ---
        self.interval = self.config.get("screenshot_interval_seconds", 10)
        self.api_key = self.config.get("api_key", None)  # 通用 API Key
        self.base_url = self.config.get("openai_compatible_base_url", None)  # OpenAI 兼容 URL
        self.model_name = self.config.get("model_name", "qwen-vl-plus")  # 模型名称
        self.vl_prompt = self.config.get("vl_prompt", "请用一句话简洁描述这张图片的主要内容和活动窗口标题。")
        self.timeout_seconds = self.config.get("request_timeout", 20)  # 请求超时
        self.context_provider_name = self.config.get("context_provider_name", "screen_content_latest")
        self.context_priority = self.config.get("context_priority", 20)

        # --- 检查关键配置 ---
        if not self.api_key or "YOUR_API_KEY_HERE" in self.api_key:
            logger.error("API Key 未在 config.toml 中配置！ScreenMonitorPlugin 已禁用。")
            self.enabled = False
            return
        if not self.base_url:
            logger.error(
                "OpenAI 兼容 Base URL (openai_compatible_base_url) 未在 config.toml 中配置！ScreenMonitorPlugin 已禁用。"
            )
            self.enabled = False
            return

        # --- 状态变量 ---
        self.openai_client: Optional[AsyncOpenAI] = None  # OpenAI 客户端实例
        self._monitor_task: Optional[asyncio.Task] = None
        self.is_running = False
        self.latest_description = "屏幕信息尚未获取。"
        self.description_lock = asyncio.Lock()  # 保护 latest_description 的访问

        # --- 初始化 OpenAI 客户端 ---
        try:
            self.openai_client = AsyncOpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
                timeout=self.timeout_seconds,
                # 可以根据需要添加 max_retries 等参数
            )
            logger.info(f"AsyncOpenAI 客户端已为模型 '{self.model_name}' 初始化 (Base URL: {self.base_url})。")
        except Exception as e:
            logger.error(f"初始化 AsyncOpenAI 客户端失败: {e}", exc_info=True)
            self.enabled = False
            return

        logger.info(f"ScreenMonitorPlugin 初始化完成。截图间隔: {self.interval}s, 模型: {self.model_name}")

    async def setup(self):
        await super().setup()
        if not self.enabled:
            return

        # --- 移除 aiohttp Session 创建 ---

        # 注册 Prompt 上下文提供者 (保持不变)
        prompt_ctx_service = self.core.get_service("prompt_context")
        if prompt_ctx_service:
            prompt_ctx_service.register_context_provider(
                provider_name=self.context_provider_name,
                context_info=self.get_latest_description,  # 传递异步方法引用
                priority=self.context_priority,
                tags=["screen", "context", "vision", "dynamic"],
            )
            logger.info(
                f"已向 PromptContext 注册动态屏幕上下文提供者 '{self.context_provider_name}' (优先级: {self.context_priority})。"
            )
        else:
            logger.warning("未找到 PromptContext 服务，无法注册屏幕上下文。")

        # 启动后台监控循环 (保持不变)
        self.is_running = True
        self._monitor_task = asyncio.create_task(self._monitoring_loop(), name="ScreenMonitorLoop")
        logger.info("屏幕监控后台任务已启动。")

    async def cleanup(self):
        logger.info("正在清理 ScreenMonitorPlugin...")
        self.is_running = False  # 通知后台任务停止

        # 取消并等待后台任务 (保持不变)
        if self._monitor_task and not self._monitor_task.done():
            logger.debug("正在取消屏幕监控任务...")
            self._monitor_task.cancel()
            try:
                await asyncio.wait_for(self._monitor_task, timeout=2.0)
            except asyncio.TimeoutError:
                logger.warning("屏幕监控任务未能及时取消。")
            except asyncio.CancelledError:
                pass  # 预期行为

        # --- 关闭 OpenAI 客户端 ---
        if self.openai_client:
            try:
                # 使用 openai 库的关闭方法 (如果存在且需要)
                # await self.openai_client.close() # 根据 openai v1.x+ 文档，似乎不需要显式 close
                pass
            except Exception as e:
                logger.warning(f"关闭 OpenAI 客户端时出错(通常不需要): {e}")
            self.openai_client = None
            logger.info("OpenAI 客户端引用已清除。")

        # 取消注册 Prompt 上下文 (保持不变)
        prompt_ctx_service = self.core.get_service("prompt_context")
        if prompt_ctx_service:
            try:
                prompt_ctx_service.unregister_context_provider(self.context_provider_name)
                logger.info(f"已从 PromptContext 取消注册屏幕上下文 '{self.context_provider_name}'。")
            except Exception as e:
                logger.warning(f"尝试取消注册 '{self.context_provider_name}' 时出错: {e}")

        await super().cleanup()
        logger.info("ScreenMonitorPlugin 清理完成。")

    async def get_latest_description(self) -> str:
        """(供 PromptContext 调用) 异步安全地获取最新屏幕描述。"""
        async with self.description_lock:
            return self.latest_description

    async def _monitoring_loop(self):
        """后台任务：定期截图并调用 VL 模型更新描述。"""
        logger.info("屏幕监控循环启动。")
        while self.is_running:
            start_time = time.monotonic()
            try:
                await self._capture_and_process_screenshot()
            except Exception as e:
                # 捕获截图或处理中的意外错误
                logger.error(f"屏幕监控循环中发生错误: {e}", exc_info=True)

            # --- 计算等待时间 ---
            elapsed = time.monotonic() - start_time
            wait_time = max(0, self.interval - elapsed)
            logger.debug(f"本次屏幕处理耗时 {elapsed:.2f}s，将等待 {wait_time:.2f}s 进行下一次。")

            try:
                # 使用 asyncio.sleep 进行可中断的等待
                await asyncio.sleep(wait_time)
            except asyncio.CancelledError:
                logger.info("屏幕监控循环被取消。")
                break  # 退出循环
        logger.info("屏幕监控循环结束。")

    async def _capture_and_process_screenshot(self):
        """执行截图、编码和调用 VL 模型。"""
        if not self.openai_client:
            return  # 检查 OpenAI 客户端

        logger.debug("正在截取屏幕...")
        encoded_image: Optional[str] = None
        try:
            with mss.mss() as sct:
                monitor = sct.monitors[1]
                sct_img = sct.grab(monitor)
                img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
                buffer = BytesIO()
                img.save(buffer, format="PNG")
                img_bytes = buffer.getvalue()
                encoded_image = base64.b64encode(img_bytes).decode("utf-8")
                logger.debug(f"截图成功并编码为 Base64 (大小: {len(encoded_image)} bytes)")
        except Exception as e:
            logger.error(f"截图或编码失败: {e}", exc_info=True)
            return

        if not encoded_image:
            return

        # --- 调用 VL 模型 (使用新方法) ---
        logger.debug(f"准备调用 VL 模型: {self.model_name} (通过 OpenAI 兼容接口)")
        new_description = await self._query_vl_model(encoded_image)  # 调用重命名后的方法

        if new_description:
            async with self.description_lock:
                self.latest_description = new_description
            logger.info(f"屏幕描述已更新: {new_description[:100]}...")
        else:
            logger.warning("未能从 VL 模型获取有效描述。")

    async def _query_vl_model(self, base64_image: str) -> Optional[str]:
        """通过 OpenAI 兼容接口调用 VL 模型获取图像描述。"""
        if not self.openai_client:
            return None

        # 构建符合 OpenAI Vision API 格式的 messages
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": self.vl_prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            # 使用 Data URL 格式
                            "url": f"data:image/png;base64,{base64_image}"
                        },
                    },
                ],
            }
        ]

        try:
            logger.debug(f"向 {self.base_url} 发送 OpenAI 兼容请求 (模型: {self.model_name})...")
            completion = await self.openai_client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                max_tokens=300,  # 可以根据需要调整 max_tokens
            )
            logger.debug(f"OpenAI 兼容 API 响应: {completion}")

            # 解析响应
            if completion.choices and completion.choices[0].message:
                content = completion.choices[0].message.content
                if content:
                    return content.strip()
                else:
                    logger.warning("VL API 响应的消息内容为空。")
                    return None
            else:
                logger.warning(f"VL API 响应格式不符合预期: {completion}")
                return None

        except openai.APITimeoutError:
            logger.error(f"OpenAI 兼容 API 请求超时 (超时设置: {self.timeout_seconds}s)。")
            return None
        except openai.APIConnectionError as e:
            logger.error(f"无法连接到 OpenAI 兼容 API ({self.base_url}): {e}")
            return None
        except openai.RateLimitError as e:
            logger.error(f"OpenAI 兼容 API 速率限制错误: {e}")
            return None
        except openai.APIStatusError as e:
            logger.error(f"OpenAI 兼容 API 返回错误状态码 {e.status_code}: {e.response}")
            return None
        except Exception as e:
            logger.error(f"调用 OpenAI 兼容 API 时发生意外错误: {e}", exc_info=True)
            return None


# --- Plugin Entry Point ---
plugin_entrypoint = ScreenMonitorPlugin
