# src/plugins/websocket_lip_sync/plugin.py

import asyncio
import json
from typing import Any, Dict, Optional, List
import numpy as np
import threading
from collections import deque
import websockets

# 尝试导入音频分析相关库
try:
    import librosa
    import scipy.signal
    AUDIO_ANALYSIS_AVAILABLE = True
except ImportError:
    librosa = None
    scipy = None
    AUDIO_ANALYSIS_AVAILABLE = False

# 从 core 导入基类和核心类
from src.core.plugin_manager import BasePlugin
from src.core.amaidesu_core import AmaidesuCore
from maim_message.message_base import MessageBase

# 导入表情处理模块
from .emotion_handler import EmotionHandler
class WebsocketLipSyncPlugin(BasePlugin):
    """
    Analyzes audio from TTS and sends lip-sync parameters to a specified WebSocket address.
    """

    def __init__(self, core: AmaidesuCore, plugin_config: Dict[str, Any]):
        super().__init__(core, plugin_config)
        self.config = self.plugin_config

        # --- WebSocket 客户端配置 ---
        self.ws_host = self.config.get("ws_host", "localhost")
        self.ws_port = self.config.get("ws_port", 19190)
        self.websocket: Optional[websockets.WebSocketClientProtocol] = None
        self._connection_task: Optional[asyncio.Task] = None
        self._is_connected = False

        # --- 口型同步相关配置 ---
        lip_sync_config = self.config.get("lip_sync", {})
        self.lip_sync_enabled = lip_sync_config.get("enabled", True)
        self.volume_threshold = lip_sync_config.get("volume_threshold", 0.01)
        self.smoothing_factor = lip_sync_config.get("smoothing_factor", 0.3)
        self.vowel_detection_sensitivity = lip_sync_config.get("vowel_detection_sensitivity", 0.5)
        self.sample_rate = lip_sync_config.get("sample_rate", 32000)
        self.buffer_size = lip_sync_config.get("buffer_size", 1024)
        # 音频超时配置：如果超过这个时间没有音频数据，就认为停止说话了
        self.audio_timeout = lip_sync_config.get("audio_timeout", 1.5)  # 0.5秒

        # 状态管理：区分会话状态和说话状态
        self.session_active = False  # 会话是否激活（start到stop之间）
        self.is_speaking = False     # 是否真正在处理音频数据
        self.reseted = False        # 是否重置了嘴部状态
        self.last_audio_time = 0     # 最后一次收到音频数据的时间
        
        # 口型同步状态变量
        self.audio_buffer = deque(maxlen=self.sample_rate * 2)  # 2秒音频缓存
        self.current_vowel_values = {"A": 0.0, "I": 0.0, "U": 0.0, "E": 0.0, "O": 0.0}
        self.current_volume = 0.0
        self.audio_analysis_lock = threading.Lock()
        self.accumulated_audio = bytearray()

        # 元音频率特征
        self.vowel_formants = {
            "A": [730, 1090], "I": [270, 2290], "U": [300, 870],
            "E": [530, 1840], "O": [570, 840],
        }

        # 检查音频分析依赖
        if self.lip_sync_enabled and not AUDIO_ANALYSIS_AVAILABLE:
            self.logger.warning(
                "Lip sync enabled but audio analysis libraries not available. Install with: pip install librosa scipy"
            )
            self.lip_sync_enabled = False
            
        # 初始化表情处理器
        self.emotion_handler = EmotionHandler(self.logger)
        
        # watching消息翻译表
        self.watching_translation = {
            "lens": "相机",
            "danmu": "弹幕区", 
            "wandering": None
        }
            
    async def handle_maicore_message(self, message: MessageBase):
        """处理从 MaiCore 收到的消息，根据消息段类型进行不同的处理。"""
        
        # self.logger.info(message)
        
        if not message.message_segment:
            return

        # self.logger.info(message.message_segment.type)
        # self.logger.info(message.message_segment.data)        # 处理 face_emotion 类型的消息段
        if message.message_segment.type == "face_emotion":
            emotion_data = message.message_segment.data
            self.logger.info(f"收到face_emotion消息: '{emotion_data}'")
            
            # 使用表情处理器处理消息
            await self.emotion_handler.process_emotion_message(
                emotion_data, 
                self.websocket if self._is_connected else None
            )
            
        if message.message_segment.type == "watching":
            watching_data = message.message_segment.data
            self.logger.info(f"收到watching消息: '{watching_data}'")
            
            # 使用翻译表转换data
            translated_data = self.watching_translation.get(str(watching_data), str(watching_data))
            self.logger.info(f"翻译后的watching数据: '{translated_data}'")
            
            # 发送watching动作到WebSocket
            if self._is_connected and self.websocket:
                try:
                    payload = json.dumps({"action": "watching", "data": translated_data})
                    self.logger.info(f"正在发送watching动作: {payload}")
                    await self.websocket.send(payload)
                except websockets.exceptions.ConnectionClosed:
                    self.logger.warning("WebSocket connection closed while trying to send watching data.")
                except Exception as e:
                    self.logger.error(f"Failed to send watching data: {e}", exc_info=True)
            else:
                self.logger.warning("WebSocket not connected, unable to send watching data.")
            

    async def setup(self):
        await super().setup()
        self.logger.info("Initializing WebsocketLipSyncPlugin setup...")
        if not self.lip_sync_enabled:
            self.logger.error("SETUP FAILED for WebsocketLipSyncPlugin: Lip-sync is disabled in config or dependencies (librosa, scipy) are missing.")
            return
        
        self.core.register_websocket_handler("*", self.handle_maicore_message)
        self.logger.info("Warudo 插件已设置，监听所有 MaiCore WebSocket 消息。")

        # 启动连接的后台任务
        self._connection_task = asyncio.create_task(self._connect_websocket(), name="WebSocketLipSync_Connect")
        self.logger.info("WebSocket connection task started.")

        # 注册为TTS音频数据处理器
        self.core.register_service("websocket_lip_sync", self)
        self.logger.info("Registered 'websocket_lip_sync' service for audio analysis.")

    async def _connect_websocket(self):
        """Internal task to connect to the WebSocket server."""
        uri = f"ws://{self.ws_host}:{self.ws_port}"
        while True:
            try:
                self.logger.info(f"Attempting to connect to WebSocket server at {uri}...")
                self.websocket = await websockets.connect(uri)
                self._is_connected = True
                self.logger.info(f"Successfully connected to WebSocket server at {uri}.")
                # Keep the connection alive
                await self.websocket.wait_closed()
            except (websockets.exceptions.ConnectionClosed, ConnectionRefusedError) as e:
                self.logger.warning(f"WebSocket connection lost or refused: {e}. Reconnecting in 5 seconds...")
            except Exception as e:
                self.logger.error(f"An unexpected error occurred with WebSocket connection: {e}. Reconnecting in 5 seconds...")
            finally:
                self._is_connected = False
                self.websocket = None
                await asyncio.sleep(5)

    async def cleanup(self):
        """Close the WebSocket connection and cancel tasks."""
        self.logger.info("Cleaning up WebsocketLipSyncPlugin...")
        if self._connection_task:
            self._connection_task.cancel()
        if self.websocket:
            await self.websocket.close()
            self.logger.info("WebSocket connection closed.")
        await super().cleanup()

    async def analyze_audio_chunk(self, audio_data: bytes, sample_rate: int) -> Dict[str, float]:
        """Analyzes a chunk of audio data and returns lip-sync parameters."""
        if not AUDIO_ANALYSIS_AVAILABLE:
            return {}

        try:
            # 将字节数据转换为numpy数组
            audio_np = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32) / 32768.0

            # 1. 计算音量 (RMS)
            rms = np.sqrt(np.mean(audio_np**2))
            volume = float(rms)

            # 2. 分析元音特征
            # 动态计算合适的FFT窗口大小，确保不超过输入信号长度
            audio_length = len(audio_np)
            n_fft = min(512, audio_length)  # 使用较小的FFT窗口大小，最大不超过音频长度
            
            # 如果音频太短，跳过频谱分析
            if audio_length < 64:  # 最小FFT窗口大小
                vowel_features = {f"vowel_{vowel.lower()}": 0.0 for vowel in self.vowel_formants.keys()}
            else:
                D = librosa.stft(audio_np, n_fft=n_fft, hop_length=n_fft//4)
                magnitude, phase = librosa.magphase(D)
                freqs = librosa.fft_frequencies(sr=sample_rate, n_fft=n_fft)
                vowel_features = self._analyze_vowel_features(magnitude, freqs)

            return {"volume": volume, **vowel_features}
        except Exception as e:
            self.logger.error(f"Error during audio analysis: {e}", exc_info=True)
            return {}

    def _analyze_vowel_features(self, magnitude: np.ndarray, freqs: np.ndarray) -> Dict[str, float]:
        """Analyzes spectral magnitude to determine vowel features."""
        vowel_strengths = {}
        total_energy = np.sum(magnitude)
        if total_energy == 0:
            return {f"vowel_{vowel.lower()}": 0.0 for vowel in self.vowel_formants.keys()}

        for vowel, (f1, f2) in self.vowel_formants.items():
            f1_idx = np.argmin(np.abs(freqs - f1))
            f2_idx = np.argmin(np.abs(freqs - f2))
            
            # 添加边界检查，防止索引越界
            mag_len = magnitude.shape[0]
            f1_start = max(0, f1_idx - 5)
            f1_end = min(mag_len, f1_idx + 5)
            f2_start = max(0, f2_idx - 5)
            f2_end = min(mag_len, f2_idx + 5)
            
            energy = np.sum(magnitude[f1_start:f1_end]) + np.sum(magnitude[f2_start:f2_end])
            vowel_strengths[f"vowel_{vowel.lower()}"] = energy / total_energy
            
        return vowel_strengths

    async def _check_audio_timeout(self):
        """检查音频超时，如果超时则停止说话状态"""
        if self.is_speaking and self.last_audio_time > 0:
            current_time = asyncio.get_event_loop().time()
            if current_time - self.last_audio_time > self.audio_timeout:
                self.logger.info("音频数据超时，停止说话状态")
                await self._stop_speaking()

    async def _start_speaking(self):
        """开始说话状态"""
        if not self.is_speaking:
            # 记录说话前的嘴部状态
            if self._is_connected and self.websocket:
                await self.emotion_handler.record_current_mouth_state(self.websocket)
                # 重置所有嘴部动作为0，为口型同步做准备
                await self.emotion_handler.reset_mouth_actions(self.websocket)
            
            self.is_speaking = True
            self.reseted = True
            self.emotion_handler.set_speaking_state(True)
            self.logger.info("开始说话状态")

    async def _stop_speaking(self):
        """停止说话状态"""
        if self.is_speaking:
            self.is_speaking = False
            self.emotion_handler.set_speaking_state(False)
            
            if self._is_connected and self.websocket:
                try:
                    # 发送最终的闭嘴指令（清零所有元音值）
                    await self._update_lip_sync_parameters({"volume": 0.0})
                    
                    
                    await self.emotion_handler.restore_pre_speaking_mouth_state(self.websocket)
                    # 发送延迟的嘴部动作（如果有）
                    await self.emotion_handler.send_pending_mouth_actions(self.websocket)
                    
                    # 恢复说话前的嘴部状态
                    
                    
                except Exception as e:
                    self.logger.error(f"停止说话时处理嘴部状态失败: {e}")
            
            self.logger.info("停止说话状态")

    async def process_tts_audio(self, audio_data: bytes, sample_rate: int):
        """Receives audio from TTS, analyzes it, and sends parameters via WebSocket."""
        # 只检查会话是否激活和连接状态
        if not self.session_active or not self._is_connected:
            return

        # 更新最后音频时间
        self.last_audio_time = asyncio.get_event_loop().time()
        
        # 开始说话状态（如果还没有的话）
        if not self.reseted:
            await self._start_speaking()

        with self.audio_analysis_lock:
            self.accumulated_audio.extend(audio_data)
            
        self.logger.info(f"accumulated_audio: {len(self.accumulated_audio)}")

        # 使用 while 循环处理所有累积的音频数据
        required_bytes = self.buffer_size * 2  # int16 = 2 bytes
        while len(self.accumulated_audio) >= required_bytes:
            # 在循环内部锁定，仅在操作共享数据时
            with self.audio_analysis_lock:
                chunk_to_analyze = self.accumulated_audio[:required_bytes]
                self.accumulated_audio = self.accumulated_audio[required_bytes:]

            self.logger.info(f"chunk_to_analyze: {len(chunk_to_analyze)}")
            analysis_result = await self.analyze_audio_chunk(bytes(chunk_to_analyze), sample_rate)
            if analysis_result:
                self.logger.info(f"analysis_result: {analysis_result}")
                await self._update_lip_sync_parameters(analysis_result)

        # 检查音频超时
        await self._check_audio_timeout()

        # --- 修改：计算并等待块播放时长，并加入可配置的偏移量 ---
        try:
            # 计算当前处理的音频块的播放时长
            chunk_duration = self.buffer_size / sample_rate
            # 等待音频块播放完成，实现与音频播放同步
            await asyncio.sleep(chunk_duration)
        except Exception as e:
            self.logger.error(f"Error during lip-sync delay: {e}", exc_info=True)

    async def _update_lip_sync_parameters(self, analysis_result: Dict[str, float]):
        """Smooths parameters and sends them over WebSocket one by one."""
        if not self._is_connected or not self.websocket:
            return

        # 平滑处理参数
        smoothing = self.smoothing_factor
        self.current_volume = self.current_volume * smoothing + analysis_result.get("volume", 0.0) * (1 - smoothing)
        
        for vowel in self.vowel_formants.keys():
            key = f"vowel_{vowel.lower()}"
            self.current_vowel_values[vowel] = self.current_vowel_values[vowel] * smoothing + analysis_result.get(key, 0.0) * (1 - smoothing)

        # 准备要发送的数据
        params_to_send = {}
        
        # 添加元音参数
        for vowel, value in self.current_vowel_values.items():
            params_to_send[f"Vowel{vowel}"] = value * self.vowel_detection_sensitivity
        
        # 逐个发送参数
        for action, data in params_to_send.items():
            try:
                payload = json.dumps({"action": action, "data": data})
                self.logger.info(f"正在发送口型动作: {payload}")
                await self.websocket.send(payload)
            except websockets.exceptions.ConnectionClosed:
                self.logger.warning("WebSocket connection closed while trying to send data.")
                break # 连接已关闭，无需继续发送
            except Exception as e:
                self.logger.error(f"Failed to send parameter data for action '{action}': {e}", exc_info=True)

    async def start_lip_sync_session(self, text: str = ""):
        """Called by TTS plugin to start a lip-sync session."""
        self.logger.info("Lip-sync session started.")
        
        # 激活会话，但不立即设置说话状态
        self.session_active = True
        self.accumulated_audio.clear()
        self.last_audio_time = 0
        self.reseted = False

    async def stop_lip_sync_session(self):
        """Called by TTS plugin to stop a lip-sync session."""
        self.logger.info("Lip-sync session stopped.")
        
        # 结束会话
        self.session_active = False
        
        # 如果正在说话，停止说话状态（这会自动处理嘴部状态恢复）
        if self.is_speaking:
            await self._stop_speaking()

# 必须有这个入口点
plugin_entrypoint = WebsocketLipSyncPlugin 