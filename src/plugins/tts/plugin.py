# Amaidesu TTS Plugin: src/plugins/tts/plugin.py

import asyncio

# import logging
import os
import sys
import socket
import tempfile
from typing import Dict, Any, Optional
import numpy as np  # 确保导入 numpy

# --- Dependencies Check (Inform User) ---
# Try importing required libraries and inform the user if they are missing.
# Actual error will be caught later if import fails during use.
dependencies_ok = True
try:
    import edge_tts
except ImportError:
    print("依赖缺失: 请运行 'pip install edge-tts' 来使用 Edge TTS 功能。", file=sys.stderr)
    dependencies_ok = False
try:
    import sounddevice as sd
    import soundfile as sf
except ImportError:
    print("依赖缺失: 请运行 'pip install sounddevice soundfile' 来使用音频播放功能。", file=sys.stderr)
    dependencies_ok = False
try:
    import aiohttp
except ImportError:
    print("依赖缺失: 请运行 'pip install aiohttp' 来使用 Qwen TTS 功能。", file=sys.stderr)
    dependencies_ok = False
# try:
#     from openai import AsyncOpenAI, APIConnectionError, RateLimitError, APIStatusError
# except ImportError:
#     pass # openai is optional for this plugin now

# --- TOML Loading ---
try:
    import tomllib
except ModuleNotFoundError:
    try:
        import toml as tomllib
    except ImportError:
        print("依赖缺失: 请运行 'pip install toml' 来加载 TTS 插件配置。", file=sys.stderr)
        tomllib = None
        dependencies_ok = False

# --- Amaidesu Core Imports ---
from src.core.plugin_manager import BasePlugin
from src.core.amaidesu_core import AmaidesuCore
from maim_message import MessageBase  # Import MessageBase for type hint

# --- TTS Engines ---
try:
    from .omni_tts import OmniTTS

    OMNI_TTS_AVAILABLE = True
except ImportError as e:
    print(f"警告: 无法导入 OmniTTS: {e}", file=sys.stderr)
    OMNI_TTS_AVAILABLE = False

# --- Plugin Configuration Loading ---
# 移除旧的配置加载相关变量和函数
# _PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
# _CONFIG_FILE = os.path.join(_PLUGIN_DIR, "config.toml")
#
#
# def load_plugin_config() -> Dict[str, Any]:
#     """Loads the plugin's specific config.toml file."""
#     if tomllib is None:
#         logger.error("TOML library not available, cannot load TTS plugin config.")
#         return {}
#     try:
#         with open(_CONFIG_FILE, "rb") as f:
#             config = tomllib.load(f)
#             logger.info(f"成功加载 TTS 插件配置文件: {_CONFIG_FILE}")
#             return config
#     except FileNotFoundError:
#         logger.warning(f"TTS 插件配置文件未找到: {_CONFIG_FILE}。将使用默认值。")
#     except tomllib.TOMLDecodeError as e:
#         logger.error(f"TTS 插件配置文件 '{_CONFIG_FILE}' 格式无效: {e}。将使用默认值。")
#     except Exception as e:
#         logger.error(f"加载 TTS 插件配置文件 '{_CONFIG_FILE}' 时发生未知错误: {e}", exc_info=True)
#     return {}


