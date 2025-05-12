import asyncio
import json  # 用于解析和构建 JSON

# import websockets # 不再需要
from typing import Any, Dict, Optional, List  # 增加 List
import time
import os
import tomllib
import mineland
import numpy as np
from enum import Enum

from src.core.plugin_manager import BasePlugin
from src.core.amaidesu_core import AmaidesuCore
from maim_message import MessageBase, UserInfo, GroupInfo, FormatInfo, BaseMessageInfo, Seg

from src.utils.logger import get_logger

logger = get_logger("MinecraftPlugin")


# Minecraft动作类型枚举
class MinecraftActionType(Enum):
    """Minecraft动作类型枚举，规范化动作类型的使用"""

    NO_OP = "NO_OP"  # 不执行任何操作
    NEW = "NEW"  # 提交新代码
    RESUME = "RESUME"  # 恢复执行
    CHAT = "CHAT"  # 聊天消息
    CHAT_OP = "CHAT_OP"  # 聊天消息（与CHAT相同）

    @classmethod
    def from_string(cls, action_type_str: str) -> "MinecraftActionType":
        """从字符串获取动作类型枚举"""
        try:
            return cls[action_type_str.upper()]
        except (KeyError, AttributeError):
            # 如果找不到对应的枚举值，返回NO_OP
            logger.warning(f"未知动作类型: '{action_type_str}'，使用 NO_OP 代替。")
            return cls.NO_OP

    @classmethod
    def is_chat_action(cls, action_type) -> bool:
        """判断是否为聊天类动作"""
        return action_type in (cls.CHAT, cls.CHAT_OP)


class MinelandJSONEncoder(json.JSONEncoder):
    """自定义JSON编码器，处理MineLand特有的类型"""

    def default(self, obj):
        if hasattr(obj, "__dict__"):
            return {k: v for k, v in obj.__dict__.items() if not k.startswith("_")}
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
        elif isinstance(
            obj,
            (
                np.int_,
                np.intc,
                np.intp,
                np.int8,
                np.int16,
                np.int32,
                np.int64,
                np.uint8,
                np.uint16,
                np.uint32,
                np.uint64,
            ),
        ):
            return int(obj)
        elif isinstance(obj, (np.float_, np.float16, np.float32, np.float64)):
            return float(obj)
        elif isinstance(obj, (np.bool_)):
            return bool(obj)
        return super(MinelandJSONEncoder, self).default(obj)


def json_serialize_mineland(obj):
    """使用自定义编码器序列化MineLand对象"""
    return json.dumps(obj, cls=MinelandJSONEncoder)


def numpy_to_list_recursive(item):  # 保留以防万一，但 MinelandJSONEncoder 通常更优
    """递归地将 NumPy 数组和其他不可JSON序列化对象转换为可序列化类型。"""
    if isinstance(item, np.ndarray):
        return item.tolist()
    elif hasattr(item, "__dict__"):
        return {k: numpy_to_list_recursive(v) for k, v in item.__dict__.items() if not k.startswith("_")}
    elif isinstance(item, dict):
        return {k: numpy_to_list_recursive(v) for k, v in item.items()}
    elif isinstance(item, list) or isinstance(item, tuple):
        return [numpy_to_list_recursive(elem) for elem in item]
    elif isinstance(
        item,
        (np.int_, np.intc, np.intp, np.int8, np.int16, np.int32, np.int64, np.uint8, np.uint16, np.uint32, np.uint64),
    ):
        return int(item)
    elif isinstance(item, (np.float_, np.float16, np.float32, np.float64)):
        return float(item)
    elif isinstance(item, np.bool_):
        return bool(item)
    return item


# --- Helper Function ---
def load_plugin_config() -> Dict[str, Any]:
    # (配置加载逻辑 - 与其他插件类似)
    config_path = os.path.join(os.path.dirname(__file__), "config.toml")
    try:
        with open(config_path, "rb") as f:
            if hasattr(tomllib, "load"):
                return tomllib.load(f)
            else:
                try:
                    import toml

                    with open(config_path, "r", encoding="utf-8") as rf:
                        return toml.load(rf)
                except ImportError:
                    logger.exception("toml package needed for Python < 3.11.")
                    return {}
                except FileNotFoundError:
                    logger.warning(f"Config file not found: {config_path}")
                    return {}
    except Exception as e:
        logger.exception(f"Error loading config: {config_path}: {e}", exc_info=True)
        return {}


