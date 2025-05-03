import asyncio
import base64
import json
import logging
import os
import sys
import time
from datetime import datetime
from typing import Dict, Any, Optional, AsyncGenerator, List
import numpy as np

# --- Dependencies Check & TOML ---
try:
    import sounddevice as sd
except ImportError:
    print("依赖缺失: 请运行 'pip install sounddevice' 来使用音频输入。", file=sys.stderr)
    sd = None

try:
    import aiohttp
except ImportError:
    print("依赖缺失: 请运行 'pip install aiohttp' 来与 FunASR API 通信。", file=sys.stderr)
    aiohttp = None

try:
    import tomllib
except ModuleNotFoundError:
    try:
        import toml as tomllib
    except ImportError:
        print("依赖缺失: 请运行 'pip install toml' 来加载配置。", file=sys.stderr)
        tomllib = None

from core.plugin_manager import BasePlugin
from core.amaidesu_core import AmaidesuCore
from maim_message import MessageBase, BaseMessageInfo, UserInfo, GroupInfo, Seg, FormatInfo

logger = logging.getLogger(__name__)

# --- Plugin Configuration Loading ---
_PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
_CONFIG_FILE = os.path.join(_PLUGIN_DIR, "config.toml")


def load_plugin_config() -> Dict[str, Any]:
    """加载插件的配置文件。"""
    if tomllib is None:
        logger.error("TOML 库不可用，无法加载配置。")
        return {}
    try:
        with open(_CONFIG_FILE, "rb") as f:
            config = tomllib.load(f)
            logger.info(f"成功加载配置文件: {_CONFIG_FILE}")
            return config
    except FileNotFoundError:
        logger.warning(f"配置文件未找到: {_CONFIG_FILE}。将使用默认值。")
    except tomllib.TOMLDecodeError as e:
        logger.error(f"配置文件 '{_CONFIG_FILE}' 格式无效: {e}。将使用默认值。")
    except Exception as e:
        logger.error(f"加载配置文件 '{_CONFIG_FILE}' 时发生未知错误: {e}", exc_info=True)
    return {}


