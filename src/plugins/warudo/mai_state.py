import asyncio
import json
import logging
import time
from typing import Dict, Any, Optional
from enum import Enum
import websockets
from .action_sender import action_sender

ALL_EYEBROW_STATE = {
    "eyebrow_happy_weak": 0.0,
    "eyebrow_happy_strong": 0.0,
    "eyebrow_angry_weak": 0.0,
    "eyebrow_angry_strong": 0.0,
    "eyebrow_sad_weak": 0.0,
    "eyebrow_sad_strong": 0.0,
}

class EyebrowState():
    def __init__(self):
        self.first_layer = {
            "eyebrow_happy_weak": 0.0,
            "eyebrow_happy_strong": 0.0,
            "eyebrow_angry_weak": 0.0,
            "eyebrow_angry_strong": 0.0,
            "eyebrow_sad_weak": 0.0,
            "eyebrow_sad_strong": 0.0,
        }
        
        self.changed = True
        
    async def send_state(self):
        state = self.get_eyebrow_state()
        for k, v in state.items():
            await action_sender.send_action(k, v)
                
    def get_eyebrow_state(self) -> Dict[str, float]:
        result = ALL_EYEBROW_STATE.copy()
        if any(v > 0 for v in self.first_layer.values()):
            for k in result:
                if k in self.first_layer:
                    result[k] = self.first_layer[k]
        return result
                    
    def set_first_layer(self, key: str):
        for k in self.first_layer:
            self.first_layer[k] = 0.0
        self.first_layer[key] = 1.0
        self.changed = True

ALL_EYE_STATE = {
    "eye_happy_strong": 0.0,
    "eye_close": 0.0,
}

class EyeState():
    def __init__(self):
        self.first_layer = {
            "eye_happy_strong": 0.0,
            "eye_close": 0.0,
        }
        
        self.is_blinking = False
        
        self.changed = True
        
    def can_blink(self):
        # 只要 eye_happy_weak 或 eye_close 有值（非0），就不能眨眼
        if self.first_layer.get("eye_happy_strong", 0.0) > 0 or self.first_layer.get("eye_close", 0.0) > 0:
            return False
        return True
        
    async def send_state(self):
        state = self.get_eye_state()
        for k, v in state.items():
            await action_sender.send_action(k, v)
            
    def set_blinking(self, is_blinking: bool):
        self.is_blinking = is_blinking
        self.changed = True
    
    def set_first_layer(self, key: str):
        if not key:
            for k in self.first_layer:
                self.first_layer[k] = 0.0
            self.changed = True
            return
        
        for k in self.first_layer:
            self.first_layer[k] = 0.0
        self.first_layer[key] = 1.0
        self.changed = True
        
    def get_eye_state(self) -> Dict[str, float]:
        result = ALL_EYE_STATE.copy()
        if self.is_blinking:
            result["eye_close"] = 1.0
            return result

        if any(v > 0 for v in self.first_layer.values()):
            for k in result:
                if k in self.first_layer:
                    result[k] = self.first_layer[k]
        return result


ALL_PUPIL_STATE = {
    "eye_shift_left": 0.0,
    "eye_shift_right": 0.0,
}

class PupilState():
    """瞳孔状态"""
    def __init__(self):
        self.first_layer = {
            "eye_shift_left": 0.0,
            "eye_shift_right": 0.0,
        }
        self.changed = True
        
    async def send_state(self):
        state = self.get_pupil_state()
        for k, v in state.items():
            await action_sender.send_action(k, v)
        
    def get_pupil_state(self) -> Dict[str, float]:
        result = ALL_PUPIL_STATE.copy()
        if any(v > 0 for v in self.first_layer.values()):
            for k in result:
                if k in self.first_layer:
                    result[k] = self.first_layer[k]
        return result
    
    def set_state(self, direction: str, intensity: float):
        self.first_layer[direction] = intensity
        self.changed = True

ALL_MOUTH_STATE = {
    "mouth_happy_strong": 0.0,
    "mouth_angry_weak": 0.0,
    "VowelA": 0.0,
    "VowelI": 0.0,
    "VowelU": 0.0,
    "VowelE": 0.0,
    "VowelO": 0.0,
}

