import json
from typing import Dict, Any, Optional
from src.utils.logger import get_logger
from .name_map import ITEM_NAME_MAP


class RecipeFinder:
    def __init__(self, mcp_client=None):
        self.mcp_client = mcp_client
        self.logger = get_logger("RecipeFinder")
        
        # 物品别名映射表，将常用别名映射成标准名称
    
    def _normalize_item_name(self, item_name: str) -> str:
        """
        将物品名称标准化，将别名映射成标准名称
        
        Args:
            item_name: 输入的物品名称（可能是别名）
            
        Returns:
            标准化的物品名称
        """
        # 去除首尾空格并转换为小写
        normalized = item_name.strip().lower()
        
        # 查找映射
        if normalized in ITEM_NAME_MAP:
            return ITEM_NAME_MAP[normalized]
        
        # 如果没有找到映射，返回原名称
        return item_name
    
    async def find_recipe(self, item_name: str) -> str:
        """
        通过 MCP 工具获取物品的合成表并翻译成可读格式
        
        Args:
            item_name: 物品名称
            
        Returns:
            可读的合成表描述
        """
        if not self.mcp_client:
            return "错误：MCP 客户端未初始化"
        
        try:
            # 标准化物品名称
            normalized_name = self._normalize_item_name(item_name)
            if normalized_name != item_name:
                self.logger.info(f"[RecipeFinder] 物品名称标准化: '{item_name}' -> '{normalized_name}'")
            

            arguments = {"item": normalized_name}
            result = await self.mcp_client.call_tool_directly("query_recipe", arguments)
            
            if result.is_error:
                self.logger.error(f"[RecipeFinder] 获取合成表失败：{result}")
                return f"获取合成表失败：{result.content[0].text if result.content else '未知错误'}"
            
            # 解析返回结果
            recipe_info = await self._parse_recipe_result(result, normalized_name)
            
            arguments_crafting_table = {"item": normalized_name,"useCraftingTable":True}
            result_crafting_table = await self.mcp_client.call_tool_directly("query_recipe", arguments_crafting_table)
            
            if result_crafting_table.is_error:
                self.logger.error(f"[RecipeFinder] 获取合成表失败：{result_crafting_table}")
                return ""
            
            # 解析返回结果
            recipe_info_crafting_table = await self._parse_recipe_result(result_crafting_table, normalized_name, True)
            
            
            if not recipe_info and not recipe_info_crafting_table:
                return ""
            
            
            return recipe_info + recipe_info_crafting_table
            
        except Exception as e:
            error_msg = f"获取合成表时发生错误：{str(e)}"
            self.logger.error(error_msg)
            return error_msg
    
    async def _parse_recipe_result(self, result, item_name: str = "", use_crafting_table: bool = False) -> str:
        """
        解析 MCP 工具返回的合成表结果
        
        Args:
            result: MCP 工具返回的结果
            item_name: 物品名称，用于格式化输出
            
        Returns:
            可读的合成表描述
        """
        try:
            # 从结果中提取文本内容
            if hasattr(result, 'content') and result.content:
                result_text = ""
                for content in result.content:
                    if hasattr(content, 'text'):
                        result_text += content.text
                
                # 尝试解析 JSON 结果
                try:
                    result_json = json.loads(result_text)
                    
                    # 检查是否成功
                    if isinstance(result_json, dict):
                        if result_json.get("ok") is True:
                            data = result_json.get("data", {})
                            recipes = data.get("recipes", [])
                            tips = data.get("tips", "")
                            
                            # 判断 recipes 是否为空或仅为嵌套空列表（如 [[]]、[[], []] 等）
                            if not recipes or all(isinstance(r, list) and not r for r in recipes):
                                return ""
                            
                            # 生成可读的合成表描述
                            recipe_description = self._format_recipes(item_name, recipes, use_crafting_table)
                            
                            # 添加提示信息
                            if tips:
                                recipe_description += f"\n提示：{tips}"
                            
                            return recipe_description
                        else:
                            self.logger.error(f"获取合成表失败：\n{result_json}")
                            return ""
                    else:
                        return f"返回结果格式错误：{result_text}"
                        
                except json.JSONDecodeError:
                    # 如果不是 JSON 格式，直接返回文本内容
                    return f"合成表信息：{result_text}"
            else:
                return "未获取到合成表信息"
                
        except Exception as e:
            error_msg = f"解析合成表结果时发生错误：{str(e)}"
            self.logger.error(error_msg)
            return error_msg
    
    def _format_recipes(self, item_name: str, recipes: list, use_crafting_table: bool = False) -> str:
        """
        格式化合成表为可读格式
        
        Args:
            item_name: 物品名称
            recipes: 合成表列表
            
        Returns:
            格式化的合成表描述
        """
        if not recipes:
            return f"❌ 未找到 {item_name} 的合成表"
        
        formatted_recipes = []
        
        for i, recipe in enumerate(recipes, 1):
            if isinstance(recipe, list):
                # 处理材料列表
                materials = []
                for material in recipe:
                    if isinstance(material, dict):
                        name = material.get("name", "未知材料")
                        name = self._normalize_item_name(name)
                        count = material.get("count", 1)
                        if count > 1:
                            materials.append(f"{name} × {count}")
                        else:
                            materials.append(name)
                    else:
                        materials.append(self._normalize_item_name(material))
                
                recipe_str = " + ".join(materials)
                formatted_recipes.append(f"{i}. {recipe_str}")
            else:
                # 处理单个材料
                formatted_recipes.append(f"{i}. {self._normalize_item_name(recipe)}")
        
        # 构建最终的合成表描述
        recipe_text = f"🔧 {item_name} 的合成表：\n"
        if use_crafting_table:
            recipe_text += "使用工作台合成：\n"
        recipe_text += "\n".join(formatted_recipes)
        
        return recipe_text
    
    def set_mcp_client(self, mcp_client):
        """设置 MCP 客户端实例"""
        self.mcp_client = mcp_client
    
    

recipe_finder = RecipeFinder()