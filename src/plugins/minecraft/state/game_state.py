import contextlib
from typing import Any, Dict, Optional, List
import time
from mineland import Observation, CodeInfo, Event
from ..events.event import MinecraftEvent


class MinecraftGameState:
    """Minecraft游戏状态管理器"""

    def __init__(self):
        # MineLand 状态变量（单智能体）
        self.current_obs: Optional[Observation] = None
        self.current_code_info: Optional[CodeInfo] = None
        self.current_event: Optional[List[MinecraftEvent]] = None
        self.current_done: bool = False
        self.current_task_info: Optional[Dict[str, Any]] = None
        self.current_step_num: int = 0

        # 目标相关
        self.goal: str = "挖到铁矿"
        self.goal_history: List[Dict[str, Any]] = []

        # 计划和进度相关
        self.current_plan: List[str] = []
        self.current_step: str = "暂无步骤"
        self.target_value: int = 0
        self.current_value: int = 0

    def reset_state(self, initial_obs: List[Observation]):
        """重置游戏状态"""
        self.current_obs = initial_obs[0] if initial_obs and len(initial_obs) > 0 else None

        self.current_code_info = None
        self.current_event = []
        self.current_done = False
        self.current_task_info = {}
        self.current_step_num = 0

    def update_state(
        self,
        obs: List[Observation],
        code_info: List[CodeInfo],
        event: List[List[Event]],  # MineLand返回Event列表
        done,
        task_info: Dict[str, Any],
    ):
        """更新游戏状态"""
        self.current_obs = obs[0] if obs else None
        self.current_code_info = code_info[0] if code_info else None

        # 处理事件数据：将mineland.Event转换为MinecraftEvent
        if event and len(event) > 0:
            raw_events = event[0]
            self.current_event = []
            for raw_event in raw_events:
                if isinstance(raw_event, Event):
                    # 将mineland.Event转换为MinecraftEvent（保持兼容性）
                    minecraft_event = MinecraftEvent.from_mineland_event(raw_event)
                    self.current_event.append(minecraft_event)
                elif isinstance(raw_event, dict):
                    # 处理字典格式（向后兼容）
                    minecraft_event = MinecraftEvent.from_dict(raw_event)
                    self.current_event.append(minecraft_event)
                else:
                    # 如果已经是MinecraftEvent，直接添加
                    self.current_event.append(raw_event)
        else:
            self.current_event = []

        self.current_done = done
        self.current_task_info = task_info
        self.current_step_num += 1

    def is_ready_for_next_action(self) -> bool:
        """检查是否准备好执行下一个动作"""
        if not self.current_code_info:
            return True

        return self.current_code_info.is_ready

    def update_goal(self, new_goal: str):
        """更新目标并记录历史"""
        if new_goal != self.goal:
            goal_record = {
                "goal": self.goal,
                "timestamp": time.time(),
                "step_num": self.current_step_num,
                "completed_time": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
            }
            self.goal_history.append(goal_record)

            # 保持历史记录在合理范围内
            if len(self.goal_history) > 50:
                self.goal_history.pop(0)

            self.goal = new_goal

    def get_goal_history_text(self, max_count: int = 10) -> str:
        """获取目标历史的文本描述"""
        if not self.goal_history:
            return "暂无目标历史记录"

        recent_history = self.goal_history[-max_count:]
        history_lines = []
        for i, record in enumerate(recent_history, 1):
            history_lines.append(
                f"{i}. 目标: {record['goal']} (完成于步骤 {record['step_num']}, 时间: {record['completed_time']})"
            )

        return "\n".join(history_lines)

    def update_action_data(self, action_data: Dict[str, Any]):
        """更新从AI响应中解析出的动作数据"""
        if not action_data:
            return

        if "plan" in action_data:
            self.current_plan = action_data["plan"]

        if "step" in action_data:
            self.current_step = action_data["step"]

        if "targetValue" in action_data:
            with contextlib.suppress(ValueError, TypeError):
                self.target_value = int(action_data["targetValue"])

        if "currentValue" in action_data:
            with contextlib.suppress(ValueError, TypeError):
                self.current_value = int(action_data["currentValue"])

    def get_effective_done(self) -> bool:
        """获取有效的完成状态"""
        return self.current_done

    def add_initial_goal_record(self):
        """添加初始目标记录"""
        initial_goal_record = {
            "goal": "初始化",
            "timestamp": time.time(),
            "step_num": 0,
            "completed_time": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
        }
        self.goal_history.append(initial_goal_record)
