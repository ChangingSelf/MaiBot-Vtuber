import asyncio
from typing import Any, Dict, Optional

from src.utils.logger import get_logger
from .agent import MaicraftAgent
from .task_queue import TaskQueue, RunnerTask
from maim_message import MessageBase


class AgentRunner:
    """简化的Agent运行器，专注于任务调度"""

    def __init__(self, core, mcp_client, agent: MaicraftAgent, agent_cfg: Dict[str, Any]):
        self.core = core
        self.mcp_client = mcp_client
        self.agent = agent
        self.agent_cfg = agent_cfg
        self.logger = get_logger("AgentRunner")

        # 使用TaskQueue替代简单的asyncio.Queue
        self.task_queue = TaskQueue(agent_cfg)
        self.running = False
        self._task = None
        self._current_task = None  # 当前正在执行的任务

        # 配置参数
        self.tick_seconds = float(agent_cfg.get("tick_seconds", 8.0))
        self.report_each_step = bool(agent_cfg.get("report_each_step", True))

        # 统计信息
        self.stats = {"tasks_processed": 0, "goals_proposed": 0, "errors_handled": 0, "start_time": None}

    async def start(self):
        """启动Agent运行器"""
        try:
            self.logger.info("[AgentRunner] 启动Agent运行器")

            # 初始化Agent
            await self.agent.initialize()

            # 启动运行循环
            self.running = True
            self.stats["start_time"] = asyncio.get_event_loop().time()
            self._task = asyncio.create_task(self._run_loop())

            self.logger.info("[AgentRunner] Agent运行器启动成功")

        except Exception as e:
            self.logger.error(f"[AgentRunner] 启动失败: {e}")
            raise

    async def stop(self):
        """停止Agent运行器"""
        try:
            self.logger.info("[AgentRunner] 停止Agent运行器")

            # 停止运行循环
            self.running = False

            # 取消当前任务
            if self._current_task and not self._current_task.done():
                self._current_task.cancel()
                try:
                    await self._current_task
                except asyncio.CancelledError:
                    self.logger.info("[AgentRunner] 当前任务已取消")

            # 取消运行任务
            if self._task:
                self._task.cancel()
                try:
                    await self._task
                except asyncio.CancelledError:
                    pass

            self.logger.info("[AgentRunner] Agent运行器已停止")

        except Exception as e:
            self.logger.error(f"[AgentRunner] 停止失败: {e}")

    async def _run_loop(self):
        """主运行循环"""
        try:
            self.logger.info("[AgentRunner] 开始主运行循环")

            while self.running:
                try:
                    # 处理任务队列
                    await self._process_task_queue()

                    # 提议并执行目标
                    await self._propose_and_execute_goal()

                    # 等待下一个tick
                    await asyncio.sleep(self.tick_seconds)

                except asyncio.CancelledError:
                    self.logger.info("[AgentRunner] 运行循环被取消")
                    break
                except Exception as e:
                    self.logger.error(f"[AgentRunner] 运行循环错误: {e}")
                    await asyncio.sleep(1.0)  # 短暂等待后继续

            self.logger.info("[AgentRunner] 主运行循环结束")

        except Exception as e:
            self.logger.error(f"[AgentRunner] 运行循环异常: {e}")

    async def _process_task_queue(self):
        """处理任务队列"""
        try:
            # 检查是否有待处理的任务
            if not await self.task_queue.is_queue_idle():
                task = await self.task_queue.pop_next_task()
                if task:
                    await self._process_task(task)

        except Exception as e:
            self.logger.error(f"[AgentRunner] 处理任务队列失败: {e}")

    async def _process_task(self, task: RunnerTask):
        """处理任务"""
        try:
            self.logger.info(f"[AgentRunner] 处理任务: {task.goal} (优先级: {task.priority}, 来源: {task.source})")

            # 创建异步任务，支持取消
            self._current_task = asyncio.create_task(self._execute_task(task))

            try:
                # 等待任务完成
                result = await self._current_task

                # 报告结果
                await self._report_result(result, "task_execution")

                # 更新统计
                self.stats["tasks_processed"] += 1

                self.logger.info(f"[AgentRunner] 任务处理完成: {task.goal}")

            except asyncio.CancelledError:
                self.logger.info(f"[AgentRunner] 任务被取消: {task.goal}")
                # 报告任务取消
                cancel_result = {
                    "success": False,
                    "error": "任务被用户打断",
                    "task_goal": task.goal,
                    "user_message": f"任务 '{task.goal}' 已被打断",
                }
                await self._report_result(cancel_result, "task_cancelled")
                self.stats["errors_handled"] += 1

        except Exception as e:
            self.logger.error(f"[AgentRunner] 处理任务失败: {e}")
            self.stats["errors_handled"] += 1

            # 报告错误
            error_result = {
                "success": False,
                "error": str(e),
                "task_goal": task.goal,
                "user_message": "任务执行失败，请稍后重试",
            }
            await self._report_result(error_result, "error")

        finally:
            self._current_task = None

    async def _execute_task(self, task: RunnerTask) -> Dict[str, Any]:
        """执行具体任务"""
        try:
            # 使用Agent执行任务
            result = await self.agent.plan_and_execute(task.goal)
            return result

        except Exception as e:
            self.logger.error(f"[AgentRunner] 执行任务失败: {e}")
            raise

    async def _propose_and_execute_goal(self):
        """提议并执行目标"""
        try:
            # 检查是否需要提议目标
            if await self.task_queue.is_queue_idle():
                self.logger.debug("[AgentRunner] 提议下一个目标")

                # 使用Agent提议目标
                goal = await self.agent.propose_next_goal()
                if goal:
                    self.logger.info(f"[AgentRunner] 提议目标: {goal}")

                    # 将目标作为任务添加到队列（低优先级）
                    await self.task_queue.enqueue_goal_with_split(
                        goal=goal, priority=self.task_queue.PRIORITY_NORMAL, source="auto"
                    )

                    # 更新统计
                    self.stats["goals_proposed"] += 1

                    # 报告目标提议
                    goal_result = {
                        "success": True,
                        "goal": goal,
                        "source": "agent_proposal",
                        "user_message": f"我建议下一个目标: {goal}",
                    }
                    await self._report_result(goal_result, "goal_proposal")

        except Exception as e:
            self.logger.error(f"[AgentRunner] 提议目标失败: {e}")
            self.stats["errors_handled"] += 1

    async def _report_result(self, result: Dict[str, Any], source: str):
        """报告执行结果"""
        try:
            # 格式化结果
            formatted_result = {
                "source": source,
                "timestamp": asyncio.get_event_loop().time(),
                "success": result.get("success", False),
                "content": result.get("user_message", ""),
                "data": result,
                "stats": self.stats.copy(),
            }

            # 发送到核心系统
            if hasattr(self.core, "send_message"):
                await self.core.send_message({"type": "agent_result", "data": formatted_result})

            # 记录日志
            if self.report_each_step:
                self.logger.info(f"[AgentRunner] 报告结果 - 来源: {source}, 成功: {result.get('success', False)}")

        except Exception as e:
            self.logger.error(f"[AgentRunner] 报告结果失败: {e}")

    async def handle_message(self, message: MessageBase):
        """处理外部消息"""
        try:
            message_type = message.message_segment.type if message.message_segment else "unknown"
            self.logger.info(f"[AgentRunner] 收到消息: {message_type}")

            # 提取用户输入
            user_input = self._extract_user_input(message)
            if user_input:
                # 检查是否需要打断当前任务
                if self._current_task and not self._current_task.done():
                    self.logger.info("[AgentRunner] 检测到新消息，准备打断当前任务")
                    await self._interrupt_current_task()

                # 将用户输入添加到队列（高优先级）
                await self.task_queue.enqueue_goal_with_split(
                    goal=user_input, priority=self.task_queue.PRIORITY_MAICORE, source="maicore"
                )

                self.logger.info(f"[AgentRunner] 用户任务已添加到队列: {user_input}")
            else:
                self.logger.warning("[AgentRunner] 消息中没有有效的用户输入")

        except Exception as e:
            self.logger.error(f"[AgentRunner] 处理消息失败: {e}")

    async def _interrupt_current_task(self):
        """打断当前正在执行的任务"""
        try:
            if self._current_task and not self._current_task.done():
                self.logger.info("[AgentRunner] 正在打断当前任务")

                # 取消当前任务
                self._current_task.cancel()

                # 等待任务取消完成
                try:
                    await self._current_task
                except asyncio.CancelledError:
                    self.logger.info("[AgentRunner] 当前任务已成功取消")

                self._current_task = None

        except Exception as e:
            self.logger.error(f"[AgentRunner] 打断任务失败: {e}")

    def _extract_user_input(self, message: MessageBase) -> Optional[str]:
        """从MessageBase对象中提取用户输入"""
        try:
            # 首先尝试从message_segment中提取
            if message.message_segment:
                segment_type = message.message_segment.type
                segment_data = message.message_segment.data

                # 根据消息类型提取内容
                if segment_type == "text":
                    if isinstance(segment_data, str):
                        return segment_data
                    elif isinstance(segment_data, dict):
                        # 如果是字典，尝试提取text或content字段
                        return segment_data.get("text") or segment_data.get("content")

            # 如果message_segment中没有找到，尝试从raw_message中提取
            if message.raw_message:
                if isinstance(message.raw_message, str):
                    return message.raw_message
                elif isinstance(message.raw_message, dict):
                    # 如果是字典，尝试提取常见字段
                    for key in ["text", "content", "message", "command"]:
                        if key in message.raw_message:
                            content = message.raw_message[key]
                            if isinstance(content, str):
                                return content

            # 如果都没有找到，记录日志并返回None
            self.logger.debug(
                f"[AgentRunner] 无法从消息中提取用户输入，消息类型: {message.message_segment.type if message.message_segment else 'None'}"
            )
            return None

        except Exception as e:
            self.logger.error(f"[AgentRunner] 提取用户输入失败: {e}")
            return None

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        stats = self.stats.copy()
        if stats["start_time"]:
            stats["uptime"] = asyncio.get_event_loop().time() - stats["start_time"]
        stats["queue_size"] = 0  # TaskQueue没有直接的qsize方法
        stats["running"] = self.running
        stats["current_task"] = self._current_task is not None and not self._current_task.done()
        return stats

    def clear_stats(self):
        """清除统计信息"""
        self.stats = {
            "tasks_processed": 0,
            "goals_proposed": 0,
            "errors_handled": 0,
            "start_time": asyncio.get_event_loop().time(),
        }
        self.logger.info("[AgentRunner] 统计信息已清除")
