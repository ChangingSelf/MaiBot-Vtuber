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
        "query_state",      # 查询状态
        "query_events",     # 查询事件
        "get_state",        # 获取状态
        "get_events",       # 获取事件
        "list_players",     # 列出玩家
        "get_inventory",    # 获取物品栏
        "get_position",     # 获取位置
        "get_health",       # 获取生命值
        "get_hunger",       # 获取饥饿值
        "get_experience",   # 获取经验值
        "get_weather",      # 获取天气
        "get_time",         # 获取时间
        "get_biome",        # 获取生物群系
        "get_block_info",   # 获取方块信息
        "get_entity_info",  # 获取实体信息
    }
    
    # 定义动作类工具名称（需要保留的工具）
    action_tool_names = {
        "chat",             # 发送聊天消息
        "mine_block",       # 挖掘方块
        "place_block",      # 放置方块
        "craft_item",       # 合成物品
        "smelt_item",       # 熔炼物品
        "use_chest",        # 使用箱子
        "swim_to_land",     # 游向陆地
        "kill_mob",         # 击杀生物
        "follow_player",    # 跟随玩家
        "move_to",          # 移动到指定位置
        "jump",             # 跳跃
        "attack",           # 攻击
        "use_item",         # 使用物品
        "drop_item",        # 丢弃物品
        "pickup_item",      # 拾取物品
        "eat_food",         # 吃食物
        "sleep",            # 睡觉
        "open_door",        # 开门
        "close_door",       # 关门
        "break_block",      # 破坏方块
        "build_structure",  # 建造结构
        "plant_crop",       # 种植作物
        "harvest_crop",     # 收获作物
        "breed_animal",     # 繁殖动物
        "tame_animal",      # 驯服动物
    }
    
    filtered_tools = []
    
    for tool in available_tools:
        tool_name = tool.name.lower() if tool.name else ""
        
        # 如果工具名称在查询类工具列表中，则跳过
        if tool_name in query_tool_names:
            logger.debug(f"[MaiAgent] 排除查询类工具: {tool.name}")
            continue
        
        # 如果工具名称在动作类工具列表中，则保留
        if tool_name in action_tool_names:
            filtered_tools.append(tool)
            logger.debug(f"[MaiAgent] 保留动作类工具: {tool.name}")
            continue
        
        # 如果工具名称包含查询相关关键词，则排除
        query_keywords = ["query", "get", "list", "find", "search", "check", "inspect", "examine"]
        if any(keyword in tool_name for keyword in query_keywords):
            logger.debug(f"[MaiAgent] 排除查询类工具（关键词匹配）: {tool.name}")
            continue
        
        # 如果工具名称包含动作相关关键词，则保留
        action_keywords = ["mine", "place", "craft", "smelt", "use", "swim", "kill", "follow", "move", "jump", "attack", "drop", "pickup", "eat", "sleep", "open", "close", "break", "build", "plant", "harvest", "breed", "tame"]
        if any(keyword in tool_name for keyword in action_keywords):
            filtered_tools.append(tool)
            logger.debug(f"[MaiAgent] 保留动作类工具（关键词匹配）: {tool.name}")
            continue
        
        # 默认情况下，如果工具描述包含动作相关词汇，则保留
        if tool.description:
            action_desc_keywords = ["执行", "操作", "移动", "挖掘", "放置", "合成", "熔炼", "使用", "攻击", "建造", "种植", "收获"]
            if any(keyword in tool.description for keyword in action_desc_keywords):
                filtered_tools.append(tool)
                logger.debug(f"[MaiAgent] 保留动作类工具（描述匹配）: {tool.name}")
                continue
        
        # 如果都不匹配，则排除（保守策略）
        logger.debug(f"[MaiAgent] 排除未知类型工具: {tool.name}")
    
    return filtered_tools