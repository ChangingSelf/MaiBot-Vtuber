import time
from typing import Dict, List

from maim_message import MessageBase, TemplateInfo, UserInfo, GroupInfo, FormatInfo, BaseMessageInfo, Seg
from .prompt_builder import build_prompt
from ..state.game_state import MinecraftGameState
from ..events.event_manager import MinecraftEventManager


class MinecraftMessageBuilder:
    """Minecraft消息构建器"""

    def __init__(self, platform: str, user_id: str, nickname: str, group_id: str = None):
        self.platform = platform
        self.user_id = user_id
        self.nickname = nickname
        self.group_id = group_id

    def build_state_message(
        self, game_state: MinecraftGameState, event_manager: MinecraftEventManager, agents_config: List[Dict[str, str]]
    ) -> MessageBase:
        """构建游戏状态消息"""
        # 确保有观察数据
        if not game_state.current_obs:
            raise ValueError("当前没有可用的观察数据，无法构建状态")

        # 使用GameState的状态分析方法
        agent_info = agents_config[0]
        status_prompts = game_state.get_status_analysis()

        # 构建消息基础信息
        message_info = self._build_message_info(game_state, event_manager, agent_info, status_prompts)

        # 构建消息文本
        message_text = self._build_message_text(event_manager, game_state.current_event, agent_info["name"])

        message_segment = Seg(type="text", data=message_text)

        return MessageBase(message_info=message_info, message_segment=message_segment, raw_message=message_text)

    def _build_message_info(
        self,
        game_state: MinecraftGameState,
        event_manager: MinecraftEventManager,
        agent_info: Dict[str, str],
        status_prompts: List[str],
    ) -> BaseMessageInfo:
        """构建消息信息"""
        current_time = int(time.time())
        message_id = int(time.time())

        user_info = UserInfo(platform=self.platform, user_id=str(self.user_id), user_nickname=self.nickname)

        group_info = None
        if self.group_id:
            group_info = GroupInfo(
                platform=self.platform,
                group_id=self.group_id,
            )

        format_info = FormatInfo(content_format="text", accept_format="text")

        # 构建模板信息
        template_items = build_prompt(
            agent_info=agent_info,
            status_prompts=status_prompts,
            obs=game_state.current_obs,
            events=game_state.current_event,
            code_infos=[game_state.current_code_info] if game_state.current_code_info else [],
            event_history=event_manager.event_history,
            goal=game_state.goal,
            current_plan=game_state.current_plan,
            current_step=game_state.current_step,
            target_value=game_state.target_value,
            current_value=game_state.current_value,
        )

        template_info = TemplateInfo(
            template_items=template_items,
            template_name="Minecraft",
            template_default=False,
        )

        return BaseMessageInfo(
            platform=self.platform,
            message_id=message_id,
            time=current_time,
            user_info=user_info,
            group_info=group_info,
            format_info=format_info,
            additional_config={
                "maimcore_reply_probability_gain": 1,  # 确保必然回复
            },
            template_info=template_info,
        )

    def _build_message_text(self, event_manager: MinecraftEventManager, current_events, agent_name: str) -> str:
        """构建消息文本"""
        # 获取当前事件信息，如果当前事件为空，则使用事件历史的最新几条
        event_messages = event_manager.get_current_events_text(
            current_events, agent_name
        ) or event_manager.get_recent_events_text(agent_name, max_count=10)

        # 构建消息文本
        if event_messages:
            return "最新游戏事件：\n" + "\n".join(event_messages)
        else:
            return "当前没有新的游戏事件"
