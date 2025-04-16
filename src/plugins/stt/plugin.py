# Amaidesu STT Plugin: src/plugins/stt/plugin.py

import asyncio
import logging
import os
import sys
import socket  # For type hints/exceptions if needed
import base64
import hashlib
import hmac
import json
import ssl
import time
import collections
import numpy as np
from datetime import datetime
from time import mktime
from urllib.parse import urlencode, quote
from typing import Dict, Any, Optional, AsyncGenerator

# --- Dependencies Check & TOML ---
try:
    import torch
except ImportError:
    print("依赖缺失: 请运行 'pip install torch' 来使用 VAD 功能。", file=sys.stderr)
    torch = None
try:
    # Attempt to load VAD model to check torch availability
    if torch:
        torch.hub.load(repo_or_dir="snakers4/silero-vad", model="silero_vad", trust_repo=True)
except Exception:
    print("依赖缺失或加载失败: Silero VAD 模型无法加载。", file=sys.stderr)
    # VAD won't work
    pass
try:
    import sounddevice as sd
except ImportError:
    print("依赖缺失: 请运行 'pip install sounddevice' 来使用音频输入。", file=sys.stderr)
    sd = None
try:
    import aiohttp
except ImportError:
    print("依赖缺失: 请运行 'pip install aiohttp' 来与讯飞 API 通信。", file=sys.stderr)
    aiohttp = None

try:
    import tomllib
except ModuleNotFoundError:
    try:
        import toml as tomllib
    except ImportError:
        print("依赖缺失: 请运行 'pip install toml' 来加载 STT 插件配置。", file=sys.stderr)
        tomllib = None

# --- Amaidesu Core Imports ---
from core.plugin_manager import BasePlugin
from core.amaidesu_core import AmaidesuCore
from maim_message import MessageBase, BaseMessageInfo, UserInfo, GroupInfo, Seg, FormatInfo, TemplateInfo

logger = logging.getLogger(__name__)

# --- Plugin Configuration Loading ---
_PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
_CONFIG_FILE = os.path.join(_PLUGIN_DIR, "config.toml")


def load_plugin_config() -> Dict[str, Any]:
    """Loads the plugin's specific config.toml file."""
    if tomllib is None:
        logger.error("TOML library not available, cannot load STT plugin config.")
        return {}
    try:
        with open(_CONFIG_FILE, "rb") as f:
            config = tomllib.load(f)
            logger.info(f"成功加载 STT 插件配置文件: {_CONFIG_FILE}")
            return config
    except FileNotFoundError:
        logger.warning(f"STT 插件配置文件未找到: {_CONFIG_FILE}。将使用默认值。")
    except tomllib.TOMLDecodeError as e:
        logger.error(f"STT 插件配置文件 '{_CONFIG_FILE}' 格式无效: {e}。将使用默认值。")
    except Exception as e:
        logger.error(f"加载 STT 插件配置文件 '{_CONFIG_FILE}' 时发生未知错误: {e}", exc_info=True)
    return {}


# Status for iFlytek frames
STATUS_FIRST_FRAME = 0
STATUS_CONTINUE_FRAME = 1
STATUS_LAST_FRAME = 2


