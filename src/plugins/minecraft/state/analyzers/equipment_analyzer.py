"""
装备分析器

负责分析玩家当前的装备状态，包括武器、工具、护甲等
"""

from typing import List, Dict
from .base_analyzer import BaseAnalyzer


class EquipmentAnalyzer(BaseAnalyzer):
    """装备分析器"""

    def __init__(self, obs, config=None):
        super().__init__(obs, config)

        # 加载配置参数
        self.durability_critical_threshold = self._get_config_value("durability_critical_threshold", 10)
        self.durability_low_threshold = self._get_config_value("durability_low_threshold", 25)
        self.armor_good_protection_threshold = self._get_config_value("armor_good_protection_threshold", 3)
        self.armor_partial_threshold = self._get_config_value("armor_partial_threshold", 1)
        self.armor_total_slots = self._get_config_value("armor_total_slots", 4)

    def analyze(self) -> List[str]:
        """
        分析当前装备状态

        Returns:
            List[str]: 装备状态分析提示列表
        """
        equipment_prompts = []

        # 获取装备信息
        equip = self._safe_getattr(self.obs, "equip")
        if not equip:
            return equipment_prompts

        try:
            # 装备槽位映射
            slot_names = {
                "main hand": "主手",
                "off hand": "副手",
                "head": "头部",
                "body": "胸部",
                "leg": "腿部",
                "foot": "脚部",
            }

            equipped_items = {}
            empty_slots = []

            # 遍历所有装备槽位
            for slot_key, slot_name in slot_names.items():
                slot_data = self._safe_getattr(equip, slot_key)

                if slot_data:
                    item_name = self._safe_getattr(slot_data, "name")

                    # 过滤空气，视为无装备
                    if item_name and item_name not in ["air", "null"]:
                        quantity = self._safe_getattr(slot_data, "quantity", 1)
                        cur_durability = self._safe_getattr(slot_data, "cur_durability")
                        max_durability = self._safe_getattr(slot_data, "max_durability")

                        # 构建装备信息
                        item_info = f"{slot_name}: {item_name}"
                        if quantity > 1:
                            item_info += f" x{quantity}"

                        # 添加耐久度信息
                        if cur_durability is not None and max_durability is not None and max_durability > 0:
                            durability_percent = int((cur_durability / max_durability) * 100)
                            item_info += f" (耐久度: {durability_percent}%)"

                            # 耐久度警告
                            if durability_percent <= self.durability_critical_threshold:
                                equipment_prompts.append(
                                    f"警告：{slot_name}的{item_name}耐久度极低({durability_percent}%)，即将损坏！"
                                )
                            elif durability_percent <= self.durability_low_threshold:
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

                # 装备类型检测
                self._analyze_equipment_types(equipped_items, equipment_prompts)

                # 护甲完整性分析
                self._analyze_armor_coverage(equipped_items, equipment_prompts)
            else:
                equipment_prompts.append("你目前没有装备任何物品")

            # 提醒重要空槽位
            important_empty_slots = [slot for slot in empty_slots if slot in ["主手", "头部", "胸部"]]
            if important_empty_slots and equipped_items:
                equipment_prompts.append(f"空装备槽位: {', '.join(important_empty_slots)}")

        except Exception as e:
            self.logger.warning(f"分析装备数据时出错: {e}")

        return equipment_prompts

    def _analyze_equipment_types(self, equipped_items: Dict[str, str], prompts: List[str]):
        """分析装备类型"""
        # 检测武器
        weapon_keywords = ["sword", "axe", "bow", "crossbow", "trident"]
        has_weapon = any(
            keyword in item_info.lower() for item_info in equipped_items.values() for keyword in weapon_keywords
        )
        if has_weapon:
            prompts.append("你装备了武器，可以用于战斗")

        # 检测工具
        tool_keywords = ["pickaxe", "shovel", "hoe", "shears"]
        has_tool = any(
            keyword in item_info.lower() for item_info in equipped_items.values() for keyword in tool_keywords
        )
        if has_tool:
            prompts.append("你装备了工具，可以高效地收集资源")

    def _analyze_armor_coverage(self, equipped_items: Dict[str, str], prompts: List[str]):
        """分析护甲覆盖情况"""
        armor_slots = ["头部", "胸部", "腿部", "脚部"]
        equipped_armor = [slot for slot in armor_slots if slot in equipped_items]

        if len(equipped_armor) >= self.armor_good_protection_threshold:
            prompts.append(f"你穿戴了较完整的护甲({len(equipped_armor)}/{self.armor_total_slots}件)，有良好的防护")
        elif len(equipped_armor) >= self.armor_partial_threshold:
            prompts.append(f"你穿戴了部分护甲({len(equipped_armor)}/{self.armor_total_slots}件)")
