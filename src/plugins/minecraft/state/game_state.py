import contextlib
import json
from typing import Any, Dict, Optional, List
import time
from mineland import Observation, CodeInfo, Event
from ..events.event import MinecraftEvent
from .analyzers import StateAnalyzer

from src.utils.logger import get_logger

logger = get_logger("MinecraftPlugin")


class MinecraftGameState:
    """Minecraft游戏状态管理器"""

    def __init__(self, config: Dict[str, Any] = None):
        self.logger = logger
        # 配置参数
        self.config = config or {}

        # MineLand 状态变量（单智能体）
        self.current_obs: Optional[Observation] = None
        self.current_code_info: Optional[CodeInfo] = None
        self.current_event: Optional[List[MinecraftEvent]] = None
        self.current_done: bool = False
        self.current_task_info: Optional[Dict[str, Any]] = None
        self.current_step_num: int = 0

        # 目标相关 - 使用配置中的默认目标
        self.goal: str = self.config.get("default_initial_goal", "挖到铁矿")
        self.goal_history: List[Dict[str, Any]] = []
        self.goal_history_max_count: int = self.config.get("goal_history_max_count", 50)

        # 计划和进度相关
        self.current_plan: List[str] = []
        self.current_step: str = "暂无步骤"
        self.target_value: int = 0
        self.current_value: int = 0

        # 状态分析器
        self._state_analyzer: Optional[StateAnalyzer] = None
        self._last_analyzed_obs_id: Optional[int] = None  # 用于缓存判断
        self._cached_status_prompts: List[str] = []
        self._cache_enabled: bool = self.config.get("state_analysis_cache_enabled", True)

    def reset_state(self, initial_obs: List[Observation]):
        """重置游戏状态"""
        self.current_obs: Optional[Observation] = initial_obs[0] if initial_obs and initial_obs else None

        self.current_code_info = None
        self.current_event = []
        self.current_done = False
        self.current_task_info = {}
        self.current_step_num = 0

        # 重置状态分析器和缓存
        self._state_analyzer = None
        self._last_analyzed_obs_id = None
        self._cached_status_prompts = []

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

        self.logger.info(f"观察信息: {json.dumps(str(self.current_obs.target_entities), indent=4)}")

        self.current_event = []
        # 处理事件数据：将mineland.Event转换为MinecraftEvent
        if event:
            raw_events = event[0]
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
        self.current_done = done
        self.current_task_info = task_info
        self.current_step_num += 1

        # 清除缓存，因为状态已更新
        self._last_analyzed_obs_id = None
        self._cached_status_prompts = []

    def get_status_analysis(self) -> List[str]:
        """
        获取当前游戏状态分析

        实现缓存机制，避免重复分析相同的状态

        Returns:
            List[str]: 状态分析提示列表
        """
        if not self.current_obs:
            return ["当前没有可用的游戏状态数据"]

        # 使用观察对象的id作为缓存键
        current_obs_id = id(self.current_obs)

        # 如果启用缓存且是相同的观察数据且已有缓存，直接返回缓存结果
        if self._cache_enabled and self._last_analyzed_obs_id == current_obs_id and self._cached_status_prompts:
            return self._cached_status_prompts.copy()

        # 创建或更新状态分析器
        if not self._state_analyzer or self._state_analyzer.obs != self.current_obs:
            self._state_analyzer = StateAnalyzer(self.current_obs, self.config)

        # 执行状态分析
        self._cached_status_prompts = self._state_analyzer.analyze_all()
        if self._cache_enabled:
            self._last_analyzed_obs_id = current_obs_id

        return self._cached_status_prompts.copy()

    def get_detailed_status_analysis(self) -> Dict[str, List[str]]:
        """
        获取详细的分类状态分析

        Returns:
            Dict[str, List[str]]: 按类别分组的状态分析
        """
        if not self.current_obs:
            return {"error": ["当前没有可用的游戏状态数据"]}

        if not self._state_analyzer or self._state_analyzer.obs != self.current_obs:
            self._state_analyzer = StateAnalyzer(self.current_obs, self.config)

        return {
            "life_stats": self._state_analyzer.life_stats_analyzer.analyze(),
            "position": self._state_analyzer.motion_analyzer.analyze_position(),
            "direction": self._state_analyzer.motion_analyzer.analyze_direction(),
            "velocity": self._state_analyzer.motion_analyzer.analyze_velocity(),
            "equipment": self._state_analyzer.equipment_analyzer.analyze(),
            "inventory": self._state_analyzer.inventory_analyzer.analyze(),
            "environment": self._state_analyzer.analyze_environment(),
            "collision": self._state_analyzer.collision_analyzer.analyze(),
            "time": self._state_analyzer.environment_analyzer.analyze_time(),
            "weather": self._state_analyzer.environment_analyzer.analyze_weather(),
            "game_info": self._state_analyzer.environment_analyzer.analyze_game_info(),
        }

    def is_ready_for_next_action(self) -> bool:
        """检查是否准备好执行下一个动作"""
        return self.current_code_info.is_ready if self.current_code_info else True

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
            if len(self.goal_history) > self.goal_history_max_count:
                self.goal_history.pop(0)

            self.goal = new_goal

    def get_goal_history_text(self, max_count: int = 10) -> str:
        """获取目标历史的文本描述"""
        if not self.goal_history:
            return "暂无目标历史记录"

        recent_history = self.goal_history[-max_count:]
        history_lines = []
        history_lines.extend(
            f"{i}. 目标: {record['goal']} (完成于步骤 {record['step_num']}, 时间: {record['completed_time']})"
            for i, record in enumerate(recent_history, 1)
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