class STTPlugin(BasePlugin):
    """执行 VAD 和 iFlytek STT，并将结果（可选修正后）发送到 Core。"""

    _is_amaidesu_plugin: bool = True  # Plugin marker

    def __init__(self, core: AmaidesuCore, plugin_config: Dict[str, Any]):
        super().__init__(core, plugin_config)
        self.config = load_plugin_config()
        self.enabled = True  # Assume enabled unless dependencies fail

        # --- Basic Dependency Check ---
        if torch is None or sd is None or aiohttp is None or tomllib is None:
            self.logger.error("缺少核心依赖 (torch, sounddevice, aiohttp, toml)，STT 插件禁用。")
            self.enabled = False
            return

        # --- Load Specific Config Sections ---
        self.iflytek_config = self.config.get("iflytek_asr", {})
        self.vad_config = self.config.get("vad", {})
        self.audio_config = self.config.get("audio", {})
        self.enable_correction = self.config.get("enable_correction", True)

        # --- Load Message Config Defaults from plugin's config.toml ---
        self.message_config = self.config.get("message_config", {})  # Expecting a [message_config] section
        if not self.message_config:
            self.logger.warning("在 stt/config.toml 中未找到 [message_config] 配置段，将使用硬编码默认值。")
            self.message_config = {
                "user_id": "stt_user_fallback",
                "user_nickname": "语音",
                "user_cardname": "Fallback",
                "enable_group_info": True,  # Default to True based on previous findings
                "group_id": 0,
                "group_name": "stt_default",
                "content_format": ["text"],
                "accept_format": ["text", "vts_command"],  # Default to align with console
                "enable_template_info": False,
                "template_name": "default",
                "template_default": False,
                "additional_config": {
                    "is_from_adapter": True,
                    "adapter_type": "amaidesu_stt",
                    "original_type": "text",
                    "interaction_mode": "direct_command",
                },
            }
        else:
            self.logger.info("已加载来自 stt/config.toml 的 [message_config]。")

        # --- Load Template Items Separately (if enabled and exists within message_config) ---
        # STT typically doesn't need its own main prompt template
        self.template_items = None
        if self.message_config.get("enable_template_info", False):
            # Load template_items directly from the message_config dictionary
            self.template_items = self.message_config.get("template_items", {})
            if not self.template_items:
                self.logger.warning("配置启用了 template_info，但在 message_config 中未找到 template_items。")

        # --- iFlytek Config Check ---
        if not all([self.iflytek_config.get(k) for k in ["appid", "api_key", "api_secret", "host", "path"]]):
            self.logger.error("讯飞 ASR 配置不完整 (appid, api_key, api_secret, host, path)，STT 插件禁用。")
            self.enabled = False
            return

        # --- VAD Model Loading ---
        self.vad_enabled = self.vad_config.get("enable", True)
        self.vad_model = None
        self.vad_utils = None
        if self.vad_enabled:
            try:
                self.logger.info("加载 Silero VAD 模型... (trust_repo=True)")
                self.vad_model, self.vad_utils = torch.hub.load(
                    repo_or_dir="snakers4/silero-vad",
                    model="silero_vad",
                    force_reload=False,
                    onnx=False,
                    trust_repo=True,
                )
                self.logger.info("Silero VAD 模型加载成功。")
            except Exception as e:
                self.logger.error(f"加载 Silero VAD 模型失败: {e}", exc_info=True)
                self.logger.warning("VAD 功能将不可用。")
                self.vad_enabled = False
        else:
            self.logger.info("VAD 在配置中被禁用。")

        # --- Audio Config ---
        self.sample_rate = self.audio_config.get("sample_rate", 16000)
        self.channels = self.audio_config.get("channels", 1)
        self.dtype_str = self.audio_config.get("dtype", "int16")
        self.dtype = np.int16 if self.dtype_str == "int16" else np.float32
        self.input_device_name = self.audio_config.get("stt_input_device_name") or None
        self.input_device_index = self._find_device_index(self.input_device_name, kind="input")

        # --- VAD Parameters ---
        self.block_size_ms = 32
        self.block_size_samples = int(self.sample_rate * self.block_size_ms / 1000)
        self.speech_buffer_duration = 0.2
        self.speech_buffer_frames = int(self.speech_buffer_duration * self.sample_rate / self.block_size_samples)
        self.min_silence_duration_ms = int(self.vad_config.get("silence_seconds", 1.0) * 1000)
        self.min_speech_duration_ms = 250
        self.max_record_seconds = self.vad_config.get("max_record_seconds", 15.0)
        self.vad_threshold = self.vad_config.get("vad_threshold", 0.5)

        # --- Control Flow ---
        self._stt_task: Optional[asyncio.Task] = None
        self.stop_event = asyncio.Event()

        self.logger.info(f"STT 插件初始化完成。Enabled={self.enabled}, VAD Enabled={self.vad_enabled}")

    def _find_device_index(self, device_name: Optional[str], kind: str = "input") -> Optional[int]:
        """根据设备名称查找设备索引。"""
        if sd is None:
            self.logger.error("sounddevice library not available.")
            return None
        try:
            devices = sd.query_devices()
            if device_name:
                for i, device in enumerate(devices):
                    if device_name.lower() in device["name"].lower() and device[f"{kind}_channels"] > 0:
                        self.logger.info(f"找到 {kind} 设备 '{device['name']}' (匹配 '{device_name}')，索引: {i}")
                        return i
                self.logger.warning(f"未找到名称包含 '{device_name}' 的 {kind} 设备，将使用默认设备。")
            default_device_indices = sd.default.device
            default_index = default_device_indices[0] if kind == "input" else default_device_indices[1]
            if default_index == -1:
                self.logger.warning(f"未找到默认 {kind} 设备。将尝试使用 None (由 sounddevice 选择)。")
                return None
            self.logger.info(f"使用默认 {kind} 设备索引: {default_index} ({sd.query_devices(default_index)['name']})")
            return default_index
        except Exception as e:
            self.logger.error(f"查找音频设备时出错: {e}", exc_info=True)
            return None

    async def setup(self):
        """启动 STT 监听任务。"""
        await super().setup()
        if not self.enabled:
            self.logger.warning("STT 插件未启用或初始化失败，不启动监听任务。")
            return
        if not self.vad_enabled:
            self.logger.warning("VAD 未启用或加载失败，STT 插件无法运行（目前依赖VAD）。")
            return

        self.logger.info(
            "启动 STT 音频监听和处理任务..."
            + (f" (设备: {self.input_device_index})" if self.input_device_index is not None else " (默认设备)")
        )
        self.stop_event.clear()
        self._stt_task = asyncio.create_task(self._run_stt_pipeline(), name="STT_Pipeline")

    async def cleanup(self):
        """停止 STT 任务。"""
        self.logger.info("请求停止 STT 插件...")
        self.stop_event.set()
        if self._stt_task and not self._stt_task.done():
            self.logger.info("正在等待 STT 任务结束 (最多 5 秒)...")
            try:
                await asyncio.wait_for(self._stt_task, timeout=5.0)
            except asyncio.TimeoutError:
                self.logger.warning("STT 任务在超时后仍未结束，将强制取消。")
                self._stt_task.cancel()
            except asyncio.CancelledError:
                self.logger.info("STT 任务已被取消。")
            except Exception as e:
                self.logger.error(f"等待 STT 任务结束时出错: {e}", exc_info=True)
        self.logger.info("STT 插件清理完成。")
        await super().cleanup()

    async def _run_stt_pipeline(self):
        """主流水线：捕获音频 -> VAD -> 讯飞 STT -> 可选修正 -> 发送消息。"""
        self.logger.info("STT 流水线任务已启动。")
        try:
            async for result in self.transcribe_stream():
                if self.stop_event.is_set():
                    self.logger.info("STT 流水线检测到停止信号，退出。")
                    break

                if result and not result.startswith("["):
                    self.logger.info(f"原始 STT 结果: '{result}'")
                    final_text = result
                    # --- 可选：调用修正服务 ---
                    if self.enable_correction:
                        correction_service = self.core.get_service("stt_correction")
                        if correction_service:
                            self.logger.debug("找到 stt_correction 服务，尝试修正文本...")
                            try:
                                corrected = await correction_service.correct_text(result)
                                if corrected:
                                    self.logger.info(f"修正后 STT 结果: '{corrected}'")
                                    final_text = corrected
                                else:
                                    self.logger.info("STT 修正服务未返回有效结果，使用原始文本。")
                            except AttributeError:
                                self.logger.error("获取到的 'stt_correction' 服务没有 'correct_text' 方法。")
                            except Exception as e:
                                self.logger.error(f"调用 stt_correction 服务时出错: {e}", exc_info=True)
                        else:
                            self.logger.warning("配置启用了 STT 修正，但未找到 'stt_correction' 服务。")

                    # --- 发送消息到 Core ---
                    message_to_send = self._create_stt_message(final_text)
                    # Add debug log for the message object being sent
                    self.logger.debug(f"准备发送 STT 消息对象: {repr(message_to_send)}")
                    await self.core.send_to_maicore(message_to_send)

                elif result:  # Handle errors yielded from transcribe_stream
                    self.logger.warning(f"STT 流产生警告/错误: {result}")
        except Exception as e:
            self.logger.error(f"STT 流水线任务异常终止: {e}", exc_info=True)
        finally:
            self.logger.info("STT 流水线任务结束。")

    def _create_stt_message(self, text: str) -> MessageBase:
        """使用从 config.toml 加载的 [message_config] 创建 MessageBase 对象。"""
        timestamp = time.time()
        cfg = self.message_config  # Use the loaded message config

        # --- User Info ---
        user_id_from_config = cfg.get("user_id", 0)  # Assume int from config, default to 0
        user_info = UserInfo(
            platform=self.core.platform,
            user_id=user_id_from_config,
            user_nickname=cfg.get("user_nickname", "语音"),
            user_cardname=cfg.get("user_cardname", ""),
        )

        # --- Group Info (Conditional) ---
        group_info: Optional[GroupInfo] = None
        if cfg.get("enable_group_info", True):  # Default to True
            group_info = GroupInfo(
                platform=self.core.platform,
                group_id=cfg.get("group_id", 0),
                group_name=cfg.get("group_name", "stt_default"),
            )

        # --- Format Info ---
        format_info = FormatInfo(
            content_format=cfg.get("content_format", ["text"]),
            accept_format=cfg.get("accept_format", ["text", "vts_command"]),  # Align with console
        )

        # --- Template Info (Conditional & Modification) ---
        final_template_info_value = None
        if cfg.get("enable_template_info", False) and self.template_items:
            # 1. 获取原始模板项 (创建副本)
            modified_template_items = (self.template_items or {}).copy()

            # 2. --- 获取并追加 Prompt 上下文 ---
            additional_context = ""
            prompt_ctx_service = self.core.get_service("prompt_context")
            if prompt_ctx_service:
                try:
                    # 调用服务获取格式化后的上下文
                    additional_context = prompt_ctx_service.get_formatted_context()
                    self.logger.debug(f"Fetched context from service: '{additional_context}'")
                    if additional_context:
                        self.logger.debug(f"获取到聚合 Prompt 上下文: '{additional_context[:100]}...'")
                except Exception as e:
                    self.logger.error(f"调用 prompt_context 服务时出错: {e}", exc_info=True)
            # else: # 可以选择性记录服务未找到的日志
            #    self.logger.debug("未找到 prompt_context 服务。")

            # 3. 修改主 Prompt (如果上下文非空且主 Prompt 存在)
            main_prompt_key = "reasoning_prompt_main"  # 假设主 Prompt 的键是这个
            if additional_context and main_prompt_key in modified_template_items:
                original_prompt = modified_template_items[main_prompt_key]
                # 在原始 Prompt 和附加内容之间添加换行符，确保分隔
                modified_template_items[main_prompt_key] = original_prompt + "\n" + additional_context
                self.logger.debug(f"已将聚合上下文追加到 '{main_prompt_key}'。")

            # 4. 使用修改后的模板项构建最终结构
            final_template_info_value = {"template_items": modified_template_items}
        # else: # 不需要模板或模板项为空时，final_template_info_value 保持 None

        # --- Additional Config ---
        additional_config = cfg.get("additional_config", {}).copy()  # Use copy to avoid modifying original dict
        # Add source automatically
        additional_config["source"] = "stt_plugin"
        # Add sender_name for convenience in prompts
        additional_config["sender_name"] = user_info.user_nickname

        # --- Base Message Info ---
        message_info = BaseMessageInfo(
            platform=self.core.platform,
            # Consider casting time to int for consistency
            message_id=f"stt_{int(timestamp * 1000)}_{hash(text) % 10000}",
            time=int(timestamp),
            user_info=user_info,
            group_info=group_info,
            # 使用可能已修改过的 template_info
            template_info=final_template_info_value,
            format_info=format_info,
            additional_config=additional_config,  # This should be the top-level one
        )

        # --- Message Segment ---
        # Segment type is usually fixed for STT messages sending to core
        message_segment = Seg(
            type="text",  # Use text type
            data=text,
        )

        # --- Final MessageBase ---
        return MessageBase(message_info=message_info, message_segment=message_segment, raw_message=text)

    # --- transcribe_stream: Core STT logic ---
    async def transcribe_stream(self) -> AsyncGenerator[str, None]:
        """Captures audio stream, performs VAD, sends to iFlytek, yields results."""
        if not self.vad_enabled or not self.vad_model:
            self.logger.error("VAD 未启用或未加载，无法进行流式 STT。")
            yield "[错误：VAD不可用]"
            return

        loop = asyncio.get_event_loop()
        q = asyncio.Queue(maxsize=100)
        audio_buffer = collections.deque(maxlen=self.speech_buffer_frames)

        triggered = False
        silence_blocks = 0
        speech_blocks = 0
        max_blocks = int(self.sample_rate * self.max_record_seconds / self.block_size_samples)
        silence_frames_needed = int(self.min_silence_duration_ms / self.block_size_ms)
        min_speech_blocks = int(self.min_speech_duration_ms / self.block_size_ms)

        session: Optional[aiohttp.ClientSession] = None
        stream = None
        ws: Optional["aiohttp.ClientWebSocketResponse"] = None
        receiver_task: Optional[asyncio.Task] = None
        result_future: Optional[asyncio.Future] = None

        try:
            session = aiohttp.ClientSession()
            self.logger.info("为讯飞 STT 创建了新的 aiohttp ClientSession。")

            def callback(indata: np.ndarray, frame_count: int, time_info: Any, status: "sd.CallbackFlags"):
                if status:
                    self.logger.warning(f"音频输入状态: {status}")
                try:
                    loop.call_soon_threadsafe(q.put_nowait, indata.copy())
                except asyncio.QueueFull:
                    self.logger.warning("STT 音频队列已满！丢弃数据。")

            self.logger.info(
                "开始 STT 音频流..."
                + (f" (设备索引: {self.input_device_index})" if self.input_device_index is not None else " (默认设备)")
            )
            stream = sd.InputStream(
                samplerate=self.sample_rate,
                blocksize=self.block_size_samples,
                device=self.input_device_index,
                channels=self.channels,
                dtype=self.dtype_str,
                callback=callback,
            )
            stream.start()
            self.logger.info(
                f"音频流已启动。监听语音 (VAD 阈值: {self.vad_threshold}, 静音: {self.min_silence_duration_ms}ms)..."
            )

            while not self.stop_event.is_set():
                try:
                    chunk = await asyncio.wait_for(q.get(), timeout=1.0)
                    q.task_done()

                    if chunk.dtype == np.int16:
                        chunk_float32 = chunk.astype(np.float32) / 32768.0
                    elif chunk.dtype == np.float32:
                        chunk_float32 = chunk
                    else:
                        self.logger.warning(f"不支持的音频数据类型: {chunk.dtype}，跳过块。")
                        continue

                    if chunk_float32.ndim > 1 and self.channels == 1:
                        chunk_float32 = chunk_float32[:, 0]

                    if len(audio_buffer) == self.speech_buffer_frames:
                        audio_buffer.popleft()
                    audio_buffer.append(chunk_float32)

                    speech_prob = 0.0
                    try:
                        audio_tensor = torch.from_numpy(chunk_float32)
                        speech_prob = self.vad_model(audio_tensor, self.sample_rate).item()
                    except Exception as vad_err:
                        self.logger.error(f"VAD 推理错误: {vad_err}", exc_info=True)
                        continue

                    is_speech = speech_prob > self.vad_threshold

                    if is_speech:
                        silence_blocks = 0
                        if not triggered:
                            triggered = True
                            speech_blocks = 1
                            self.logger.info(f"VAD 触发 (概率: {speech_prob:.2f}) - 开始语音段")
                            if ws is None or ws.closed:
                                self.logger.debug("开始讯飞 WebSocket 连接...")
                                try:
                                    auth_url = self._build_iflytek_auth_url()
                                    if session is None or session.closed:
                                        self.logger.warning("Aiohttp session was closed unexpectedly, recreating.")
                                        session = aiohttp.ClientSession()
                                    ws = await session.ws_connect(auth_url, ssl=ssl.SSLContext())
                                    self.logger.info("已连接到讯飞 WebSocket。")
                                    result_future = asyncio.Future()
                                    receiver_task = asyncio.create_task(
                                        self._iflytek_receiver(ws, result_future), name="iFlytekReceiver"
                                    )

                                    start_frame = self._build_iflytek_start_frame()
                                    if audio_buffer:
                                        buffered_audio_float32 = np.concatenate(list(audio_buffer))
                                        if self.dtype == np.int16:
                                            buffered_audio_int16 = (buffered_audio_float32 * 32767.0).astype(np.int16)
                                            audio_bytes = buffered_audio_int16.tobytes()
                                        else:
                                            audio_bytes = buffered_audio_float32.tobytes()
                                        audio_base64 = base64.b64encode(audio_bytes).decode("utf-8")
                                        start_frame["data"]["audio"] = audio_base64
                                        self.logger.debug(
                                            f"在首帧中发送了 {len(audio_buffer)} 个缓冲块 ({len(audio_bytes)} bytes)。"
                                        )
                                        audio_buffer.clear()
                                    await ws.send_json(start_frame)
                                    self.logger.debug("已发送讯飞起始帧 JSON。")

                                except Exception as connect_err:
                                    self.logger.error(f"连接或发送起始帧到讯飞失败: {connect_err}", exc_info=True)
                                    if ws and not ws.closed:
                                        await ws.close()
                                        ws = None
                                    if receiver_task and not receiver_task.done():
                                        receiver_task.cancel()
                                    triggered = False
                                    continue
                        else:
                            speech_blocks += 1
                            if ws and not ws.closed:
                                try:
                                    await self._send_iflytek_audio_frame(ws, chunk)
                                except Exception as send_err:
                                    self.logger.error(f"发送音频帧到讯飞失败: {send_err}")
                                    await self._close_iflytek_connection(
                                        ws, receiver_task, "send_error", close_session=False
                                    )
                                    ws = None
                                    receiver_task = None
                                    result_future = None
                                    triggered = False
                                    continue
                    else:
                        if triggered:
                            silence_blocks += 1
                            if silence_blocks >= silence_frames_needed:
                                self.logger.info(
                                    f"VAD 未触发 (静音 {silence_blocks * self.block_size_ms}ms 在 {speech_blocks} 语音块后达到)"
                                )
                                triggered = False
                                if speech_blocks >= min_speech_blocks:
                                    self.logger.info(
                                        f"语音段足够长 ({speech_blocks * self.block_size_ms}ms)，结束讯飞段落。"
                                    )
                                    yield await self._end_iflytek_segment(
                                        ws, receiver_task, result_future, "silence_end", session
                                    )
                                else:
                                    self.logger.info(f"语音段太短 ({speech_blocks * self.block_size_ms}ms)，丢弃。")
                                    await self._close_iflytek_connection(
                                        ws, receiver_task, "short_speech", close_session=False
                                    )
                                ws = None
                                receiver_task = None
                                result_future = None
                                audio_buffer.clear()

                    if triggered and speech_blocks >= max_blocks:
                        self.logger.warning(f"达到最大录制时长 ({self.max_record_seconds}s)。结束段落。")
                        triggered = False
                        yield await self._end_iflytek_segment(ws, receiver_task, result_future, "max_duration", session)
                        ws = None
                        receiver_task = None
                        result_future = None
                        audio_buffer.clear()

                except asyncio.TimeoutError:
                    continue
                except asyncio.CancelledError:
                    self.logger.info("transcribe_stream 任务被取消。")
                    break
                except Exception as e:
                    self.logger.error(f"STT 流主循环出错: {e}", exc_info=True)
                    break
        except sd.PortAudioError as pae:
            self.logger.error(f"PortAudio 错误: {pae}")
            yield f"[音频错误: {pae}]"
        except Exception as e:
            self.logger.error(f"启动或运行音频流时出错: {e}", exc_info=True)
            yield f"[音频流错误: {e}]"
        finally:
            self.logger.info("停止音频流并清理 STT transcribe_stream...")
            if stream is not None:
                try:
                    stream.stop()
                    stream.close()
                    self.logger.debug("Sounddevice stream stopped and closed.")
                except Exception as sd_err:
                    self.logger.error(f"停止 sounddevice 流时出错: {sd_err}", exc_info=True)
            await self._close_iflytek_connection(ws, receiver_task, "stream_end", close_session=False)
            if session and not session.closed:
                try:
                    await session.close()
                    self.logger.info("Aiohttp session closed in finally block.")
                except Exception as session_err:
                    self.logger.error(f"关闭 aiohttp session 时出错: {session_err}", exc_info=True)
            self.logger.info("STT transcribe_stream 清理完成。")

    def _build_iflytek_auth_url(self) -> str:
        """Generates the authenticated WebSocket URL for iFlytek ASR."""
        cfg = self.iflytek_config
        url = f"wss://{cfg['host']}{cfg['path']}"
        now = datetime.now()
        date = datetime.utcfromtimestamp(mktime(now.timetuple())).strftime("%a, %d %b %Y %H:%M:%S GMT")
        signature_origin = f"host: {cfg['host']}\ndate: {date}\nGET {cfg['path']} HTTP/1.1"
        signature_sha = hmac.new(
            cfg["api_secret"].encode("utf-8"), signature_origin.encode("utf-8"), digestmod=hashlib.sha256
        ).digest()
        signature_sha_base64 = base64.b64encode(signature_sha).decode(encoding="utf-8")
        authorization_origin = f'api_key="{cfg["api_key"]}", algorithm="hmac-sha256", headers="host date request-line", signature="{signature_sha_base64}"'
        authorization = base64.b64encode(authorization_origin.encode("utf-8")).decode(encoding="utf-8")
        v = {"authorization": authorization, "date": date, "host": cfg["host"]}
        signed_url = url + "?" + urlencode(v, quote_via=quote)
        self.logger.debug(f"生成讯飞认证 URL (结尾): ...?{urlencode(v, quote_via=quote)[-20:]}")
        return signed_url

    async def _iflytek_receiver(self, ws: aiohttp.ClientWebSocketResponse, result_future: asyncio.Future):
        """Receives messages from iFlytek WebSocket and sets the final result."""
        full_text = ""
        self.logger.debug("讯飞接收器任务启动。")
        try:
            async for msg in ws:
                if self.stop_event.is_set():
                    break
                if msg.type == aiohttp.WSMsgType.TEXT:
                    try:
                        resp = json.loads(msg.data)
                        if resp.get("code", -1) != 0:
                            err_msg = f"讯飞 API 错误: Code={resp.get('code')}, Message={resp.get('message')}"
                            self.logger.error(err_msg)
                            if not result_future.done():
                                result_future.set_exception(RuntimeError(err_msg))
                            break
                        data = resp.get("data", {})
                        status = data.get("status", -1)
                        result = data.get("result", {})
                        text_segment = ""
                        if "ws" in result:
                            for w in result["ws"]:
                                for cw in w.get("cw", []):
                                    text_segment += cw.get("w", "")
                        if text_segment:
                            full_text += text_segment
                        if status == STATUS_LAST_FRAME:
                            self.logger.info("讯飞收到结束帧信号 (status=2)。")
                            if not result_future.done():
                                result_future.set_result(full_text)
                            break
                    except json.JSONDecodeError:
                        self.logger.error(f"无法解码来自讯飞的 JSON: {msg.data}")
                    except Exception as e:
                        self.logger.exception(f"处理讯飞消息时出错: {msg.data}")
                        if not result_future.done():
                            result_future.set_exception(e)
                        break
                elif msg.type == aiohttp.WSMsgType.ERROR:
                    err = ws.exception() or RuntimeError("讯飞 WebSocket 错误")
                    self.logger.error(f"讯飞 WebSocket 错误: {err}")
                    if not result_future.done():
                        result_future.set_exception(err)
                    break
                elif msg.type == aiohttp.WSMsgType.CLOSED:
                    self.logger.warning(f"讯飞 WebSocket 连接被关闭: Code={ws.close_code}")
                    if not result_future.done():
                        self.logger.warning("在最终结果前连接关闭。返回部分文本。")
                        result_future.set_result(full_text)
                    break
        except asyncio.CancelledError:
            self.logger.info("讯飞接收器任务被取消。")
        except Exception as e:
            self.logger.exception("讯飞接收器任务异常。")
            if not result_future.done():
                result_future.set_exception(e)
        finally:
            if not result_future.done():
                self.logger.warning("接收器任务意外退出。设置部分结果。")
                result_future.set_result(full_text)
            self.logger.debug("讯飞接收器任务结束。")

    def _build_iflytek_start_frame(self) -> Dict[str, Any]:
        """Builds the initial frame to send to iFlytek."""
        return {
            "common": {"app_id": self.iflytek_config["appid"]},
            "business": {
                "language": "zh_cn",
                "domain": "iat",
                "accent": "mandarin",
                "ptt": 0,
                "vad_eos": self.min_silence_duration_ms,
            },
            "data": {
                "status": STATUS_FIRST_FRAME,
                "format": f"audio/L16;rate={self.sample_rate}",
                "encoding": "raw",
                "audio": "",
            },
        }

    async def _send_iflytek_audio_frame(self, ws: aiohttp.ClientWebSocketResponse, chunk: np.ndarray):
        """Sends an audio chunk (numpy array) as a continue frame."""
        if chunk.dtype == np.float32:
            chunk_int16 = (chunk * 32767.0).astype(np.int16)
        elif chunk.dtype == np.int16:
            chunk_int16 = chunk
        else:
            self.logger.warning(f"不支持的音频数据类型用于发送: {chunk.dtype}，尝试转换为 int16。")
            chunk_int16 = chunk.astype(np.int16)
        audio_bytes = chunk_int16.tobytes()
        audio_base64 = base64.b64encode(audio_bytes).decode("utf-8")
        frame = {
            "data": {
                "status": STATUS_CONTINUE_FRAME,
                "format": f"audio/L16;rate={self.sample_rate}",
                "encoding": "raw",
                "audio": audio_base64,
            }
        }
        if not ws.closed:
            await ws.send_json(frame)
        else:
            self.logger.warning("尝试发送音频帧时 WebSocket 已关闭。")

    async def _end_iflytek_segment(
        self,
        ws: Optional[aiohttp.ClientWebSocketResponse],
        receiver_task: Optional[asyncio.Task],
        result_future: Optional[asyncio.Future],
        reason: str,
        session: Optional[aiohttp.ClientSession],
    ) -> str:
        """Sends the end frame, waits for result, and cleans up websocket connection (NOT session)."""
        final_text = f"[{reason} - 未收到结果]"
        if ws and not ws.closed and result_future and receiver_task:
            try:
                end_frame = {"data": {"status": STATUS_LAST_FRAME}}
                self.logger.debug(f"尝试发送讯飞结束帧 (原因: {reason})。")
                await ws.send_json(end_frame)
                self.logger.info(f"等待讯飞转录结果 (原因: {reason})... (最多 10s)")
                final_text = await asyncio.wait_for(result_future, timeout=10.0)
                self.logger.info(f"讯飞最终结果 (原因: {reason}): '{final_text}'")
                if not final_text:
                    final_text = "[识别结果为空]"
            except asyncio.TimeoutError:
                self.logger.error(f"等待讯飞结果超时 (原因: {reason})。")
                final_text = "[识别超时]"
            except asyncio.CancelledError:
                self.logger.info(f"结果 future 被取消 (原因: {reason})。")
                final_text = "[识别被取消]"
            except Exception as e:
                self.logger.error(f"发送结束帧或获取讯飞结果时出错 (原因: {reason}): {e}", exc_info=True)
                final_text = f"[识别错误]"
            finally:
                await self._close_iflytek_connection(ws, receiver_task, reason, close_session=False)
        else:
            self.logger.warning(f"尝试结束段落 ({reason}) 时连接已关闭或任务/future 丢失。")
        return final_text

    async def _close_iflytek_connection(
        self,
        ws: Optional[aiohttp.ClientWebSocketResponse],
        receiver_task: Optional[asyncio.Task],
        reason: str,
        close_session: bool = False,
    ):
        """Safely close websocket and cancel receiver task. Optionally close session."""
        self.logger.debug(f"开始清理讯飞连接 (原因: {reason}, 关闭会话: {close_session})...")
        if receiver_task and not receiver_task.done():
            self.logger.debug("取消讯飞接收器任务...")
            receiver_task.cancel()
            try:
                await asyncio.wait_for(receiver_task, timeout=0.5)
            except asyncio.TimeoutError:
                self.logger.warning("讯飞接收器任务取消超时。")
            except asyncio.CancelledError:
                pass
            except Exception as e:
                self.logger.warning(f"等待接收器任务取消时出错: {e}")
        if ws and not ws.closed:
            self.logger.debug("关闭讯飞 WebSocket...")
            try:
                await ws.close()
            except Exception as ws_err:
                self.logger.warning(f"关闭 WebSocket 时出错: {ws_err}")

        if close_session and session and not session.closed:
            self.logger.debug(f"请求关闭 aiohttp session (原因: {reason})...")
            try:
                await session.close()
                self.logger.info(f"Aiohttp session closed by helper (原因: {reason}).")
            except Exception as session_err:
                self.logger.error(f"Helper 关闭 aiohttp session 时出错: {session_err}", exc_info=True)

        self.logger.debug(f"讯飞连接清理完成 (原因: {reason})。")


# --- Plugin Entry Point ---
plugin_entrypoint = STTPlugin
