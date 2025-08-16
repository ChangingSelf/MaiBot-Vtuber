from typing import Dict, List, Any, Optional
from langchain.agents import AgentExecutor, create_react_agent
from langchain_openai import ChatOpenAI
from langchain_core.tools import BaseTool
from langchain.memory import ConversationBufferMemory
from langchain_core.prompts import ChatPromptTemplate
from src.utils.logger import get_logger
from ..chains.base import BaseChain
from ..chains.task_planning_chain import TaskPlanningChain
from ..chains.goal_proposal_chain import GoalProposalChain
from ..chains.memory_chain import MemoryChain
from ..chains.error_handling_chain import ErrorHandlingChain
from ..mcp.mcp_tool_adapter import MCPToolAdapter
from ..config import MaicraftConfig


class MaicraftAgent:
    """基于LangChain Agent的Minecraft Agent（简化版）"""

    def __init__(self, config: MaicraftConfig, mcp_client):
        self.config = config
        self.mcp_client = mcp_client
        self.logger = get_logger("MaicraftAgent")

        # 初始化LLM和工具适配器
        self.llm = self._create_llm()
        self.tool_adapter = MCPToolAdapter(mcp_client, self.config.error_detection.model_dump())

        # 延迟初始化
        self.tools: Optional[List[BaseTool]] = None
        self.agent_executor: Optional[AgentExecutor] = None
        self.memory: Optional[ConversationBufferMemory] = None

        # LCEL链组件
        self.task_planning_chain: Optional[TaskPlanningChain] = None
        self.goal_proposal_chain: Optional[GoalProposalChain] = None
        self.memory_chain: Optional[MemoryChain] = None
        self.error_handling_chain: Optional[ErrorHandlingChain] = None

        # 初始化状态
        self.initialized = False

    def _create_llm(self) -> ChatOpenAI:
        """创建LLM实例"""
        try:
            llm_config = self.config.llm

            # 创建LLM实例
            llm = ChatOpenAI(
                model=llm_config.model,
                temperature=llm_config.temperature,
                api_key=llm_config.api_key,
                base_url=llm_config.base_url,
            )

            self.logger.info(f"[MaicraftAgent] LLM创建成功: {llm_config.model}")
            return llm

        except Exception as e:
            self.logger.error(f"[MaicraftAgent] LLM创建失败: {e}")
            raise

    async def initialize(self):
        """异步初始化"""
        try:
            self.logger.info("[MaicraftAgent] 开始初始化")

            # 获取工具
            self.tools = await self.tool_adapter.create_langchain_tools()
            self.logger.info(f"[MaicraftAgent] 获取到 {len(self.tools)} 个工具")

            # 创建记忆
            self.memory = ConversationBufferMemory(memory_key="chat_history", return_messages=True)
            self.logger.info("[MaicraftAgent] 记忆创建成功")

            # 创建LCEL链
            await self._create_chains()

            # 创建Agent执行器
            await self._create_agent_executor()

            self.initialized = True
            self.logger.info("[MaicraftAgent] 初始化完成")

        except Exception as e:
            self.logger.error(f"[MaicraftAgent] 初始化失败: {e}")
            raise

    async def _create_chains(self):
        """创建LCEL链"""
        try:
            # 创建任务规划链
            self.task_planning_chain = TaskPlanningChain(self.llm, self.tools)
            self.logger.info("[MaicraftAgent] 任务规划链创建成功")

            # 创建目标提议链
            self.goal_proposal_chain = GoalProposalChain(self.llm)
            self.logger.info("[MaicraftAgent] 目标提议链创建成功")

            # 创建记忆管理链
            self.memory_chain = MemoryChain(self.llm, self.memory)
            self.logger.info("[MaicraftAgent] 记忆管理链创建成功")

            # 创建错误处理链
            self.error_handling_chain = ErrorHandlingChain(self.llm)
            self.logger.info("[MaicraftAgent] 错误处理链创建成功")

        except Exception as e:
            self.logger.error(f"[MaicraftAgent] 创建LCEL链失败: {e}")
            raise

    async def _create_agent_executor(self):
        """创建Agent执行器"""
        try:
            # 确保工具列表不为空
            if not self.tools:
                raise ValueError("没有可用的工具")

            self.logger.info(f"[MaicraftAgent] 创建Agent，可用工具: {[tool.name for tool in self.tools]}")

            # 使用LangChain内置的Agent创建方法
            from langchain.agents import initialize_agent, AgentType

            # 创建Agent执行器（使用LangChain内置的Agent创建方法）
            self.agent_executor = initialize_agent(
                tools=self.tools,
                llm=self.llm,
                agent=AgentType.ZERO_SHOT_REACT_DESCRIPTION,
                verbose=self.config.langchain.verbose,
                handle_parsing_errors=self.config.langchain.handle_parsing_errors,
                max_iterations=self.config.agent.max_steps,
                memory=self.memory,
            )

            self.logger.info("[MaicraftAgent] Agent执行器创建成功")

        except Exception as e:
            self.logger.error(f"[MaicraftAgent] 创建Agent执行器失败: {e}")
            raise

    async def plan_and_execute(self, user_input: str) -> Dict[str, Any]:
        """规划并执行任务（使用AgentExecutor调用工具）"""
        try:
            if not self.initialized:
                raise RuntimeError("Agent未初始化")

            self.logger.info(f"[MaicraftAgent] 开始规划并执行任务: {user_input}")

            # 使用AgentExecutor执行任务（这会实际调用工具）
            if not self.agent_executor:
                raise RuntimeError("Agent执行器未初始化")

            result = await self.agent_executor.ainvoke({"input": user_input, "chat_history": self.get_chat_history()})

            # 格式化结果
            formatted_result = {
                "success": True,
                "task_planning_result": {
                    "summary": f"成功执行任务: {user_input}",
                    "user_response": result.get("output", "任务执行完成"),
                    "status_update": "任务完成",
                    "success": True,
                },
                "execution_details": {
                    "actions_taken": result.get("intermediate_steps", []),
                    "result": result.get("output", ""),
                    "next_steps": [],
                },
                "raw_result": result,
            }

            # 更新记忆
            await self._update_memory(user_input, formatted_result)

            self.logger.info("[MaicraftAgent] 任务执行完成")
            return formatted_result

        except Exception as e:
            self.logger.error(f"[MaicraftAgent] 任务执行失败: {e}")
            # 使用错误处理链处理错误
            error_result = await self._handle_error(e, user_input)
            return error_result

    async def propose_next_goal(self) -> Optional[str]:
        """提议下一个目标"""
        try:
            if not self.initialized:
                return None

            self.logger.info("[MaicraftAgent] 开始提议下一个目标")

            # 准备输入数据（使用默认的游戏状态）
            input_data = {
                "game_state": "Minecraft生存模式",
                "player_position": "出生点附近",
                "inventory": "基础工具和材料",
                "environment": "平原或森林环境",
                "recent_activities": ["刚刚开始游戏"],
                "player_preferences": {"探索": "高", "建造": "中", "收集": "高"},
                "time_constraints": {"可用时间": "15-30分钟"},
                "current_resources": {"木材": "少量", "石头": "少量", "食物": "基础"},
            }

            # 使用目标提议链生成目标
            result = await self.goal_proposal_chain.execute(input_data)

            # 检查是否有目标提议结果（包括备用目标）
            if "goal_proposal_result" in result:
                goal_result = result["goal_proposal_result"]
                if "feasible_goals" in goal_result and goal_result["feasible_goals"]:
                    recommended_goal = goal_result["feasible_goals"][0]["goal"]
                    success_status = result.get("success", False)
                    if success_status:
                        self.logger.info(f"[MaicraftAgent] 提议目标: {recommended_goal}")
                    else:
                        self.logger.info(f"[MaicraftAgent] 使用备用目标: {recommended_goal}")
                    return recommended_goal

            self.logger.warning("[MaicraftAgent] 未能生成合适的目标")
            return None

        except Exception as e:
            self.logger.error(f"[MaicraftAgent] 目标提议失败: {e}")
            return None

    def get_chat_history(self) -> List[str]:
        """获取聊天历史"""
        try:
            if self.memory_chain:
                return self.memory_chain.get_chat_history()
            return []
        except Exception as e:
            self.logger.error(f"[MaicraftAgent] 获取聊天历史失败: {e}")
            return []

    def clear_memory(self):
        """清除记忆"""
        try:
            if self.memory_chain:
                self.memory_chain.clear_memory()
            self.logger.info("[MaicraftAgent] 记忆已清除")
        except Exception as e:
            self.logger.error(f"[MaicraftAgent] 清除记忆失败: {e}")

    async def _update_memory(self, user_input: str, result: Dict[str, Any]):
        """更新记忆"""
        try:
            if self.memory_chain:
                memory_data = {
                    "current_memory": "",
                    "new_information": f"用户输入: {user_input}, 执行结果: {result}",
                    "memory_type": "task_execution",
                    "memory_limits": {"max_tokens": self.config.langchain.max_token_limit},
                }
                await self.memory_chain.execute(memory_data)
        except Exception as e:
            self.logger.error(f"[MaicraftAgent] 更新记忆失败: {e}")

    async def _handle_error(self, error: Exception, user_input: str) -> Dict[str, Any]:
        """处理错误"""
        try:
            error_data = {
                "error_message": str(error),
                "error_type": type(error).__name__,
                "error_context": {"user_input": user_input},
                "execution_history": [],
                "available_resources": {},
                "system_state": {"initialized": self.initialized},
                "user_impact": "任务执行失败",
            }

            result = await self.error_handling_chain.execute(error_data)
            return result

        except Exception as e:
            self.logger.error(f"[MaicraftAgent] 错误处理失败: {e}")
            return {"success": False, "error": str(error), "user_response": "系统出现错误，请稍后重试"}
