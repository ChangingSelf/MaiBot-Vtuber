from typing import Dict, Any, Optional, List, Callable, Set
import logging
import asyncio
import time
import json
import random

from src.core.synaptic_network import SynapticNetwork
from src.signals.neural_signal import NeuralSignal, SignalType
from src.signals.motor_signals import Live2DSignal
from src.actuators.base_actuator import Actuator
from src.utils.vtubestudio_controller import VTubeStudioController

logger = logging.getLogger(__name__)


class Live2DActuator(Actuator):
    """Live2D执行器 - 负责控制Live2D模型的表情和动作"""

    def __init__(self, synaptic_network: SynapticNetwork, name: Optional[str] = None):
        super().__init__(synaptic_network, name or "Live2D执行器")
        self.live2d_controller = None  # Live2D控制器
        self.available_expressions = set()  # 可用表情列表
        self.available_motions = set()  # 可用动作列表
        self.available_parameters = {}  # 可用参数列表 {param_name: {min: float, max: float}}
        self.current_expression = None  # 当前表情
        self.current_motions = {}  # 当前执行的动作 {motion_id: end_time}
        self.current_parameters = {}  # 当前参数值
        self.auto_motion_task = None  # 自动动作任务
        self.auto_expression_task = None  # 自动表情任务
        self.idle_mode = False  # 是否处于空闲模式

    async def _initialize(self, config: Dict[str, Any]) -> None:
        """初始化Live2D执行器

        Args:
            config: Live2D执行器配置
        """
        # 设置可用表情
        if "expressions" in config:
            self.available_expressions = set(config["expressions"])

        # 设置可用动作
        if "motions" in config:
            self.available_motions = set(config["motions"])

        # 设置可用参数
        if "parameters" in config:
            self.available_parameters = config["parameters"]

        # 设置空闲模式
        self.idle_mode = config.get("idle_mode", False)

        # 初始化VTubeStudio控制器（如果配置中有相关参数）
        if "vtubestudio" in config:
            vts_config = config["vtubestudio"]
            try:
                plugin_name = vts_config.get("plugin_name", "MaiBot-Vtuber")
                developer = vts_config.get("developer", "MaiBot")
                token_path = vts_config.get("token_path", "./token.txt")
                host = vts_config.get("host", "localhost")
                port = vts_config.get("port", 8001)

                # 创建并设置控制器
                vts_controller = VTubeStudioController(
                    plugin_name=plugin_name, developer=developer, token_path=token_path, host=host, port=port
                )
                self.set_controller(vts_controller)

                # 连接到VTubeStudio
                connected = await vts_controller.connect()
                if connected:
                    # 更新可用表情列表
                    self.available_expressions.update(vts_controller.available_expressions)
                    # 记录可用热键作为可用动作
                    self.available_motions.update(vts_controller.available_hotkeys)
                    logger.info(
                        f"已连接到VTubeStudio，获取到{len(vts_controller.available_expressions)}个表情和{len(vts_controller.available_hotkeys)}个热键"
                    )
                else:
                    logger.warning("无法连接到VTubeStudio")
            except Exception as e:
                logger.error(f"初始化VTubeStudio控制器时出错: {e}")

        logger.info(
            f"Live2D执行器初始化完成: {self.name}, 表情数量: {len(self.available_expressions)}, "
            f"动作数量: {len(self.available_motions)}, 参数数量: {len(self.available_parameters)}"
        )

    def set_controller(self, controller: Any) -> None:
        """设置Live2D控制器

        Args:
            controller: Live2D控制器对象
        """
        self.live2d_controller = controller
        logger.info(f"Live2D执行器设置了控制器: {self.name}")

    async def _activate(self) -> None:
        """激活Live2D执行器"""
        await super()._activate()

        # 如果启用了空闲模式，启动自动动作和表情任务
        if self.idle_mode:
            self.auto_motion_task = asyncio.create_task(self._auto_motion_loop())
            self.auto_expression_task = asyncio.create_task(self._auto_expression_loop())
            logger.info(f"Live2D执行器已启动自动模式: {self.name}")

    async def _deactivate(self) -> None:
        """停用Live2D执行器"""
        # 停止自动任务
        if self.auto_motion_task:
            self.auto_motion_task.cancel()
            try:
                await self.auto_motion_task
            except asyncio.CancelledError:
                pass
            self.auto_motion_task = None

        if self.auto_expression_task:
            self.auto_expression_task.cancel()
            try:
                await self.auto_expression_task
            except asyncio.CancelledError:
                pass
            self.auto_expression_task = None

        # 重置模型状态
        if self.live2d_controller:
            try:
                # 重置表情
                await self._set_expression(None)
                # 重置参数
                for param in self.current_parameters:
                    await self._set_parameter(param, 0)
                self.current_parameters.clear()

                # 如果是VTubeStudioController，关闭连接
                if isinstance(self.live2d_controller, VTubeStudioController):
                    await self.live2d_controller.close()
            except Exception as e:
                logger.error(f"重置Live2D模型状态时出错: {e}")

        await super()._deactivate()

    async def _convert_signal_to_action(self, signal: NeuralSignal) -> Optional[Dict[str, Any]]:
        """将神经信号转换为Live2D动作

        Args:
            signal: 神经信号

        Returns:
            Live2D动作
        """
        # 检查是否为Live2D信号
        if isinstance(signal, Live2DSignal):
            action_data = {"type": "live2d", "id": signal.id, "source_signal": signal.id}

            # 提取表情
            if "expression" in signal.data and signal.data["expression"]:
                action_data["expression"] = signal.data["expression"]

            # 提取动作
            if "motion" in signal.data and signal.data["motion"]:
                action_data["motion"] = signal.data["motion"]
                action_data["duration"] = signal.data.get("duration", 3.0)

            # 提取参数
            if "parameters" in signal.data and signal.data["parameters"]:
                action_data["parameters"] = signal.data["parameters"]

            # 只有当信号中包含表情、动作或参数时才返回动作
            if any(k in action_data for k in ["expression", "motion", "parameters"]):
                return action_data

        # 检查其他类型的信号，可能需要触发表情或动作
        elif signal.signal_type == SignalType.SENSORY:
            # 例如，根据弹幕内容触发表情
            if "content" in signal.data:
                content = signal.data["content"]
                # 简单的情绪检测
                if any(word in content for word in ["高兴", "开心", "笑", "哈哈"]):
                    return {"type": "live2d", "id": signal.id, "expression": "happy", "source_signal": signal.id}
                elif any(word in content for word in ["难过", "伤心", "哭", "悲伤"]):
                    return {"type": "live2d", "id": signal.id, "expression": "sad", "source_signal": signal.id}

        return None

    async def _perform_action(self, action: Dict[str, Any]) -> None:
        """执行Live2D动作

        Args:
            action: 要执行的动作
        """
        if not self.live2d_controller:
            logger.warning(f"Live2D执行器无控制器，无法执行动作: {action.get('id')}")
            return

        try:
            # 处理表情
            if "expression" in action:
                expression = action["expression"]
                await self._set_expression(expression)

            # 处理动作
            if "motion" in action:
                motion = action["motion"]
                duration = action.get("duration", 3.0)
                await self._play_motion(motion, duration)

            # 处理参数
            if "parameters" in action:
                parameters = action["parameters"]
                for param, value in parameters.items():
                    await self._set_parameter(param, value)
        except Exception as e:
            logger.error(f"执行Live2D动作时出错: {e}, 动作: {action}")
            self.stats["errors"] += 1

    async def _set_expression(self, expression: Optional[str]) -> None:
        """设置表情

        Args:
            expression: 表情名称，None表示重置表情
        """
        # 检查表情是否可用
        if expression and expression not in self.available_expressions:
            logger.warning(f"尝试设置不可用的表情: {expression}")
            return

        try:
            # 调用控制器设置表情
            if self.live2d_controller:
                await self.live2d_controller.set_expression(expression)
                self.current_expression = expression
                logger.debug(f"设置表情: {expression}")
        except Exception as e:
            logger.error(f"设置表情时出错: {e}, 表情: {expression}")
            raise

    async def _play_motion(self, motion: str, duration: float) -> None:
        """播放动作

        Args:
            motion: 动作名称
            duration: 动作持续时间
        """
        # 检查动作是否可用
        if motion not in self.available_motions:
            logger.warning(f"尝试播放不可用的动作: {motion}")
            return

        try:
            # 调用控制器播放动作
            if self.live2d_controller:
                motion_id = f"{motion}_{int(time.time())}"
                end_time = time.time() + duration

                await self.live2d_controller.play_motion(motion)
                self.current_motions[motion_id] = end_time
                logger.debug(f"播放动作: {motion}, 持续时间: {duration}秒")

                # 异步清理动作
                asyncio.create_task(self._cleanup_motion(motion_id, end_time))
        except Exception as e:
            logger.error(f"播放动作时出错: {e}, 动作: {motion}")
            raise

    async def _cleanup_motion(self, motion_id: str, end_time: float) -> None:
        """清理已完成的动作

        Args:
            motion_id: 动作ID
            end_time: 结束时间
        """
        try:
            # 等待动作完成
            wait_time = end_time - time.time()
            if wait_time > 0:
                await asyncio.sleep(wait_time)

            # 移除动作记录
            if motion_id in self.current_motions:
                del self.current_motions[motion_id]
                logger.debug(f"动作完成: {motion_id}")
        except asyncio.CancelledError:
            # 任务被取消，也移除动作记录
            if motion_id in self.current_motions:
                del self.current_motions[motion_id]
        except Exception as e:
            logger.error(f"清理动作时出错: {e}, 动作ID: {motion_id}")

    async def _set_parameter(self, parameter: str, value: float) -> None:
        """设置参数

        Args:
            parameter: 参数名称
            value: 参数值
        """
        # 检查参数是否可用
        if parameter not in self.available_parameters:
            logger.warning(f"尝试设置不可用的参数: {parameter}")
            return

        try:
            # 检查参数范围
            param_range = self.available_parameters[parameter]
            min_value = param_range.get("min", 0.0)
            max_value = param_range.get("max", 1.0)

            # 限制在有效范围内
            clamped_value = max(min_value, min(max_value, value))

            # 调用控制器设置参数
            if self.live2d_controller:
                await self.live2d_controller.set_parameter(parameter, clamped_value)
                self.current_parameters[parameter] = clamped_value
                logger.debug(f"设置参数: {parameter} = {clamped_value}")
        except Exception as e:
            logger.error(f"设置参数时出错: {e}, 参数: {parameter}, 值: {value}")
            raise

    async def _auto_motion_loop(self) -> None:
        """自动播放动作的循环任务"""
        while self.is_active:
            try:
                # 如果没有正在进行的动作，随机播放一个
                if not self.current_motions and self.available_motions:
                    # 有80%的几率保持不动，20%的几率播放动作
                    if random.random() < 0.2:
                        motion = random.choice(list(self.available_motions))
                        await self._play_motion(motion, random.uniform(2.0, 5.0))

                # 随机等待5-15秒
                await asyncio.sleep(random.uniform(5.0, 15.0))
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"自动动作循环出错: {e}")
                await asyncio.sleep(5.0)  # 出错时延长等待时间

    async def _auto_expression_loop(self) -> None:
        """自动切换表情的循环任务"""
        while self.is_active:
            try:
                # 有70%的几率保持当前表情，30%的几率切换表情
                if random.random() < 0.3 and self.available_expressions:
                    # 随机选择一个不同于当前表情的表情
                    available = list(self.available_expressions - {self.current_expression})
                    if available:
                        expression = random.choice(available)
                        await self._set_expression(expression)

                # 随机等待15-60秒
                await asyncio.sleep(random.uniform(15.0, 60.0))
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"自动表情循环出错: {e}")
                await asyncio.sleep(10.0)  # 出错时延长等待时间