class FunASRPlugin(BasePlugin):
    """使用 FunASR API 进行语音识别的插件。"""

    _is_amaidesu_plugin: bool = True

    def __init__(self, core: AmaidesuCore, plugin_config: Dict[str, Any]):
        super().__init__(core, plugin_config)
        self.config = load_plugin_config()
        self.enabled = True
        self.logger = logging.getLogger(__name__)

        # --- Control Flow ---
        self._stt_task: Optional[asyncio.Task] = None
        self.stop_event = asyncio.Event()

        # --- Basic Dependency Check ---
        if sd is None or aiohttp is None or tomllib is None:
            self.logger.error("缺少核心依赖 (sounddevice, aiohttp, toml)，插件禁用。")
            self.enabled = False
            return

        # --- Load Config Sections ---
        self.funasr_config = self.config.get("funasr_api", {})
        self.vad_config = self.config.get("vad", {})
        self.audio_config = self.config.get("audio", {})
        self.message_config = self.config.get("message_config", {})

        # --- API Config Check ---
        if not all(self.funasr_config.get(k) for k in ["url", "token"]):
            self.logger.error("FunASR API 配置不完整 (url, token)，插件禁用。")
            self.enabled = False
            return

        # --- Audio Config ---
        self.sample_rate = self.audio_config.get("sample_rate", 16000)
        self.channels = self.audio_config.get("channels", 1)
        self.dtype_str = self.audio_config.get("dtype", "int16")
        self.dtype = np.int16 if self.dtype_str == "int16" else np.float32
        self.input_device_name = self.audio_config.get("input_device_name") or None
        self.input_device_index = self._find_device_index(self.input_device_name, kind="input")

        # --- VAD Config ---
        self.vad_enabled = self.vad_config.get("enable", True)
        self.silence_duration = self.vad_config.get("silence_seconds", 1.0)
        self.max_record_seconds = self.vad_config.get("max_record_seconds", 15.0)
        self.voice_threshold = self.vad_config.get("voice_threshold", 0.05)
        self.sample_window = self.vad_config.get("sample_window", 0.032)
        self.window_samples = int(self.sample_window * self.sample_rate)
        self.block_size_samples = self.window_samples

        # --- Context Tags ---
        self.context_tags: Optional[List[str]] = self.message_config.get("context_tags")
        if not isinstance(self.context_tags, list):
            if self.context_tags is not None:
                self.logger.warning(
                    f"Config 'context_tags' is not a list ({type(self.context_tags)}), will fetch all context."
                )
            self.context_tags = None
        elif not self.context_tags:
            self.logger.info("'context_tags' is empty, will fetch all context.")
            self.context_tags = None

        # --- Template Items ---
        self.template_items = None
        if self.message_config.get("enable_template_info", False):
            self.template_items = self.message_config.get("template_items", {})
            if not self.template_items:
                self.logger.warning("配置启用了 template_info，但未找到 template_items。")

    def _find_device_index(self, device_name: Optional[str], kind: str = "input") -> Optional[int]:
        """根据设备名称查找设备索引。"""
        if sd is None:
            self.logger.error("sounddevice 库不可用。")
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
            self.logger.warning("插件未启用或初始化失败，不启动监听任务。")
            return

        self.logger.info(
            "启动 FunASR 音频监听和处理任务..."
            + (f" (设备: {self.input_device_index})" if self.input_device_index is not None else " (默认设备)")
        )
        self.stop_event.clear()
        self._stt_task = asyncio.create_task(self._run_stt_pipeline(), name="FunASR_Pipeline")

    async def cleanup(self):
        """停止 STT 任务。"""
        self.logger.info("请求停止 FunASR 插件...")
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
        self.logger.info("FunASR 插件清理完成。")
        await super().cleanup()

    async def _run_stt_pipeline(self):
        """主流水线：捕获音频 -> 简单 VAD -> FunASR API -> 发送消息。"""
        self.logger.info("FunASR 流水线任务已启动。")
        try:
            async for result in self.transcribe_stream():
                if self.stop_event.is_set():
                    self.logger.info("FunASR 流水线检测到停止信号，退出。")
                    break

                if result and not result.startswith("["):
                    self.logger.info(f"FunASR 识别结果: '{result}'")
                    message_to_send = await self._create_stt_message(result)
                    self.logger.debug(f"准备发送 STT 消息对象: {repr(message_to_send)}")
                    await self.core.send_to_maicore(message_to_send)
                elif result:
                    self.logger.warning(f"FunASR 流产生警告/错误: {result}")

        except Exception as e:
            self.logger.error(f"FunASR 流水线任务异常终止: {e}", exc_info=True)
        finally:
            self.logger.info("FunASR 流水线任务结束。")

    async def _create_stt_message(self, text: str) -> MessageBase:
        """使用配置创建 MessageBase 对象。"""
        timestamp = time.time()
        cfg = self.message_config

        # --- User Info ---
        user_id_from_config = cfg.get("user_id", 0)
        user_info = UserInfo(
            platform=self.core.platform,
            user_id=user_id_from_config,
            user_nickname=cfg.get("user_nickname", "语音"),
            user_cardname=cfg.get("user_cardname", ""),
        )

        # --- Group Info ---
        group_info: Optional[GroupInfo] = None
        if cfg.get("enable_group_info", True):
            group_info = GroupInfo(
                platform=self.core.platform,
                group_id=cfg.get("group_id", 0),
                group_name=cfg.get("group_name", "funasr_default"),
            )

        # --- Format Info ---
        format_info = FormatInfo(
            content_format=cfg.get("content_format", ["text"]),
            accept_format=cfg.get("accept_format", ["text", "vts_command"]),
        )

        # --- Template Info ---
        final_template_info_value = None
        if cfg.get("enable_template_info", False) and self.template_items:
            modified_template_items = self.template_items.copy()
            additional_context = ""
            prompt_ctx_service = self.core.get_service("prompt_context")
            if prompt_ctx_service:
                try:
                    additional_context = await prompt_ctx_service.get_formatted_context(tags=self.context_tags)
                    if additional_context:
                        self.logger.debug(f"获取到聚合 Prompt 上下文: '{additional_context[:100]}...'")
                except Exception as e:
                    self.logger.error(f"调用 prompt_context 服务时出错: {e}", exc_info=True)

            main_prompt_key = "reasoning_prompt_main"
            if additional_context and main_prompt_key in modified_template_items:
                original_prompt = modified_template_items[main_prompt_key]
                modified_template_items[main_prompt_key] = original_prompt + "\n" + additional_context
                self.logger.debug(f"已将聚合上下文追加到 '{main_prompt_key}'。")

            final_template_info_value = {"template_items": modified_template_items}

        # --- Additional Config ---
        additional_config = cfg.get("additional_config", {}).copy()
        additional_config["source"] = "funasr_plugin"
        additional_config["sender_name"] = user_info.user_nickname

        # --- Base Message Info ---
        message_info = BaseMessageInfo(
            platform=self.core.platform,
            message_id=f"funasr_{int(timestamp * 1000)}_{hash(text) % 10000}",
            time=int(timestamp),
            user_info=user_info,
            group_info=group_info,
            template_info=final_template_info_value,
            format_info=format_info,
            additional_config=additional_config,
        )

        # --- Message Segment ---
        message_segment = Seg(
            type="text",
            data=text,
        )

        return MessageBase(message_info=message_info, message_segment=message_segment, raw_message=text)

    async def transcribe_stream(self) -> AsyncGenerator[str, None]:
        """捕获音频流，执行简单 VAD，发送到 FunASR，返回结果。"""
        loop = asyncio.get_event_loop()
        q = asyncio.Queue(maxsize=100)
        audio_buffer = []
        is_recording = False
        silence_counter = 0
        max_samples = int(self.max_record_seconds * self.sample_rate)
        silence_samples = int(self.silence_duration * self.sample_rate)

        def callback(indata: np.ndarray, frame_count: int, time_info: Any, status: "sd.CallbackFlags"):
            if status:
                self.logger.warning(f"音频输入状态: {status}")
            try:
                loop.call_soon_threadsafe(q.put_nowait, indata.copy())
            except asyncio.QueueFull:
                self.logger.warning("音频队列已满！丢弃数据。")

        stream = None
        ws = None
        try:
            stream = sd.InputStream(
                samplerate=self.sample_rate,
                blocksize=self.block_size_samples,
                device=self.input_device_index,
                channels=self.channels,
                dtype=self.dtype_str,
                callback=callback,
            )
            stream.start()
            self.logger.info(f"开始音频流，阈值: {self.voice_threshold}, 静音: {self.silence_duration}s")

            async with aiohttp.ClientSession() as session:
                while not self.stop_event.is_set():
                    try:
                        chunk = await asyncio.wait_for(q.get(), timeout=1.0)
                        q.task_done()

                        # 转换数据类型
                        if chunk.dtype == np.int16:
                            chunk_float32 = chunk.astype(np.float32) / 32768.0
                        else:
                            chunk_float32 = chunk

                        # 计算音量
                        volume = np.abs(chunk_float32).mean()
                        is_speech = volume > self.voice_threshold

                        if is_speech:
                            if not is_recording:
                                is_recording = True
                                self.logger.info(f"检测到语音 (音量: {volume:.3f})")
                                if ws is None or ws.closed:
                                    try:
                                        # 连接 WebSocket
                                        ws = await session.ws_connect(self.funasr_config["url"])

                                        # 发送初始配置
                                        init_message = {
                                            "mode": "2pass",  # 使用2pass模式进行实时识别和句尾纠错
                                            "wav_name": f"stream_{int(time.time())}",
                                            "wav_format": "pcm",
                                            "is_speaking": True,
                                            "chunk_size": [5, 10, 5],  # 设置流式模型latency配置
                                            "audio_fs": self.sample_rate,
                                            "itn": True,  # 启用智能数字转换
                                        }
                                        await ws.send_json(init_message)
                                        self.logger.debug("已发送 FunASR 初始配置")

                                    except Exception as connect_err:
                                        self.logger.error(f"连接或发送初始配置到 FunASR 失败: {connect_err}")
                                        if ws and not ws.closed:
                                            await ws.close()
                                        ws = None
                                        is_recording = False
                                        continue

                            silence_counter = 0
                            # 发送音频数据
                            if ws and not ws.closed:
                                try:
                                    if chunk.dtype == np.float32:
                                        chunk_int16 = (chunk * 32767.0).astype(np.int16)
                                    else:
                                        chunk_int16 = chunk
                                    await ws.send_bytes(chunk_int16.tobytes())
                                except Exception as send_err:
                                    self.logger.error(f"发送音频数据失败: {send_err}")
                                    if ws and not ws.closed:
                                        await ws.close()
                                    ws = None
                                    is_recording = False
                                    continue

                            audio_buffer.extend(chunk.flatten().tolist())

                        elif is_recording:
                            silence_counter += len(chunk)
                            if silence_counter >= silence_samples or len(audio_buffer) >= max_samples:
                                is_recording = False
                                if ws and not ws.closed:
                                    try:
                                        # 发送结束标记
                                        await ws.send_json({"is_speaking": False})

                                        # 等待并接收结果
                                        result_text = ""
                                        timeout = time.time() + 5  # 5秒超时
                                        while time.time() < timeout:
                                            try:
                                                msg = await asyncio.wait_for(ws.receive(), 1.0)
                                                if msg.type == aiohttp.WSMsgType.TEXT:
                                                    data = json.loads(msg.data)
                                                    if "text" in data:
                                                        # 因为使用2pass模式，我们等待最终结果
                                                        if data.get("mode") == "2pass-offline":
                                                            result_text = data["text"]
                                                            break
                                                elif msg.type == aiohttp.WSMsgType.ERROR:
                                                    self.logger.error(f"WebSocket错误: {ws.exception()}")
                                                    break
                                            except asyncio.TimeoutError:
                                                continue
                                            except Exception as e:
                                                self.logger.error(f"接收结果时出错: {e}")
                                                break

                                        # 关闭当前 WebSocket 连接
                                        await ws.close()
                                        ws = None

                                        if result_text:
                                            yield result_text
                                        else:
                                            yield "[无识别结果]"

                                    except Exception as e:
                                        self.logger.error(f"处理结果时出错: {e}")
                                        yield f"[识别错误: {str(e)}]"
                                        if ws and not ws.closed:
                                            await ws.close()
                                        ws = None
                                else:
                                    self.logger.info("语音段结束，但 WebSocket 已关闭")
                                audio_buffer = []
                                silence_counter = 0

                    except asyncio.TimeoutError:
                        continue
                    except Exception as e:
                        self.logger.error(f"处理音频数据时出错: {e}", exc_info=True)
                        yield f"[处理错误: {str(e)}]"

        except Exception as e:
            self.logger.error(f"音频流出错: {e}", exc_info=True)
            yield f"[音频流错误: {str(e)}]"
        finally:
            if stream is not None:
                try:
                    stream.stop()
                    stream.close()
                except Exception as e:
                    self.logger.error(f"关闭音频流时出错: {e}", exc_info=True)
            if ws and not ws.closed:
                try:
                    await ws.close()
                except Exception as e:
                    self.logger.error(f"关闭 WebSocket 时出错: {e}", exc_info=True)


# --- Plugin Entry Point ---
plugin_entrypoint = FunASRPlugin
