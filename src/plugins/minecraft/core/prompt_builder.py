import json
from typing import List, Dict, Any, Optional

from src.utils.logger import get_logger
from src.plugins.minecraft.core.state_analyzers import analyze_voxels, analyze_equipment
from mineland import Observation, Event, CodeInfo

logger = get_logger("MinecraftPrompt")


def build_state_analysis(obs: Observation, events: List[Event], code_infos: List[CodeInfo]) -> List[str]:
    """
    分析游戏状态并生成状态提示

    Args:
        obs: Mineland观察对象

    Returns:
        List[str]: 状态提示列表
    """
    status_prompts = []

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

    # 提取最近的聊天消息或事件
    if events:
        recent_events = []
        for event in events[-5:]:  # 仅取最近5条消息
            if hasattr(event, "type") and hasattr(event, "only_message"):
                recent_events.append({"type": event.type, "message": event.only_message})
        if recent_events:
            recent_events_str = [f"{e['type']}: {e['message']}" for e in recent_events]
            status_prompts.append(f"最近的事件: {', '.join(recent_events_str)}")

    return status_prompts


def build_prompt(status_prompts: List[str], obs: Observation) -> Dict[str, str]:
    """
    构建发送给AI的提示词

    Args:
        status_prompts: 状态提示列表

    Returns:
        Dict[str, str]: 包含提示词的模板项字典
    """

    status_text = ";".join(status_prompts)

    # 提示词
    chat_target_group1 = "你正在直播Minecraft游戏，以下是游戏的当前状态："
    chat_target_group2 = "正在直播Minecraft游戏"
    reasoning_prompt_main = f"""
    你正在直播Minecraft游戏，以下是游戏的当前状态：{status_text}。
    请分析游戏状态并提供一个JSON格式的动作指令。你的回复必须严格遵循JSON格式。不要包含任何markdown标记 (如 ```json ... ```), 也不要包含任何解释性文字、注释或除了纯JSON对象之外的任何内容。
    请提供一个JSON对象，包含一个名为 `actions` 的字段，该字段是Mineflayer JavaScript代码字符串。

以下是一些有用的Mineflayer API和函数:
- `bot.chat(message)`: 发送聊天消息，聊天消息请使用中文
- `mineBlock(bot, name, count)`: 收集指定方块，例如`mineBlock(bot,'oak_log',10)`
- `craftItem(bot, name, count)`: 合成物品
- `placeItem(bot, name, position)`: 放置方块
- `smeltItem(bot, name, count)`: 冶炼物品
- `killMob(bot, name, timeout)`: 击杀生物

编写代码时的注意事项:
- 代码需要符合JavaScript语法
- 检查机器人库存再使用物品
- 使用`bot.chat()`显示进度
- 不要使用`bot.on`或`bot.once`注册事件监听器
- 尽可能使用mineBlock、craftItem、placeItem、smeltItem、killMob等高级函数，如果没有，才使用Mineflayer API
    """
    return {
        "chat_target_group1": chat_target_group1,
        "chat_target_group2": chat_target_group2,
        "reasoning_prompt_main": reasoning_prompt_main,
    }
