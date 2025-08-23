#!/usr/bin/env python3
"""
测试MaiAgent的工具执行历史记录功能
"""

def test_format_executed_tools_history():
    """测试工具执行历史记录格式化功能"""
    
    # 模拟工具执行历史记录
    executed_tools_history = [
        {
            "tool_name": "mine_block",
            "arguments": {"block_type": "stone", "count": 5},
            "success": True,
            "result": "成功挖掘了5个石头",
            "timestamp": 1234567890.123
        },
        {
            "tool_name": "place_block",
            "arguments": {"block_type": "dirt", "position": "x:10,y:64,z:20"},
            "success": False,
            "result": "放置方块失败：位置无效",
            "timestamp": 1234567890.456
        },
        {
            "tool_name": "craft_item",
            "arguments": {"item": "wooden_pickaxe"},
            "success": True,
            "result": "成功合成了木制镐子",
            "timestamp": 1234567890.789
        }
    ]
    
    # 模拟MaiAgent类的_format_executed_tools_history方法
    def format_executed_tools_history(history):
        if not history:
            return "暂无已执行的工具"
        
        formatted_history = []
        for record in history:
            status = "成功" if record["success"] else "失败"
            tool_name = record["tool_name"]
            arguments = record["arguments"]
            result = record["result"]
            
            # 格式化参数
            if isinstance(arguments, dict):
                args_str = ", ".join([f"{k}={v}" for k, v in arguments.items()])
            else:
                args_str = str(arguments)
            
            # 格式化结果
            result_str = str(result)[:100] + "..." if len(str(result)) > 100 else str(result)
            
            formatted_record = f"工具: {tool_name}({args_str}) - {status} - 结果: {result_str}"
            formatted_history.append(formatted_record)
        
        return "\n".join(formatted_history)
    
    # 测试格式化功能
    formatted_result = format_executed_tools_history(executed_tools_history)
    
    print("=== 工具执行历史记录格式化测试 ===")
    print("原始数据:")
    for record in executed_tools_history:
        print(f"  - {record}")
    
    print("\n格式化结果:")
    print(formatted_result)
    
    # 验证结果
    expected_lines = [
        "工具: mine_block(block_type=stone, count=5) - 成功 - 结果: 成功挖掘了5个石头",
        "工具: place_block(block_type=dirt, position=x:10,y:64,z:20) - 失败 - 结果: 放置方块失败：位置无效",
        "工具: craft_item(item=wooden_pickaxe) - 成功 - 结果: 成功合成了木制镐子"
    ]
    
    print("\n验证结果:")
    for i, expected in enumerate(expected_lines):
        if expected in formatted_result:
            print(f"  ✓ 第{i+1}行匹配成功")
        else:
            print(f"  ✗ 第{i+1}行匹配失败")
            print(f"    期望: {expected}")
            print(f"    实际: {formatted_result.split('\\n')[i] if i < len(formatted_result.split('\\n')) else 'N/A'}")

if __name__ == "__main__":
    test_format_executed_tools_history()
