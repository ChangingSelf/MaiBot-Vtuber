from typing import List, Dict, Optional

from src.utils.logger import get_logger
from mineland import Observation, CodeInfo
from ..events.event import MinecraftEvent

logger = get_logger("MinecraftPlugin")


def build_prompt(
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

    status_text = "\n".join(status_prompts)

    # 构建事件历史提示
    logger.info(f"events: {events}")
    logger.info(f"event_history: {event_history}")
    event_prompt = ""

    # 优先使用事件历史记录
    if event_history:
        recent_events = []
        other_player_events = []
        repetition_warning = ""

        # 处理历史事件
        for event_record in event_history[-20:]:  # 取最近20条
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
        if recent_events:
            # 检查最近的聊天消息是否有重复
            chat_messages = [event for event in recent_events if event.startswith("chat:")]
            if len(chat_messages) >= 3:
                # 检查最近3条聊天消息
                recent_chat = chat_messages[-3:]
                # 简单的重复检测：检查是否有相似的内容
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

                if similar_count >= 2:
                    repetition_warning = """
🚨 **重要提醒**：你最近在重复说相似的话！请避免重复，尝试：
1. 换一个话题或活动
2. 问问其他玩家的想法
3. 尝试新的游戏策略
4. 保持沉默一会儿，专注于游戏行动
请不要再重复刚才说过的话！
"""

        # 如果没有历史事件，则使用当前事件
        if not recent_events and events:
            for event in events:
                if hasattr(event, "type") and hasattr(event, "message"):
                    msg = event.message.replace(agent_info.get("name", "Mai"), "你")
                    recent_events.append(f"{event.type}: {msg}")

        # 构建事件提示
        if recent_events or other_player_events:
            event_sections = []

            if other_player_events:
                event_sections.append(
                    "🔥重要：其他玩家的发言（请优先关注并友好回应）:\n- " + "\n- ".join(other_player_events[-5:])
                )  # 最近5条其他玩家发言

            if recent_events:
                recent_events_str = recent_events[-15:]  # 最近15条一般事件
                event_sections.append(
                    "最近的游戏事件（包含你自己的行为和报错信息，请认真阅读并调整行为）:\n- "
                    + "\n- ".join(recent_events_str)
                )

            # 添加重复警告
            if repetition_warning:
                event_sections.insert(0, repetition_warning)

            event_prompt = "\n\n".join(event_sections)

    # 如果没有事件历史，回退到原有逻辑
    elif events:
        recent_events = []
        for event in events:
            if hasattr(event, "type") and hasattr(event, "message"):
                msg = event.message.replace(agent_info.get("name", "Mai"), "你")
                recent_events.append(f"{event.type}: {msg}")

        if recent_events:
            recent_events_str = recent_events[-10:]
            event_prompt = (
                "最近的事件（包含你自己说的报错信息，请认真阅读报错并调整行为，并留意其他玩家的发言，与他们作出友好互动）:\n- "
                + "\n- ".join(recent_events_str)
            )

    # 检查代码执行错误
    error_prompt = ""
    if code_infos:
        for code_info in code_infos:
            if code_info and hasattr(code_info, "code_error") and code_info.code_error:
                # 从 code_info 中提取错误信息
                error_type = code_info.code_error.get("error_type", "未知错误")
                error_message = code_info.code_error.get("error_message", "无详细信息")
                last_code = getattr(code_info, "last_code", "无代码记录")

                # 对代码中的花括号进行转义，避免在字符串格式化时出现问题
                escaped_last_code = last_code.replace("{", "\\{").replace("}", "\\}")

                error_prompt = f"""
重要提醒：上次执行的代码出现了错误，请务必修正！
- 错误类型：{error_type}
- 错误信息：{error_message}
- 出错的代码：{escaped_last_code}

在编写新代码时，请特别注意避免以下问题：
1. 检查是否有语法错误（括号匹配、分号等）
2. 确保所有引用的变量和函数都已定义
3. 验证API调用的参数是否正确
4. 避免访问可能不存在的属性或方法
5. 确保代码逻辑的正确性

请根据错误信息修正问题并重新编写正确的代码。
                """
                break  # 只处理第一个错误

    # 构建目标和计划信息
    goal_prompt = ""
    if goal or current_plan or current_step:
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
            goal_lines.append("✅ 目标已完成！请制定下一个目标并开始新的计划。")
        elif goal and current_plan:
            goal_lines.append("继续按照计划执行当前目标，如遇到问题请调整策略。")

        goal_prompt = "\n".join(goal_lines)

    # 提示词
    chat_target_group1 = "你正在直播Minecraft游戏，以下是游戏的当前状态："
    chat_target_group2 = "正在直播Minecraft游戏"

    # 构建主要的推理提示词，包含目标信息
    personality = "你的网名叫\\{bot_name\\}，有人也叫你\\{bot_other_names\\}，\\{prompt_personality\\}"
    base_prompt = f"""{personality}
你正在直播Minecraft游戏，实现游戏目标的同时不要忘记和观众或其他玩家互动。

## 游戏状态
{status_text}

## 当前目标和计划
{goal_prompt}

{error_prompt}
{event_prompt}

请分析游戏状态并提供一个JSON格式的动作指令。你的回复必须严格遵循JSON格式。不要包含任何markdown标记 (如 ```json ... ```), 也不要包含任何解释性文字、注释或除了纯JSON对象之外的任何内容。

请提供一个JSON对象，包含如下字段：
- `goal`: 当前目标，例如："制作1个铁镐"、"建造1个房子"等。目标必须有可执行的步骤，具体的完成数值，不能模糊。如果上一个目标已完成，请设定新目标
- `plan`: 实现当前目标的详细计划，分解为多个步骤，使用字符串数组，例如：["1.收集原木","2.合成木板","3.制作工作台","4.制作木镐"]
- `step`: 当前正在执行的步骤，例如："3.制作工作台"
- `targetValue`: 当前目标的数值（如果适用），例如目标是收集10个石头，则为10
- `currentValue`: 当前目标的完成度（如果适用），例如已收集5个石头，则为5
- `actions`: Mineflayer JavaScript代码字符串，用于执行当前步骤

以下是一些有用的Mineflayer API和函数:
- `bot.chat(message)`: 发送聊天消息，聊天消息请使用中文
- `mineBlock(bot, name, count)`: 收集指定方块，例如`mineBlock(bot,'oak_log',5)`。无法挖掘非方块，例如想要挖掘铁矿石需要`iron_ore`而不是`raw_iron`
- `craftItem(bot, name, count)`: 合成物品，合成之前请先制作并放置工作台，否则无法合成
- `placeItem(bot, name, position)`: 放置方块
- `smeltItem(bot, name, count)`: 冶炼物品
- `killMob(bot, name, timeout)`: 击杀生物
- `bot.toss(itemType, metadata, count)`: 丢弃物品，丢弃时记得离开原地，否则物品会被吸收回来

编写代码时的注意事项:
- 代码需要符合JavaScript语法，使用bot相关异步函数时记得在async函数内await，但是mineBlock之类的高级函数不需要await
- 检查机器人库存再使用物品
- 每次不要收集太多物品，够用即可
- 只编写能够在10秒内完成的代码
- 请保持角色移动，不要一直站在原地
- 一次不要写太多代码，否则容易出现错误。不要写复杂判断，一次只写几句代码
- 如果状态一直没有变化，请检查代码是否正确（例如方块或物品名称是否正确）并使用新的代码，而不是重复执行同样的代码
- 如果目标一直无法完成，请切换目标
- **重要：避免重复说话！** 在使用`bot.chat()`时，请检查你最近是否说过类似的话。如果已经说过，就不要再重复了，或者换一个完全不同的表达方式
- 如果你发现自己在重复相同的行为或话语，立即改变策略：尝试新的活动、换个话题、或者保持沉默专注于游戏
- 不要使用`bot.on`或`bot.once`注册事件监听器
- 尽可能使用mineBlock、craftItem、placeItem、smeltItem、killMob等高级函数，如果没有，才使用Mineflayer API
- 如果你看到有玩家和你聊天，请友好回应，不要不理他们，但也不要反复说同样的话
    """

    reasoning_prompt_main = base_prompt.strip()

    return {
        "chat_target_group1": chat_target_group1,
        "chat_target_group2": chat_target_group2,
        "reasoning_prompt_main": reasoning_prompt_main,
    }
