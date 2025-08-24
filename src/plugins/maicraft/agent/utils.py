import json
from json_repair import repair_json
from typing import List, Dict, Any
from loguru import logger

def parse_json(text: str) -> dict:
    """解析json字符串"""
    try:
        repaired_json = repair_json(text)
        return json.loads(repaired_json)
    except json.JSONDecodeError:
        return None
    
def convert_mcp_tools_to_openai_format(mcp_tools) -> List[Dict[str, Any]]:
    """将MCP工具转换为OpenAI工具格式"""
    openai_tools = []
    
    for tool in mcp_tools:
        # 构建工具描述
        description = tool.description or f"执行{tool.name}操作"
        if tool.inputSchema:
            properties = tool.inputSchema.get("properties", {})
            required = tool.inputSchema.get("required", [])
            
            # 添加参数信息到描述
            if properties:
                description += "\n\n参数说明："
                for prop_name, prop_info in properties.items():
                    prop_type = prop_info.get("type", "string")
                    prop_desc = prop_info.get("description", "")
                    required_mark = " (必需)" if prop_name in required else " (可选)"
                    description += f"\n- {prop_name}: {prop_type}{required_mark}"
                    if prop_desc:
                        description += f" - {prop_desc}"
        
        openai_tool = {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": description,
                "parameters": tool.inputSchema or {
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            }
        }
        openai_tools.append(openai_tool)
    
    return openai_tools

def parse_tool_result(result) -> tuple[bool, str]:
    """解析工具执行结果，判断是否真的成功
    
    Args:
        result: MCP工具返回的结果
        
    Returns:
        (是否成功, 结果内容)
    """
    try:
        # 首先检查MCP层面的错误
        if result.is_error:
            return False, f"MCP错误: {result.content}"
        
        # 从结果中提取文本内容
        if hasattr(result, 'content') and result.content:
            result_text = ""
            for content in result.content:
                if hasattr(content, 'text'):
                    result_text += content.text
            
            # 尝试解析JSON结果
            try:
                import json
                result_json = json.loads(result_text)
                
                # 检查常见的成功/失败字段
                if isinstance(result_json, dict):
                    # 检查ok字段
                    if "ok" in result_json:
                        if result_json["ok"] is False:
                            error_msg = result_json.get("error_message", "未知错误")
                            error_code = result_json.get("error_code", "")
                            return False, f"工具执行失败: {error_msg} (错误代码: {error_code})"
                        elif result_json["ok"] is True:
                            return True, result_text
                    
                    # 检查success字段
                    if "success" in result_json:
                        if result_json["success"] is False:
                            error_msg = result_json.get("error_message", "未知错误")
                            error_code = result_json.get("error_code", "")
                            return False, f"工具执行失败: {error_msg} (错误代码: {error_code})"
                        elif result_json["success"] is True:
                            return True, result_text
                    
                    # 检查error相关字段
                    if "error" in result_json and result_json["error"]:
                        error_msg = result_json.get("error_message", "未知错误")
                        error_code = result_json.get("error_code", "")
                        return False, f"工具执行失败: {error_msg} (错误代码: {error_code})"
                    
                    # 检查error_code字段
                    if "error_code" in result_json and result_json["error_code"]:
                        error_msg = result_json.get("error_message", "未知错误")
                        error_code = result_json["error_code"]
                        return False, f"工具执行失败: {error_msg} (错误代码: {error_code})"
                    
                    # 如果没有明确的错误信息，检查文本内容中是否包含错误关键词
                    error_keywords = ["错误", "失败", "error", "failed", "exception", "not found", "不足", "无效"]
                    for keyword in error_keywords:
                        if keyword.lower() in result_text.lower():
                            return False, f"工具执行失败: {result_text}"
                    
                    # 默认认为成功
                    return True, result_text
                
            except json.JSONDecodeError:
                # 如果不是JSON格式，检查文本内容
                error_keywords = ["错误", "失败", "error", "failed", "exception", "not found", "不足", "无效"]
                for keyword in error_keywords:
                    if keyword.lower() in result_text.lower():
                        return False, f"工具执行失败: {result_text}"
                
                # 默认认为成功
                return True, result_text
        
        # 如果没有内容，认为失败
        return False, "工具执行结果为空"
        
    except Exception as e:
        logger.error(f"[MaiAgent] 解析工具结果异常: {e}")
        return False, f"解析工具结果异常: {str(e)}"
    
    

