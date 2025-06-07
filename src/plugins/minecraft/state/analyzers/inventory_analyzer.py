"""
库存分析器

负责分析玩家的物品栏状态和物品管理
"""

from typing import List, Dict
from .base_analyzer import BaseAnalyzer


class InventoryAnalyzer(BaseAnalyzer):
    """库存分析器"""

    def __init__(self, obs, config=None):
        super().__init__(obs, config)

        # 加载配置参数
        self.inventory_full_warning_threshold = self._get_config_value("inventory_full_warning_threshold", 5)
        self.default_inventory_slots = self._get_config_value("default_inventory_slots", 36)

    def analyze(self) -> List[str]:
        """
        分析库存相关状态

        Returns:
            List[str]: 库存状态提示列表
        """
        inventory_prompts = []

        try:
            # 库存容量分析
            full_slots = self._safe_getattr(self.obs, "inventory_full_slot_count", 0)
            total_slots = self._safe_getattr(self.obs, "inventory_slot_count", self.default_inventory_slots)

            if full_slots >= total_slots - self.inventory_full_warning_threshold:
                inventory_prompts.append("你的物品栏几乎已满，需要整理或丢弃一些物品。")

            # 库存内容分析
            inventory_items = self._extract_inventory_items()
            if inventory_items:
                inventory_prompts.extend(self._build_inventory_summary(inventory_items))
            else:
                inventory_prompts.append("你的物品栏是空的")

        except Exception as e:
            self.logger.warning(f"分析库存数据时出错: {e}")

        return inventory_prompts

    def _extract_inventory_items(self) -> Dict[str, int]:
        """提取库存物品信息"""
        inventory_items = {}

        # 优先使用inventory_all字段
        inventory_all = self._safe_getattr(self.obs, "inventory_all")
        if inventory_all:
            for slot_id, item_info in inventory_all.items():
                if isinstance(item_info, dict):
                    item_name = item_info.get("name")
                    item_count = item_info.get("count", 0)

                    # 过滤空气和空物品
                    if item_name and item_name not in ["air", "null"] and item_count > 0:
                        inventory_items[item_name] = inventory_items.get(item_name, 0) + item_count

        # 回退到inventory字段
        elif hasattr(self.obs, "inventory"):
            inventory = self.obs.inventory
            if hasattr(inventory, "name"):
                for idx, item_name in enumerate(inventory.name):
                    if item_name and item_name not in ["null", "air"]:
                        quantity = (
                            inventory.quantity[idx]
                            if hasattr(inventory, "quantity") and idx < len(inventory.quantity)
                            else 1
                        )
                        inventory_items[item_name] = inventory_items.get(item_name, 0) + quantity

        return inventory_items

    def _build_inventory_summary(self, inventory_items: Dict[str, int]) -> List[str]:
        """构建库存摘要信息"""
        summary_prompts = []

        # 构建详细的物品栏信息
        items_list = []
        total_items = 0

        for item_name, count in inventory_items.items():
            items_list.append(f"{count}个{item_name}")
            total_items += count

        items_summary = ", ".join(items_list)
        summary_prompts.append(f"你的物品栏包含: {items_summary}（共{total_items}个物品）")

        # 如果物品种类较多，额外提供分类总结
        if len(inventory_items) > 5:
            summary_prompts.append(f"你总共有{len(inventory_items)}种不同的物品")

        return summary_prompts
