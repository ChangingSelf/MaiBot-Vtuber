from typing import List
from src.utils.logger import get_logger

logger = get_logger("MinecraftStateAnalyzers")


def analyze_voxels(voxels) -> List[str]:
    """
    分析周围方块环境

    Args:
        voxels: 3x3x3的方块数据结构，voxels[i][j][k] = blocksAt(MyPosition.offset(i-1, j-1, k-1))

    Returns:
        List[str]: 周围环境分析提示列表
    """
    voxel_prompts = []

    try:
        # 检查voxels是否有block_name字段
        if not hasattr(voxels, "block_name") and not (isinstance(voxels, dict) and "block_name" in voxels):
            return voxel_prompts

        # 获取方块名称数据 (3x3x3数组)
        block_names = voxels.block_name if hasattr(voxels, "block_name") else voxels["block_name"]
        is_collidable = (
            getattr(voxels, "is_collidable", None)
            if hasattr(voxels, "is_collidable")
            else voxels.get("is_collidable", None)
        )
        is_liquid = (
            getattr(voxels, "is_liquid", None) if hasattr(voxels, "is_liquid") else voxels.get("is_liquid", None)
        )
        is_solid = getattr(voxels, "is_solid", None) if hasattr(voxels, "is_solid") else voxels.get("is_solid", None)

        # 收集所有方块类型
        block_counts = {}
        liquid_blocks = []
        solid_blocks = []
        air_blocks = 0

        # 遍历3x3x3数组 (i, j, k对应offset(i-1, j-1, k-1))
        for x in range(len(block_names)):
            for y in range(len(block_names[x])):
                for z in range(len(block_names[x][y])):
                    block_name = block_names[x][y][z]

                    if block_name == "air":
                        air_blocks += 1
                    elif block_name and block_name != "null":
                        # 统计方块类型
                        if block_name in block_counts:
                            block_counts[block_name] += 1
                        else:
                            block_counts[block_name] = 1

                        # 检查是否是液体
                        if is_liquid and x < len(is_liquid) and y < len(is_liquid[x]) and z < len(is_liquid[x][y]):
                            if is_liquid[x][y][z]:
                                liquid_blocks.append(block_name)

                        # 检查是否是固体
                        if is_solid and x < len(is_solid) and y < len(is_solid[x]) and z < len(is_solid[x][y]):
                            if is_solid[x][y][z]:
                                solid_blocks.append(block_name)

        # === 新增：直白简明的方块种类描述 ===
        if block_counts:
            # 按数量排序方块类型
            sorted_blocks = sorted(block_counts.items(), key=lambda x: x[1], reverse=True)

            # 构建简洁的方块列表描述
            block_list = []
            for block_name, count in sorted_blocks:
                if count >= 3:  # 数量较多的方块
                    block_list.append(f"{block_name}（{count}个）")
                else:  # 数量较少的方块
                    block_list.append(block_name)

            # 生成方块种类总览
            if len(block_list) <= 3:
                voxel_prompts.append(f"附近方块: {', '.join(block_list)}")
            else:
                # 如果方块种类太多，只显示主要的几种
                main_blocks = block_list[:3]
                other_count = len(block_list) - 3
                voxel_prompts.append(f"附近方块: {', '.join(main_blocks)}等{other_count + 3}种")

        # 分析玩家当前位置的方块 (voxels[1][1][1] = offset(0, 0, 0))
        if len(block_names) > 1 and len(block_names[1]) > 1 and len(block_names[1][1]) > 1:
            current_block = block_names[1][1][1]
            if current_block and current_block != "air":
                voxel_prompts.append(f"你当前位置有{current_block}方块，可能需要移动")

        # 分析脚下的方块 (voxels[1][0][1] = offset(0, -1, 0))
        if len(block_names) > 1 and len(block_names[1]) > 0 and len(block_names[1][0]) > 1:
            ground_block = block_names[1][0][1]
            if ground_block and ground_block != "air":
                voxel_prompts.append(f"你脚下是{ground_block}方块")

                # 如果脚下是液体，给出警告
                if is_liquid and len(is_liquid) > 1 and len(is_liquid[1]) > 0 and len(is_liquid[1][0]) > 1:
                    if is_liquid[1][0][1]:
                        voxel_prompts.append("警告：你脚下是液体，可能会溺水或受伤！")

        # 分析周围环境的总体情况
        if block_counts:
            # 找出最常见的方块类型
            most_common_block = max(block_counts, key=block_counts.get)
            most_common_count = block_counts[most_common_block]

            # 构建周围环境描述
            if most_common_count >= 10:  # 在3x3x3=27个方块中，如果某种方块超过10个就算主要环境
                voxel_prompts.append(f"你周围的方块主要是：{most_common_block}")

            # 特殊环境检测
            if "water" in block_counts or "lava" in block_counts:
                liquids = [name for name in block_counts.keys() if name in ["water", "lava"]]
                if liquids:
                    voxel_prompts.append(f"警告：周围有{', '.join(liquids)}，需要小心移动")

            if "stone" in block_counts and block_counts["stone"] >= 5:
                voxel_prompts.append("你附近都是石头，可能在洞穴或山区")

            if "grass_block" in block_counts and block_counts["grass_block"] >= 5:
                voxel_prompts.append("你附近是草地")

            if "sand" in block_counts and block_counts["sand"] >= 5:
                voxel_prompts.append("你附近是沙漠")

            if "oak_log" in block_counts or "birch_log" in block_counts or "spruce_log" in block_counts:
                voxel_prompts.append("你附近有树木，可以收集木材")

        # 分析空气方块比例，判断是否在开阔区域
        total_blocks = 27  # 3x3x3
        if air_blocks >= 20:
            voxel_prompts.append("你处于开阔区域")
        elif air_blocks <= 5:
            voxel_prompts.append("你处于封闭或狭窄的空间")

        # 检查头顶是否有遮挡 (voxels[1][2][1] = offset(0, 1, 0))
        if len(block_names) > 1 and len(block_names[1]) > 2 and len(block_names[1][2]) > 1:
            overhead_block = block_names[1][2][1]
            if overhead_block and overhead_block != "air":
                voxel_prompts.append(f"你头顶有{overhead_block}方块，可能需要挖掘才能向上移动")

    except (IndexError, KeyError, AttributeError) as e:
        logger.warning(f"分析voxels数据时出错: {e}")

    return voxel_prompts


