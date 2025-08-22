from typing import Dict, Any, List, Optional
from langchain_core.runnables import Runnable, RunnablePassthrough
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from .base import BaseChain
from src.utils.logger import get_logger


class ErrorHandlingChain(BaseChain):
    """错误处理链：错误检测 -> 错误恢复 -> 错误报告"""

    def __init__(self, llm: ChatOpenAI):
        super().__init__("ErrorHandling")
        self.llm = llm
        self.logger = get_logger("ErrorHandlingChain")

    def build(self) -> Runnable:
        """构建错误处理LCEL链"""
        try:
            # 错误检测模板
            error_detector = ChatPromptTemplate.from_template("""
            检测和分析错误信息。
            
            错误信息: {error_message}
            错误类型: {error_type}
            错误上下文: {error_context}
            执行历史: {execution_history}
            
            请分析错误:
            1. 错误严重程度 (低/中/高/严重)
            2. 错误原因分析
            3. 影响范围评估
            4. 错误分类
            
            返回错误分析:
            {{
                "severity": "错误严重程度",
                "root_cause": "根本原因",
                "impact_scope": "影响范围",
                "error_category": "错误分类",
                "error_summary": "错误总结"
            }}
            """)

            # 错误恢复模板
            error_recovery = ChatPromptTemplate.from_template("""
            制定错误恢复策略。
            
            错误分析: {error_analysis}
            可用资源: {available_resources}
            系统状态: {system_state}
            
            请制定恢复策略:
            1. 立即恢复措施
            2. 长期修复方案
            3. 预防措施
            4. 回退方案
            
            返回恢复策略:
            {{
                "immediate_actions": ["立即执行的操作"],
                "long_term_fixes": ["长期修复方案"],
                "prevention_measures": ["预防措施"],
                "fallback_plan": "回退方案",
                "recovery_priority": "恢复优先级"
            }}
            """)

            # 错误报告模板
            error_reporter = ChatPromptTemplate.from_template("""
            生成错误报告和用户通知。
            
            错误分析: {error_analysis}
            恢复策略: {recovery_strategy}
            用户影响: {user_impact}
            
            请生成:
            1. 技术错误报告
            2. 用户友好通知
            3. 状态更新
            4. 后续行动建议
            
            返回错误报告:
            {{
                "technical_report": "技术错误报告",
                "user_notification": "用户友好通知",
                "status_update": "状态更新",
                "next_actions": ["后续行动"],
                "report_priority": "报告优先级"
            }}
            """)

            # 构建LCEL链
            chain = (
                RunnablePassthrough.assign(error_analysis=error_detector | self.llm)
                | RunnablePassthrough.assign(recovery_strategy=error_recovery | self.llm)
                | RunnablePassthrough.assign(error_report=error_reporter | self.llm)
                | (
                    lambda x: {
                        "error_handling_result": x["error_report"],
                        "error_analysis": x["error_analysis"],
                        "recovery_strategy": x["recovery_strategy"],
                    }
                )
            )

            self.logger.info("[错误处理链] LCEL链构建完成")
            return chain

        except Exception as e:
            self.logger.error(f"[错误处理链] 构建LCEL链失败: {e}")
            # 返回简单的传递链作为后备
            return RunnablePassthrough()

    async def execute(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """执行错误处理"""
        try:
            self.logger.info(f"[错误处理链] 开始执行错误处理")

            # 准备输入数据
            chain_input = {
                "error_message": input_data.get("error_message", ""),
                "error_type": input_data.get("error_type", "unknown"),
                "error_context": input_data.get("error_context", {}),
                "execution_history": input_data.get("execution_history", []),
                "available_resources": input_data.get("available_resources", {}),
                "system_state": input_data.get("system_state", {}),
                "user_impact": input_data.get("user_impact", "unknown"),
            }

            # 获取链并执行
            chain = self.get_chain()
            result = await chain.ainvoke(chain_input)

            # 记录执行日志
            self.log_execution(input_data, result)

            return result

        except Exception as e:
            self.logger.error(f"[错误处理链] 执行失败: {e}")
            return {
                "success": False,
                "error": str(e),
                "error_handling_result": {
                    "technical_report": f"错误处理链执行失败: {e}",
                    "user_notification": "系统错误处理出现问题",
                    "status_update": "错误处理失败",
                    "next_actions": ["重启系统", "检查日志"],
                    "report_priority": "高",
                },
            }

    def handle_specific_error(self, error_type: str, error_data: Dict[str, Any]) -> Dict[str, Any]:
        """处理特定类型的错误"""
        try:
            self.logger.info(f"[错误处理链] 处理特定错误: {error_type}")

            # 根据错误类型选择处理策略
            if error_type == "tool_execution_error":
                return self._handle_tool_error(error_data)
            elif error_type == "llm_error":
                return self._handle_llm_error(error_data)
            elif error_type == "memory_error":
                return self._handle_memory_error(error_data)
            elif error_type == "network_error":
                return self._handle_network_error(error_data)
            else:
                return self._handle_generic_error(error_data)

        except Exception as e:
            self.logger.error(f"[错误处理链] 处理特定错误失败: {e}")
            return {"success": False, "error": str(e), "error_type": "error_handling_failure"}

    def _handle_tool_error(self, error_data: Dict[str, Any]) -> Dict[str, Any]:
        """处理工具执行错误"""
        return {
            "success": False,
            "error_type": "tool_execution_error",
            "recovery_action": "retry_with_fallback",
            "user_message": "工具执行出现问题，正在尝试替代方案",
        }

    def _handle_llm_error(self, error_data: Dict[str, Any]) -> Dict[str, Any]:
        """处理LLM错误"""
        return {
            "success": False,
            "error_type": "llm_error",
            "recovery_action": "retry_with_different_model",
            "user_message": "AI处理出现问题，正在尝试其他方案",
        }

    def _handle_memory_error(self, error_data: Dict[str, Any]) -> Dict[str, Any]:
        """处理记忆错误"""
        return {
            "success": False,
            "error_type": "memory_error",
            "recovery_action": "clear_and_rebuild_memory",
            "user_message": "记忆系统出现问题，正在重新初始化",
        }

    def _handle_network_error(self, error_data: Dict[str, Any]) -> Dict[str, Any]:
        """处理网络错误"""
        return {
            "success": False,
            "error_type": "network_error",
            "recovery_action": "retry_with_backoff",
            "user_message": "网络连接出现问题，正在重试",
        }

    def _handle_generic_error(self, error_data: Dict[str, Any]) -> Dict[str, Any]:
        """处理通用错误"""
        return {
            "success": False,
            "error_type": "generic_error",
            "recovery_action": "log_and_continue",
            "user_message": "系统出现问题，正在处理",
        }
