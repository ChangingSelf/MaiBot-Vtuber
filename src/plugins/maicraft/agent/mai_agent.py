import asyncio
import json
import time
from datetime import datetime
from typing import Dict, List, Any, Optional
from langchain.agents import AgentExecutor
from langchain_openai import ChatOpenAI
from langchain_core.tools import BaseTool
from langchain.memory import ConversationBufferMemory
from src.utils.logger import get_logger
from ..chains.goal_proposal_chain import GoalProposalChain
from ..chains.memory_chain import MemoryChain
from ..chains.error_handling_chain import ErrorHandlingChain
from ..mcp.mcp_tool_adapter import MCPToolAdapter
from ..config import MaicraftConfig
from ..openai_client.llm_request import LLMClient
from .environment_updater import EnvironmentUpdater
from .environment import global_environment
from .prompt_manager.prompt_manager import prompt_manager
from .prompt_manager.template import init_templates
from .utils import parse_json, convert_mcp_tools_to_openai_format, parse_tool_result, filter_action_tools

class MaiAgent:
    def __init__(self, config: MaicraftConfig, mcp_client):
        self.config = config
        self.mcp_client = mcp_client
        self.logger = get_logger("MaiAgent")

        # 初始化LLM客户端
        self.llm_client: Optional[LLMClient] = None

        # 初始化LLM和工具适配器
        # 延迟初始化
        self.tools: Optional[List[BaseTool]] = None

        # 环境更新器
        self.environment_updater: Optional[EnvironmentUpdater] = None

        # 初始化状态
        self.initialized = False
        
        
        self.goal_list: list[tuple[str, bool]] = []
        
    async def initialize(self):
        """异步初始化"""
        try:
            self.logger.info("[MaiAgent] 开始初始化")
            
            init_templates()

            # 初始化LLM客户端
            self.llm_client = LLMClient(self.config)
            self.logger.info("[MaiAgent] LLM客户端初始化成功")

            # 创建并启动环境更新器
            self.environment_updater = EnvironmentUpdater(
                agent=self,
                update_interval=2,  # 默认5秒更新间隔
                auto_start=False  # 不自动启动，等初始化完成后再启动
            )

            # 启动环境更新器
            if self.environment_updater.start():
                self.logger.info("[MaiAgent] 环境更新器启动成功")
            else:
                self.logger.error("[MaiAgent] 环境更新器启动失败")

            self.initialized = True
            self.logger.info("[MaiAgent] 初始化完成")
            
            

        except Exception as e:
            self.logger.error(f"[MaiAgent] 初始化失败: {e}")
            raise
        
        
    async def run_loop(self):
        """
        运行主循环
        """
        while True:
            success, goal = await self.propose_next_goal()
            if not success:
                self.logger.error("[MaiAgent] 目标提议失败")
                continue
            
            steps, notes = await self.anaylze_goal(goal)
            if not steps:
                self.logger.error(f"[MaiAgent] 目标分解失败: {notes}")
                continue
            
            success, result = await self.execute_goal(goal=goal, steps=steps, notes=notes)
            self.goal_list.append((goal, success))
            if not success:
                self.logger.error(f"[MaiAgent] 目标执行失败: {result}")
                continue
            
            # self.goal_list.append((goal, success))
            
            self.logger.info(f"[MaiAgent] 目标执行成功: {result}")
            
    def format_executed_goals(self) -> str:
        """
        以更详细、结构化的方式格式化已执行目标列表
        """
        if not self.goal_list:
            return "无已执行目标"
        lines = []
        for idx, (goal, success) in enumerate(self.goal_list, 1):
            # status = "成功" if success else "失败"
            if success:
                lines.append(f"{idx}. 完成了目标：{goal}")
            else:
                lines.append(f"{idx}. 尝试目标：{goal}。但最终失败了，没有完成该目标")
        return "\n".join(lines)
    
    
    async def propose_next_goal(self) -> tuple[str, str]:
        self.logger.info("[MaiAgent] 开始提议下一个目标")
        environment_info = global_environment.get_summary()
        executed_goals = self.format_executed_goals()
        input_data = {
            "player_position": "当前游戏位置",
            "inventory": "当前物品栏",
            "environment": environment_info,
            "time_constraints": {"可用时间": "15-30分钟"},
            "current_resources": {"基于当前状态"},
            "executed_goals": executed_goals,
        }
        
        prompt = prompt_manager.generate_prompt("minecraft_goal_generation", **input_data)
        self.logger.info(f"[MaiAgent] 目标提议输入数据: {input_data}")
        self.logger.info(f"[MaiAgent] 目标提议提示词: {prompt}")
        
        response = await self.llm_client.simple_chat(prompt)
        self.logger.info(f"[MaiAgent] 目标提议响应: {response}")
        
        return True, response
        
        
    async def anaylze_goal(self, goal: str) -> tuple[list[str], str]:
        """
        将目标分解为可操作的步骤，以及注意事项
        返回: (步骤列表, 注意事项字符串)
        """
        #需要返回对目标的拆解
        #和额外的注意事项
        environment_info = global_environment.get_summary()
        input_data = {
            "goal": goal,
            "environment": environment_info,
        }
        prompt = prompt_manager.generate_prompt("minecraft_analyze_goal", **input_data)
        # self.logger.info(f"[MaiAgent] 目标拆解输入数据: {input_data}")
        self.logger.info(f"[MaiAgent] 目标拆解提示词: {prompt}")
        
        response = await self.llm_client.simple_chat(prompt)
        self.logger.info(f"[MaiAgent] 目标拆解响应: {response}")
        
        parsed_response = parse_json(response)
        if parsed_response is None:
            self.logger.error(f"[MaiAgent] 目标拆解响应解析失败: {response}")
            return [], ""
        
        steps = parsed_response.get("steps", [])
        notes = parsed_response.get("notes", "")
        
        
        return steps, notes
    
    
    async def execute_goal(self, goal: str, steps: list[str], notes: str):
        """
        执行目标
        返回: (执行结果, 执行状态)
        """
        try:
            # 获取所有可用的MCP工具
            available_tools = await self.mcp_client.get_tools_metadata()
            if not available_tools:
                self.logger.error("[MaiAgent] 没有可用的MCP工具")
                return False, "没有可用的MCP工具"
            
            self.logger.info(f"[MaiAgent] 获取到 {len(available_tools)} 个可用工具")
            
            # 过滤工具，只保留动作类工具，排除查询类工具
            action_tools = filter_action_tools(available_tools)
            self.logger.info(f"[MaiAgent] 过滤后可用动作工具: {len(action_tools)} 个")
            
            # 将MCP工具转换为OpenAI工具格式
            openai_tools = convert_mcp_tools_to_openai_format(action_tools)
            
            # 记录工具执行历史
            executed_tools_history = []
            
            done = False
            attempt = 0
            max_attempts = 10
            
            while not done and attempt < max_attempts:
                attempt += 1
                self.logger.info(f"[MaiAgent] 执行目标: {goal} 尝试 {attempt}/{max_attempts}")
                
                # 获取当前环境信息
                environment_info = global_environment.get_summary()
                
                # 构建已执行工具的历史记录字符串
                executed_tools_str = self._format_executed_tools_history(executed_tools_history)
                
                # 使用原有的提示词模板，但通过call_tool传入工具
                input_data = {
                    "goal": goal,
                    "all_steps": steps,
                    "environment": environment_info,
                    "executed_tools": executed_tools_str,
                }
                prompt = prompt_manager.generate_prompt("minecraft_excute_step", **input_data)
                self.logger.info(f"[MaiAgent] 执行步骤提示词: {prompt}")
                
                # 使用call_tool方法调用LLM，传入工具参数
                response = await self.llm_client.call_tool(
                    prompt=prompt,
                    tools=openai_tools,
                    system_message="你是一个Minecraft游戏助手，请选择合适的工具来执行游戏步骤。"
                )
                
                # self.logger.info(f"[MaiAgent] 执行步骤响应: {response}")
                
                if not response.get("success"):
                    self.logger.error(f"[MaiAgent] LLM调用失败: {response.get('error')}")
                    continue
                
                # 检查是否有工具调用
                response_content = response.get("content", "")
                self.logger.info(f"[MaiAgent] 使用了工具，想法: {response_content}")
                if "完成" in response_content:
                    done = True
                    break
                
                tool_calls = response.get("tool_calls", [])
                if tool_calls:
                    # 执行选中的工具
                    for tool_call in tool_calls:
                        tool_name = tool_call["function"]["name"]
                        tool_args = tool_call["function"]["arguments"]
                        
                        self.logger.info(f"[MaiAgent] 执行工具: {tool_name} 参数: {tool_args}")
                        
                        try:
                            # 解析工具参数
                            if isinstance(tool_args, str):
                                parsed_args = json.loads(tool_args)
                            else:
                                parsed_args = tool_args
                            
                            # 调用MCP工具
                            result = await self.mcp_client.call_tool_directly(tool_name, parsed_args)
                            
                            # 解析工具执行结果，判断是否真的成功
                            is_success, result_content = parse_tool_result(result)
                            
                            # 记录工具执行历史
                            tool_execution_record = {
                                "tool_name": tool_name,
                                "response": response_content,
                                "arguments": parsed_args,
                                "success": is_success,
                                "result": result_content,
                                "timestamp": time.time()
                            }
                            executed_tools_history.append(tool_execution_record)
                            
                            if not is_success:
                                self.logger.error(f"[MaiAgent] 工具执行失败: {result_content}")
                                continue
                            
                            self.logger.info(f"[MaiAgent] 工具执行成功: {result_content}")
                            
                        except Exception as e:
                            # 记录工具执行异常
                            tool_execution_record = {
                                "tool_name": tool_name,
                                "response": response_content,
                                "arguments": parsed_args,
                                "success": False,
                                "result": f"执行异常: {str(e)}",
                                "timestamp": time.time()
                            }
                            executed_tools_history.append(tool_execution_record)
                            
                            self.logger.error(f"[MaiAgent] 工具执行异常: {e}")
                            continue
                else:
                    # 如果没有工具调用，检查文本响应
                    content = response.get("content", "")
                    self.logger.info(f"[MaiAgent] 没有使用工具，产生想法: {content}")
                    
                    if "完成" in content:
                        done = True
                        break
                
                # 如果步骤未完成，等待一段时间再重试
                if not done:
                    await asyncio.sleep(2)
            
            if not done:
                self.logger.warning(f"[MaiAgent] 目标执行超时: {goal}")
                return False, f"目标执行超时: {goal}"
            
            self.logger.info("[MaiAgent] 所有步骤执行完成")
            return True, f"目标执行成功，最终想法：{response_content}"
            
        except Exception as e:
            self.logger.error(f"[MaiAgent] 目标执行异常: {e}")
            return False, f"执行异常: {str(e)}"
    

    
    def _format_executed_tools_history(self, executed_tools_history: List[Dict[str, Any]]) -> str:
        """格式化已执行工具的历史记录"""
        if not executed_tools_history:
            return "暂无已执行的工具"
        
        formatted_history = []
        for record in executed_tools_history:
            status = "成功" if record["success"] else "失败"
            timestamp = record["timestamp"]
            tool_name = record["tool_name"]
            arguments = record["arguments"]
            result = record["result"]
            response = record["response"]
            
            # 格式化参数
            if isinstance(arguments, dict):
                args_str = ", ".join([f"{k}={v}" for k, v in arguments.items()])
            else:
                args_str = str(arguments)
            
            # 格式化结果
            if hasattr(result, 'content') and result.content:
                result_text = ""
                for content in result.content:
                    if hasattr(content, 'text'):
                        result_text += content.text
                result_str = result_text
            else:
                result_str = str(result)
            
            # 将时间戳转换为可读格式（不是13位毫秒时间戳，直接按秒处理）
            readable_time = datetime.fromtimestamp(timestamp).strftime("%H:%M:%S")
                
            formatted_record = f"{readable_time}，你的想法：{response}你使用 {tool_name}({args_str})\n结果: {result_str}\n"
            formatted_history.append(formatted_record)
        
        return "\n".join(formatted_history)
            
    