def filter_action_tools(available_tools) -> List:
    """过滤工具，只保留动作类工具，排除查询类工具
    
    Args:
        available_tools: 所有可用的MCP工具列表
        
    Returns:
        过滤后的动作类工具列表
    """
    # 定义查询类工具名称（需要排除的工具）
    query_tool_names = {
        "query_game_state", # 查询游戏状态
        "query_player_status", # 查询玩家状态
        "query_recent_events", # 查询最近事件
        # "query_recipe", # 查询配方
        "query_surroundings", # 查询周围环境
    }
    
    filtered_tools = []
    
    for tool in available_tools:
        tool_name = tool.name.lower() if tool.name else ""
        
        # 如果工具名称在查询类工具列表中，则跳过
        if tool_name in query_tool_names:
            logger.debug(f"[MaiAgent] 排除查询类工具: {tool.name}")
            continue
        
        filtered_tools.append(tool)
    
    return filtered_tools


def _translate_block_name(block_name: str) -> str:
    """将英文方块名转换为中文
    
    Args:
        block_name: 英文方块名
        
    Returns:
        中文方块名
    """
    # 方块名称映射表
    block_name_mapping = {
        # 基础方块
        "stone": "石头",
        "dirt": "泥土",
        "grass": "草方块",
        "sand": "沙子",
        "gravel": "沙砾",
        "clay": "粘土",
        "soul_sand": "灵魂沙",
        "soul_soil": "灵魂土",
        
        # 矿物方块
        "coal_ore": "煤矿石",
        "iron_ore": "铁矿石",
        "gold_ore": "金矿石",
        "diamond_ore": "钻石矿石",
        "emerald_ore": "绿宝石矿石",
        "lapis_ore": "青金石矿石",
        "redstone_ore": "红石矿石",
        "copper_ore": "铜矿石",
        "deepslate_coal_ore": "深板岩煤矿石",
        "deepslate_iron_ore": "深板岩铁矿石",
        "deepslate_gold_ore": "深板岩金矿石",
        "deepslate_diamond_ore": "深板岩钻石矿石",
        "deepslate_emerald_ore": "深板岩绿宝石矿石",
        "deepslate_lapis_ore": "深板岩青金石矿石",
        "deepslate_redstone_ore": "深板岩红石矿石",
        "deepslate_copper_ore": "深板岩铜矿石",
        
        # 装饰方块
        "oak_log": "橡木原木",
        "spruce_log": "云杉原木",
        "birch_log": "白桦原木",
        "jungle_log": "丛林原木",
        "acacia_log": "金合欢原木",
        "dark_oak_log": "深色橡木原木",
        "mangrove_log": "红树木原木",
        "cherry_log": "樱花原木",
        "bamboo_block": "竹子块",
        
        # 树叶
        "oak_leaves": "橡木树叶",
        "spruce_leaves": "云杉树叶",
        "birch_leaves": "白桦树叶",
        "jungle_leaves": "丛林树叶",
        "acacia_leaves": "金合欢树叶",
        "dark_oak_leaves": "深色橡木树叶",
        "mangrove_leaves": "红树树叶",
        "cherry_leaves": "樱花树叶",
        "bamboo": "竹子",
        
        # 其他常见方块
        "cobblestone": "圆石",
        "mossy_cobblestone": "苔石",
        "stone_bricks": "石砖",
        "mossy_stone_bricks": "苔石砖",
        "cracked_stone_bricks": "裂纹石砖",
        "chiseled_stone_bricks": "錾制石砖",
        "granite": "花岗岩",
        "polished_granite": "磨制花岗岩",
        "diorite": "闪长岩",
        "polished_diorite": "磨制闪长岩",
        "andesite": "安山岩",
        "polished_andesite": "磨制安山岩",
        "netherrack": "下界岩",
        "basalt": "玄武岩",
        "polished_basalt": "磨制玄武岩",
        "blackstone": "黑石",
        "polished_blackstone": "磨制黑石",
        "end_stone": "末地石",
        "purpur_block": "紫珀块",
        "obsidian": "黑曜石",
        "bedrock": "基岩",
        "water": "水",
        "lava": "岩浆",
        "air": "空气",
        "cave_air": "洞穴空气",
        "void_air": "虚空空气",
    }
    
    # 返回中文名称，如果没有找到则返回原英文名称
    return block_name_mapping.get(block_name.lower(), block_name)