class MouthState():
    """嘴巴状态，获取状态时，如果有口型，会优先只返回口型状态"""
    def __init__(self):
        self.first_layer = {
            "mouth_happy_strong": 0.0,
            "mouth_angry_weak": 0.0,
        }
        self.second_layer = {
            "VowelA": 0.0,
            "VowelI": 0.0,
            "VowelU": 0.0,
            "VowelE": 0.0,
            "VowelO": 0.0,
        }
        
        self.changed = True
        
    async def send_state(self):
        state = self.get_mouth_state()
        for k, v in state.items():
            await action_sender.send_action(k, v)
            
    def set_first_layer(self, key: str):
        for k in self.first_layer:
            self.first_layer[k] = 0.0
        self.first_layer[key] = 1.0
        self.changed = True
        

    def get_mouth_state(self) -> Dict[str, float]:
        result = ALL_MOUTH_STATE.copy()
        if any(v > 0 for v in self.second_layer.values()):
            for k in result:
                if k in self.second_layer:
                    result[k] = self.second_layer[k]
        else:
            for k in result:
                if k in self.first_layer:
                    result[k] = self.first_layer[k]
                elif k in self.second_layer:
                    result[k] = self.second_layer[k]
        return result
    
    def set_vowel_state(self, lip_sync_states):
        """
        设置口型状态
        
        Args:
            lip_sync_states: 字典，格式为 {"VowelA": 0.8, "VowelI": 0.3, ...}
        """
        for vowel_key, intensity in lip_sync_states.items():
            if vowel_key in self.second_layer:
                # 限制强度值范围
                intensity = max(0.0, min(1.0, float(intensity)))
                self.second_layer[vowel_key] = intensity
                
                self.changed = True



class GazeState(Enum):
    """视线状态枚举"""
    WANDERING = "wandering"  # 随意
    LENS = "lens"           # 相机
    DANMU = "danmu"         # 弹幕


class WarudoStateManager:
    """Warudo模型状态管理器"""
    
    def __init__(self, logger: logging.Logger):
        self.logger = logger
        
        self.eye_state = EyeState()
        self.pupil_state = PupilState()
        self.mouth_state = MouthState()
        self.eyebrow_state = EyebrowState()
    
        
        # 需要使用debug日志级别的动作列表
        self.debug_actions = {
            "eye_shift_left",  # 默认嘴型
            "eye_shift_right",      # 默认视线
            "eye_close",      # 眨眼动作
        }
        self.logger.info("Warudo状态管理器已初始化")
        
        asyncio.create_task(self.check_and_send_state())
        self.logger.info("检测发送已启动")
        

    
    async def check_and_send_state(self):
        while True:
            # self.logger.info("检查并发送状态")
            await asyncio.sleep(0.1)
            if self.mouth_state.changed:
                await self.mouth_state.send_state()
                self.logger.info("发送嘴巴状态")
                self.mouth_state.changed = False
                
            if self.eye_state.changed:
                await self.eye_state.send_state()
                self.logger.info("发送眼睛状态")
                self.eye_state.changed = False
                
            if self.pupil_state.changed:
                await self.pupil_state.send_state()
                self.logger.info("发送瞳孔状态")
                self.pupil_state.changed = False
                
            if self.eyebrow_state.changed:
                await self.eyebrow_state.send_state()
                self.logger.info("发送眉毛状态")
                self.eyebrow_state.changed = False
    
    

    


