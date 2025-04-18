import asyncio

# import logging # 移除标准logging导入
import tomllib
import os
import time  # 引入 time 模块 (虽然在修改后的代码中没直接用，但可能其他地方会用到)
from typing import Any, Dict, Optional

# 导入全局logger
from src.utils.logger import logger

# 尝试导入 aiohttp
try:
    import aiohttp
except ImportError:
    aiohttp = None

from core.plugin_manager import BasePlugin
from core.amaidesu_core import VupNextCore
from maim_message import MessageBase  # 导入 MessageBase


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
class ElectricityMonitorPlugin(BasePlugin):
    """
    监听来自 MaiCore 的消息，如果包含特定关键词 ("电")，
    则通过 HTTP API 控制 DG-LAB 设备设置强度和波形。
    """

    _is_vup_next_plugin: bool = True

    def __init__(self, core: VupNextCore, plugin_config: Dict[str, Any]):
        super().__init__(core, plugin_config)

        # --- 加载配置 ---
        loaded_config = load_plugin_config()
        self.config = loaded_config.get("electricity_monitor", {})
        self.enabled = self.config.get("enabled", True)

        # --- 检查依赖 ---
        if aiohttp is None:
            logger.error(
                "aiohttp library not found. Please install it (`pip install aiohttp`). ElectricityMonitorPlugin disabled."
            )
            self.enabled = False
            return

        if not self.enabled:
            logger.warning("ElectricityMonitorPlugin 在配置中被禁用。")
            return

        # --- 获取配置值 ---
        self.keyword = self.config.get("keyword", "电")
        self.api_base_url = self.config.get("dg_lab_api_base_url", "http://127.0.0.1:8081").rstrip("/")
        self.target_strength = self.config.get("target_strength", 10)
        self.target_waveform = self.config.get("target_waveform", "big")
        self.timeout = aiohttp.ClientTimeout(total=self.config.get("request_timeout", 5))
        self.context_priority = self.config.get("context_priority", 60)  # 默认优先级提高到 60
        self.context_provider_name = "dg_lab_electricity_warning"  # 上下文提供者名称

        # --- 状态 ---
        self.http_session: Optional[aiohttp.ClientSession] = None
        self.control_lock = asyncio.Lock()  # 防止并发控制请求

        logger.info(
            f"ElectricityMonitorPlugin 初始化完成。将监听关键词 '{self.keyword}' 并控制 API: {self.api_base_url}"
        )

    async def setup(self):
        await super().setup()
        if not self.enabled:
            return

        # 创建 aiohttp Session
        if aiohttp:
            self.http_session = aiohttp.ClientSession(timeout=self.timeout)
            logger.info("aiohttp.ClientSession 已创建。")
        else:
            logger.error("aiohttp 未安装，插件功能受限。")
            self.enabled = False  # 禁用插件如果核心依赖缺失
            return

        # 注册通配符处理器，监听所有来自 MaiCore 的消息
        self.core.register_websocket_handler("*", self.check_and_control_device)
        logger.info("已注册通配符消息处理器 check_and_control_device。")

        # --- 启动后台任务来注册 Prompt 上下文 ---
        # 这样做可以避免阻塞 setup，并在服务可用时进行注册
        asyncio.create_task(self._register_context_when_ready())

    async def _register_context_when_ready(self):
        """后台任务：等待 PromptContext 服务可用后注册上下文。"""
        retry_delay = 2  # 初始重试延迟（秒）
        max_retries = 5  # 最大重试次数
        attempt = 0

        while attempt < max_retries:
            prompt_ctx_service = self.core.get_service("prompt_context")
            if prompt_ctx_service:
                context_text = f"""
!!!! 重要 !!!!
如果你在回复中包含"{self.keyword}"字，系统将立即触发一个物理电击反馈！
这不是比喻或玩笑 - 真的会有电击发生。
不过你可以利用这一点和admin开玩笑 qwq
!!!! 重要 !!!!
"""
                effective_priority = self.config.get("context_priority", 60)

                try:  # 添加 try-except 块以防 register_context_provider 本身出错
                    prompt_ctx_service.register_context_provider(
                        provider_name=self.context_provider_name,
                        context_info=context_text,
                        priority=effective_priority,
                        tags=["dg-lab", "warning", "feedback", "consequence", "critical"],
                    )
                    logger.info(
                        f"已向 PromptContext 注册警告信息 '{self.context_provider_name}' (优先级: {effective_priority})。"
                    )
                    return  # 注册成功，任务完成
                except Exception as e:
                    logger.error(f"注册上下文时发生错误: {e}", exc_info=True)
                    # 即使出错也跳出循环，避免无限重试
                    return
            else:
                attempt += 1
                if attempt < max_retries:
                    logger.warning(
                        f"未找到 PromptContext 服务 (尝试 {attempt}/{max_retries})，将在 {retry_delay} 秒后重试..."
                    )
                    await asyncio.sleep(retry_delay)
                    retry_delay *= 2  # 可以增加重试间隔
                else:
                    logger.error(f"超过最大重试次数，未能注册电击警告上下文。")
                    return  # 达到最大次数，任务结束

    async def cleanup(self):
        logger.info("正在清理 ElectricityMonitorPlugin...")
        # 关闭 aiohttp Session
        if self.http_session:
            await self.http_session.close()
            logger.info("aiohttp.ClientSession 已关闭。")
            self.http_session = None

        # --- 取消注册 Prompt 上下文 ---
        # cleanup 时服务应该存在，直接尝试取消注册
        prompt_ctx_service = self.core.get_service("prompt_context")
        if prompt_ctx_service:
            try:
                prompt_ctx_service.unregister_context_provider(self.context_provider_name)
                logger.info(f"已从 PromptContext 取消注册警告信息 '{self.context_provider_name}'。")
            except Exception as e:  # 可能 provider 没注册成功，unregister 会报错
                logger.warning(f"尝试取消注册 '{self.context_provider_name}' 时出错 (可能未成功注册): {e}")

        # 如果 Core 支持，可以取消注册处理器
        # self.core.unregister_websocket_handler("*", self.check_and_control_device)

        await super().cleanup()
        logger.info("ElectricityMonitorPlugin 清理完成。")

    async def check_and_control_device(self, message: MessageBase):
        """检查收到的消息是否包含关键词，如果包含则触发设备控制。"""
        if not self.enabled or not self.http_session:
            return

        # 检查消息类型和内容
        if (
            message.message_segment
            and message.message_segment.type == "text"
            and isinstance(message.message_segment.data, str)
        ):
            text_content = message.message_segment.data

            # 检查是否包含关键词
            if self.keyword in text_content:
                logger.info(f"检测到关键词 '{self.keyword}' 在消息中: '{text_content[:50]}...'")

                # 使用锁防止短时间内重复触发大量控制请求
                if not self.control_lock.locked():
                    async with self.control_lock:
                        # 创建异步任务执行控制命令，不阻塞当前消息处理
                        asyncio.create_task(self._send_control_commands(text_content))
                        # 添加短暂延迟防止因单条消息内多个关键词导致锁争用 (可选)
                        # await asyncio.sleep(0.1)
                else:
                    logger.debug("控制锁已被占用，跳过此次触发以防止请求堆积。")

    async def _send_control_commands(self, original_text: str):
        """异步发送控制命令到 DG-LAB HTTP API，并在延迟后将强度归零。"""
        if not self.http_session:
            return

        strength_url = f"{self.api_base_url}/control/strength"
        waveform_url = f"{self.api_base_url}/control/waveform"
        headers = {"Content-Type": "application/json"}

        initial_tasks = []

        # --- 准备初始 API 调用任务 ---
        logger.info(f"检测到 '{self.keyword}'，准备发送初始设置命令...")
        # 设置通道 A 强度
        initial_tasks.append(
            self._make_api_call(
                strength_url,
                {"channel": "a", "strength": self.target_strength},
                headers,
                f"设置通道 A 强度为 {self.target_strength}",
            )
        )
        # 设置通道 B 强度
        initial_tasks.append(
            self._make_api_call(
                strength_url,
                {"channel": "b", "strength": self.target_strength},
                headers,
                f"设置通道 B 强度为 {self.target_strength}",
            )
        )
        # 设置通道 A 波形
        initial_tasks.append(
            self._make_api_call(
                waveform_url,
                {"channel": "a", "preset": self.target_waveform},
                headers,
                f"设置通道 A 波形为 '{self.target_waveform}'",
            )
        )
        # 设置通道 B 波形
        initial_tasks.append(
            self._make_api_call(
                waveform_url,
                {"channel": "b", "preset": self.target_waveform},
                headers,
                f"设置通道 B 波形为 '{self.target_waveform}'",
            )
        )

        # --- 并发执行初始 API 调用 ---
        results = await asyncio.gather(*initial_tasks, return_exceptions=True)

        # --- 检查初始调用结果 ---
        initial_success_count = 0
        tasks_descriptions = [  # 手动创建描述列表，因为从 task 获取描述困难
            f"设置通道 A 强度为 {self.target_strength}",
            f"设置通道 B 强度为 {self.target_strength}",
            f"设置通道 A 波形为 '{self.target_waveform}'",
            f"设置通道 B 波形为 '{self.target_waveform}'",
        ]
        for i, result in enumerate(results):
            desc = tasks_descriptions[i]
            if isinstance(result, Exception):
                logger.error(f"初始命令 '{desc}' 执行失败: {result}")
            elif result is False:  # _make_api_call 返回 False 表示 API 调用失败
                pass  # 失败日志已在 _make_api_call 中记录
            else:  # result is True
                initial_success_count += 1

        if initial_success_count < 4:
            logger.warning(f"初始控制命令发送完成，但有 {4 - initial_success_count} 个失败。仍将尝试在延迟后归零强度。")
        else:
            logger.info(f"所有 4 个初始控制命令已成功发送。")

        # --- 等待并发送强度归零命令 ---
        logger.info("等待 2 秒后将强度归零...")
        await asyncio.sleep(2)

        reset_tasks = []
        logger.info("准备发送强度归零命令...")
        # 设置通道 A 强度为 0
        reset_tasks.append(
            self._make_api_call(strength_url, {"channel": "a", "strength": 0}, headers, "设置通道 A 强度为 0")
        )
        # 设置通道 B 强度为 0
        reset_tasks.append(
            self._make_api_call(strength_url, {"channel": "b", "strength": 0}, headers, "设置通道 B 强度为 0")
        )

        # --- 并发执行归零 API 调用 ---
        reset_results = await asyncio.gather(*reset_tasks, return_exceptions=True)

        # --- 检查归零调用结果 ---
        reset_success_count = 0
        reset_tasks_descriptions = ["设置通道 A 强度为 0", "设置通道 B 强度为 0"]
        for i, result in enumerate(reset_results):
            desc = reset_tasks_descriptions[i]
            if isinstance(result, Exception):
                logger.error(f"强度归零命令 '{desc}' 执行失败: {result}")
            elif result is False:
                pass
            else:
                reset_success_count += 1

        if reset_success_count == 2:
            logger.info("强度归零命令已成功发送。")
        else:
            logger.warning(f"强度归零命令发送完成，但有 {2 - reset_success_count} 个失败。")

    async def _make_api_call(self, url: str, payload: Dict, headers: Dict, description: str) -> bool:
        """辅助函数：发送单个 POST 请求并处理响应/错误。"""
        if not self.http_session:
            return False

        try:
            logger.debug(f"发送请求: {description} 到 {url}，数据: {payload}")
            async with self.http_session.post(url, json=payload, headers=headers) as response:
                if 200 <= response.status < 300:
                    resp_json = await response.json()
                    logger.info(f"成功: {description} (响应: {resp_json})")
                    return True
                else:
                    error_text = await response.text()
                    logger.error(f"失败: {description} (状态码: {response.status}, 错误: {error_text[:200]})")
                    return False
        except aiohttp.ClientError as e:
            logger.error(f"请求错误 ({description}): {e}")
            return False
        except asyncio.TimeoutError:
            logger.error(f"请求超时 ({description})")
            return False
        except Exception as e:
            logger.error(f"发送 API 请求时发生意外错误 ({description}): {e}", exc_info=True)
            return False


# --- Plugin Entry Point ---
plugin_entrypoint = ElectricityMonitorPlugin