def analyze_equipment(equip) -> List[str]:
    """
    分析当前装备状态

    Args:
        equip: 装备信息对象，包含各个装备槽位的信息

    Returns:
        List[str]: 装备状态分析提示列表
    """
    equipment_prompts = []

    try:
        # 定义装备槽位的中文名称映射
        slot_names = {
            "main hand": "主手",
            "off hand": "副手",
            "head": "头部",
            "body": "胸部",
            "leg": "腿部",
            "foot": "脚部",
        }

        # 收集已装备的物品
        equipped_items = {}
        empty_slots = []

        # 遍历所有装备槽位
        for slot_key, slot_name in slot_names.items():
            if hasattr(equip, slot_key) or (isinstance(equip, dict) and slot_key in equip):
                slot_data = getattr(equip, slot_key, None) if hasattr(equip, slot_key) else equip.get(slot_key, None)

                if slot_data:
                    # 获取装备名称
                    item_name = (
                        getattr(slot_data, "name", None) if hasattr(slot_data, "name") else slot_data.get("name", None)
                    )

                    # 过滤空气，视为无装备
                    if item_name and item_name != "air" and item_name != "null":
                        # 获取数量信息
                        quantity = (
                            getattr(slot_data, "quantity", 1)
                            if hasattr(slot_data, "quantity")
                            else slot_data.get("quantity", 1)
                        )

                        # 获取耐久度信息
                        cur_durability = (
                            getattr(slot_data, "cur_durability", None)
                            if hasattr(slot_data, "cur_durability")
                            else slot_data.get("cur_durability", None)
                        )
                        max_durability = (
                            getattr(slot_data, "max_durability", None)
                            if hasattr(slot_data, "max_durability")
                            else slot_data.get("max_durability", None)
                        )

                        # 构建装备信息
                        item_info = f"{slot_name}: {item_name}"
                        if quantity > 1:
                            item_info += f" x{quantity}"

                        # 添加耐久度信息（如果有）
                        if cur_durability is not None and max_durability is not None and max_durability > 0:
                            durability_percent = int((cur_durability / max_durability) * 100)
                            item_info += f" (耐久度: {durability_percent}%)"

                            # 耐久度警告
                            if durability_percent <= 10:
                                equipment_prompts.append(
                                    f"警告：{slot_name}的{item_name}耐久度极低({durability_percent}%)，即将损坏！"
                                )
                            elif durability_percent <= 25:
                                equipment_prompts.append(
                                    f"注意：{slot_name}的{item_name}耐久度较低({durability_percent}%)，建议修理或更换"
                                )

                        equipped_items[slot_name] = item_info
                    else:
                        empty_slots.append(slot_name)
                else:
                    empty_slots.append(slot_name)

        # 生成装备概述
        if equipped_items:
            equipment_list = list(equipped_items.values())
            equipment_prompts.append(f"当前装备: {', '.join(equipment_list)}")

            # 特殊装备类型检测
            all_equipment = ", ".join(equipped_items.keys())

            # 检测是否有武器
            weapon_keywords = ["sword", "axe", "bow", "crossbow", "trident"]
            has_weapon = any(
                keyword in item_info.lower() for item_info in equipped_items.values() for keyword in weapon_keywords
            )
            if has_weapon:
                equipment_prompts.append("你装备了武器，可以用于战斗")

            # 检测是否有工具
            tool_keywords = ["pickaxe", "shovel", "hoe", "shears"]
            has_tool = any(
                keyword in item_info.lower() for item_info in equipped_items.values() for keyword in tool_keywords
            )
            if has_tool:
                equipment_prompts.append("你装备了工具，可以高效地收集资源")

            # 检测护甲完整性
            armor_slots = ["头部", "胸部", "腿部", "脚部"]
            equipped_armor = [slot for slot in armor_slots if slot in equipped_items]
            if len(equipped_armor) >= 3:
                equipment_prompts.append(f"你穿戴了较完整的护甲({len(equipped_armor)}/4件)，有良好的防护")
            elif len(equipped_armor) >= 1:
                equipment_prompts.append(f"你穿戴了部分护甲({len(equipped_armor)}/4件)")
        else:
            equipment_prompts.append("你目前没有装备任何物品")

        # 提醒空装备槽位（如果有重要槽位为空）
        important_empty_slots = [slot for slot in empty_slots if slot in ["主手", "头部", "胸部"]]
        if important_empty_slots and len(equipped_items) > 0:  # 只在有其他装备时提醒空槽位
            equipment_prompts.append(f"空装备槽位: {', '.join(important_empty_slots)}")

    except (AttributeError, KeyError) as e:
        logger.warning(f"分析装备数据时出错: {e}")

    return equipment_prompts
