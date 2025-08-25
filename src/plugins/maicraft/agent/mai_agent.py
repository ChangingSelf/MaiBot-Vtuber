import asyncio
import json
import time
from datetime import datetime
from typing import Dict, List, Any, Optional
from langchain_core.tools import BaseTool
from src.utils.logger import get_logger
from ..config import MaicraftConfig
from ..openai_client.llm_request import LLMClient
from .environment_updater import EnvironmentUpdater
from .environment import global_environment
from .prompt_manager.prompt_manager import prompt_manager
from .prompt_manager.template import init_templates
from .utils import parse_json, convert_mcp_tools_to_openai_format, parse_tool_result, filter_action_tools, format_executed_goals, extract_between
from .to_do_list import ToDoList


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
        
        
        self.goal_list: list[tuple[str, str, str]] = []  # (goal, status, details)
        
        
        self.to_do_list: ToDoList = ToDoList()
        
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
        
        
    async def run_plan_loop(self):
        """
        运行主循环
        """
        while True:
            success, goal = await self.propose_next_goal()
            if not success:
                self.logger.error("[MaiAgent] 目标提议失败")
                continue
            
            await self.propose_all_task(goal=goal, to_do_list=self.to_do_list, environment_info=global_environment.get_summary())
            while True:
                if self.to_do_list.check_if_all_done():
                    self.logger.info(f"[MaiAgent] 所有任务已完成，目标{goal}完成")
                    self.to_do_list.clear()
                    self.goal_list.append((goal, "done", "所有任务已完成"))
                    break
                
                if self.to_do_list.need_edit:
                    self.logger.info(f"[MaiAgent] 任务列表需要修改: {self.to_do_list.need_edit}")
                    self.goal_list.append((goal, "edit", self.to_do_list.need_edit))
                    self.to_do_list.need_edit = ""
                    break
                    
                await asyncio.sleep(1)
                
                
    
    
    async def run_execute_loop(self):
        """
        运行执行循环
        """
        while True:
            if len(self.to_do_list.items) == 0:
                await asyncio.sleep(1)
                continue
            
            choose_success, choose_result, details = await self.choose_next_task(to_do_list=self.to_do_list, environment_info=global_environment.get_summary())
            if not choose_success:            
                if choose_result == "edit":
                    self.logger.info(f"[MaiAgent] 任务列表需要修改: {details}")
                    self.to_do_list.need_edit = details
                    self.to_do_list.clear()
                else:
                    self.logger.error(f"[MaiAgent] 任务选择失败: {choose_result}")
                    await asyncio.sleep(5)
                    continue
            
            if choose_result == "done":
                task = self.to_do_list.get_task_by_id(details)
                if task is not None:
                    task.done = True
                    task.details = f"任务{details}已完成"
                    self.logger.info(f"[MaiAgent] 任务{details}已完成")
                    continue
                continue
            
            if choose_result == "do":
                success, result = await self.execute_next_task(details)
                if not success:
                    self.logger.error(f"[MaiAgent] 任务执行失败: {result}")
                    continue
                self.logger.info(f"[MaiAgent] 任务执行成功: {result}")
            
            
    
    async def propose_all_task(self, goal: str, to_do_list: ToDoList, environment_info: str) -> bool:
        self.logger.info("[MaiAgent] 开始提议任务")
        # 使用原有的提示词模板，但通过call_tool传入工具
        input_data = {
            "goal": goal,
            "environment": environment_info,
            "to_do_list": to_do_list.__str__(),
        }
        prompt = prompt_manager.generate_prompt("minecraft_to_do", **input_data)
        self.logger.info(f"[MaiAgent] 任务提议提示词: {prompt}")
        
        response = await self.llm_client.simple_chat(prompt)
        self.logger.info(f"[MaiAgent] 任务提议响应: {response}")
        
        tasks_list = parse_json(response)
        
        
        no_new_task = False
        for task in tasks_list:
            try:
                task_type = str(task.get("type", "")).strip().lower()
                if task_type == "none":
                    self.logger.info("[MaiAgent] 没有新任务需要添加")
                    no_new_task = True
                    break
                details = str(task.get("details", "")).strip()
                done_criteria = str(task.get("done_criteria", "")).strip()
                if not task_type or not details:
                    # 不完整任务，跳过
                    self.logger.warning(f"[MaiAgent] 跳过不完整任务: {task}")
                    continue
                self.to_do_list.add_task(type=task_type, details=details, done_criteria=done_criteria)
            except Exception as e:
                self.logger.error(f"[MaiAgent] 处理任务时异常: {e}，任务内容: {task}")
                continue
        
        return no_new_task
    
    
    async def propose_next_goal(self) -> tuple[str, str]:
        self.logger.info("[MaiAgent] 开始提议下一个目标")
        environment_info = global_environment.get_summary()
        executed_goals = format_executed_goals(self.goal_list)
        input_data = {
            "player_position": "当前游戏位置",
            "inventory": "当前物品栏",
            "environment": environment_info,
            "time_constraints": {"可用时间": "15-30分钟"},
            "current_resources": {"基于当前状态"},
            "executed_goals": executed_goals,
        }
        
        prompt = prompt_manager.generate_prompt("minecraft_goal_generation", **input_data)
        # self.logger.info(f"[MaiAgent] 目标提议输入数据: {input_data}")
        self.logger.info(f"[MaiAgent] 目标提议提示词: {prompt}")
        
        response = await self.llm_client.simple_chat(prompt)
        self.logger.info(f"[MaiAgent] 目标提议响应: {response}")
        
        return True, response

    async def choose_next_task(self, to_do_list: ToDoList, environment_info: str):
        """
        执行目标
        返回: (执行结果, 执行状态)
        """
        try:
            input_data = {
                "to_do_list": to_do_list.__str__(),
                "environment": environment_info,
            }
            prompt = prompt_manager.generate_prompt("minecraft_choose_task", **input_data)
            self.logger.info(f"[MaiAgent] 任务选择提示词: {prompt}")
            
            response = await self.llm_client.simple_chat(prompt)
            self.logger.info(f"[MaiAgent] 任务选择响应: {response}")

            # 解析响应，支持形如：
            # <修改：修改的原因>
            # <执行：执行的任务id>
            text = str(response) if response is not None else ""

            # 优先判断修改
            modification_reason = extract_between(text, "<修改：", "<修改:")
            if modification_reason is None and "<修改>" in text:
                modification_reason = ""
            if modification_reason is not None or "<修改>" in text:
                reason = modification_reason if modification_reason is not None else ""
                return False, "edit", reason

            # 判断执行
            execute_task_id = extract_between(text, "<执行：", "<执行:")
            if execute_task_id is None and "<执行>" in text:
                execute_task_id = ""
            if execute_task_id is not None or "<执行>" in text:
                task_id = execute_task_id if execute_task_id is not None else ""
                return True, "do", task_id
                
            # 判断完成
            done_task_id = extract_between(text, "<完成：", "<完成:")
            if done_task_id is None and "<完成>" in text:
                done_task_id = ""
            if done_task_id is not None or "<完成>" in text:
                task_id = done_task_id if done_task_id is not None else ""
                return True, "done", task_id

            # 兜底：无法解析
            self.logger.warning(f"[MaiAgent] 无法从响应中解析任务选择结果: {text}")
            return False, "edit", "无法解析任务选择结果"
        except Exception as e:
            self.logger.error(f"[MaiAgent] 任务选择解析异常: {e}")
            return False, "edit", f"解析异常: {str(e)}"


    
    async def execute_next_task(self, id: str) -> tuple[bool, str]:
        """
        执行目标
        返回: (执行结果, 执行状态)
        """
        try:
            task = self.to_do_list.get_task_by_id(id)
            
            if task is None:
                self.logger.error(f"[MaiAgent] 任务不存在: {id}")
                return False, "任务不存在"
            
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
            max_attempts = 20
            
            while not done and attempt < max_attempts:
                attempt += 1
                self.logger.info(f"[MaiAgent] 执行任务: {task} 尝试 {attempt}/{max_attempts}")
                
                # 获取当前环境信息
                environment_info = global_environment.get_summary()
                
                # 构建已执行工具的历史记录字符串
                executed_tools_str = self._format_executed_tools_history(executed_tools_history)
                
                # 使用原有的提示词模板，但通过call_tool传入工具
                input_data = {
                    "task": task.__str__(),
                    "environment": environment_info,
                    "executed_tools": executed_tools_str,
                }
                prompt = prompt_manager.generate_prompt("minecraft_excute_task", **input_data)
                self.logger.info(f"[MaiAgent] 执行任务提示词: {prompt}")
                
                # 使用call_tool方法调用LLM，传入工具参数
                response = await self.llm_client.call_tool(
                    prompt=prompt,
                    tools=openai_tools,
                    system_message="你是一个Minecraft游戏助手，请选择合适的工具来执行游戏步骤。"
                )
                
                
                if not response.get("success"):
                    self.logger.error(f"[MaiAgent] LLM调用失败: {response.get('error')}")
                    continue
                
                # 检查是否有工具调用
                response_content = response.get("content", "")
                self.logger.info(f"[MaiAgent] 任务想法: {response_content}")
                # 如果想法中包含可修复的JSON，解析并更新任务进度
                try:
                    parsed = parse_json(response_content) if isinstance(response_content, str) else None
                    if isinstance(parsed, dict):
                        if "progress" in parsed:
                            task.progress = str(parsed.get("progress"))
                        if "done" in parsed:
                            task.done = bool(parsed.get("done"))
                except Exception as e:
                    self.logger.warning(f"[MaiAgent] 解析任务进度JSON失败: {e}")
                
                
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
                    # 同样尝试解析并更新任务进度
                    try:
                        parsed_no_tool = parse_json(content) if isinstance(content, str) else None
                        if isinstance(parsed_no_tool, dict):
                            if "progress" in parsed_no_tool:
                                task.progress = str(parsed_no_tool.get("progress"))
                            if "done" in parsed_no_tool:
                                task.done = bool(parsed_no_tool.get("done"))
                    except Exception as e:
                        self.logger.warning(f"[MaiAgent] 解析无工具响应JSON失败: {e}")

                if task.done:
                    done = True
                    return True, f"任务执行成功: {task.__str__()}"
            
            if not done:
                self.logger.warning(f"[MaiAgent] 任务执行超时: {task.__str__()}")
                return False, f"任务执行超时: {task.__str__()}"

            
        except Exception as e:
            self.logger.error(f"[MaiAgent] 任务执行异常: {e}")
            return False, f"任务执行异常: {str(e)}"
    

    
    def _format_executed_tools_history(self, executed_tools_history: List[Dict[str, Any]]) -> str:
        """格式化已执行工具的历史记录"""
        if not executed_tools_history:
            return "暂无已执行的工具"
        
        formatted_history = []
        for record in executed_tools_history:
            # status 变量不再使用，保留逻辑可读性但避免未使用告警
            _ = "成功" if record["success"] else "失败"
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
                # 根据工具类型使用专门的翻译函数
                if tool_name == "move":
                    result_str = self._translate_move_tool_result(result, arguments)
                elif tool_name == "query_recipe":
                    result_str = self._translate_query_recipe_tool_result(result)
                elif tool_name == "craft_item":
                    result_str = self._translate_craft_item_tool_result(result)
                elif tool_name == "mine_block":
                    result_str = self._translate_mine_block_tool_result(result)
                else:
                    result_str = str(result)
            
            # 将时间戳转换为可读格式（不是13位毫秒时间戳，直接按秒处理）
            readable_time = datetime.fromtimestamp(timestamp).strftime("%H:%M:%S")
                
            formatted_record = f"{readable_time}，你的想法：{response}你使用 {tool_name}({args_str})\n结果: {result_str}\n"
            formatted_history.append(formatted_record)
        
        return "\n".join(formatted_history)
            
    
    def _translate_move_tool_result(self, result: Any, arguments: Any = None) -> str:
        """
        翻译move工具的执行结果，使其更可读
        
        Args:
            result: move工具的执行结果
            arguments: 工具调用参数，用于提供更准确的错误信息
            
        Returns:
            翻译后的可读文本
        """
        try:
            # 如果结果是字符串，尝试解析JSON
            if isinstance(result, str):
                try:
                    result_data = json.loads(result)
                except json.JSONDecodeError:
                    return str(result)
            else:
                result_data = result
            
            # 检查是否是move工具的结果
            if not isinstance(result_data, dict):
                return str(result)
            
            # 提取关键信息
            ok = result_data.get("ok", False)
            data = result_data.get("data", {})
            
            if not ok:
                # 处理移动失败的情况
                error_msg = result_data.get("error", "")
                if "MOVE_FAILED" in error_msg:
                    if "Took to long to decide path to goal" in error_msg:
                        # 根据工具参数提供更准确的错误信息
                        if arguments and isinstance(arguments, dict):
                            if "block" in arguments:
                                block_name = arguments["block"]
                                return f"移动失败: 这附近没有{block_name}"
                            elif "type" in arguments and arguments["type"] == "coordinate":
                                return "移动失败: 无法到达指定坐标"
                        return "移动失败: 这附近没有目标方块"
                    else:
                        return f"移动失败: {error_msg}"
                else:
                    return f"移动失败: {error_msg}"
            
            # 提取移动信息
            target = data.get("target", "")
            distance = data.get("distance", 0)
            position = data.get("position", {})
            
            # 格式化位置信息
            x = position.get("x", 0)
            y = position.get("y", 0)
            z = position.get("z", 0)
            
            # 构建可读文本
            readable_text = f"成功移动到坐标 ({x}, {y}, {z})"
            
            if target:
                readable_text += f"，目标：{target}"
            
            if distance is not None:
                readable_text += f"，距离目标：{distance} 格"
            
            return readable_text
            
        except Exception:
            # 如果解析失败，返回原始结果
            return str(result)
    
    def _translate_query_recipe_tool_result(self, result: Any) -> str:
        """
        翻译query_recipe工具的执行结果，使其更可读
        
        Args:
            result: query_recipe工具的执行结果
            
        Returns:
            翻译后的可读文本
        """
        try:
            # 如果结果是字符串，尝试解析JSON
            if isinstance(result, str):
                try:
                    result_data = json.loads(result)
                except json.JSONDecodeError:
                    return str(result)
            else:
                result_data = result
            
            # 检查是否是query_recipe工具的结果
            if not isinstance(result_data, dict):
                return str(result)
            
            # 提取关键信息
            ok = result_data.get("ok", False)
            data = result_data.get("data", [])
            
            if not ok:
                return "查询配方失败"
            
            # 处理配方数据
            if not data:
                return "没有找到该物品的配方"
            
            # 构建可读文本
            readable_text = "找到以下配方：\n"
            
            for i, recipe in enumerate(data, 1):
                if isinstance(recipe, list):
                    ingredients = []
                    for ingredient in recipe:
                        if isinstance(ingredient, dict):
                            name = ingredient.get("name", "未知物品")
                            count = ingredient.get("count", 1)
                            ingredients.append(f"{count}个{name}")
                    
                    if ingredients:
                        readable_text += f"配方{i}: {', '.join(ingredients)}\n"
            
            return readable_text.strip()
            
        except Exception:
            # 如果解析失败，返回原始结果
            return str(result)
    
    def _translate_craft_item_tool_result(self, result: Any) -> str:
        """
        翻译craft_item工具的执行结果，使其更可读
        
        Args:
            result: craft_item工具的执行结果
            
        Returns:
            翻译后的可读文本
        """
        try:
            # 如果结果是字符串，尝试解析JSON
            if isinstance(result, str):
                try:
                    result_data = json.loads(result)
                except json.JSONDecodeError:
                    return str(result)
            else:
                result_data = result
            
            # 检查是否是craft_item工具的结果
            if not isinstance(result_data, dict):
                return str(result)
            
            # 提取关键信息
            ok = result_data.get("ok", False)
            data = result_data.get("data", {})
            
            if not ok:
                return "合成物品失败"
            
            # 提取合成信息
            item_name = data.get("item", "未知物品")
            count = data.get("count", 1)
            
            # 构建可读文本
            if count == 1:
                readable_text = f"成功合成1个{item_name}"
            else:
                readable_text = f"成功合成{count}个{item_name}"
            
            return readable_text
            
        except Exception:
            # 如果解析失败，返回原始结果
            return str(result)
    
    def _translate_mine_block_tool_result(self, result: Any) -> str:
        """
        翻译mine_block工具的执行结果，使其更可读
        
        Args:
            result: mine_block工具的执行结果
            
        Returns:
            翻译后的可读文本
        """
        try:
            # 如果结果是字符串，尝试解析JSON
            if isinstance(result, str):
                try:
                    result_data = json.loads(result)
                except json.JSONDecodeError:
                    return str(result)
            else:
                result_data = result
            
            # 检查是否是mine_block工具的结果
            if not isinstance(result_data, dict):
                return str(result)
            
            # 提取关键信息
            ok = result_data.get("ok", False)
            data = result_data.get("data", {})
            
            if not ok:
                return "挖掘方块失败"
            
            # 检查是否有挖掘数据
            if "minedCount" in data:
                mined_count = data["minedCount"]
                block_name = data.get("blockName", "未知方块")

                
                # 构建可读文本
                if mined_count == 1:
                    readable_text = f"成功挖掘了1个{block_name}"
                else:
                    readable_text = f"成功挖掘了{mined_count}个{block_name}"
                
                return readable_text
            else:
                # 如果没有挖掘数据，返回原始结果
                return str(result)
            
        except Exception:
            # 如果解析失败，返回原始结果
            return str(result)
    
    def _extract_modification_reason(self, response_content: str) -> str:
        """
        从响应内容中提取目标修改的原因
        
        Args:
            response_content: LLM的响应内容
            
        Returns:
            提取的修改原因
        """
        try:
            if "<修改：" in response_content:
                # 找到<修改：标记的位置
                start_pos = response_content.find("<修改：")
                if start_pos != -1:
                    # 找到对应的结束标记
                    end_pos = response_content.find(">", start_pos)
                    if end_pos != -1:
                        # 提取修改原因（去掉<修改：和>标记）
                        reason = response_content[start_pos + 4:end_pos].strip()
                        return reason
            
            # 如果没有找到标准格式，返回原始内容
            return response_content
            
        except Exception:
            # 如果提取失败，返回原始内容
            return response_content