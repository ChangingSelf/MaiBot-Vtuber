# -*- coding: utf-8 -*-
import asyncio
import contextlib
from typing import Any, Dict, Optional, List, Union
import time
import mineland

from src.core.plugin_manager import BasePlugin
from src.core.amaidesu_core import AmaidesuCore
from maim_message import MessageBase

from .state.game_state import MinecraftGameState
from .events.event_manager import MinecraftEventManager
from .actions.action_executor import MinecraftActionExecutor
from .message.message_builder import MinecraftMessageBuilder

# 核心管理组件
from .core.config_manager import ConfigManager
from .core.agent_manager import AgentManager


class MinecraftPlugin(BasePlugin):
    """Minecraft插件 - 支持MaiCore和智能体两种控制模式"""

    def __init__(self, core: AmaidesuCore, plugin_config: Dict[str, Any]):
        super().__init__(core, plugin_config)

        config = self.plugin_config

        # 基础配置
        self.task_id: str = config.get("mineland_task_id", "playground")
        self.server_host: str = config.get("server_host", "127.0.0.1")
        self.server_port: int = config.get("server_port", 1746)

        # 智能体配置（转换为兼容格式）
        self.agents_count: int = config.get("agents_count", 1)
        raw_agents_config = config.get("agents_config", [{"name": "Mai"}])
        # 确保agents_config符合类型要求
        self.agents_config: List[Dict[str, Union[str, int]]] = []
        for agent_cfg in raw_agents_config:
            converted_cfg = {}
            for k, v in agent_cfg.items():
                converted_cfg[k] = v  # 保持原值，Dict[str, Union[str, int]]能接受str
            self.agents_config.append(converted_cfg)

        self.headless: bool = config.get("mineland_headless", True)
        self.ticks_per_step: int = config.get("mineland_ticks_per_step", 20)

        # 图像大小配置
        image_size_config = config.get("mineland_image_size", [180, 320])
        if isinstance(image_size_config, list) and len(image_size_config) == 2:
            self.image_size: tuple[int, int] = tuple(image_size_config)
        else:
            self.logger.warning(f"配置的 image_size 无效: {image_size_config}，使用默认值 (180, 320)")
            self.image_size: tuple[int, int] = (180, 320)

        # 自动发送配置
        self.auto_send_interval: float = config.get("auto_send_interval", 30.0)
        self._auto_send_task: Optional[asyncio.Task] = None
        self._last_response_time: float = 0.0

        # MineLand实例
        self.mland: Optional[mineland.MineLand] = None

        # 管理组件
        self.config_manager = ConfigManager(plugin_config)
        self.agent_manager = AgentManager()

        # 当前控制模式 - 简化为直接的模式标识
        self.current_mode: str = self.config_manager.get_control_mode()
        self._mode_tasks: Dict[str, Optional[asyncio.Task]] = {
            "maicore_auto_send": None,
            "agent_decision": None,
            "status_report": None,
        }

        # 核心组件 - 使用配置文件中的参数
        action_executor_config = config.get("action_executor", {})
        event_manager_config = config.get("event_manager", {})
        game_state_config = config.get("game_state", {})

        self.game_state = MinecraftGameState(game_state_config)
        self.event_manager = MinecraftEventManager(
            event_manager_config.get("max_event_history", 20),
            config,  # 传递完整配置
        )
        self.action_executor = MinecraftActionExecutor(
            self.game_state,
            self.event_manager,
            max_wait_cycles=action_executor_config.get("max_wait_cycles", 100),
            wait_cycle_interval=action_executor_config.get("wait_cycle_interval", 0.1),
            config=config,  # 传递完整配置
        )
        self.message_builder = MinecraftMessageBuilder(
            platform=self.core.platform,
            user_id=config.get("user_id", "minecraft_bot"),
            nickname=config.get("nickname", "Minecraft Observer"),
            group_id=config.get("group_id", ""),
            config=config.get("prompt", {}),
        )

    async def setup(self):
        """初始化插件"""
        await super().setup()

        # 初始化MineLand环境
        await self._initialize_mineland()

        # 初始化智能体管理器
        await self.agent_manager.initialize(self.config_manager.get_agent_config())

        # 注册消息处理器 - 修复类型问题，使用wrapper
        def message_handler_wrapper(message: MessageBase):
            return asyncio.create_task(self.handle_external_message(message))

        self.core.register_websocket_handler("*", message_handler_wrapper)

        # 启动对应模式的控制循环
        await self._start_mode_control_loop()

        self.logger.info(f"Minecraft插件初始化完成，当前模式: {self.current_mode}")

    async def _initialize_mineland(self):
        """初始化MineLand环境"""
        self.logger.info("Minecraft 插件已加载，正在初始化 MineLand 环境...")
        try:
            # 初始化MineLand环境
            self.mland = mineland.MineLand(
                server_host=self.server_host,
                server_port=self.server_port,
                agents_count=self.agents_count,
                agents_config=self.agents_config,
                headless=self.headless,
                image_size=self.image_size,
                enable_low_level_action=False,
                ticks_per_step=self.ticks_per_step,
            )
            self.logger.info(f"MineLand 环境 (Task ID: {self.task_id}) 初始化成功。")

            # 将 mland 实例注入到 action_executor 中
            self.action_executor.set_mland(self.mland)

            # 重置环境并初始化状态
            initial_obs = self.mland.reset()
            self.game_state.reset_state(initial_obs)
            self.game_state.add_initial_goal_record()

            self.logger.info(f"MineLand 环境已重置，收到初始观察: {len(initial_obs)} 个智能体。")
            self.logger.info(f"已记录初始目标: {self.game_state.goal}")

        except Exception as e:
            self.logger.exception(f"初始化 MineLand 环境失败: {e}")
            raise

    async def _start_mode_control_loop(self):
        """启动对应模式的控制循环"""
        if self.current_mode == "maicore":
            await self._start_maicore_mode()
        elif self.current_mode == "agent":
            await self._start_agent_mode()
        else:
            self.logger.warning(f"不支持的控制模式: {self.current_mode}，使用默认maicore模式")
            self.current_mode = "maicore"
            await self._start_maicore_mode()

    async def _start_maicore_mode(self):
        """启动MaiCore模式"""
        if self._mode_tasks["maicore_auto_send"] is None:
            self._mode_tasks["maicore_auto_send"] = asyncio.create_task(
                self._maicore_auto_send_loop(), name="MaiCoreAutoSend"
            )
            self.logger.info(f"已启动MaiCore自动发送任务，间隔: {self.auto_send_interval}秒")

    async def _start_agent_mode(self):
        """启动智能体模式"""
        if self._mode_tasks["agent_decision"] is None:
            self._mode_tasks["agent_decision"] = asyncio.create_task(
                self._agent_decision_loop(), name="AgentDecisionLoop"
            )
            self.logger.info("已启动智能体决策循环")

        # 如果启用了MaiCore集成，启动状态报告任务
        maicore_config = self.plugin_config.get("maicore_integration", {})
        if maicore_config.get("accept_commands", True) and self._mode_tasks["status_report"] is None:
            report_interval = maicore_config.get("status_report_interval", 60)
            self._mode_tasks["status_report"] = asyncio.create_task(
                self._status_report_loop(report_interval), name="StatusReportLoop"
            )
            self.logger.info(f"已启动状态报告任务，间隔: {report_interval}秒")

    # === MaiCore模式相关方法 ===
    async def _maicore_auto_send_loop(self):
        """MaiCore模式：定期发送状态的循环任务"""
        while True:
            try:
                await asyncio.sleep(self.auto_send_interval)

                current_time = time.time()
                if current_time - self._last_response_time > self.auto_send_interval:
                    # 超时时间内未收到响应，刷新状态并重新发送
                    await self.action_executor.execute_no_op()
                    self.logger.info("超时时间内未收到响应，刷新状态并重新发送")
                    if self.game_state.is_ready_for_next_action():
                        # 如果智能体准备好，则发送状态
                        await self._send_state_to_maicore()
            except asyncio.CancelledError:
                self.logger.info("MaiCore自动发送状态任务被取消")
                break
            except Exception as e:
                self.logger.error(f"MaiCore自动发送状态时出错: {e}")
                await asyncio.sleep(1)

    async def _send_state_to_maicore(self):
        """构建并发送当前Mineland状态给AmaidesuCore"""
        try:
            # 转换agents_config类型以匹配接口要求
            agents_config_str = [{k: str(v) for k, v in agent_cfg.items()} for agent_cfg in self.agents_config]
            msg_to_maicore = self.message_builder.build_state_message(
                self.game_state, self.event_manager, agents_config_str
            )

            # 如果消息为空，则执行no_op
            if not msg_to_maicore:
                await self.action_executor.execute_no_op()
                return

            await self.core.send_to_maicore(msg_to_maicore)
            self.logger.info(
                f"已将 Mineland 事件状态 (step {self.game_state.current_step_num}, done: {self.game_state.current_done}) 发送给 MaiCore。"
            )
        except Exception as e:
            self.logger.error(f"构建或发送状态消息时出错: {e}")
            raise

    async def _handle_maicore_message(self, message: MessageBase):
        """MaiCore模式：处理从 MaiCore 返回的动作指令"""
        self.logger.info(f"收到来自 MaiCore 的响应: {message.message_segment.data}")

        # 更新最后响应时间
        self._last_response_time = time.time()

        if not self.mland:
            self.logger.error("收到 MaiCore 响应，但 MineLand 环境未初始化。忽略消息。")
            return

        if message.message_segment.type not in ["text", "seglist"]:
            self.logger.warning(
                f"MaiCore 返回的消息不是文本消息: type='{message.message_segment.type}'. 期望是'text'或'seglist'。丢弃消息。"
            )
            return

        # 提取消息内容
        message_json_str = ""
        if message.message_segment.type == "seglist":
            # 取出其中的text类型消息
            seg_data = message.message_segment.data
            if isinstance(seg_data, list):
                for seg in seg_data:
                    if hasattr(seg, "type") and seg.type == "text" and hasattr(seg, "data"):
                        # 安全地获取和处理数据
                        seg_data_content = seg.data
                        if isinstance(seg_data_content, str):
                            message_json_str = seg_data_content.strip()
                        else:
                            message_json_str = str(seg_data_content).strip()
                        self.logger.debug(f"从 MaiCore 收到原始动作指令: {message_json_str}")
                        break
                else:
                    self.logger.warning("从 MaiCore 收到seglist消息，但其中没有text类型消息。丢弃消息。")
                    return
            else:
                self.logger.warning("消息段数据格式不正确。丢弃消息。")
                return
        elif message.message_segment.type == "text":
            if hasattr(message.message_segment, "data") and isinstance(message.message_segment.data, str):
                message_json_str = message.message_segment.data.strip()
                self.logger.debug(f"从 MaiCore 收到原始动作指令: {message_json_str}")
            else:
                self.logger.warning("消息数据格式不正确。丢弃消息。")
                return

        try:
            # 执行动作（包括等待完成、状态更新等）
            await self.action_executor.execute_maicore_action(message_json_str)

            # 发送新的状态给 MaiCore
            await self._send_state_to_maicore()

        except Exception as e:
            self.logger.error(f"处理 MaiCore 动作指令时出错: {e}")
            # 发送错误状态给 MaiCore
            await self._send_state_to_maicore()

    # === 智能体模式相关方法 ===
    async def _agent_decision_loop(self):
        """智能体模式：智能体决策循环"""
        loop_count = 0
        while True:
            try:
                loop_count += 1

                # 每100次循环输出一次调试信息
                if loop_count % 100 == 1:
                    self.logger.info(f"智能体决策循环运行中，第 {loop_count} 次")

                # 获取当前智能体
                agent = await self.agent_manager.get_current_agent()
                if not agent:
                    if loop_count % 100 == 1:
                        self.logger.warning("没有当前智能体，等待中...")
                    await asyncio.sleep(1)
                    continue

                # 检查游戏状态是否准备好
                is_ready = self.game_state.is_ready_for_next_action()
                if not is_ready:
                    if loop_count % 100 == 1:
                        self.logger.debug(
                            f"游戏状态未准备好，等待中... (code_info: {self.game_state.current_code_info is not None})"
                        )
                    await asyncio.sleep(0.1)
                    continue

                # 构建观察数据
                obs = self._build_agent_observation()
                if loop_count % 100 == 1:
                    self.logger.debug(f"构建观察数据: {len(str(obs))} 字符")

                # 智能体决策
                self.logger.debug(f"开始智能体决策...")
                # 转换code_info为dict类型
                code_info_dict = None
                if self.game_state.current_code_info:
                    code_info_dict = getattr(self.game_state.current_code_info, "__dict__", {})

                action = await agent.run(
                    obs,
                    code_info=code_info_dict,
                    done=self.game_state.current_done,
                    task_info=self.game_state.current_task_info,
                )

                if action:
                    # 执行动作
                    self.logger.info(f"智能体生成动作: {action.code}")
                    await self.action_executor.execute_action(action)
                    self.logger.debug(f"动作执行完成")
                else:
                    # 如果智能体没有返回动作，执行no_op
                    self.logger.warning("智能体没有返回动作，执行no_op")
                    await self.action_executor.execute_no_op()

                await asyncio.sleep(0.1)

            except asyncio.CancelledError:
                self.logger.info("智能体决策循环被取消")
                break
            except Exception as e:
                self.logger.error(f"智能体决策循环错误: {e}")
                import traceback

                self.logger.error(f"错误详情: {traceback.format_exc()}")
                await asyncio.sleep(1)

    def _build_agent_observation(self) -> Dict[str, Any]:
        """构建智能体的观察数据 - 集成状态分析器"""
        try:
            observation_data = {}

            # 从游戏状态中获取当前观察
            current_obs = self.game_state.current_obs
            if current_obs:
                # 基础观察数据
                if hasattr(current_obs, "__dict__"):
                    observation_data["raw_observation"] = current_obs.__dict__
                else:
                    observation_data["raw_observation"] = str(current_obs)

                # 集成状态分析器的环境感知能力
                try:
                    # 获取完整的状态分析
                    status_analysis = self.game_state.get_status_analysis()
                    if status_analysis:
                        observation_data["environment_analysis"] = {
                            "summary": status_analysis,
                            "analysis_count": len(status_analysis),
                        }

                    # 获取详细的分类状态分析
                    detailed_analysis = self.game_state.get_detailed_status_analysis()
                    if detailed_analysis:
                        observation_data["detailed_environment"] = detailed_analysis

                        # 提取关键环境信息作为顶级字段
                        if "life_stats" in detailed_analysis:
                            observation_data["health_status"] = detailed_analysis["life_stats"]

                        if "environment" in detailed_analysis:
                            observation_data["surrounding_blocks"] = detailed_analysis["environment"]

                        if "position" in detailed_analysis:
                            observation_data["position_info"] = detailed_analysis["position"]

                        if "inventory" in detailed_analysis:
                            observation_data["inventory_status"] = detailed_analysis["inventory"]

                        if "equipment" in detailed_analysis:
                            observation_data["equipment_status"] = detailed_analysis["equipment"]

                        # 碰撞和移动信息
                        if "collision" in detailed_analysis:
                            observation_data["movement_obstacles"] = detailed_analysis["collision"]

                        if "facing_wall" in detailed_analysis:
                            observation_data["facing_direction"] = detailed_analysis["facing_wall"]

                        # 时间和天气信息
                        if "time" in detailed_analysis:
                            observation_data["game_time"] = detailed_analysis["time"]

                        if "weather" in detailed_analysis:
                            observation_data["weather_info"] = detailed_analysis["weather"]

                    self.logger.debug(f"成功集成状态分析器数据，包含 {len(observation_data)} 个数据类别")

                except Exception as e:
                    self.logger.warning(f"获取状态分析时出错: {e}")
                    observation_data["analysis_error"] = str(e)
            else:
                observation_data["error"] = "没有可用的观察数据"

            return observation_data

        except Exception as e:
            self.logger.error(f"构建智能体观察数据时出错: {e}")
            return {"error": f"构建观察数据失败: {str(e)}"}

    async def _status_report_loop(self, interval: int):
        """智能体模式：定期向MaiCore报告状态"""
        while True:
            try:
                await asyncio.sleep(interval)
                await self._report_status_to_maicore()
            except asyncio.CancelledError:
                self.logger.info("状态报告循环被取消")
                break
            except Exception as e:
                self.logger.error(f"状态报告循环错误: {e}")
                await asyncio.sleep(1)

    async def _report_status_to_maicore(self):
        """向MaiCore报告当前状态"""
        try:
            # 获取智能体状态
            agent = await self.agent_manager.get_current_agent()
            if agent:
                agent_status = await agent.get_status()
            else:
                agent_status = {"status": "no_agent"}

            # 构建状态消息 - 转换agents_config类型
            agents_config_str = [{k: str(v) for k, v in agent_cfg.items()} for agent_cfg in self.agents_config]
            msg_to_maicore = self.message_builder.build_state_message(
                self.game_state, self.event_manager, agents_config_str
            )

            if msg_to_maicore:
                await self.core.send_to_maicore(msg_to_maicore)
                self.logger.debug("已向MaiCore报告智能体状态")

        except Exception as e:
            self.logger.error(f"向MaiCore报告状态时出错: {e}")

    async def _handle_agent_message(self, message: MessageBase):
        """智能体模式：处理外部消息 - 可选地传递给智能体"""
        maicore_config = self.plugin_config.get("maicore_integration", {})
        if not maicore_config.get("accept_commands", True):
            self.logger.debug("MaiCore集成已禁用，忽略外部消息")
            return

        self.logger.info(f"收到来自 MaiCore 的指令: {message.message_segment.data}")

        # 提取消息内容
        command = ""
        if message.message_segment.type == "text":
            if hasattr(message.message_segment, "data") and isinstance(message.message_segment.data, str):
                command = message.message_segment.data.strip()
            else:
                self.logger.warning("消息数据格式不正确。忽略消息。")
                return
        elif message.message_segment.type == "seglist":
            # 取出其中的text类型消息
            seg_data = message.message_segment.data
            if isinstance(seg_data, list):
                for seg in seg_data:
                    if hasattr(seg, "type") and seg.type == "text" and hasattr(seg, "data"):
                        # 安全地获取和处理数据
                        seg_data_content = seg.data
                        if isinstance(seg_data_content, str):
                            command = seg_data_content.strip()
                        else:
                            command = str(seg_data_content).strip()
                        break
                else:
                    self.logger.warning("从 MaiCore 收到seglist消息，但其中没有text类型消息。忽略消息。")
                    return
            else:
                self.logger.warning("消息段数据格式不正确。忽略消息。")
                return
        else:
            self.logger.warning(f"不支持的消息类型: {message.message_segment.type}")
            return

        # 获取指令优先级配置
        priority = maicore_config.get("default_command_priority", "normal")

        # 传递给当前智能体
        try:
            agent = await self.agent_manager.get_current_agent()
            if agent:
                await agent.receive_command(command, priority)
                self.logger.info(f"已将MaiCore指令传递给智能体: {command}")
            else:
                self.logger.warning("没有可用的智能体接收MaiCore指令")

        except Exception as e:
            self.logger.error(f"传递MaiCore指令给智能体时出错: {e}")

    # === 统一入口方法 ===
    async def handle_external_message(self, message: MessageBase):
        """处理外部消息 - 根据当前模式分发"""
        if self.current_mode == "maicore":
            await self._handle_maicore_message(message)
        elif self.current_mode == "agent":
            await self._handle_agent_message(message)
        else:
            self.logger.warning(f"未知的控制模式: {self.current_mode}")

    # === 模式切换方法 ===
    async def switch_mode(self, new_mode: str) -> bool:
        """切换控制模式"""
        if new_mode not in ["maicore", "agent"]:
            self.logger.error(f"不支持的模式: {new_mode}")
            return False

        if self.current_mode == new_mode:
            self.logger.info(f"已经处于{new_mode}模式")
            return True

        try:
            self.logger.info(f"开始从{self.current_mode}模式切换到{new_mode}模式")

            # 停止当前模式的任务
            await self._stop_current_mode_tasks()

            # 切换模式
            old_mode = self.current_mode
            self.current_mode = new_mode

            # 启动新模式的控制循环
            await self._start_mode_control_loop()

            self.logger.info(f"成功从{old_mode}模式切换到{new_mode}模式")
            return True

        except Exception as e:
            self.logger.error(f"模式切换失败: {e}")
            return False

    async def _stop_current_mode_tasks(self):
        """停止当前模式的任务"""
        for task_name, task in self._mode_tasks.items():
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                self._mode_tasks[task_name] = None
                self.logger.debug(f"已停止任务: {task_name}")

    # === 状态查询方法 ===
    async def get_current_mode(self) -> str:
        """获取当前模式"""
        return self.current_mode

    async def get_agent_status(self) -> dict:
        """获取智能体状态"""
        if hasattr(self, "agent_manager") and self.agent_manager:
            return await self.agent_manager.get_agent_status()
        return {"error": "智能体管理器未初始化"}

    async def cleanup(self):
        """清理插件资源"""
        self.logger.info("正在清理 Minecraft 插件...")

        # 停止所有模式任务
        await self._stop_current_mode_tasks()

        # 清理智能体管理器
        if hasattr(self, "agent_manager") and self.agent_manager:
            try:
                await self.agent_manager.cleanup()
            except Exception as e:
                self.logger.error(f"清理智能体管理器时出错: {e}")

        # 关闭MineLand环境
        if self.mland:
            try:
                self.logger.info("正在关闭 MineLand 环境...")
                self.mland.close()
                self.logger.info("MineLand 环境已关闭。")
            except Exception as e:
                self.logger.exception(f"关闭 MineLand 环境时发生错误: {e}")

        self.logger.info("Minecraft 插件清理完毕。")


# --- 插件入口点 ---
plugin_entrypoint = MinecraftPlugin
