# Amaidesu TTS Plugin: src/plugins/tts/plugin.py

import asyncio
import logging
import os
import sys
import socket
import tempfile
from typing import Dict, Any, Optional
import numpy as np # 确保导入 numpy

# --- Dependencies Check (Inform User) ---
# Try importing required libraries and inform the user if they are missing.
# Actual error will be caught later if import fails during use.
dependencies_ok = True
try:
    import edge_tts
except ImportError:
    print("依赖缺失: 请运行 'pip install edge-tts' 来使用 TTS 功能。", file=sys.stderr)
    dependencies_ok = False
try:
    import sounddevice as sd
    import soundfile as sf
except ImportError:
    print("依赖缺失: 请运行 'pip install sounddevice soundfile' 来使用音频播放功能。", file=sys.stderr)
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
from core.plugin_manager import BasePlugin
from core.amaidesu_core import AmaidesuCore
from maim_message import MessageBase # Import MessageBase for type hint

logger = logging.getLogger(__name__)

# --- Plugin Configuration Loading ---
_PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
_CONFIG_FILE = os.path.join(_PLUGIN_DIR, "config.toml")

def load_plugin_config() -> Dict[str, Any]:
    """Loads the plugin's specific config.toml file."""
    if tomllib is None:
        logger.error("TOML library not available, cannot load TTS plugin config.")
        return {}
    try:
        with open(_CONFIG_FILE, "rb") as f:
            config = tomllib.load(f)
            logger.info(f"成功加载 TTS 插件配置文件: {_CONFIG_FILE}")
            return config
    except FileNotFoundError:
        logger.warning(f"TTS 插件配置文件未找到: {_CONFIG_FILE}。将使用默认值。")
    except tomllib.TOMLDecodeError as e:
        logger.error(f"TTS 插件配置文件 '{_CONFIG_FILE}' 格式无效: {e}。将使用默认值。")
    except Exception as e:
        logger.error(f"加载 TTS 插件配置文件 '{_CONFIG_FILE}' 时发生未知错误: {e}", exc_info=True)
    return {}

