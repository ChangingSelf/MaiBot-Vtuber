import json
from typing import List, Dict, Any, Optional

from src.utils.logger import get_logger

logger = get_logger("MinecraftPrompt")


def build_state_analysis(agent_obs) -> tuple[List[str], Dict[str, Any]]:
    """
    分析游戏状态并生成状态提示和状态摘要

    Args:
        agent_obs: Mineland观察对象

    Returns:
        tuple: (状态提示列表, 状态摘要字典)
    """
    status_hints = []
    state_summary = {"step": 0, "agent": {}}

    # 提取生命统计信息
    if hasattr(agent_obs, "life_stats") and agent_obs.life_stats:
        # 饥饿状态分析
        food_level = getattr(agent_obs.life_stats, "food", 20)
        if food_level <= 6:
            status_hints.append("你现在非常饥饿，需要尽快寻找食物。")
        elif food_level <= 10:
            status_hints.append("你的饥饿值较低，应该考虑寻找食物。")

        # 生命值分析
        health = getattr(agent_obs.life_stats, "life", 20)
        if health <= 5:
            status_hints.append("警告：你的生命值极低，处于危险状态！")
        elif health <= 10:
            status_hints.append("你的生命值较低，需要小心行动。")

        # 氧气值分析
        oxygen = getattr(agent_obs.life_stats, "oxygen", 20)
        if oxygen < 20:
            status_hints.append(f"你的氧气值不足，当前只有{oxygen}/20。")

        # 添加到状态摘要
        state_summary["agent"]["health"] = health
        state_summary["agent"]["food"] = food_level
        state_summary["agent"]["oxygen"] = oxygen

    # 分析并提取库存状态
    if hasattr(agent_obs, "inventory_full_slot_count") and hasattr(agent_obs, "inventory_slot_count"):
        full_slots = getattr(agent_obs, "inventory_full_slot_count", 0)
        total_slots = getattr(agent_obs, "inventory_slot_count", 36)
        if full_slots >= total_slots - 5:
            status_hints.append("你的物品栏几乎已满，需要整理或丢弃一些物品。")

        # 添加到状态摘要
        state_summary["agent"]["inventory"] = {"full_slots": full_slots, "total_slots": total_slots}

        # 提取物品栏内容摘要
        if hasattr(agent_obs, "inventory") and hasattr(agent_obs.inventory, "name"):
            inventory_items = {}
            for idx, item_name in enumerate(agent_obs.inventory.name):
                if item_name and item_name != "null":
                    quantity = (
                        agent_obs.inventory.quantity[idx]
                        if hasattr(agent_obs.inventory, "quantity") and idx < len(agent_obs.inventory.quantity)
                        else 1
                    )
                    if item_name in inventory_items:
                        inventory_items[item_name] += quantity
                    else:
                        inventory_items[item_name] = quantity

            state_summary["agent"]["items"] = inventory_items

    # 分析并提取环境状态
    if hasattr(agent_obs, "location_stats"):
        location_summary = {}

        # 位置坐标
        if hasattr(agent_obs.location_stats, "pos"):
            pos = getattr(agent_obs.location_stats, "pos", [0, 0, 0])
            location_summary["position"] = pos
            if pos[1] < 30:  # Y坐标较低
                status_hints.append("你处于较低的高度，可能接近地下洞穴或矿层。")

        # 天气状态
        is_raining = getattr(agent_obs.location_stats, "is_raining", False)
        location_summary["is_raining"] = is_raining
        if is_raining:
            status_hints.append("当前正在下雨，可能影响视野和移动。")

        state_summary["agent"]["location"] = location_summary

    # 提取时间状态
    if hasattr(agent_obs, "time"):
        game_time = getattr(agent_obs, "time", 0)
        state_summary["time"] = game_time
        if 13000 <= game_time <= 23000:
            status_hints.append("现在是夜晚，小心可能出现的敌对生物。")

    # 提取最近的聊天消息或事件
    if hasattr(agent_obs, "event") and agent_obs.event:
        recent_events = []
        for event in agent_obs.event[-5:]:  # 仅取最近5条消息
            if hasattr(event, "type") and hasattr(event, "only_message"):
                recent_events.append({"type": event.type, "message": event.only_message})
        if recent_events:
            state_summary["recent_events"] = recent_events

    return status_hints, state_summary


