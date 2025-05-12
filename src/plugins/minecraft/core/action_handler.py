import json
from typing import List, Any, Optional, Tuple, Dict, Union

import mineland
from src.utils.logger import get_logger

logger = get_logger("MinecraftAction")


def parse_mineland_action(
    action_json_str: str, agents_count: int, current_step_num: int, enable_low_level_action: bool = False
) -> Tuple[List[Any], str]:
    """
    解析从MaiCore收到的动作JSON字符串，并返回MineLand格式的动作

    Args:
        action_json_str: JSON格式的动作字符串
        agents_count: 智能体数量
        current_step_num: 当前步数
        enable_low_level_action: 是否启用低级动作模式

    Returns:
        Tuple[List[Any], str]: (MineLand格式的动作列表, 用于日志的动作描述)
    """
    try:
        action_data = json.loads(action_json_str)
    except json.JSONDecodeError as e:
        logger.exception(f"解析来自 MaiCore 的动作 JSON 失败: {e}. 原始数据: {action_json_str}")
        return mineland.Action.no_op(agents_count), "无操作 (NO_OP - JSON解析失败)"

    # --- 解析动作并准备 current_actions ---
    # 目前仅支持单智能体 (agents_count=1)
    current_actions = []
    parsed_action_for_log = "NO_OP"  # 用于日志记录的已解析动作字符串

    if agents_count == 1:
        # 获取 actions 字段并根据类型判断是高级还是低级动作
        actions = action_data.get("actions")

        if actions is None:
            # 无 actions 字段，执行无操作
            logger.info(f"步骤 {current_step_num}: 未提供 actions 字段，将执行无操作。")
            current_actions = mineland.Action.no_op(agents_count)
            parsed_action_for_log = "无操作 (NO_OP)"
        elif isinstance(actions, str) and actions.strip():
            # actions 是字符串，执行高级动作
            parsed_agent_action_obj = mineland.Action(type=mineland.Action.NEW, code=actions)
            current_actions = [parsed_agent_action_obj]
            parsed_action_for_log = f"高级动作: {actions[:50]}{'...' if len(actions) > 50 else ''}"
        elif isinstance(actions, list) and len(actions) == 8:
            # actions 是数组，执行低级动作
            lla = mineland.LowLevelAction()
            for i in range(len(actions)):
                try:
                    component_value = int(actions[i])
                    lla[i] = component_value
                except (ValueError, AssertionError) as err_lla:
                    logger.warning(
                        f"步骤 {current_step_num}: 低级动作组件 {i} 值 '{actions[i]}' 无效 ({err_lla})。使用默认值 0。"
                    )
                    # lla[i] 将保留默认值 (0)
            current_actions = [lla]
            parsed_action_for_log = f"低级动作: {lla.data}"
        else:
            # actions 格式不正确，执行无操作
            logger.warning(f"步骤 {current_step_num}: actions 字段格式不正确 (应为字符串或8元素数组)，将执行无操作。")
            current_actions = mineland.Action.no_op(agents_count)
            parsed_action_for_log = "无操作 (NO_OP - 格式错误)"
    else:  # 多智能体 (agents_count > 1)
        logger.warning(f"步骤 {current_step_num}: 多智能体 (AGENTS_COUNT > 1) 暂不支持，将执行无操作。")
        current_actions = mineland.Action.no_op(agents_count)
        parsed_action_for_log = "多智能体-无操作"

    action_mode = "低级 (数值数组)" if enable_low_level_action else "高级 (JavaScript)"
    logger.info(f"步骤 {current_step_num}: 动作类型偏好: {action_mode}, 解析结果: {parsed_action_for_log}")

    return current_actions, parsed_action_for_log


def execute_mineland_action(
    mland: mineland.MineLand, current_actions: List[Any]
) -> Tuple[List[Any], List[Any], List[List[Any]], Union[bool, List[bool]], Dict[str, Any]]:
    """
    在MineLand环境中执行动作并返回结果

    Args:
        mland: MineLand环境实例
        current_actions: 要执行的动作列表

    Returns:
        Tuple: (next_obs, next_code_info, next_event, next_done, next_task_info)
    """
    return mland.step(action=current_actions)