class MinecraftPlugin(BasePlugin):
    _is_amaidesu_plugin: bool = True

    def __init__(self, core: AmaidesuCore, plugin_config: Dict[str, Any]):
        super().__init__(core, plugin_config)

        self.plugin_config = load_plugin_config()
        minecraft_config = self.plugin_config.get("minecraft", {})

        # 从配置文件加载所有配置
        self.task_id: str = minecraft_config.get("mineland_task_id", "playground")

        # 智能体配置，默认为1个智能体
        self.agents_count: int = 1  # 目前硬编码为1，将来可以考虑加入配置
        self.agents_config: List[Dict[str, str]] = [{"name": f"MaiMai{i}"} for i in range(self.agents_count)]

        self.headless: bool = minecraft_config.get("mineland_headless", True)

        # 检查 image_size 是否为列表并有两个元素
        image_size_config = minecraft_config.get("mineland_image_size", [180, 320])
        if isinstance(image_size_config, list) and len(image_size_config) == 2:
            self.image_size: tuple[int, int] = tuple(image_size_config)
        else:
            self.logger.warning(f"配置的 image_size 无效: {image_size_config}，使用默认值 (180, 320)")
            self.image_size: tuple[int, int] = (180, 320)

        self.enable_low_level_action: bool = minecraft_config.get("mineland_enable_low_level_action", False)
        self.ticks_per_step: int = minecraft_config.get("mineland_ticks_per_step", 20)

        self.user_id: str = minecraft_config.get("user_id", "minecraft_bot")
        self.group_id_str: Optional[str] = minecraft_config.get("group_id")
        self.nickname: str = minecraft_config.get("nickname", "Minecraft Observer")
        self.json_prompt_prefix: str = minecraft_config.get(
            "json_prompt_prefix", "Minecraft环境状态如下，请提供JSON格式的动作指令："
        )

        # Mineland 实例
        self.mland: Optional[mineland.MineLand] = None
        # Mineland 状态变量
        self.current_obs: Optional[Any] = None  # 当前观察值
        self.current_code_info: Optional[List[Any]] = None  # 当前代码信息 (根据mineland_script.py是列表)
        self.current_event: Optional[List[List[Any]]] = None  # 当前事件 (根据mineland_script.py是列表的列表)
        self.current_done: bool = False  # 当前是否完成
        self.current_task_info: Optional[Dict[str, Any]] = None  # 当前任务信息
        self.current_step_num: int = 0  # 当前步数

    async def setup(self):
        await super().setup()
        # MaiCore 将通过此 handler 发送动作指令给插件
        self.core.register_websocket_handler("text", self.handle_maicore_response)

        self.logger.info("Minecraft 插件已加载，正在初始化 MineLand 环境...")
        try:
            self.mland = mineland.make(
                task_id=self.task_id,
                agents_count=self.agents_count,
                agents_config=self.agents_config,
                headless=self.headless,
                image_size=self.image_size,
                enable_low_level_action=self.enable_low_level_action,  # MineLand环境是否启用低级动作
                ticks_per_step=self.ticks_per_step,
            )
            self.logger.info(f"MineLand 环境 (Task ID: {self.task_id}) 初始化成功。")

            # 重置环境并获取初始观察
            self.current_obs = self.mland.reset()  # 所有智能体的观察值
            self.current_code_info = [None] * self.agents_count
            self.current_event = [[] for _ in range(self.agents_count)]
            self.current_done = False
            self.current_task_info = {}  # 通常在 step 后更新
            self.current_step_num = 0

            self.logger.info(f"MineLand 环境已重置，收到初始观察: {len(self.current_obs)} 个智能体。")

            # 发送初始状态给 MaiCore
            await self._send_state_to_maicore()

        except Exception as e:
            self.logger.exception(f"初始化 MineLand 环境失败: {e}", exc_info=True)
            # 可以在这里决定是否阻止插件加载或进行其他处理
            return  # 阻止进一步设置

    async def _send_state_to_maicore(self):
        """构建并发送当前Mineland状态给AmaidesuCore。"""

        state_payload = {
            "step": self.current_step_num,
            "observations": self.current_obs,
            "code_infos": self.current_code_info,
            "events": self.current_event,
            "is_done": self.current_done,
            "task_info": self.current_task_info,
            "low_level_action_enabled": self.enable_low_level_action,
        }

        try:
            # 使用 MinelandJSONEncoder 进行序列化，确保 NumPy 等类型正确处理
            # json_str_payload = json.dumps(state_payload, cls=MinelandJSONEncoder) # 直接传递字典，让MessageBase处理
            # prompted_message_content = f"{self.json_prompt_prefix}{json_str_payload}"

            # MaiCore可能期望一个更结构化的输入，而不仅仅是一个JSON字符串。
            # 我们将整个 state_payload 作为消息内容的一部分，而不是纯文本。
            # FormatInfo可能需要调整，或者MaiCore需要能处理dict类型的data。
            # 暂时，我们仍将其序列化为JSON字符串作为文本内容。

            prompted_message_content = f"{self.json_prompt_prefix}{json_serialize_mineland(state_payload)}"

        except Exception as e:
            self.logger.exception(f"序列化 Mineland 状态失败: {e}", exc_info=True)
            return

        current_time = int(time.time())
        message_id = f"mc_direct_{current_time}_{hash(prompted_message_content + str(self.user_id)) % 10000}"

        user_info = UserInfo(platform=self.core.platform, user_id=str(self.user_id), user_nickname=self.nickname)

        group_info_obj = None
        if self.group_id_str:
            try:
                parsed_group_id = int(self.group_id_str)
                group_info_obj = GroupInfo(
                    platform=self.core.platform,
                    group_id=parsed_group_id,
                )
            except ValueError:
                self.logger.warning(f"配置的 group_id '{self.group_id_str}' 不是有效的整数。将忽略 GroupInfo。")

        # format_info = FormatInfo(content_format="application/json", accept_format="application/json") # MaiCore需要能处理
        format_info = FormatInfo(content_format="text", accept_format="text")  # 保持文本格式，内容是JSON字符串

        additional_cfg = {
            "source_plugin": "minecraft",
            "low_level_action_enabled": self.enable_low_level_action,
        }

        message_info = BaseMessageInfo(
            platform=self.core.platform,
            message_id=message_id,
            time=current_time,
            user_info=user_info,
            group_info=group_info_obj,
            format_info=format_info,
            additional_config=additional_cfg,
            template_info=None,
        )

        # message_segment = Seg(type="json", data=state_payload) # 如果MaiCore支持
        message_segment = Seg(type="text", data=prompted_message_content)

        msg_to_maicore = MessageBase(
            message_info=message_info, message_segment=message_segment, raw_message=prompted_message_content
        )

        await self.core.send_to_maicore(msg_to_maicore)
        self.logger.info(
            f"已将 Mineland 状态 (step {self.current_step_num}, done: {self.current_done}) 发送给 MaiCore。"
        )
        self.logger.debug(f"发送给 MaiCore 的状态详情: {prompted_message_content[:300]}...")

    async def handle_maicore_response(self, message: MessageBase):
        """处理从 MaiCore 返回的动作指令。"""
        self.logger.info(f"收到来自 MaiCore 的响应: {message.message_segment.data}")

        if not self.mland:
            self.logger.exception("收到 MaiCore 响应，但 MineLand 环境未初始化。忽略消息。")
            return

        if message.message_segment.type != "text":
            self.logger.warning(
                f"MaiCore 返回的消息不是文本消息: type='{message.message_segment.type}'. 期望是'text' (包含JSON动作)。丢弃消息。"
            )
            return

        action_json_str = message.message_segment.data.strip()
        self.logger.debug(f"从 MaiCore 收到原始动作指令: {action_json_str}...")

        try:
            action_data = json.loads(action_json_str)
        except json.JSONDecodeError as e:
            self.logger.exception(f"解析来自 MaiCore 的动作 JSON 失败: {e}. 原始数据: {action_json_str}")
            # 可以考虑发送一个 no_op 动作或者通知错误
            # 目前，如果动作无效，我们将跳过此步骤并且不发送新状态。
            return

        # --- 解析动作并准备 current_actions (逻辑移植自 mineland_script.py) ---
        # 注意: 此处假设 AGENTS_COUNT 总是 1，与 mineland_script.py 中处理单 Agent 的逻辑对齐
        # 如果将来需要多 Agent，这里的逻辑需要扩展。
        current_actions = []
        parsed_action_for_log = "no_op"  # 用于日志记录的已解析动作字符串

        if self.agents_count == 1:
            if self.enable_low_level_action:
                agent_action_values = action_data.get("values")
                if (
                    agent_action_values
                    and isinstance(agent_action_values, list)
                    and len(agent_action_values) == 8  # mineland.LowLevelAction.dim 低级动作维度，通常为8
                ):
                    lla = mineland.LowLevelAction()
                    for i in range(len(agent_action_values)):  # 通常是8个组件
                        try:
                            component_value = int(agent_action_values[i])
                            lla[i] = component_value
                        except (ValueError, AssertionError) as err_lla:
                            logger.warning(
                                f"步骤 {self.current_step_num}: 低级别动作组件 {i} 值 '{agent_action_values[i]}' 无效 ({err_lla})。对该组件使用默认值 0。"
                            )
                            # lla[i] 将保留其默认值 (0)
                    current_actions = [lla]
                    parsed_action_for_log = f"LLA: {lla.data}"
                else:
                    logger.warning(
                        f"步骤 {self.current_step_num}: 低级别动作数据格式或长度错误 (期望列表长度8)，将使用 no_op。数据: {agent_action_values}"
                    )
                    current_actions = mineland.LowLevelAction.no_op(self.agents_count)
            else:  # 高级别动作
                action_type_str = action_data.get("action_type_name", MinecraftActionType.NO_OP.value)
                action_type = MinecraftActionType.from_string(action_type_str)
                parsed_agent_action_obj = None

                if action_type == MinecraftActionType.NEW:
                    action_param_code = action_data.get("code", "")
                    parsed_agent_action_obj = mineland.Action(type=mineland.Action.NEW, code=action_param_code)
                    parsed_action_for_log = f"NEW: {action_param_code[:50]}"  # 记录动作类型和代码片段
                elif action_type == MinecraftActionType.RESUME:
                    parsed_agent_action_obj = mineland.Action(type=mineland.Action.RESUME, code="")
                    parsed_action_for_log = "RESUME"  # 记录RESUME动作
                elif MinecraftActionType.is_chat_action(action_type):
                    # 在CHAT和CHAT_OP类型之间进行统一处理
                    chat_message = action_data.get("message", "")
                    # mineland.Action.chat_op 返回一个动作列表
                    current_actions = mineland.Action.chat_op(self.agents_count, chat_message)
                    parsed_action_for_log = f"CHAT: {chat_message[:50]}"  # 记录CHAT动作和消息片段
                    self.logger.info(f"执行聊天动作: '{chat_message}'")
                else:  # NO_OP 或未知动作类型
                    # parsed_agent_action_obj 保持 None，后续逻辑会生成 no_op
                    parsed_action_for_log = f"NO_OP (或未知动作: {action_type_str})"

                if parsed_agent_action_obj:  # 如果是 NEW 或 RESUME 动作
                    current_actions = [parsed_agent_action_obj]
                elif not current_actions:  # 如果不是 CHAT_OP 且 parsed_agent_action_obj 未设置 (即 NO_OP 或未知)
                    current_actions = mineland.Action.no_op(self.agents_count)
        else:  # 多智能体 (self.agents_count > 1)
            logger.warning(f"步骤 {self.current_step_num}: AGENTS_COUNT > 1 的动作解析尚未完全支持，将使用 no_op。")
            current_actions = (
                mineland.LowLevelAction.no_op(self.agents_count)
                if self.enable_low_level_action
                else mineland.Action.no_op(self.agents_count)
            )
            parsed_action_for_log = "fallback_no_op"  # 记录回退到no_op

        self.logger.info(f"步骤 {self.current_step_num}: MaiCore 返回动作，解析为: {parsed_action_for_log}")

        # 在 MineLand 环境中执行动作
        try:
            (
                next_obs,
                next_code_info,
                next_event,
                next_done,  # 这是每个智能体的布尔值列表
                next_task_info,
            ) = self.mland.step(action=current_actions)  # action 是一个动作列表

            self.current_obs = next_obs
            self.current_code_info = next_code_info
            self.current_event = next_event
            self.current_done = next_done
            self.current_task_info = next_task_info
            self.current_step_num += 1

            # 对于单Agent，通常直接取done[0]
            # 如果是多Agent，需要决定整体的done状态 (当前仅支持单Agent)
            effective_done = (
                self.current_done[0] if isinstance(self.current_done, list) and self.current_done else False
            )

            self.logger.debug(
                f"步骤 {self.current_step_num - 1} MineLand step 执行完毕。Effective Done: {effective_done}"
            )

            if effective_done:
                self.logger.info(f"任务在步骤 {self.current_step_num - 1} 完成。将重置环境并发送新初始状态。")
                self.current_obs = self.mland.reset()
                self.current_code_info = [None] * self.agents_count
                self.current_event = [[] for _ in range(self.agents_count)]
                self.current_done = False  # 重置 done 状态
                self.current_task_info = {}
                self.current_step_num = 0  # 为新的回合重置步数
                self.logger.info(f"环境已重置，收到新的初始观察。")

            # 发送新的状态给 MaiCore
            await self._send_state_to_maicore()

        except Exception as e:
            self.logger.exception(f"执行 Mineland step 或处理后续状态时出错: {e}", exc_info=True)
            # 此处可能需要更复杂的错误处理，例如尝试重置环境或停止插件

    async def cleanup(self):
        self.logger.info("正在清理 Minecraft 插件...")
        if self.mland:
            try:
                self.logger.info("正在关闭 MineLand 环境...")
                self.mland.close()
                self.logger.info("MineLand 环境已关闭。")
            except Exception as e:
                self.logger.exception(f"关闭 MineLand 环境时发生错误: {e}", exc_info=True)

        self.logger.info("Minecraft 插件清理完毕。")


# --- Plugin Entry Point ---
# --- 插件入口点 ---
plugin_entrypoint = MinecraftPlugin
