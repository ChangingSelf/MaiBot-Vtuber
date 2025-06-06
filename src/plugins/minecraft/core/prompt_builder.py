import json
from typing import List, Dict, Any, Optional

from src.utils.logger import get_logger
from src.plugins.minecraft.core.state_analyzers import analyze_voxels, analyze_equipment
from mineland import Observation, Event, CodeInfo

logger = get_logger("MinecraftPlugin")


def build_state_analysis(
    agent_info: Dict[str, str], obs: Observation, events: List[Event], code_infos: List[CodeInfo]
) -> List[str]:
    """
    分析游戏状态并生成状态提示

    Args:
        obs: Mineland观察对象

    Returns:
        List[str]: 状态提示列表
    """
    status_prompts = []

    # 提取坐标信息
    if hasattr(obs, "location_stats") and obs.location_stats:
        if pos := getattr(obs.location_stats, "pos", None):
            status_prompts.append(f"你的当前坐标是{pos}")

    # 提取生命统计信息
    if hasattr(obs, "life_stats") and obs.life_stats:
        # 饥饿状态分析
        food_level = getattr(obs.life_stats, "food", 20)
        if food_level <= 6:
            status_prompts.append("你现在非常饥饿，需要尽快寻找食物。")
        elif food_level <= 10:
            status_prompts.append("你的饥饿值较低，应该考虑寻找食物。")

        # 生命值分析
        health = getattr(obs.life_stats, "life", 20)
        if health <= 5:
            status_prompts.append("警告：你的生命值极低，处于危险状态！")
        elif health <= 10:
            status_prompts.append("你的生命值较低，需要小心行动。")

        # 氧气值分析
        oxygen = getattr(obs.life_stats, "oxygen", 20)
        if oxygen < 20:
            status_prompts.append(f"你的氧气值不足，当前只有{oxygen}/20。")

    # 分析当前装备状态
    if hasattr(obs, "equip") and obs.equip:
        equipment_prompts = analyze_equipment(obs.equip)
        status_prompts.extend(equipment_prompts)

    # 分析并提取库存状态
    if hasattr(obs, "inventory_full_slot_count") and hasattr(obs, "inventory_slot_count"):
        full_slots = getattr(obs, "inventory_full_slot_count", 0)
        total_slots = getattr(obs, "inventory_slot_count", 36)
        if full_slots >= total_slots - 5:
            status_prompts.append("你的物品栏几乎已满，需要整理或丢弃一些物品。")

        # 使用inventory_all字段提取物品栏内容摘要
        if hasattr(obs, "inventory_all") and obs.inventory_all:
            inventory_items = {}

            # 遍历inventory_all字典，直接获取物品名称和数量
            for slot_id, item_info in obs.inventory_all.items():
                if isinstance(item_info, dict) and "name" in item_info and "count" in item_info:
                    item_name = item_info["name"]
                    item_count = item_info["count"]

                    # 过滤空气和空物品
                    if item_name and item_name != "air" and item_name != "null" and item_count > 0:
                        if item_name in inventory_items:
                            inventory_items[item_name] += item_count
                        else:
                            inventory_items[item_name] = item_count

            if inventory_items:
                # 构建详细的物品栏信息
                items_list = []
                total_items = 0
                for item_name, count in inventory_items.items():
                    items_list.append(f"{count}个{item_name}")
                    total_items += count

                items_summary = ", ".join(items_list)
                status_prompts.append(f"你的物品栏包含: {items_summary}（共{total_items}个物品）")

                # 如果物品种类较多，额外提供分类总结
                if len(inventory_items) > 5:
                    status_prompts.append(f"你总共有{len(inventory_items)}种不同的物品")
            else:
                status_prompts.append("你的物品栏是空的")

        # 如果没有inventory_all字段，回退到原来的inventory字段处理方式
        elif hasattr(obs, "inventory") and hasattr(obs.inventory, "name"):
            inventory_items = {}
            for idx, item_name in enumerate(obs.inventory.name):
                if item_name and item_name != "null" and item_name != "air":
                    quantity = (
                        obs.inventory.quantity[idx]
                        if hasattr(obs.inventory, "quantity") and idx < len(obs.inventory.quantity)
                        else 1
                    )
                    if item_name in inventory_items:
                        inventory_items[item_name] += quantity
                    else:
                        inventory_items[item_name] = quantity

            if inventory_items:
                status_prompts.append(f"你的物品栏包含: {', '.join([f'{v}个{k}' for k, v in inventory_items.items()])}")
            else:
                status_prompts.append("你的物品栏是空的")

    # 分析并提取环境状态
    if hasattr(obs, "location_stats"):
        location_summary = {}

        # 位置坐标
        if hasattr(obs.location_stats, "pos"):
            pos = getattr(obs.location_stats, "pos", [0, 0, 0])
            location_summary["position"] = pos
            if pos[1] < 30:  # Y坐标较低
                status_prompts.append("你处于较低的高度，可能接近地下洞穴或矿层。")

        # 天气状态
        is_raining = getattr(obs.location_stats, "is_raining", False)
        location_summary["is_raining"] = is_raining
        if is_raining:
            status_prompts.append("当前正在下雨，可能影响视野和移动。")

    # 提取时间状态
    if hasattr(obs, "time"):
        game_time = getattr(obs, "time", 0)
        if 13000 <= game_time <= 23000:
            status_prompts.append("现在是夜晚，小心可能出现的敌对生物。")

    # 分析周围方块环境 (voxels)
    if hasattr(obs, "voxels") and obs.voxels:
        voxel_prompts = analyze_voxels(obs.voxels)
        status_prompts.extend(voxel_prompts)

    return status_prompts


