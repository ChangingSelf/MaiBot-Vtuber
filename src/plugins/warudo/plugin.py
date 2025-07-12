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
        # 新增：同步偏移量，用于微调口型同步，单位为秒

        # 口型同步状态变量
        self.audio_buffer = deque(maxlen=self.sample_rate * 2)  # 2秒音频缓存
        self.current_vowel_values = {"A": 0.0, "I": 0.0, "U": 0.0, "E": 0.0, "O": 0.0}
        self.current_volume = 0.0
        self.is_speaking = False
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
            
    async def handle_maicore_message(self, message: MessageBase):
        """处理从 MaiCore 收到的消息，根据消息段类型进行不同的处理。"""
        if not message.message_segment:
            return

        # 处理 face_emotion 类型的消息段
        if message.message_segment.type == "face_emotion":
            emotion_data_str = message.message_segment.data
            if not isinstance(emotion_data_str, str) or not emotion_data_str.strip():
                self.logger.debug("收到非字符串或空的face_emotion消息段，跳过")
                return

            self.logger.info(f"收到face_emotion消息: '{emotion_data_str}'")

            if not self.is_speaking:
                self.logger.info("当前未在说话，因此忽略收到的face_emotion消息。")
                return

            if not self._is_connected or not self.websocket:
                self.logger.warning("WebSocket未连接，无法发送面部表情。")
                return
            
            try:
                # 验证JSON格式
                payload_data = json.loads(emotion_data_str)
                if "action" not in payload_data or "data" not in payload_data:
                    self.logger.warning(f"face_emotion数据格式不正确，缺少'action'或'data': {emotion_data_str}")
                    return
                
                # 直接将原始JSON字符串发送到WebSocket
                await self.websocket.send(emotion_data_str)
                self.logger.info(f"已发送面部表情动作: {emotion_data_str}")

            except json.JSONDecodeError:
                self.logger.error(f"face_emotion消息不是有效的JSON格式: {emotion_data_str}")
            except websockets.exceptions.ConnectionClosed:
                self.logger.warning("WebSocket连接已关闭，无法发送面部表情。")
            except Exception as e:
                self.logger.error(f"发送面部表情时发生错误: {e}", exc_info=True)

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
            D = librosa.stft(audio_np)
            magnitude, phase = librosa.magphase(D)
            freqs = librosa.fft_frequencies(sr=sample_rate, n_fft=D.shape[0]*2-2)
            
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
            
            energy = np.sum(magnitude[f1_idx-5:f1_idx+5]) + np.sum(magnitude[f2_idx-5:f2_idx+5])
            vowel_strengths[f"vowel_{vowel.lower()}"] = energy / total_energy
            
        return vowel_strengths

    async def process_tts_audio(self, audio_data: bytes, sample_rate: int):
        """Receives audio from TTS, analyzes it, and sends parameters via WebSocket."""
        if not self.is_speaking or not self._is_connected:
            return

        with self.audio_analysis_lock:
            self.accumulated_audio.extend(audio_data)

        # 使用 while 循环处理所有累积的音频数据
        required_bytes = self.buffer_size * 2  # int16 = 2 bytes
        while len(self.accumulated_audio) >= required_bytes:
            # 在循环内部锁定，仅在操作共享数据时
            with self.audio_analysis_lock:
                chunk_to_analyze = self.accumulated_audio[:required_bytes]
                self.accumulated_audio = self.accumulated_audio[required_bytes:]

            analysis_result = await self.analyze_audio_chunk(bytes(chunk_to_analyze), sample_rate)
            if analysis_result:
                await self._update_lip_sync_parameters(analysis_result)

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
        # 不再发送 MouthOpen，由 MouthShut 在会话开始和结束时控制
        # params_to_send["MouthOpen"] = min(1.0, self.current_volume / self.volume_threshold)
        
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
        self.is_speaking = True
        self.accumulated_audio.clear()
        if self._is_connected and self.websocket:
             try:
                # 使用新的格式发送会话开始信号
                payload = json.dumps({"action": "session_start", "data": text})
                await self.websocket.send(payload)
                
                # 发送 MouthShut: 0，表示嘴巴开始活动
                payload = json.dumps({"action": "MouthShut", "data": 0.0})
                await self.websocket.send(payload)
                self.logger.info("Sent MouthShut: 0 at session start.")
             except Exception as e:
                self.logger.error(f"Failed to send session_start signal or MouthShut: {e}")

    async def stop_lip_sync_session(self):
        """Called by TTS plugin to stop a lip-sync session."""
        self.logger.info("Lip-sync session stopped.")
        self.is_speaking = False
        if self._is_connected and self.websocket:
            try:
                # 发送最终的闭嘴指令（清零所有元音值）
                await self._update_lip_sync_parameters({"volume": 0.0})

                # 发送 MouthShut: 1，表示嘴巴完全关闭
                payload = json.dumps({"action": "MouthShut", "data": 1.0})
                await self.websocket.send(payload)
                self.logger.info("Sent MouthShut: 1 at session stop.")

                # 使用新的格式发送会话结束信号
                payload = json.dumps({"action": "session_stop", "data": True})
                await self.websocket.send(payload)
            except Exception as e:
                self.logger.error(f"Failed to send session_stop signal or MouthShut: {e}")

# 必须有这个入口点
plugin_entrypoint = WebsocketLipSyncPlugin 