def build_prompt(
    state_summary: Dict[str, Any], status_hints: List[str], step_num: int, enable_low_level_action: bool
) -> str:
    """
    构建发送给AI的提示词

    Args:
        state_summary: 游戏状态摘要
        status_hints: 状态提示列表
        step_num: 当前步数
        enable_low_level_action: 是否启用低级动作

    Returns:
        str: 完整的提示词
    """
    # 基础提示
    base_prompt = (
        "你是一个Minecraft智能体助手。请分析游戏状态并提供一个JSON格式的动作指令。\n"
        "你的回复必须严格遵循JSON格式。不要包含任何markdown标记 (如 ```json ... ```), "
        "也不要包含任何解释性文字、注释或除了纯JSON对象之外的任何内容。"
    )

    # 添加状态提示
    if status_hints:
        status_analysis = "\n\n状态分析：\n" + "\n".join([f"- {hint}" for hint in status_hints])
        base_prompt += status_analysis

    # 添加状态摘要
    if state_summary:
        try:
            state_summary["step"] = step_num  # 确保步数是最新的
            state_summary_json = json.dumps(state_summary, ensure_ascii=False, indent=2)
            state_summary_section = f"\n\n当前游戏状态摘要：\n{state_summary_json}"
            base_prompt += state_summary_section
        except Exception as e:
            logger.exception(f"序列化状态摘要失败: {e}", exc_info=True)

    # 高级动作提示
    high_level_example = {"actions": "bot.chat('Hello from Minecraft!'); bot.jump();"}
    high_level_instructions = f"""请提供一个JSON对象，包含一个名为 `actions` 的字段，该字段是Mineflayer JavaScript代码字符串。

你是一个编写Mineflayer JavaScript代码的助手，帮助机器人完成Minecraft中的任务。
以下是一些有用的Mineflayer API和函数:
- `bot.chat(message)`: 发送聊天消息
- `mineBlock(bot, name, count)`: 收集指定方块，例如`mineBlock(bot,'oak_log',10)`
- `craftItem(bot, name, count)`: 合成物品
- `placeItem(bot, name, position)`: 放置方块
- `smeltItem(bot, name, count)`: 冶炼物品
- `killMob(bot, name, timeout)`: 击杀生物

编写代码时的注意事项:
- 使用`async/await`语法处理异步操作
- 避免无限循环和递归函数
- 检查机器人库存再使用物品
- 使用`bot.chat()`显示进度
- 不要使用`bot.on`或`bot.once`注册事件监听器

简单示例代码:
```
async function findAndCollectWood(bot) {{
  bot.chat('开始寻找并收集木头');
  
  // 尝试寻找橡木
  const log = bot.findBlock({{
    matching: block => block.name.includes('log'),
    maxDistance: 32
  }});
  
  if (!log) {{
    bot.chat('附近没有找到木头，四处探索');
    // 向前移动10秒
    bot.setControlState('forward', true);
    await new Promise(resolve => setTimeout(resolve, 10000));
    bot.setControlState('forward', false);
    return;
  }}
  
  bot.chat('找到木头，准备收集');
  await mineBlock(bot, 'log', 3);
  bot.chat('成功收集了木头');
}}
```

`{json.dumps(high_level_example)}`

如果不提供 `actions` 字段或其不是有效的字符串，将不执行任何操作。
回复必须是纯JSON，不含其他文本或标记。
"""

    # 低级动作提示
    low_level_example = {"actions": [0, 1, 0, 0, 12, 0, 0, 0]}
    low_level_instructions = f"""请提供一个JSON对象，包含一个名为 `actions` 的字段，该字段是包含8个整数的数组。

这8个整数控制智能体的基本动作:
- 索引 0: 前进/后退 (0=无, 1=前进, 2=后退), 范围: [0, 2]
- 索引 1: 左移/右移 (0=无, 1=左移, 2=右移), 范围: [0, 2]
- 索引 2: 跳跃/下蹲 (0=无, 1=跳跃, 2=下蹲, 3=其他), 范围: [0, 3]
- 索引 3: 摄像头水平旋转 (0-24, 12=无变化), 范围: [0, 24]
- 索引 4: 摄像头垂直旋转 (0-24, 12=无变化), 范围: [0, 24]
- 索引 5: 交互类型 (0=无, 1=攻击, 2=使用, 3=放置...), 范围: [0, 9]
- 索引 6: 方块/物品选择 (0-243), 范围: [0, 243]
- 索引 7: 库存管理 (0-45), 范围: [0, 45]

例如: `{json.dumps(low_level_example)}`

如果不提供 `actions` 字段或其不是包含8个整数的数组，将不执行任何操作。
回复必须是纯JSON，不含其他文本或标记。
"""

    # 根据配置选择提示词
    detailed_instructions = low_level_instructions if enable_low_level_action else high_level_instructions

    # 最终的提示内容
    prompted_message_content = f"{base_prompt}\n\n{detailed_instructions}"

    return prompted_message_content
