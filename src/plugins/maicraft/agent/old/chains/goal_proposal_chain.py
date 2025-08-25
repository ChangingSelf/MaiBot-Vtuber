from typing import Dict, Any, List
from langchain_core.runnables import Runnable, RunnablePassthrough
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from .base import BaseChain
from src.utils.logger import get_logger
import random


class GoalProposalChain(BaseChain):
    """目标提议链：生成简单的游戏目标"""

    def __init__(self, llm: ChatOpenAI):
        super().__init__("GoalProposal")
        self.llm = llm
        self.logger = get_logger("GoalProposalChain")

        # 预定义的备用目标
        self.fallback_goals = [
            "探索周围环境，寻找资源",
            "收集木材和石头",
            "建造一个简单的庇护所",
            "寻找食物和水源",
            "制作基础工具",
            "挖掘一个简单的矿洞",
            "种植一些农作物",
            "驯养一些动物",
            "探索附近的洞穴",
            "建造一个农场",
            "制作更高级的工具",
            "寻找矿物资源",
            "建造一个更大的房子",
            "制作武器和防具",
            "探索更远的地方",
        ]

    def _generate_fallback_goal(self, game_state: str) -> str:
        """根据游戏状态生成备用目标"""
        try:
            # 根据游戏状态选择合适的目标
            if "生存" in game_state or "开始" in game_state:
                # 早期游戏目标
                early_goals = [
                    "探索周围环境，寻找资源",
                    "收集木材和石头",
                    "建造一个简单的庇护所",
                    "寻找食物和水源",
                    "制作基础工具",
                ]
                return random.choice(early_goals)
            elif "建造" in game_state or "发展" in game_state:
                # 中期游戏目标
                mid_goals = ["建造一个更大的房子", "制作更高级的工具", "种植一些农作物", "驯养一些动物", "建造一个农场"]
                return random.choice(mid_goals)
            else:
                # 默认目标
                return random.choice(self.fallback_goals)
        except Exception as e:
            self.logger.error(f"生成备用目标失败: {e}")
            return "探索周围环境"

    def build(self) -> Runnable:
        """构建简化的目标提议LCEL链"""
        try:
            # 简化的目标生成模板
            goal_generator = ChatPromptTemplate.from_template("""
            你是一个Minecraft游戏助手。请为玩家生成一个简单可行的游戏目标。
            
            当前信息:
            - 游戏状态: {game_state}
            - 玩家位置: {player_position}
            - 库存: {inventory}
            - 环境: {environment}
            
            请生成一个简单、具体、可执行的目标。目标应该：
            1. 简单明确（一句话描述）
            2. 可立即执行
            3. 不需要复杂资源
            4. 5-15分钟内可完成
            
            直接返回目标描述，不要JSON格式，不要复杂分析：
            """)

            # 构建简化的LCEL链
            chain = RunnablePassthrough.assign(simple_goal=goal_generator | self.llm) | (
                lambda x: {
                    "success": True,
                    "goal_proposal_result": {
                        "feasible_goals": [
                            {
                                "goal": x["simple_goal"].content.strip()
                                if hasattr(x["simple_goal"], "content")
                                else str(x["simple_goal"]).strip(),
                                "feasibility_score": 0.8,
                                "requirements_met": True,
                                "estimated_success_rate": "高",
                                "estimated_time": "5-15分钟",
                            }
                        ],
                        "overall_recommendation": "建议执行上述目标",
                        "risk_assessment": "低风险",
                    },
                    "simple_goal": x["simple_goal"],
                }
            )

            self.logger.info("[目标提议链] 简化LCEL链构建完成")
            return chain

        except Exception as e:
            self.logger.error(f"[目标提议链] 构建LCEL链失败: {e}")
            # 返回简单的传递链作为后备
            return RunnablePassthrough()

    async def execute(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """执行目标提议"""
        try:
            self.logger.info("[目标提议链] 开始执行目标提议")

            # 准备简化的输入数据
            chain_input = {
                "game_state": input_data.get("game_state", "未知"),
                "player_position": input_data.get("player_position", "未知"),
                "inventory": input_data.get("inventory", "未知"),
                "environment": input_data.get("environment", "未知"),
            }

            # 获取链并执行
            chain = self.get_chain()
            result = await chain.ainvoke(chain_input)

            # 记录执行日志
            self.log_execution(input_data, result)

            return result

        except Exception as e:
            self.logger.error(f"[目标提议链] 执行失败: {e}")

            # 生成智能备用目标
            game_state = input_data.get("game_state", "未知")
            fallback_goal = self._generate_fallback_goal(game_state)

            return {
                "success": False,
                "error": str(e),
                "goal_proposal_result": {
                    "feasible_goals": [
                        {
                            "goal": fallback_goal,
                            "feasibility_score": 0.9,
                            "requirements_met": True,
                            "estimated_success_rate": "高",
                            "estimated_time": "5-10分钟",
                        }
                    ],
                    "overall_recommendation": f"建议{fallback_goal}",
                    "risk_assessment": "低风险",
                },
            }
