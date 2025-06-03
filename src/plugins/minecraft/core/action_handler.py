import json
import re
from typing import List, Any, Optional, Tuple, Dict, Union

import mineland
from mineland import Action, Observation, CodeInfo, Event, TaskInfo
from src.utils.logger import get_logger

logger = get_logger("MinecraftAction")


def _strip_markdown_codeblock(text: str) -> str:
    """
    去除markdown代码块包装

    Args:
        text: 可能包含markdown代码块的文本

    Returns:
        str: 去除代码块包装后的内容
    """
    text = text.strip()

    # 匹配 ```json ... ``` 或 ``` ... ``` 格式
    # 使用 re.DOTALL 让 . 匹配换行符
    pattern = r"^```(?:json)?\s*\n?(.*?)\n?```$"
    match = re.match(pattern, text, re.DOTALL)

    if match:
        # 如果匹配到代码块格式，返回内部内容
        return match.group(1).strip()

    # 如果不是代码块格式，返回原文本
    return text


def parse_message_json(message_json_str: str, agents_count: int, current_step_num: int) -> Tuple[List[Action], str]:
    """
    解析从MaiCore收到的动作JSON字符串，并返回MineLand格式的动作

    Args:
        message_json_str: JSON格式的动作字符串（可能包含markdown代码块包装）
        agents_count: 智能体数量
        current_step_num: 当前步数

    Returns:
        Tuple[List[Action], str]: MineLand格式的动作列表和目标
    """
    # 预处理：去除可能的markdown代码块包装
    cleaned_json_str = _strip_markdown_codeblock(message_json_str)

    try:
        action_data = json.loads(cleaned_json_str)
    except json.JSONDecodeError as e:
        logger.exception(f"解析来自 MaiCore 的动作 JSON 失败: {e}. 原始数据: {message_json_str}")
        return mineland.Action.no_op(agents_count)

    # --- 解析动作并准备 current_actions ---
    # 目前仅支持单智能体 (agents_count=1)
    current_actions = []

    if agents_count == 1:
        # 获取 actions 字段并根据类型判断是高级还是低级动作
        actions = action_data.get("actions")

        if actions is None:
            # 无 actions 字段，执行无操作
            logger.info(f"步骤 {current_step_num}: 未提供 actions 字段，将执行无操作。")
            current_actions = mineland.Action.no_op(agents_count)
        elif isinstance(actions, str) and actions.strip():
            # actions 是字符串，执行高级动作
            parsed_agent_action_obj = mineland.Action(type=mineland.Action.NEW, code=actions)
            current_actions = [parsed_agent_action_obj]
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
        else:
            # actions 格式不正确，执行无操作
            logger.warning(f"步骤 {current_step_num}: actions 字段格式不正确 (应为字符串或8元素数组)，将执行无操作。")
            current_actions = mineland.Action.no_op(agents_count)
    else:  # 多智能体 (agents_count > 1)
        logger.warning(f"步骤 {current_step_num}: 多智能体 (AGENTS_COUNT > 1) 暂不支持，将执行无操作。")
        current_actions = mineland.Action.no_op(agents_count)

    return current_actions, action_data.get("goal", "")


def execute_mineland_action(
    mland: mineland.MineLand, current_actions: List[Any]
) -> Tuple[List[Observation], List[CodeInfo], List[List[Event]], bool, TaskInfo]:
    """
    在MineLand环境中执行动作并返回结果

    Args:
        mland: MineLand环境实例
        current_actions: 要执行的动作列表

    Returns:
        Tuple: (next_obs, next_code_info, next_event, next_done, next_task_info)
    """
    return mland.step(action=current_actions)
