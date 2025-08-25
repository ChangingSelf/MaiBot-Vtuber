import json
from json_repair import repair_json
from typing import List, Dict, Any, Optional
from loguru import logger

def parse_json(text: str) -> dict:
    """解析json字符串"""
    try:
        repaired_json = repair_json(text)
        return json.loads(repaired_json)
    except json.JSONDecodeError:
        return None
    
    
# 统一处理全角/半角冒号
def extract_between(text: str, prefix_full: str, prefix_half: str, closing: str = ">") -> Optional[str]:
    start = -1
    use_full = False
    if prefix_full in text:
        start = text.find(prefix_full)
        use_full = True
    elif prefix_half in text:
        start = text.find(prefix_half)
        use_full = False
    if start == -1:
        return None
    end = text.find(closing, start)
    if end == -1:
        # 若无闭合符，取到文本末尾
        end = len(text)
    offset = len(prefix_full) if use_full else len(prefix_half)
    return text[start + offset:end].strip()
    
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
        "query_recipe", # 查询配方
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

def format_executed_goals(goal_list: list[tuple[str, str, str]]) -> str:
    """
    以更详细、结构化的方式格式化已执行目标列表
    """
    if not goal_list:
        return "无已执行目标"
    
    lines = []
    for idx, (goal, status, details) in enumerate(goal_list, 1):
        if status == "done":
            lines.append(f"{idx}. 完成了目标：{goal}")
            if details and "目标执行成功" in details:
                # 提取成功时的想法
                if "最终想法：" in details:
                    final_thought = details.split("最终想法：")[-1]
                    lines.append(f"   想法：{final_thought}")
        elif status == "edit":
            lines.append(f"{idx}. 目标需要修改：{goal}")
            lines.append(f"   原因：{details}")
        elif status == "fail":
            lines.append(f"{idx}. 目标执行失败：{goal}")
            lines.append(f"   原因：{details}")
    
    return "\n".join(lines)

def parse_tag(text: str) -> List[tuple[str, str]]:
    """
    解析字符串中所有的[xxxx:xxxx]标记对，只解析最外层的标记
    
    Args:
        text: 输入字符串
        
    Returns:
        包含(标记名, 标记值)元组的列表
        
    Example:
        >>> parse_tag("Hello [name:John] and [age:25]")
        [('name', 'John'), ('age', '25')]
        >>> parse_tag("Hello [outer:[inner:value]]")
        [('outer', '[inner:value]')]
    """
    import re
    
    # 使用栈来匹配最外层的括号，只解析最外层的[xxxx:xxxx]格式
    result = []
    stack = []
    start = -1
    
    for i, char in enumerate(text):
        if char == '[':
            if not stack:  # 这是最外层的左括号
                start = i
            stack.append(char)
        elif char == ']':
            if stack:  # 有对应的左括号
                stack.pop()
                if not stack and start != -1:  # 这是最外层的右括号
                    # 提取最外层的标记内容
                    content = text[start + 1:i]
                    # 检查是否包含冒号（标记格式）
                    if ':' in content:
                        # 分割标记名和标记值
                        parts = content.split(':', 1)
                        if len(parts) == 2:
                            tag_name = parts[0].strip()
                            tag_value = parts[1].strip()
                            result.append((tag_name, tag_value))
                    start = -1
    
    return result
