"""
Minecraft插件提示词管理器
重构后的提示词构建逻辑，将不同功能分离到不同的方法中
"""

from typing import List, Dict, Optional, Any

from src.utils.logger import get_logger
from mineland import Observation, CodeInfo
from ..events.event import MinecraftEvent
from .prompt_templates import MinecraftPromptTemplates

logger = get_logger("MinecraftPlugin")


class MinecraftPromptManager:
    """Minecraft提示词管理器"""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        初始化提示词管理器

        Args:
            config: 提示词相关配置字典
        """
        self.templates = MinecraftPromptTemplates()
        self.config = config or {}

    def build_prompt(
        self,
        agent_info: Dict[str, str],
        status_prompts: List[str],
        obs: Observation,
        events: List[MinecraftEvent],
        code_infos: Optional[List[CodeInfo]] = None,
        event_history: Optional[List[MinecraftEvent]] = None,
        goal: str = "",
        current_plan: List[str] = None,
        current_step: str = "",
        target_value: int = 0,
        current_value: int = 0,
    ) -> Dict[str, str]:
        """
        构建发送给AI的提示词

        Args:
            agent_info: 智能体信息
            status_prompts: 状态提示列表
            obs: Mineland观察对象
            events: 当前事件列表
            code_infos: 代码信息列表，用于检测代码执行错误
            event_history: 事件历史记录
            goal: 当前目标
            current_plan: 当前计划列表
            current_step: 当前执行步骤
            target_value: 目标值
            current_value: 当前完成度

        Returns:
            Dict[str, str]: 包含提示词的模板项字典
        """
        logger.info(f"事件历史: {event_history}")

        # 构建各个部分的提示词
        status_text = self._build_status_text(status_prompts, obs)
        event_prompt = self._build_event_prompt(agent_info, events, event_history)
        error_prompt = self._build_error_prompt(code_infos)
        goal_prompt = self._build_goal_prompt(goal, current_plan, current_step, target_value, current_value)

        # 构建主要的推理提示词
        # 首先获取模板
        template = self.templates.get_main_prompt_template()

        # 格式化模板中的占位符
        reasoning_prompt_main = template.format(
            status_text=status_text,
            goal_prompt=goal_prompt,
            error_prompt=error_prompt,
            event_prompt=event_prompt,
            # 保留bot相关占位符为字面量，供后续模板系统处理
            bot_name="{bot_name}",
            bot_other_names="{bot_other_names}",
            prompt_personality="{prompt_personality}",
        ).strip()

        return {
            "chat_target_group1": self.templates.CHAT_TARGET_GROUP1,
            "chat_target_group2": self.templates.CHAT_TARGET_GROUP2,
            "reasoning_prompt_main": reasoning_prompt_main,
        }

    def _build_status_text(self, status_prompts: List[str], obs: Observation) -> str:
        """构建状态文本"""
        status_lines = []

        # 添加状态提示
        if status_prompts:
            status_lines.extend(status_prompts)

        # 添加观察信息
        if obs and hasattr(obs, "to_prompt_string"):
            obs_text = obs.to_prompt_string()
            if obs_text:
                status_lines.append(f"当前观察：{obs_text}")

        return "\n".join(status_lines)

    def _build_event_prompt(
        self,
        agent_info: Dict[str, str],
        events: List[MinecraftEvent],
        event_history: Optional[List[MinecraftEvent]] = None,
    ) -> str:
        """构建事件提示词"""
        if event_history:
            return self._build_event_history_prompt(agent_info, event_history)
        elif events:
            return self._build_current_events_prompt(agent_info, events)
        return ""

    def _build_event_history_prompt(self, agent_info: Dict[str, str], event_history: List[MinecraftEvent]) -> str:
        """基于事件历史构建提示词"""
        recent_events = []
        other_player_events = []
        repetition_warning = ""

        # 处理历史事件
        event_limit = self.config.get("event_history_limit", 20)
        for event_record in event_history[-event_limit:]:  # 取最近N条
            event_type = event_record.type
            event_message = event_record.message

            if not event_message:
                continue

            # 替换自己的名字为"你"
            msg = event_message.replace(agent_info.get("name", "Mai"), "你")

            # 检查是否是其他玩家的发言
            is_other_player = (
                event_type == "chat" and agent_info.get("name", "Mai") not in event_message and "你" not in msg
            )

            if is_other_player:
                other_player_events.append(f"**{event_type}**: {msg}")
            else:
                recent_events.append(f"{event_type}: {msg}")

        # 检测重复行为模式
        repetition_warning = self._detect_repetition_pattern(recent_events)

        # 构建事件提示
        return self._format_event_sections(recent_events, other_player_events, repetition_warning)

    def _build_current_events_prompt(self, agent_info: Dict[str, str], events: List[MinecraftEvent]) -> str:
        """基于当前事件构建提示词"""
        recent_events = []
        for event in events:
            if hasattr(event, "type") and hasattr(event, "message"):
                msg = event.message.replace(agent_info.get("name", "Mai"), "你")
                recent_events.append(f"{event.type}: {msg}")

        if recent_events:
            fallback_limit = self.config.get("fallback_events_limit", 10)
            recent_events_str = recent_events[-fallback_limit:]
            return self.templates.FALLBACK_EVENTS_PROMPT.format(events="\n- ".join(recent_events_str))
        return ""

    def _detect_repetition_pattern(self, recent_events: List[str]) -> str:
        """检测重复行为模式"""
        # 检查是否启用重复检测
        if not self.config.get("repetition_detection_enabled", True):
            return ""

        if not recent_events:
            return ""

        # 检查最近的聊天消息是否有重复
        chat_messages = [event for event in recent_events if event.startswith("chat:")]
        chat_limit = self.config.get("chat_message_history_limit", 3)
        if len(chat_messages) < chat_limit:
            return ""

        # 检查最近N条聊天消息
        recent_chat = chat_messages[-chat_limit:]
        similar_count = 0
        last_msg = recent_chat[-1] if recent_chat else ""

        for msg in recent_chat:
            # 提取实际的聊天内容（去掉"chat: <你>"前缀）
            if "<你>" in msg:
                content = msg.split("<你>")[-1].strip()
                last_content = last_msg.split("<你>")[-1].strip() if "<你>" in last_msg else ""

                # 检查内容相似性（简单的包含检查）
                if (
                    content
                    and last_content
                    and len(content) > 10
                    and (content in last_content or last_content in content)
                ):
                    similar_count += 1

        threshold = self.config.get("repetition_threshold", 2)
        return self.templates.REPETITION_WARNING if similar_count >= threshold else ""

    def _format_event_sections(
        self, recent_events: List[str], other_player_events: List[str], repetition_warning: str
    ) -> str:
        """格式化事件部分"""
        if not recent_events and not other_player_events:
            return ""

        event_sections = []

        if other_player_events:
            other_player_limit = self.config.get("other_player_events_limit", 5)
            events_text = "\n- ".join(other_player_events[-other_player_limit:])  # 最近N条其他玩家发言
            event_sections.append(self.templates.OTHER_PLAYERS_PROMPT.format(events=events_text))

        if recent_events:
            recent_limit = self.config.get("recent_events_limit", 15)
            recent_events_str = recent_events[-recent_limit:]  # 最近N条一般事件
            events_text = "\n- ".join(recent_events_str)
            event_sections.append(self.templates.RECENT_EVENTS_PROMPT.format(events=events_text))

        # 添加重复警告
        if repetition_warning:
            event_sections.insert(0, repetition_warning)

        return "\n\n".join(event_sections)

    def _build_error_prompt(self, code_infos: Optional[List[CodeInfo]] = None) -> str:
        """构建错误提示词"""
        if not code_infos:
            return ""

        for code_info in code_infos:
            if code_info and hasattr(code_info, "code_error") and code_info.code_error:
                # 从 code_info 中提取错误信息
                error_type = code_info.code_error.get("error_type", "未知错误")
                error_message = code_info.code_error.get("error_message", "无详细信息")
                last_code = getattr(code_info, "last_code", "无代码记录")

                # 对代码中的花括号进行转义，避免在字符串格式化时出现问题
                escaped_last_code = last_code.replace("{", "\\{").replace("}", "\\}")

                return self.templates.ERROR_PROMPT_TEMPLATE.format(
                    error_type=error_type,
                    error_message=error_message,
                    escaped_code=escaped_last_code,
                )
        return ""

    def _build_goal_prompt(
        self,
        goal: str = "",
        current_plan: List[str] = None,
        current_step: str = "",
        target_value: int = 0,
        current_value: int = 0,
    ) -> str:
        """构建目标和计划信息提示词"""
        if not any([goal, current_plan, current_step]):
            return ""

        goal_lines = []

        if goal:
            goal_lines.append(f"当前目标：{goal}")

        if current_plan:
            plan_str = "; ".join(current_plan) if isinstance(current_plan, list) else str(current_plan)
            goal_lines.append(f"执行计划：{plan_str}")

        if current_step:
            goal_lines.append(f"当前步骤：{current_step}")

        if target_value > 0 or current_value > 0:
            goal_lines.append(f"进度：{current_value}/{target_value}")

        # 根据完成进度添加相应的指导提示
        if target_value > 0 and current_value >= target_value:
            goal_lines.append(self.templates.GOAL_COMPLETED_PROMPT)
        elif goal and current_plan:
            goal_lines.append(self.templates.GOAL_CONTINUE_PROMPT)

        return "\n".join(goal_lines)
