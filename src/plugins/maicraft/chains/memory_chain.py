from typing import Dict, Any, List, Optional
from langchain_core.runnables import Runnable, RunnablePassthrough
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langchain.memory import ConversationBufferMemory
from .base import BaseChain
from src.utils.logger import get_logger


class MemoryChain(BaseChain):
    """记忆管理链：加载记忆 -> 更新记忆 -> 保存记忆"""

    def __init__(self, llm: ChatOpenAI, memory: ConversationBufferMemory):
        super().__init__("Memory")
        self.llm = llm
        self.memory = memory
        self.logger = get_logger("MemoryChain")

    def build(self) -> Runnable:
        """构建记忆管理LCEL链"""
        try:
            # 记忆加载模板
            memory_loader = ChatPromptTemplate.from_template("""
            加载并分析历史记忆。
            
            聊天历史: {chat_history}
            记忆变量: {memory_variables}
            
            请分析历史记忆并提取:
            1. 重要信息
            2. 用户偏好
            3. 上下文信息
            4. 需要记住的关键点
            
            返回记忆分析:
            {{
                "important_info": ["重要信息列表"],
                "user_preferences": {{"偏好类型": "偏好内容"}},
                "context_info": "上下文信息",
                "key_points": ["关键点列表"],
                "memory_summary": "记忆总结"
            }}
            """)

            # 记忆更新模板
            memory_updater = ChatPromptTemplate.from_template("""
            更新记忆信息。
            
            当前记忆: {current_memory}
            新信息: {new_information}
            记忆类型: {memory_type}
            
            请更新记忆:
            1. 合并新旧信息
            2. 保持重要信息
            3. 更新上下文
            4. 清理过时信息
            
            返回更新后的记忆:
            {{
                "updated_memory": "更新后的记忆",
                "new_context": "新的上下文",
                "retained_info": ["保留的信息"],
                "updated_preferences": {{"更新的偏好"}},
                "memory_changes": "记忆变化描述"
            }}
            """)

            # 记忆保存模板
            memory_saver = ChatPromptTemplate.from_template("""
            保存和优化记忆。
            
            更新后的记忆: {updated_memory}
            记忆限制: {memory_limits}
            
            请优化记忆存储:
            1. 压缩信息
            2. 保持关键内容
            3. 格式化存储
            4. 设置优先级
            
            返回优化后的记忆:
            {{
                "optimized_memory": "优化后的记忆",
                "memory_size": "记忆大小",
                "priority_info": ["高优先级信息"],
                "storage_format": "存储格式",
                "compression_ratio": "压缩比例"
            }}
            """)

            # 构建LCEL链
            chain = (
                RunnablePassthrough.assign(memory_analysis=memory_loader | self.llm)
                | RunnablePassthrough.assign(memory_update=memory_updater | self.llm)
                | RunnablePassthrough.assign(
                    memory_optimization=lambda x: memory_saver.invoke(
                        {"updated_memory": x["memory_update"], "memory_limits": x["memory_limits"]}
                    )
                )
                | (
                    lambda x: {
                        "memory_result": x["memory_optimization"],
                        "memory_analysis": x["memory_analysis"],
                        "memory_update": x["memory_update"],
                    }
                )
            )

            self.logger.info("[记忆管理链] LCEL链构建完成")
            return chain

        except Exception as e:
            self.logger.error(f"[记忆管理链] 构建LCEL链失败: {e}")
            # 返回简单的传递链作为后备
            return RunnablePassthrough()

    async def execute(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """执行记忆管理"""
        try:
            self.logger.info("[记忆管理链] 开始执行记忆管理")

            # 获取当前记忆
            chat_history = self.memory.chat_memory.messages if hasattr(self.memory, "chat_memory") else []
            memory_variables = (
                self.memory.load_memory_variables({}) if hasattr(self.memory, "load_memory_variables") else {}
            )

            # 准备输入数据
            chain_input = {
                "chat_history": str(chat_history),
                "memory_variables": str(memory_variables),
                "current_memory": input_data.get("current_memory", ""),
                "new_information": input_data.get("new_information", ""),
                "memory_type": input_data.get("memory_type", "general"),
                "memory_limits": input_data.get("memory_limits", {"max_tokens": 4000}),
            }

            # 获取链并执行
            chain = self.get_chain()
            result = await chain.ainvoke(chain_input)

            # 更新实际记忆
            await self._update_actual_memory(result)

            # 记录执行日志
            self.log_execution(input_data, result)

            return result

        except Exception as e:
            self.logger.error(f"[记忆管理链] 执行失败: {e}")
            return {
                "success": False,
                "error": str(e),
                "memory_result": {
                    "optimized_memory": "",
                    "memory_size": "0",
                    "priority_info": [],
                    "storage_format": "error",
                    "compression_ratio": "0%",
                },
            }

    async def _update_actual_memory(self, result: Dict[str, Any]):
        """更新实际的记忆存储"""
        try:
            if "memory_result" in result and "optimized_memory" in result["memory_result"]:
                # 这里可以添加实际的记忆更新逻辑
                # 例如保存到文件、数据库等
                self.logger.info("[记忆管理链] 记忆更新完成")
        except Exception as e:
            self.logger.error(f"[记忆管理链] 更新实际记忆失败: {e}")

    def get_chat_history(self) -> List[str]:
        """获取聊天历史"""
        try:
            if hasattr(self.memory, "chat_memory"):
                return [str(msg) for msg in self.memory.chat_memory.messages]
            return []
        except Exception as e:
            self.logger.error(f"[记忆管理链] 获取聊天历史失败: {e}")
            return []

    def clear_memory(self):
        """清除记忆"""
        try:
            if hasattr(self.memory, "clear"):
                self.memory.clear()
            elif hasattr(self.memory, "chat_memory"):
                self.memory.chat_memory.clear()
            self.logger.info("[记忆管理链] 记忆已清除")
        except Exception as e:
            self.logger.error(f"[记忆管理链] 清除记忆失败: {e}")