def build_prompt(
    agent_info: Dict[str, str],
    status_prompts: List[str],
    obs: Observation,
    events: List[Event],
    code_infos: Optional[List[CodeInfo]] = None,
    event_history: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, str]:
    """
    构建发送给AI的提示词

    Args:
        status_prompts: 状态提示列表
        obs: Mineland观察对象
        code_infos: 代码信息列表，用于检测代码执行错误

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

        # 处理历史事件
        for event_record in event_history[-20:]:  # 取最近20条
            event_type = event_record.get("type", "unknown")
            event_message = event_record.get("message", "")

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

    # 提示词
    chat_target_group1 = "你正在直播Minecraft游戏，以下是游戏的当前状态："
    chat_target_group2 = "正在直播Minecraft游戏"

    # 构建主要的推理提示词，如果有错误则包含错误修正提示
    personality = "你的网名叫\\{bot_name\\}，有人也叫你\\{bot_other_names\\}，\\{prompt_personality\\}"
    base_prompt = f"""{personality}
你正在直播Minecraft游戏，实现游戏目标的同时不要忘记和观众或其他玩家互动。

## 游戏状态
{status_text}

## 游戏目标
请根据当前游戏状态和你之前制定的目标计划，继续执行下一步动作。
- 如果当前目标已完成或无法继续，请制定新的目标
- 如果当前步骤已完成，请继续执行计划中的下一个步骤
- 请保持目标和计划的连贯性，不要频繁更改

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
- `craftItem(bot, name, count)`: 合成物品
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
- 在你认为合适时，使用`bot.chat()`简明扼要，口语化地说明你要做什么，如果前面已经说过，就不必重复说话，或者和前面的话说出差异
- 不要使用`bot.on`或`bot.once`注册事件监听器
- 尽可能使用mineBlock、craftItem、placeItem、smeltItem、killMob等高级函数，如果没有，才使用Mineflayer API
- 如果你看到有玩家和你聊天，请友好回应，不要不理他们
    """

    reasoning_prompt_main = base_prompt.strip()

    return {
        "chat_target_group1": chat_target_group1,
        "chat_target_group2": chat_target_group2,
        "reasoning_prompt_main": reasoning_prompt_main,
    }
