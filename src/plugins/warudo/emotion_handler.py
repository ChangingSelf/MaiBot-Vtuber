import json
import logging
from typing import Any, Dict, Optional
import websockets


class EmotionHandler:
    """处理表情数据的解析和WebSocket发送"""
    
    def __init__(self, logger: logging.Logger):
        self.logger = logger
        self.is_speaking = False
        self.pending_mouth_actions = []  # 延迟发送的嘴部动作
        self.pre_speaking_mouth_state = {}  # 说话前的嘴部状态
        
        # 常见的嘴部动作列表，用于在说话前置0
        self.mouth_actions = [
            "mouth_default",
            "mouth_happy_weak",
            "mouth_happy_strong", 
            "mouth_sad_weak",
            "mouth_sad_strong",
            "mouth_angry_weak",
            "mouth_angry_strong",
            "mouth_surprised_weak",
            "mouth_surprised_strong",
            "mouth_disgusted_weak",
            "mouth_disgusted_strong"
        ]
    
    def parse_emotion_data(self, emotion_data: Any) -> Optional[Dict[str, Any]]:
        """
        解析表情数据，支持字典和JSON字符串格式
        
        Args:
            emotion_data: 原始表情数据
            
        Returns:
            解析后的字典数据，解析失败返回None
        """
        try:
            # 处理数据格式：可能是字典或JSON字符串
            if isinstance(emotion_data, dict):
                return emotion_data
            elif isinstance(emotion_data, str):
                return json.loads(emotion_data)
            else:
                self.logger.warning(f"face_emotion数据类型不支持: {type(emotion_data)}")
                return None
        except json.JSONDecodeError:
            self.logger.error(f"face_emotion消息不是有效的JSON格式: {emotion_data}")
            return None
    
    def extract_actions(self, payload_data: Dict[str, Any]) -> list:
        """
        从表情数据中提取所有动作
        
        Args:
            payload_data: 解析后的表情数据
            
        Returns:
            动作列表，每个元素包含action和data字段
        """
        actions = []
        
        # 检查是否包含表情动作数据
        if "actions" not in payload_data:
            self.logger.warning(f"face_emotion数据格式不正确，缺少'actions'字段: {payload_data}")
            return actions
        
        expression_name = payload_data.get("expression_name", "unknown")
        action_dict = payload_data.get("actions", {})
        
        # 计算总动作数量
        total_actions = sum(len(part_data) for part_data in action_dict.values() if isinstance(part_data, dict))
        self.logger.info(f"处理表情 '{expression_name}'，包含 {total_actions} 个动作")
        
        # 解析每个部位的动作
        for part_name, part_data in action_dict.items():
            if not isinstance(part_data, dict):
                self.logger.warning(f"跳过无效的部位数据 {part_name}: {part_data}")
                continue
                
            # 解析部位下的所有动作
            for action_name, action_data in part_data.items():
                if isinstance(action_data, dict) and "action" in action_data and "data" in action_data:
                    actions.append({
                        "action": action_data["action"],
                        "data": action_data["data"],
                        "part_name": part_name,
                        "action_name": action_name
                    })
                else:
                    self.logger.warning(f"跳过无效的动作数据 {part_name}.{action_name}: {action_data}")
            
        return actions
    
    async def send_actions_to_websocket(self, actions: list, websocket: websockets.WebSocketClientProtocol):
        """
        将动作列表发送到WebSocket
        
        Args:
            actions: 动作列表
            websocket: WebSocket连接对象
        """
        for action_item in actions:
            part_name = action_item.get("part_name", "unknown")
            
            # 如果是嘴部动作，检查说话状态
            if part_name == "mouth":
                if self.is_speaking:
                    # 正在说话，延迟发送
                    self.pending_mouth_actions.append(action_item)
                    action_name = action_item.get("action_name", "unknown")
                    self.logger.info(f"延迟发送嘴部动作 {part_name}.{action_name}（正在说话中）")
                    continue
                else:
                    # 不在说话，直接发送并记录状态
                    action_name = action_item.get("action", "unknown")
                    data_value = action_item.get("data", 0.0)
                    self.pre_speaking_mouth_state[action_name] = data_value
                    self.logger.info(f"记录嘴部状态 {action_name}: {data_value}")
            
            # 立即发送非嘴部动作或不在说话时的嘴部动作
            await self._send_single_action(action_item, websocket)
    
    async def _send_single_action(self, action_item: dict, websocket: websockets.WebSocketClientProtocol):
        """
        发送单个动作到WebSocket
        
        Args:
            action_item: 动作数据
            websocket: WebSocket连接对象
        """
        try:
            # 创建WebSocket消息（不包含part_name）
            message_data = {
                "action": action_item["action"],
                "data": action_item["data"]
            }
            json_message = json.dumps(message_data)
            await websocket.send(json_message)
            
            part_name = action_item.get("part_name", "unknown")
            action_name = action_item.get("action_name", "unknown")
            
            # 显示部位和具体动作名称
            self.logger.info(f"已发送 {part_name}.{action_name} 动作: {json_message}")
                
        except websockets.exceptions.ConnectionClosed:
            self.logger.warning("WebSocket连接已关闭，无法发送面部表情。")
            raise  # 重新抛出异常，让调用者处理
        except Exception as e:
            action_name = action_item.get("action", "unknown")
            self.logger.error(f"发送动作 '{action_name}' 时发生错误: {e}", exc_info=True)
    
    async def process_emotion_message(self, emotion_data: Any, websocket: Optional[websockets.WebSocketClientProtocol]):
        """
        完整处理表情消息的主要方法
        
        Args:
            emotion_data: 原始表情数据
            websocket: WebSocket连接对象
        """
        if websocket is None:
            self.logger.warning("WebSocket未连接，无法发送面部表情。")
            return
        
        # 解析数据
        payload_data = self.parse_emotion_data(emotion_data)
        if payload_data is None:
            return
        
        # 提取动作
        actions = self.extract_actions(payload_data)
        if not actions:
            return
        
        # 发送动作
        await self.send_actions_to_websocket(actions, websocket)
    
    def set_speaking_state(self, is_speaking: bool):
        """
        设置说话状态
        
        Args:
            is_speaking: 是否正在说话
        """
        self.is_speaking = is_speaking
        if is_speaking:
            self.logger.info("开始说话，嘴部动作将被延迟")
        else:
            self.logger.info("结束说话，将发送延迟的嘴部动作并恢复之前状态")
    
    async def record_current_mouth_state(self, websocket: Optional[websockets.WebSocketClientProtocol]):
        """
        记录当前嘴部状态（说话前调用）
        
        Args:
            websocket: WebSocket连接对象
        """
        if websocket is None:
            return
        
        # 如果没有记录任何嘴部状态，则假设所有嘴部动作都是0
        if not self.pre_speaking_mouth_state:
            for mouth_action in self.mouth_actions:
                self.pre_speaking_mouth_state[mouth_action] = 0.0
            self.logger.info(f"初始化嘴部状态记录，默认设置 {len(self.mouth_actions)} 个动作为0")
        else:
            self.logger.info(f"已有嘴部状态记录，包含 {len(self.pre_speaking_mouth_state)} 个动作")
    
    async def send_pending_mouth_actions(self, websocket: Optional[websockets.WebSocketClientProtocol]):
        """
        发送所有延迟的嘴部动作
        
        Args:
            websocket: WebSocket连接对象
        """
        if not self.pending_mouth_actions:
            self.logger.info("没有延迟的嘴部动作需要发送")
            return
        
        if websocket is None:
            self.logger.warning("WebSocket未连接，无法发送延迟的嘴部动作")
            self.pending_mouth_actions.clear()
            return
        
        self.logger.info(f"发送 {len(self.pending_mouth_actions)} 个延迟的嘴部动作")
        
        for action_item in self.pending_mouth_actions:
            try:
                await self._send_single_action(action_item, websocket)
                # 更新记录的状态
                action_name = action_item.get("action", "unknown")
                data_value = action_item.get("data", 0.0)
                self.pre_speaking_mouth_state[action_name] = data_value
            except websockets.exceptions.ConnectionClosed:
                self.logger.warning("WebSocket连接已关闭，停止发送延迟的嘴部动作")
                break
            except Exception as e:
                self.logger.error(f"发送延迟嘴部动作时发生错误: {e}", exc_info=True)
        
        # 清空延迟的动作列表
        self.pending_mouth_actions.clear()
    
    async def restore_pre_speaking_mouth_state(self, websocket: Optional[websockets.WebSocketClientProtocol]):
        """
        恢复说话前的嘴部状态
        
        Args:
            websocket: WebSocket连接对象
        """
        if websocket is None:
            self.logger.warning("WebSocket未连接，无法恢复嘴部状态")
            return
        
        if not self.pre_speaking_mouth_state:
            self.logger.info("没有记录的嘴部状态需要恢复")
            return
        
        self.logger.info(f"恢复 {len(self.pre_speaking_mouth_state)} 个嘴部动作到说话前状态")
        
        for action_name, data_value in self.pre_speaking_mouth_state.items():
            try:
                # 创建恢复动作
                restore_action = {
                    "action": action_name,
                    "data": data_value,
                    "part_name": "mouth",
                    "action_name": action_name
                }
                await self._send_single_action(restore_action, websocket)
                
            except websockets.exceptions.ConnectionClosed:
                self.logger.warning("WebSocket连接已关闭，停止恢复嘴部状态")
                break
            except Exception as e:
                self.logger.error(f"恢复嘴部动作 '{action_name}' 时发生错误: {e}", exc_info=True)
    
    async def reset_mouth_actions(self, websocket: Optional[websockets.WebSocketClientProtocol]):
        """
        将所有嘴部动作置0，清空嘴部状态
        
        Args:
            websocket: WebSocket连接对象
        """
        if websocket is None:
            self.logger.warning("WebSocket未连接，无法重置嘴部动作")
            return
        
        self.logger.info(f"重置 {len(self.mouth_actions)} 个嘴部动作为0")
        
        for mouth_action in self.mouth_actions:
            try:
                # 创建置0的嘴部动作
                reset_action = {
                    "action": mouth_action,
                    "data": 0.0
                }
                json_message = json.dumps(reset_action)
                await websocket.send(json_message)
                self.logger.info(f"已重置嘴部动作: {json_message}")
                
            except websockets.exceptions.ConnectionClosed:
                self.logger.warning("WebSocket连接已关闭，停止重置嘴部动作")
                break
            except Exception as e:
                self.logger.error(f"重置嘴部动作 '{mouth_action}' 时发生错误: {e}", exc_info=True) 