class TTSPlugin(BasePlugin):
    """处理文本消息，执行 TTS 播放，可选 Cleanup LLM 和 UDP 广播。"""

    def __init__(self, core: AmaidesuCore, plugin_config: Dict[str, Any]):
        # Note: plugin_config from PluginManager is the global [plugins] config
        # We load our own specific config here.
        super().__init__(core, plugin_config)
        self.tts_config = self.plugin_config  # 直接使用注入的 plugin_config

        # --- Edge TTS Service Initialization ---
        self.voice = self.tts_config.get("voice", "zh-CN-XiaoxiaoNeural")
        self.output_device_name = self.tts_config.get("output_device_name") or None  # Explicit None if empty string
        self.output_device_index = self._find_device_index(self.output_device_name, kind="output")
        self.tts_lock = asyncio.Lock()

        # --- Omni TTS Initialization ---
        self.omni_tts = None
        omni_config = self.tts_config.get("omni_tts", {})
        self.omni_enabled = omni_config.get("enabled", False)

        if self.omni_enabled:
            if not OMNI_TTS_AVAILABLE:
                self.logger.error("Omni TTS 不可用，但在配置中被启用。请检查依赖。")
                raise ImportError("Omni TTS 不可用")

            api_key = omni_config.get("api_key") or os.environ.get("DASHSCOPE_API_KEY")

            if not api_key:
                self.logger.error(
                    "Omni TTS API 密钥未配置。请在配置文件中设置 api_key 或设置环境变量 DASHSCOPE_API_KEY"
                )
                raise ValueError("Omni TTS API 密钥未配置")

            # 获取后处理配置
            post_processing = omni_config.get("post_processing", {})

            self.omni_tts = OmniTTS(
                api_key=api_key,
                model_name=omni_config.get("model_name", "qwen2.5-omni-7b"),
                voice=omni_config.get("voice", "Chelsie"),
                format=omni_config.get("format", "wav"),
                base_url=omni_config.get("base_url", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
                enable_post_processing=post_processing.get("enabled", False),
                volume_reduction_db=post_processing.get("volume_reduction", 0.0),
                noise_level=post_processing.get("noise_level", 0.0),
                blow_up_probability=omni_config.get("blow_up_probability", 0.0),
                blow_up_texts=omni_config.get("blow_up_texts", []),
            )
            self.logger.info(f"Omni TTS 初始化完成: {omni_config.get('model_name', 'qwen2.5-omni-7b')}")

        self.logger.info(
            f"TTS 服务组件初始化。Omni TTS: {'启用' if self.omni_enabled else '禁用'}, Edge语音: {self.voice}, 输出设备: {self.output_device_name or '默认设备'}"
        )

        # --- UDP Broadcast Initialization (from tts_monitor.py / mmc_client.py) ---
        udp_config = self.tts_config.get("udp_broadcast", {})
        self.udp_enabled = udp_config.get("enable", False)
        self.udp_socket = None
        self.udp_dest = None
        if self.udp_enabled:
            host = udp_config.get("host", "127.0.0.1")
            port = udp_config.get("port", 9998)
            try:
                self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                self.udp_dest = (host, port)
                self.logger.info(f"TTS UDP 广播已启用，目标: {self.udp_dest}")
            except Exception as e:
                self.logger.error(f"初始化 TTS UDP socket 失败: {e}", exc_info=True)
                self.udp_socket = None
                self.udp_enabled = False
        else:
            self.logger.info("TTS UDP 广播已禁用。")

    def _find_device_index(self, device_name: Optional[str], kind: str = "output") -> Optional[int]:
        """根据设备名称查找设备索引 (来自 tts_service.py)。"""
        if "sd" not in globals():  # Check if sounddevice was imported
            self.logger.error("sounddevice 库不可用，无法查找音频设备。")
            return None
        try:
            devices = sd.query_devices()
            if device_name:
                for i, device in enumerate(devices):
                    # Case-insensitive partial match
                    # 正确访问设备属性
                    device_name_attr = getattr(device, "name", "")
                    channels_attr = getattr(device, f"max_{kind}_channels", 0)
                    if device_name.lower() in device_name_attr.lower() and channels_attr > 0:
                        self.logger.info(f"找到 {kind} 设备 '{device_name_attr}' (匹配 '{device_name}')，索引: {i}")
                        return i
                self.logger.warning(f"未找到名称包含 '{device_name}' 的 {kind} 设备，将使用默认设备。")

            # Determine default device index based on kind
            default_device_indices = sd.default.device
            default_index = default_device_indices[1] if kind == "output" else default_device_indices[0]
            if default_index == -1:  # Indicates no default device found by sounddevice
                self.logger.warning(f"未找到默认 {kind} 设备，将使用 None (由 sounddevice 选择)。")
                return None

            default_device = sd.query_devices(default_index)
            default_device_name = getattr(default_device, "name", "Unknown")
            self.logger.info(f"使用默认 {kind} 设备索引: {default_index} ({default_device_name})")
            return default_index
        except Exception as e:
            self.logger.error(f"查找音频设备时出错: {e}，将使用 None (由 sounddevice 选择)", exc_info=True)
            return None

    async def setup(self):
        """注册处理来自 MaiCore 的 'text' 类型消息。"""
        await super().setup()
        # 注册处理函数，监听所有 WebSocket 消息
        # 我们将在处理函数内部检查消息类型是否为 'text'

        # 创建包装函数来返回 Task 而不是 Coroutine
        def websocket_handler_wrapper(message):
            return asyncio.create_task(self.handle_maicore_message(message))

        self.core.register_websocket_handler("*", websocket_handler_wrapper)
        self.logger.info("TTS 插件已设置，监听所有 MaiCore WebSocket 消息。")

    async def cleanup(self):
        """关闭 UDP socket。"""
        if self.udp_socket:
            self.logger.info("正在关闭 TTS UDP socket...")
            self.udp_socket.close()
            self.udp_socket = None
        # 可以考虑添加取消正在进行的 TTS 的逻辑
        await super().cleanup()

    async def handle_maicore_message(self, message: MessageBase):
        """处理从 MaiCore 收到的消息，如果是文本类型，则进行 TTS 处理。"""
        # 检查消息段是否存在且类型为 'text'
        if message.message_segment and message.message_segment.type == "text":
            original_text = message.message_segment.data
            if not isinstance(original_text, str) or not original_text.strip():
                self.logger.debug("收到非字符串或空文本消息段，跳过 TTS。")
                return

            original_text = original_text.strip()
            self.logger.info(f"收到文本消息，准备 TTS: '{original_text[:50]}...'")

            final_text = original_text

            # 1. (可选) 清理文本 - 通过服务调用
            cleanup_service = self.core.get_service("text_cleanup")
            if cleanup_service:
                self.logger.debug("找到 text_cleanup 服务，尝试清理文本...")
                try:
                    # 确保调用的是 await clean_text(text)
                    cleaned = await cleanup_service.clean_text(original_text)
                    if cleaned:
                        self.logger.info(
                            f"文本经 Cleanup 服务清理: '{cleaned[:50]}...' (原: '{original_text[:50]}...')"
                        )
                        final_text = cleaned
                    else:
                        self.logger.warning("Cleanup 服务调用失败或返回空，使用原始文本。")
                except AttributeError:
                    self.logger.error("获取到的 'text_cleanup' 服务没有 'clean_text' 方法。")
                except Exception as e:
                    self.logger.error(f"调用 text_cleanup 服务时出错: {e}", exc_info=True)
            else:
                # 如果配置中 cleanup_llm.enable 为 true 但服务未注册，可能需要警告
                cleanup_config_in_tts = self.tts_config.get("cleanup_llm", {})
                if cleanup_config_in_tts.get("enable", False):
                    self.logger.warning(
                        "Cleanup LLM 在 TTS 配置中启用，但未找到 'text_cleanup' 服务。请确保 CleanupLLMPlugin 已启用并成功加载。"
                    )
                else:
                    self.logger.debug("未找到 text_cleanup 服务 (可能未启用 CleanupLLMPlugin)。")

            if not final_text:
                self.logger.warning("清理后文本为空，跳过后续处理。")
                return

            # 2. (可选) UDP 广播
            if self.udp_enabled and self.udp_socket and self.udp_dest:
                self._broadcast_text(final_text)

            # 3. 执行 TTS
            await self._speak(final_text)
        else:
            # 可以选择性地记录收到的非文本消息
            # msg_type = message.message_segment.type if message.message_segment else "No Segment"
            # self.logger.debug(f"收到非文本类型消息 ({msg_type})，TTS 插件跳过。")
            pass

    def _broadcast_text(self, text: str):
        """通过 UDP 发送文本 (来自 tts_monitor.py / mmc_client.py)。"""
        if self.udp_socket and self.udp_dest:
            try:
                message_bytes = text.encode("utf-8")
                self.udp_socket.sendto(message_bytes, self.udp_dest)
                self.logger.debug(f"已发送 TTS 内容到 UDP 监听器: {self.udp_dest}")
            except Exception as e:
                self.logger.warning(f"发送 TTS 内容到 UDP 监听器失败: {e}")

    async def _speak(self, text: str):
        """执行 TTS 合成和播放，并通知 Subtitle Service。支持多种 TTS 引擎。"""
        if "sf" not in globals() or "sd" not in globals():
            self.logger.error("缺少必要的音频库 (soundfile, sounddevice)，无法播放。")
            return

        self.logger.debug(f"请求播放: '{text[:30]}...'")

        # --- 启动口型同步会话 ---
        vts_lip_sync_service = self.core.get_service("vts_lip_sync")
        if vts_lip_sync_service:
            try:
                await vts_lip_sync_service.start_lip_sync_session(text)
            except Exception as e:
                self.logger.debug(f"启动口型同步会话失败: {e}")

        async with self.tts_lock:
            self.logger.debug(f"获取 TTS 锁，开始处理: '{text[:30]}...'")
            tmp_filename = None
            duration_seconds: Optional[float] = None  # 初始化时长变量
            audio_array = None  # 初始化音频数组
            samplerate = None  # 初始化采样率
            try:
                # --- 选择 TTS 引擎进行合成 ---
                if self.omni_enabled and self.omni_tts:
                    # --- Omni TTS 合成 ---
                    self.logger.info(f"使用 Omni TTS 引擎合成: {text[:30]}...")
                    audio_data_bytes = await self.omni_tts.generate_audio(text)

                    # 创建临时文件以计算时长
                    with tempfile.NamedTemporaryFile(
                        delete=False, suffix=".wav", dir=tempfile.gettempdir()
                    ) as tmp_file:
                        tmp_filename = tmp_file.name
                        tmp_file.write(audio_data_bytes)
                    self.logger.debug(f"Omni TTS 音频已保存到临时文件: {tmp_filename}")

                    # 读取音频并计算时长
                    audio_array, samplerate = await asyncio.to_thread(sf.read, tmp_filename, dtype="float32")

                else:
                    # --- Edge TTS 合成 ---
                    self.logger.info(f"使用 Edge TTS 引擎合成: {text[:30]}...")
                    if "edge_tts" not in globals():
                        self.logger.error("Edge TTS 库不可用，无法使用 Edge TTS 引擎。")
                        return

                    communicate = edge_tts.Communicate(text, self.voice)
                    with tempfile.NamedTemporaryFile(
                        delete=False, suffix=".mp3", dir=tempfile.gettempdir()
                    ) as tmp_file:
                        tmp_filename = tmp_file.name
                    self.logger.debug(f"创建临时文件: {tmp_filename}")
                    await asyncio.to_thread(communicate.save_sync, tmp_filename)
                    self.logger.debug(f"Edge TTS 音频已保存到临时文件: {tmp_filename}")

                    # 读取音频并计算时长
                    audio_array, samplerate = await asyncio.to_thread(sf.read, tmp_filename, dtype="float32")

                # 检查音频数据是否成功加载
                if audio_array is None or samplerate is None:
                    self.logger.error("音频数据加载失败，无法播放。")
                    return

                # --- 计算音频时长 ---
                self.logger.info(f"读取音频完成，采样率: {samplerate} Hz")
                if samplerate > 0 and isinstance(audio_array, np.ndarray):
                    duration_seconds = len(audio_array) / samplerate
                    self.logger.info(f"计算得到音频时长: {duration_seconds:.3f} 秒")
                else:
                    self.logger.warning("无法计算音频时长 (采样率或数据无效)")

                # --- 通知 Subtitle Service (如果获取到时长) ---
                if duration_seconds is not None and duration_seconds > 0:
                    subtitle_service = self.core.get_service("subtitle_service")
                    if subtitle_service:
                        self.logger.debug("找到 subtitle_service，准备记录语音信息...")
                        try:
                            # 异步调用，不阻塞播放
                            asyncio.create_task(subtitle_service.record_speech(text, duration_seconds))
                        except AttributeError:
                            self.logger.error("获取到的 'subtitle_service' 没有 'record_speech' 方法。")
                        except Exception as e:
                            self.logger.error(f"调用 subtitle_service.record_speech 时出错: {e}", exc_info=True)
                    # else: # 可以选择性记录服务未找到
                    #    self.logger.debug("未找到 subtitle_service。")

                # --- 播放音频并实时进行口型同步 ---
                self.logger.info(f"开始播放音频 (设备索引: {self.output_device_index})...")

                # 如果有VTube Studio口型同步服务，使用流式播放进行实时口型同步
                if vts_lip_sync_service:
                    await self._play_with_lip_sync(audio_array, samplerate, vts_lip_sync_service)
                else:
                    # 没有口型同步服务时，使用原来的播放方式
                    await asyncio.to_thread(
                        sd.play, audio_array, samplerate=samplerate, device=self.output_device_index, blocking=True
                    )

                self.logger.info("TTS 播放完成。")

            except (sf.SoundFileError, sd.PortAudioError, edge_tts.exceptions.NoAudioReceived, Exception) as e:
                log_level = "ERROR"
                if isinstance(e, edge_tts.exceptions.NoAudioReceived):
                    log_level = "WARNING"  # Treat no audio as a warning maybe
                self.logger.log(
                    log_level,
                    f"TTS 处理或播放时发生错误: {type(e).__name__} - {e}",
                    exc_info=isinstance(e, Exception)
                    and not isinstance(e, (sf.SoundFileError, sd.PortAudioError, edge_tts.exceptions.NoAudioReceived)),
                )
            finally:
                # --- 停止口型同步会话 ---
                if vts_lip_sync_service:
                    try:
                        await vts_lip_sync_service.stop_lip_sync_session()
                    except Exception as e:
                        self.logger.debug(f"停止口型同步会话失败: {e}")

                if tmp_filename and os.path.exists(tmp_filename):
                    try:
                        os.remove(tmp_filename)
                        self.logger.debug(f"已删除临时文件: {tmp_filename}")
                    except Exception as e_rem:
                        self.logger.warning(f"删除临时文件 {tmp_filename} 时出错: {e_rem}")
                self.logger.debug(f"释放 TTS 锁: '{text[:30]}...'")

    async def _play_with_lip_sync(self, audio_data: np.ndarray, samplerate: int, vts_lip_sync_service):
        """
        播放音频并同时进行口型同步分析

        Args:
            audio_data: 音频数据数组
            samplerate: 采样率
            vts_lip_sync_service: VTube Studio口型同步服务
        """
        try:
            # 转换音频数据为int16格式用于口型同步分析
            if audio_data.dtype != np.int16:
                # 将float32转换为int16
                audio_int16 = (audio_data * 32767).astype(np.int16)
            else:
                audio_int16 = audio_data

            # 计算每个分块的样本数（每100ms一个分块）
            chunk_duration = 0.1  # 100ms
            chunk_samples = int(samplerate * chunk_duration)

            # 获取当前事件循环，用于在回调函数中安全调度协程
            loop = asyncio.get_running_loop()

            # 使用回调函数进行流式播放和口型同步
            chunk_index = 0

            def audio_callback(outdata, frames, time, status):
                nonlocal chunk_index
                try:
                    start_idx = chunk_index * frames
                    end_idx = start_idx + frames

                    if start_idx < len(audio_data):
                        # 获取当前帧的音频数据
                        current_chunk = audio_data[start_idx:end_idx]

                        # 如果数据不足一帧，用零填充
                        if len(current_chunk) < frames:
                            padded_chunk = np.zeros(frames, dtype=audio_data.dtype)
                            padded_chunk[: len(current_chunk)] = current_chunk
                            current_chunk = padded_chunk

                        outdata[:] = current_chunk.reshape(-1, 1)

                        # 异步发送音频数据进行口型同步分析
                        if chunk_index % (chunk_samples // frames) == 0:  # 每100ms分析一次
                            analysis_chunk = audio_int16[start_idx:end_idx]
                            if len(analysis_chunk) > 0:
                                # 将音频数据转换为字节格式
                                chunk_bytes = analysis_chunk.tobytes()
                                # 安全地在主事件循环中调度口型同步分析协程
                                try:
                                    asyncio.run_coroutine_threadsafe(
                                        vts_lip_sync_service.process_tts_audio(chunk_bytes, sample_rate=samplerate),
                                        loop,
                                    )
                                except Exception:
                                    # 避免在回调中记录太多日志，可能影响音频性能
                                    pass
                    else:
                        # 音频播放完成，输出静音
                        outdata.fill(0)

                    chunk_index += 1

                except Exception as e:
                    self.logger.error(f"音频回调函数出错: {e}")
                    outdata.fill(0)

            # 创建并启动音频流
            with sd.OutputStream(
                samplerate=samplerate,
                channels=1,
                dtype=audio_data.dtype,
                callback=audio_callback,
                device=self.output_device_index,
                blocksize=chunk_samples,
            ) as _stream:  # 使用下划线前缀表示有意忽略此变量
                # 计算播放时长并等待播放完成
                play_duration = len(audio_data) / samplerate
                await asyncio.sleep(play_duration + 0.5)  # 额外等待0.5秒确保播放完成

        except Exception as e:
            self.logger.error(f"流式播放和口型同步出错: {e}", exc_info=True)
            # 如果流式播放失败，回退到普通播放
            await asyncio.to_thread(
                sd.play, audio_data, samplerate=samplerate, device=self.output_device_index, blocking=True
            )


# --- Plugin Entry Point ---
plugin_entrypoint = TTSPlugin