class MoodStateManager:
    """心情状态管理器"""
    
    def __init__(self, state_manager: WarudoStateManager, logger: logging.Logger):
        self.state_manager = state_manager
        self.logger = logger
        
        # 当前心情状态 (1-10)
        self.current_mood = {
            "joy": 5,
            "anger": 1,
            "sorrow": 1,
            "fear": 1
        }
        
        # 表情组合模板（根据新的表情动作调整）
        self.expression_combinations = {
            "happy": {
                "eye": "",
                "eyebrow": "eyebrow_happy_weak", 
                "mouth": "mouth_happy_strong",
            },
            "very_happy": {
                "eye": "eye_happy_strong",
                "eyebrow": "eyebrow_happy_strong",
                "mouth": "mouth_happy_strong",
            },
            "sad": {
                "eye": "",
                "eyebrow": "eyebrow_sad_strong",
                "mouth": "mouth_happy_strong",
            },
            "angry": {
                "eye": "",
                "eyebrow": "eyebrow_angry_strong",
                "mouth": "mouth_angry_weak",
            },
            "neutral": {
                "eye": "",
                "eyebrow": "",
                "mouth": "",
            }
        }
        
        # 当前表情状态
        self.current_expression = "neutral"
        
        self.logger.info("心情状态管理器已初始化")
    
    def update_mood(self, mood_data: Dict[str, Any]) -> bool:
        """
        更新心情状态
        
        Args:
            mood_data: 包含心情数据的字典
            
        Returns:
            bool: 是否有变化发生
        """
        # mood_data里必定有这四个emotion，无需判断
        has_changes = False

        for emotion in ["joy", "anger", "sorrow", "fear"]:
            new_value = max(1, min(10, int(mood_data[emotion])))
            if self.current_mood[emotion] != new_value:
                self.current_mood[emotion] = new_value
                has_changes = True

        if has_changes:
            self.logger.info(f"心情状态已更新: {self.current_mood}")
            # 根据新心情更新表情
            self._update_expression_by_mood()

        return has_changes
    
    def _update_expression_by_mood(self):
        """根据当前心情更新表情"""
        try:
            # 选择合适的表情
            new_expression = self._select_expression_by_mood()
            
            if new_expression != self.current_expression:
                self.logger.info(f"表情变化: {self.current_expression} → {new_expression}")
                self.current_expression = new_expression
                
                # 应用新表情
                self._apply_expression(new_expression)
            else:
                self.logger.debug(f"心情更新，但表情保持不变: {new_expression}")
                
        except Exception as e:
            self.logger.error(f"根据心情更新表情时出错: {e}", exc_info=True)
    
    def _select_expression_by_mood(self) -> str:
        """根据情绪值选择合适的表情组合"""
        # 获取最强情绪
        dominant_emotion = max(self.current_mood, key=self.current_mood.get)
        dominant_value = self.current_mood[dominant_emotion]
        
        self.logger.info(f"情绪分析: joy={self.current_mood['joy']}, anger={self.current_mood['anger']}, sorrow={self.current_mood['sorrow']}, fear={self.current_mood['fear']}")
        self.logger.info(f"主导情绪: {dominant_emotion}({dominant_value})")
        
        # 根据情绪强度和类型选择表情
        if dominant_emotion == "joy":
            if self.current_mood["joy"] >= 9:
                return "very_happy"
            elif self.current_mood["joy"] >= 7:
                return "happy"
            else:
                return "neutral"
        elif dominant_emotion == "anger" and self.current_mood["anger"] >= 5:
            return "angry"
        elif dominant_emotion == "sorrow" and self.current_mood["sorrow"] >= 5:
            return "sad"
        else:
            return "neutral"
    
    def _apply_expression(self, expression_name: str):
        """应用指定的表情组合"""
        try:
            if expression_name not in self.expression_combinations:
                self.logger.warning(f"未知的表情: {expression_name}")
                return
            
            expression_config = self.expression_combinations[expression_name]
            
            
            # 应用新表情配置
            for part, action in expression_config.items():
                self.logger.info(f"应用表情 '{expression_name}' 的 {part} 状态: {action}")
                if part == "eye":
                    # 找到对应的眼部状态枚举
                    self.state_manager.eye_state.set_first_layer(action)                    
                elif part == "eyebrow":
                    # 找到对应的眉毛状态枚举
                    self.state_manager.eyebrow_state.set_first_layer(action)
                elif part == "mouth":
                    # 找到对应的嘴巴状态枚举
                    self.state_manager.mouth_state.set_first_layer(action)
            
            
            self.logger.info(f"应用表情 '{expression_name}'")
            
        except Exception as e:
            self.logger.error(f"应用表情 '{expression_name}' 时出错: {e}", exc_info=True)
    