class TTSPlugin(BasePlugin):
    """处理文本消息，执行 TTS 播放，可选 Cleanup LLM 和 UDP 广播。"""
    _is_amaidesu_plugin: bool = True # Plugin marker

    def __init__(self, core: AmaidesuCore, plugin_config: Dict[str, Any]):
        # Note: plugin_config from PluginManager is the global [plugins] config
        # We load our own specific config here.
        super().__init__(core, plugin_config)
        self.tts_config = load_plugin_config() # Load src/plugins/tts/config.toml

        # --- TTS Service Initialization (from tts_service.py) ---
        tts_settings = self.tts_config.get('tts', {})
        self.voice = tts_settings.get('voice', 'zh-CN-XiaoxiaoNeural')
        self.output_device_name = tts_settings.get('output_device_name') or None # Explicit None if empty string
        self.output_device_index = self._find_device_index(self.output_device_name, kind='output')
        self.tts_lock = asyncio.Lock()
        self.logger.info(f"TTS 服务组件初始化。语音: {self.voice}, 输出设备: {self.output_device_name or '默认设备'}")

        # --- UDP Broadcast Initialization (from tts_monitor.py / mmc_client.py) ---
        udp_config = self.tts_config.get('udp_broadcast', {})
        self.udp_enabled = udp_config.get('enable', False)
        self.udp_socket = None
        self.udp_dest = None
        if self.udp_enabled:
            host = udp_config.get('host', '127.0.0.1')
            port = udp_config.get('port', 9998)
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

    def _find_device_index(self, device_name: Optional[str], kind: str = 'output') -> Optional[int]:
        """根据设备名称查找设备索引 (来自 tts_service.py)。"""
        if 'sd' not in globals(): # Check if sounddevice was imported
            self.logger.error("sounddevice 库不可用，无法查找音频设备。")
            return None
        try:
            devices = sd.query_devices()
            if device_name:
                for i, device in enumerate(devices):
                    # Case-insensitive partial match
                    if device_name.lower() in device['name'].lower() and device[f'{kind}_channels'] > 0:
                        self.logger.info(f"找到 {kind} 设备 '{device['name']}' (匹配 '{device_name}')，索引: {i}")
                        return i
                self.logger.warning(f"未找到名称包含 '{device_name}' 的 {kind} 设备，将使用默认设备。")
            
            # Determine default device index based on kind
            default_device_indices = sd.default.device
            default_index = default_device_indices[1] if kind == 'output' else default_device_indices[0]
            if default_index == -1: # Indicates no default device found by sounddevice
                 self.logger.warning(f"未找到默认 {kind} 设备，将使用 None (由 sounddevice 选择)。")
                 return None
                 
            self.logger.info(f"使用默认 {kind} 设备索引: {default_index} ({sd.query_devices(default_index)['name']})")
            return default_index
        except Exception as e:
            self.logger.error(f"查找音频设备时出错: {e}，将使用 None (由 sounddevice 选择)", exc_info=True)
            return None

    async def setup(self):
        """注册处理来自 MaiCore 的 'text' 类型消息。"""
        await super().setup()
        # 注册处理函数，监听所有 WebSocket 消息
        # 我们将在处理函数内部检查消息类型是否为 'text'
        self.core.register_websocket_handler("*", self.handle_maicore_message)
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
                         self.logger.info(f"文本经 Cleanup 服务清理: '{cleaned[:50]}...' (原: '{original_text[:50]}...')")
                         final_text = cleaned
                     else:
                         self.logger.warning("Cleanup 服务调用失败或返回空，使用原始文本。")
                except AttributeError:
                     self.logger.error("获取到的 'text_cleanup' 服务没有 'clean_text' 方法。")
                except Exception as e:
                     self.logger.error(f"调用 text_cleanup 服务时出错: {e}", exc_info=True)
            else:
                 # 如果配置中 cleanup_llm.enable 为 true 但服务未注册，可能需要警告
                 cleanup_config_in_tts = self.tts_config.get('cleanup_llm', {})
                 if cleanup_config_in_tts.get('enable', False):
                      self.logger.warning("Cleanup LLM 在 TTS 配置中启用，但未找到 'text_cleanup' 服务。请确保 CleanupLLMPlugin 已启用并成功加载。")
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
                message_bytes = text.encode('utf-8')
                self.udp_socket.sendto(message_bytes, self.udp_dest)
                self.logger.debug(f"已发送 TTS 内容到 UDP 监听器: {self.udp_dest}")
            except Exception as e:
                self.logger.warning(f"发送 TTS 内容到 UDP 监听器失败: {e}")

    async def _speak(self, text: str):
        """执行 Edge TTS 合成和播放，并通知 Subtitle Service。"""
        if 'edge_tts' not in globals() or 'sf' not in globals() or 'sd' not in globals():
            self.logger.error("缺少必要的 TTS 或音频库 (edge_tts, soundfile, sounddevice)，无法播放。")
            return
            
        self.logger.debug(f"请求播放: '{text[:30]}...'")
        async with self.tts_lock:
            self.logger.debug(f"获取 TTS 锁，开始处理: '{text[:30]}...'")
            tmp_filename = None
            duration_seconds: Optional[float] = None # 初始化时长变量
            try:
                # --- TTS 合成 ---
                self.logger.info(f"TTS 正在合成: {text[:30]}...")
                communicate = edge_tts.Communicate(text, self.voice)
                with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3", dir=tempfile.gettempdir()) as tmp_file:
                    tmp_filename = tmp_file.name
                self.logger.debug(f"创建临时文件: {tmp_filename}")
                await asyncio.to_thread(communicate.save_sync, tmp_filename)
                self.logger.debug(f"音频已保存到临时文件: {tmp_filename}")

                # --- 读取音频并计算时长 ---
                audio_data, samplerate = await asyncio.to_thread(sf.read, tmp_filename, dtype='float32')
                self.logger.info(f"读取音频完成，采样率: {samplerate} Hz")
                if samplerate > 0 and isinstance(audio_data, np.ndarray):
                    duration_seconds = len(audio_data) / samplerate
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

                # --- 播放音频 --- 
                self.logger.info(f"开始播放音频 (设备索引: {self.output_device_index})...")
                await asyncio.to_thread(sd.play, audio_data, samplerate=samplerate, device=self.output_device_index, blocking=True)
                self.logger.info("TTS 播放完成。")
                
            except (sf.SoundFileError, sd.PortAudioError, edge_tts.exceptions.NoAudioReceived, Exception) as e:
                log_level = logging.ERROR
                if isinstance(e, edge_tts.exceptions.NoAudioReceived):
                     log_level = logging.WARNING # Treat no audio as a warning maybe
                self.logger.log(log_level, f"TTS 处理或播放时发生错误: {type(e).__name__} - {e}", exc_info=isinstance(e, Exception) and not isinstance(e, (sf.SoundFileError, sd.PortAudioError, edge_tts.exceptions.NoAudioReceived)))
            finally:
                if tmp_filename and os.path.exists(tmp_filename):
                    try:
                        os.remove(tmp_filename)
                        self.logger.debug(f"已删除临时文件: {tmp_filename}")
                    except Exception as e_rem:
                        self.logger.warning(f"删除临时文件 {tmp_filename} 时出错: {e_rem}")
                self.logger.debug(f"释放 TTS 锁: '{text[:30]}...'")

# --- Plugin Entry Point ---
plugin_entrypoint = TTSPlugin 