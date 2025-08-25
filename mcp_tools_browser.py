#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MCP工具浏览器脚本
用于获取和浏览现有的MCP工具及其参数信息
"""

import asyncio
import json
import sys
import os
from typing import Dict, List, Any, Optional
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

try:
    from src.plugins.maicraft.mcp.client import MCPClient
    from src.plugins.maicraft.mcp.mcp_tool_adapter import MCPToolAdapter
    from src.plugins.maicraft.config import MaicraftConfig
    from src.utils.logger import get_logger
except ImportError as e:
    print(f"导入错误: {e}")
    print("请确保在项目根目录下运行此脚本")
    sys.exit(1)


class MCPToolsBrowser:
    """MCP工具浏览器类"""
    
    def __init__(self):
        self.logger = get_logger("MCPToolsBrowser")
        self.mcp_client: Optional[MCPClient] = None
        self.tool_adapter: Optional[MCPToolAdapter] = None
        self.connected = False
        
    async def connect(self) -> bool:
        """连接到MCP服务器"""
        try:
            # 创建默认配置
            config = {
                "mcpServers": {
                    "maicraft": {
                        "command": "npx",
                        "args": [
                            "-y",
                            "maicraft@latest",
                            "--host",
                            "127.0.0.1",
                            "--port",
                            "25565",
                            "--username",
                            "Mai",
                            "--auth",
                            "offline"
                        ]
                    }
                }
            }
            
            self.mcp_client = MCPClient(config)
            self.connected = await self.mcp_client.connect()
            
            if self.connected:
                # 创建工具适配器
                error_detection_config = {
                    "mode": "full_json",
                    "error_keys": {"success": False, "ok": False, "error": True, "failed": True},
                    "error_message_keys": ["error_message", "error", "message", "reason"],
                    "error_code_keys": ["error_code", "code", "status_code"],
                }
                self.tool_adapter = MCPToolAdapter(self.mcp_client, error_detection_config)
                self.logger.info("成功连接到MCP服务器")
                return True
            else:
                self.logger.error("连接MCP服务器失败")
                return False
                
        except Exception as e:
            self.logger.error(f"连接过程中发生错误: {e}")
            return False
    
    async def disconnect(self):
        """断开MCP连接"""
        if self.mcp_client and self.connected:
            await self.mcp_client.disconnect()
            self.connected = False
            self.logger.info("已断开MCP连接")
    
    async def get_tools_info(self) -> List[Dict[str, Any]]:
        """获取所有MCP工具的详细信息"""
        if not self.connected or not self.mcp_client:
            return []
        
        try:
            # 获取工具元数据
            tools_metadata = await self.mcp_client.get_tools_metadata()
            if not tools_metadata:
                return []
            
            tools_info = []
            for tool in tools_metadata:
                tool_info = {
                    "name": tool.name,
                    "description": tool.description or "无描述",
                    "input_schema": tool.inputSchema or {},
                    "properties": {},
                    "required_fields": [],
                    "optional_fields": [],
                    "examples": []
                }
                
                # 解析输入模式
                if tool.inputSchema:
                    schema = tool.inputSchema
                    properties = schema.get("properties", {})
                    required_fields = schema.get("required", [])
                    
                    tool_info["properties"] = properties
                    tool_info["required_fields"] = required_fields
                    tool_info["optional_fields"] = [k for k in properties.keys() if k not in required_fields]
                    
                    # 生成示例参数
                    examples = self._generate_examples(properties, required_fields)
                    tool_info["examples"] = examples
                
                tools_info.append(tool_info)
            
            return tools_info
            
        except Exception as e:
            self.logger.error(f"获取工具信息失败: {e}")
            return []
    
    def _generate_examples(self, properties: Dict[str, Any], required_fields: List[str]) -> List[Dict[str, Any]]:
        """生成参数示例"""
        examples = []
        
        # 生成最小参数示例（只包含必需字段）
        if required_fields:
            min_example = {}
            for field in required_fields:
                if field in properties:
                    field_info = properties[field]
                    field_type = field_info.get("type", "string")
                    default_value = field_info.get("default")
                    
                    if default_value is not None:
                        min_example[field] = default_value
                    else:
                        min_example[field] = self._get_type_example(field_type)
            
            examples.append({
                "type": "最小参数（必需字段）",
                "params": min_example
            })
        
        # 生成完整参数示例（包含所有字段）
        if properties:
            full_example = {}
            for field, field_info in properties.items():
                field_type = field_info.get("type", "string")
                default_value = field_info.get("default")
                
                if default_value is not None:
                    full_example[field] = default_value
                else:
                    full_example[field] = self._get_type_example(field_type)
            
            examples.append({
                "type": "完整参数（所有字段）",
                "params": full_example
            })
        
        return examples
    
    def _get_type_example(self, field_type: str) -> Any:
        """根据字段类型生成示例值"""
        type_examples = {
            "string": "示例字符串",
            "integer": 42,
            "number": 3.14,
            "boolean": True,
            "array": ["示例1", "示例2"],
            "object": {"key": "value"}
        }
        return type_examples.get(field_type, "示例值")
    
    def display_tools_summary(self, tools_info: List[Dict[str, Any]]):
        """显示工具概览"""
        print("\n" + "="*80)
        print("MCP工具概览")
        print("="*80)
        print(f"总工具数量: {len(tools_info)}")
        
        if not tools_info:
            print("没有找到可用的MCP工具")
            return
        
        # 按类型分类工具
        query_tools = []
        action_tools = []
        
        for tool in tools_info:
            name = tool["name"].lower()
            if any(keyword in name for keyword in ["query", "get", "list", "find", "search"]):
                query_tools.append(tool)
            else:
                action_tools.append(tool)
        
        print(f"查询类工具: {len(query_tools)} 个")
        print(f"动作类工具: {len(action_tools)} 个")
        
        # 显示工具名称列表
        print("\n工具名称列表:")
        print("-" * 40)
        for i, tool in enumerate(tools_info, 1):
            tool_type = "查询" if tool in query_tools else "动作"
            print(f"{i:2d}. [{tool_type}] {tool['name']}")
    
    def display_tool_details(self, tool_info: Dict[str, Any]):
        """显示单个工具的详细信息"""
        print(f"\n{'='*60}")
        print(f"工具: {tool_info['name']}")
        print(f"{'='*60}")
        print(f"描述: {tool_info['description']}")
        
        # 显示参数信息
        properties = tool_info["properties"]
        required_fields = tool_info["required_fields"]
        optional_fields = tool_info["optional_fields"]
        
        if properties:
            print(f"\n参数信息:")
            print(f"必需参数 ({len(required_fields)} 个):")
            for field in required_fields:
                if field in properties:
                    self._display_field_info(field, properties[field], True)
            
            if optional_fields:
                print(f"\n可选参数 ({len(optional_fields)} 个):")
                for field in optional_fields:
                    if field in properties:
                        self._display_field_info(field, properties[field], False)
        else:
            print("\n参数信息: 无参数")
        
        # 显示示例
        examples = tool_info["examples"]
        if examples:
            print(f"\n参数示例:")
            for i, example in enumerate(examples, 1):
                print(f"\n{i}. {example['type']}:")
                params_json = json.dumps(example['params'], ensure_ascii=False, indent=2)
                print(f"   {params_json}")
    
    def _display_field_info(self, field_name: str, field_info: Dict[str, Any], is_required: bool):
        """显示字段信息"""
        field_type = field_info.get("type", "unknown")
        field_desc = field_info.get("description", "")
        default_value = field_info.get("default")
        
        required_mark = "[必需]" if is_required else "[可选]"
        print(f"  - {field_name} ({field_type}) {required_mark}")
        
        if field_desc:
            print(f"    描述: {field_desc}")
        
        if default_value is not None and not is_required:
            print(f"    默认值: {default_value}")
    
    def display_interactive_menu(self, tools_info: List[Dict[str, Any]]):
        """显示交互式菜单"""
        while True:
            print("\n" + "-"*60)
            print("MCP工具浏览器 - 交互式菜单")
            print("-"*60)
            print("1. 显示工具概览")
            print("2. 浏览所有工具详细信息")
            print("3. 搜索工具")
            print("4. 按名称或编号查看工具")
            print("5. 导出工具信息到JSON文件")
            print("6. 退出")
            print("-"*60)
            
            try:
                choice = input("请选择操作 (1-6): ").strip()
                
                if choice == "1":
                    self.display_tools_summary(tools_info)
                
                elif choice == "2":
                    self.browse_all_tools(tools_info)
                
                elif choice == "3":
                    self.search_tools(tools_info)
                
                elif choice == "4":
                    self.view_tool_by_name_or_id(tools_info)
                
                elif choice == "5":
                    self.export_tools_to_json(tools_info)
                
                elif choice == "6":
                    print("退出MCP工具浏览器")
                    break
                
                else:
                    print("无效选择，请输入1-6之间的数字")
                    
            except KeyboardInterrupt:
                print("\n\n用户中断，退出程序")
                break
            except Exception as e:
                print(f"操作过程中发生错误: {e}")
    
    def browse_all_tools(self, tools_info: List[Dict[str, Any]]):
        """浏览所有工具"""
        if not tools_info:
            print("没有可用的工具")
            return
        
        print(f"\n开始浏览 {len(tools_info)} 个工具...")
        
        for i, tool_info in enumerate(tools_info, 1):
            self.display_tool_details(tool_info)
            
            if i < len(tools_info):
                try:
                    input("\n按回车键继续查看下一个工具...")
                except KeyboardInterrupt:
                    print("\n用户中断浏览")
                    break
    
    def search_tools(self, tools_info: List[Dict[str, Any]]):
        """搜索工具"""
        if not tools_info:
            print("没有可用的工具")
            return
        
        search_term = input("请输入搜索关键词: ").strip().lower()
        if not search_term:
            print("搜索关键词不能为空")
            return
        
        matching_tools = []
        for tool in tools_info:
            # 在工具名称、描述和参数中搜索
            if (search_term in tool["name"].lower() or 
                search_term in tool["description"].lower() or
                any(search_term in field.lower() for field in tool["properties"].keys())):
                matching_tools.append(tool)
        
        if matching_tools:
            print(f"\n找到 {len(matching_tools)} 个匹配的工具:")
            for tool in matching_tools:
                print(f"  - {tool['name']}: {tool['description']}")
            
            # 显示详细信息
            for tool in matching_tools:
                self.display_tool_details(tool)
                try:
                    input("\n按回车键继续查看下一个匹配的工具...")
                except KeyboardInterrupt:
                    print("\n用户中断浏览")
                    break
        else:
            print(f"没有找到包含关键词 '{search_term}' 的工具")
    
    def view_tool_by_name_or_id(self, tools_info: List[Dict[str, Any]]):
        """按名称或编号查看工具详细信息"""
        if not tools_info:
            print("没有可用的工具")
            return
        
        while True:
            print(f"\n{'='*60}")
            print("按名称或编号查看工具")
            print(f"{'='*60}")
            print("支持以下输入方式:")
            print("1. 工具编号 (1-{})".format(len(tools_info)))
            print("2. 工具名称 (完整或部分)")
            print("3. 输入 'list' 显示所有工具列表")
            print("4. 输入 'back' 返回主菜单")
            print("5. 输入 'help' 显示帮助信息")
            print("-" * 60)
            
            # 显示工具列表供参考
            print("可用工具列表:")
            for i, tool in enumerate(tools_info, 1):
                tool_type = "查询" if any(keyword in tool["name"].lower() for keyword in ["query", "get", "list", "find", "search"]) else "动作"
                print(f"  {i:2d}. [{tool_type}] {tool['name']}")
            
            print("-" * 60)
            
            try:
                user_input = input("请输入工具编号、名称或命令: ").strip()
                
                if user_input.lower() == 'back':
                    print("返回主菜单...")
                    break
                elif user_input.lower() == 'list':
                    self.display_tools_summary(tools_info)
                    continue
                elif user_input.lower() == 'help':
                    self._show_view_tool_help()
                    continue
                elif not user_input:
                    print("❌ 输入不能为空，请重新输入")
                    continue
                
                # 尝试按编号查找
                if user_input.isdigit():
                    tool_id = int(user_input)
                    if 1 <= tool_id <= len(tools_info):
                        tool_info = tools_info[tool_id - 1]
                        print(f"\n✅ 找到工具 (编号 {tool_id}):")
                        self.display_tool_details(tool_info)
                        
                        # 询问是否继续查看其他工具
                        if not self._ask_continue_viewing():
                            break
                    else:
                        print(f"❌ 无效的工具编号，请输入 1-{len(tools_info)} 之间的数字")
                        continue
                
                # 按名称查找
                else:
                    matching_tools = self._find_tools_by_name(tools_info, user_input)
                    
                    if len(matching_tools) == 1:
                        # 只有一个匹配项，直接显示
                        tool_info = matching_tools[0]
                        print(f"\n✅ 找到工具: {tool_info['name']}")
                        self.display_tool_details(tool_info)
                        
                        # 询问是否继续查看其他工具
                        if not self._ask_continue_viewing():
                            break
                            
                    elif len(matching_tools) > 1:
                        # 多个匹配项，让用户选择
                        print(f"\n🔍 找到 {len(matching_tools)} 个匹配的工具:")
                        
                        # 显示匹配统计
                        query_count = sum(1 for tool in matching_tools if any(keyword in tool["name"].lower() for keyword in ["query", "get", "list", "find", "search"]))
                        action_count = len(matching_tools) - query_count
                        print(f"📊 匹配统计: 查询类 {query_count} 个, 动作类 {action_count} 个")
                        
                        for i, tool in enumerate(matching_tools, 1):
                            tool_type = "查询" if any(keyword in tool["name"].lower() for keyword in ["query", "get", "list", "find", "search"]) else "动作"
                            print(f"  {i}. [{tool_type}] {tool['name']}")
                        
                        choice_input = input("\n请选择要查看的工具编号: ").strip()
                        if choice_input.isdigit():
                            choice_id = int(choice_input)
                            if 1 <= choice_id <= len(matching_tools):
                                selected_tool = matching_tools[choice_id - 1]
                                print(f"\n✅ 查看工具: {selected_tool['name']}")
                                self.display_tool_details(selected_tool)
                                
                                # 询问是否继续查看其他工具
                                if not self._ask_continue_viewing():
                                    break
                            else:
                                print(f"❌ 无效的选择，请输入 1-{len(matching_tools)} 之间的数字")
                        else:
                            print("❌ 请输入有效的数字")
                            
                    else:
                        print(f"❌ 未找到名称包含 '{user_input}' 的工具")
                        print("💡 提示:")
                        print("  - 检查拼写是否正确")
                        print("  - 尝试使用部分名称")
                        print("  - 使用 'list' 命令查看所有可用工具")
                        print("  - 使用 'help' 命令查看帮助信息")
                        print(f"  - 当前共有 {len(tools_info)} 个可用工具")
                        continue
                        
            except KeyboardInterrupt:
                print("\n\n用户中断操作")
                break
            except Exception as e:
                print(f"❌ 操作过程中发生错误: {e}")
                continue
    
    def _show_view_tool_help(self):
        """显示查看工具的帮助信息"""
        print("\n" + "="*50)
        print("查看工具帮助信息")
        print("="*50)
        print("📋 支持的输入格式:")
        print("  • 数字: 直接输入工具编号 (如: 1, 5, 10)")
        print("  • 名称: 输入工具名称 (如: query_state, chat)")
        print("  • 部分名称: 输入名称的一部分 (如: query, mine)")
        print("  • 命令: 特殊命令")
        print("\n🔧 特殊命令:")
        print("  • list: 显示所有工具列表")
        print("  • back: 返回主菜单")
        print("  • help: 显示此帮助信息")
        print("\n💡 使用技巧:")
        print("  • 工具编号是最快的查找方式")
        print("  • 名称搜索支持模糊匹配")
        print("  • 可以连续查看多个工具")
        print("  • 随时可以返回主菜单")
        print("  • 支持中文输入 (是/否)")
        print("\n🚀 快速访问:")
        print("  • 输入 '1' 快速查看第一个工具")
        print("  • 输入 'query' 查找所有查询类工具")
        print("  • 输入 'mine' 查找挖掘相关工具")
        print("="*50)
    
    def _ask_continue_viewing(self) -> bool:
        """询问是否继续查看其他工具"""
        while True:
            try:
                continue_input = input("\n是否继续查看其他工具? (y/n): ").strip().lower()
                if continue_input in ['y', 'yes', '是', '']:
                    return True
                elif continue_input in ['n', 'no', '否']:
                    return False
                else:
                    print("请输入 y/是 或 n/否")
            except KeyboardInterrupt:
                print("\n用户中断，返回主菜单")
                return False
    
    def _find_tools_by_name(self, tools_info: List[Dict[str, Any]], search_term: str) -> List[Dict[str, Any]]:
        """根据名称查找工具（支持部分匹配和智能搜索）"""
        search_term = search_term.lower().strip()
        matching_tools = []
        
        # 精确匹配优先
        exact_matches = []
        # 部分匹配
        partial_matches = []
        # 描述匹配
        desc_matches = []
        
        for tool in tools_info:
            tool_name = tool["name"].lower()
            tool_desc = tool["description"].lower()
            
            # 精确匹配
            if search_term == tool_name:
                exact_matches.append(tool)
            # 开头匹配
            elif tool_name.startswith(search_term):
                partial_matches.append(tool)
            # 包含匹配
            elif search_term in tool_name:
                partial_matches.append(tool)
            # 描述匹配
            elif search_term in tool_desc:
                desc_matches.append(tool)
        
        # 按优先级排序：精确匹配 > 开头匹配 > 包含匹配 > 描述匹配
        matching_tools = exact_matches + partial_matches + desc_matches
        
        return matching_tools
    
    def export_tools_to_json(self, tools_info: List[Dict[str, Any]]):
        """导出工具信息到JSON文件"""
        if not tools_info:
            print("没有可用的工具信息可导出")
            return
        
        filename = input("请输入导出文件名 (默认: mcp_tools_info.json): ").strip()
        if not filename:
            filename = "mcp_tools_info.json"
        
        if not filename.endswith('.json'):
            filename += '.json'
        
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(tools_info, f, ensure_ascii=False, indent=2)
            print(f"工具信息已成功导出到: {filename}")
        except Exception as e:
            print(f"导出失败: {e}")


async def main():
    """主函数"""
    print("MCP工具浏览器启动中...")
    
    browser = MCPToolsBrowser()
    
    try:
        # 连接到MCP服务器
        print("正在连接MCP服务器...")
        if not await browser.connect():
            print("连接MCP服务器失败，请检查:")
            print("1. Minecraft服务器是否正在运行")
            print("2. 是否开启了局域网模式（端口25565）")
            print("3. Maicraft MCP服务器是否已启动")
            return
        
        # 获取工具信息
        print("正在获取MCP工具信息...")
        tools_info = await browser.get_tools_info()
        
        if not tools_info:
            print("没有找到可用的MCP工具")
            return
        
        # 显示工具概览
        browser.display_tools_summary(tools_info)
        
        # 显示交互式菜单
        browser.display_interactive_menu(tools_info)
        
    except Exception as e:
        print(f"程序运行过程中发生错误: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        # 断开连接
        await browser.disconnect()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n程序被用户中断")
    except Exception as e:
        print(f"程序启动失败: {e}")
        import traceback
        traceback.print_exc()
