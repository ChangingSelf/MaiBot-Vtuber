from typing import Dict, Any, List
from langchain_core.runnables import Runnable, RunnablePassthrough
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langchain_core.tools import BaseTool
from .base import BaseChain
from src.utils.logger import get_logger


class TaskPlanningChain(BaseChain):
    """任务规划链：输入预处理 -> Agent执行 -> 输出后处理"""

    def __init__(self, llm: ChatOpenAI, tools: List[BaseTool]):
        super().__init__("TaskPlanning")
        self.llm = llm
        self.tools = tools
        self.logger = get_logger("TaskPlanningChain")

    def build(self) -> Runnable:
        """构建任务规划LCEL链"""
        try:
            # 输入预处理模板
            input_preprocessor = ChatPromptTemplate.from_template("""
            你是一个Minecraft游戏助手。请分析用户输入并提取关键信息。
            
            用户输入: {user_input}
            聊天历史: {chat_history}
            
            请提取以下信息:
            1. 主要任务目标
            2. 任务类型 (移动/建造/收集/战斗/其他)
            3. 关键参数 (位置/物品/数量等)
            4. 优先级 (高/中/低)
            
            以JSON格式返回:
            {{
                "task_goal": "任务目标",
                "task_type": "任务类型",
                "key_parameters": {{}},
                "priority": "优先级",
                "original_input": "原始输入"
            }}
            """)

            # 任务执行模板
            task_executor = ChatPromptTemplate.from_template("""
            你是一个Minecraft游戏助手。根据任务信息执行相应的操作。
            
            任务信息: {task_info}
            可用工具: {available_tools}
            
            请选择合适的工具并执行任务。如果任务需要多个步骤，请分步执行。
            
            返回执行结果:
            {{
                "success": true/false,
                "actions_taken": ["执行的操作列表"],
                "result": "执行结果描述",
                "next_steps": ["后续步骤建议"]
            }}
            """)

            # 输出后处理模板
            output_processor = ChatPromptTemplate.from_template("""
            请将执行结果格式化为用户友好的响应。
            
            执行结果: {execution_result}
            原始任务: {original_task}
            
            请生成:
            1. 简洁的执行总结
            2. 用户友好的回复
            3. 状态更新
            
            返回格式:
            {{
                "summary": "执行总结",
                "user_response": "用户回复",
                "status_update": "状态更新",
                "success": true/false
            }}
            """)

            # 构建LCEL链
            chain = (
                RunnablePassthrough.assign(
                    task_info=input_preprocessor | self.llm,
                    available_tools=lambda x: [tool.name for tool in self.tools],
                )
                | RunnablePassthrough.assign(execution_result=task_executor | self.llm)
                | RunnablePassthrough.assign(
                    final_result=lambda x: output_processor.invoke(
                        {
                            "execution_result": x["execution_result"],
                            "original_task": x["user_input"],  # 传递原始任务
                        }
                    )
                )
                | (
                    lambda x: {
                        "task_planning_result": x["final_result"],
                        "execution_details": x["execution_result"],
                        "task_info": x["task_info"],
                    }
                )
            )

            self.logger.info("[任务规划链] LCEL链构建完成")
            return chain

        except Exception as e:
            self.logger.error(f"[任务规划链] 构建LCEL链失败: {e}")
            # 返回简单的传递链作为后备
            return RunnablePassthrough()

    async def execute(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """执行任务规划"""
        try:
            self.logger.info("[任务规划链] 开始执行任务规划")

            # 准备输入数据
            chain_input = {
                "user_input": input_data.get("user_input", ""),
                "chat_history": input_data.get("chat_history", []),
                "context": input_data.get("context", {}),
            }

            # 获取链并执行
            chain = self.get_chain()
            result = await chain.ainvoke(chain_input)

            # 记录执行日志
            self.log_execution(input_data, result)

            return result

        except Exception as e:
            self.logger.error(f"[任务规划链] 执行失败: {e}")
            return {
                "success": False,
                "error": str(e),
                "task_planning_result": {
                    "summary": "任务规划失败",
                    "user_response": "抱歉，任务规划出现错误",
                    "status_update": "系统错误",
                    "success": False,
                },
            }
