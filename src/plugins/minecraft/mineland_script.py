import asyncio
import json
import websockets
import mineland
import numpy as np
from loguru import logger
import sys

# --- Configuration ---
WEBSOCKET_SERVER_URL = "ws://localhost:8766"  # 修改为你的 Amaidesu WebSocket 服务器地址
TASK_ID = "playground"  # 你想运行的 MineLand 任务 ID
AGENTS_COUNT = 1  # 目前脚本主要针对单个智能体进行动作解析
AGENTS_CONFIG = [{"name": f"MaiMai{i}"} for i in range(AGENTS_COUNT)]
HEADLESS = True  # 是否以无头模式运行 (不显示游戏窗口)
IMAGE_SIZE = (180, 320)  # 期望的 RGB 观察图像尺寸 (高, 宽)
ENABLE_LOW_LEVEL_ACTION = True  # True: 使用低级别动作; False: 使用高级别动作
TICKS_PER_STEP = 20  # 每步对应的游戏 tick 数 (Minecraft 默认 20 ticks/秒)
MAX_STEPS = 5000  # 每个 WebSocket 会话的最大步数
RECONNECT_DELAY_SECONDS = 5  # 重连尝试之间的延迟

# 设置日志级别
logger.add(sys.stderr, level="DEBUG")
logger.add("logs/amaidesu_mineland_bridge.log", level="INFO")


class MinelandJSONEncoder(json.JSONEncoder):
    """自定义JSON编码器，处理MineLand特有的类型"""

    def default(self, obj):
        # 检查是否为Observation类型
        if hasattr(obj, "__dict__"):
            # 如果对象有__dict__属性，将其转换为字典
            return {k: v for k, v in obj.__dict__.items() if not k.startswith("_")}
        # 检查是否为NumPy数组
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
        # 检查是否为NumPy数据类型
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
        # 其他类型交给父类处理
        return super(MinelandJSONEncoder, self).default(obj)


def json_serialize_mineland(obj):
    """使用自定义编码器序列化MineLand对象"""
    return json.dumps(obj, cls=MinelandJSONEncoder)


# --- Helper Functions ---
# numpy_to_list_recursive is kept for potential direct use or deeper inspection,
# though MinelandJSONEncoder should handle most cases when applied to the whole payload.
def numpy_to_list_recursive(item):
    """递归地将 NumPy 数组和其他不可JSON序列化对象转换为可序列化类型。"""
    if isinstance(item, np.ndarray):
        return item.tolist()
    elif hasattr(item, "__dict__"):
        # 处理自定义类型（如Observation）
        return {
            k: numpy_to_list_recursive(v) for k, v in item.__dict__.items() if not k.startswith("_")
        }  # 跳过私有属性
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


async def run_mineland_bridge():
    """主函数，运行 MineLand 环境并与 WebSocket 服务器桥接，带重连机制。"""
    logger.info(f"正在初始化 MineLand 环境 (Task ID: {TASK_ID})...")
    mland = None
    try:
        mland = mineland.make(
            task_id=TASK_ID,
            agents_count=AGENTS_COUNT,
            agents_config=AGENTS_CONFIG,
            headless=HEADLESS,
            image_size=IMAGE_SIZE,
            enable_low_level_action=ENABLE_LOW_LEVEL_ACTION,
            ticks_per_step=TICKS_PER_STEP,
        )
        logger.info("MineLand 环境初始化成功。")

        # 主运行循环，处理重连
        while True:
            try:
                logger.info("正在尝试重置 MineLand 环境并开始新的 WebSocket 会话...")
                obs = mland.reset()
                logger.info(f"环境已重置，收到初始观察: {len(obs)} 个智能体。")

                # 为新会话准备初始状态信息
                code_info = [None] * AGENTS_COUNT
                event = [[] for _ in range(AGENTS_COUNT)]
                done = False  # 每个新会话开始时，done 为 False
                task_info = {}

                # ping_interval 和 ping_timeout 有助于保持连接活跃并检测断开
                async with websockets.connect(WEBSOCKET_SERVER_URL, ping_interval=20, ping_timeout=20) as websocket:
                    logger.info(f"已成功连接到 WebSocket 服务器: {WEBSOCKET_SERVER_URL}")

                    for step_num in range(MAX_STEPS):
                        if done:  # 如果上一步 mland.step() 将 done 设置为 True
                            logger.info(f"任务在步骤 {step_num - 1} (当前会话) 已完成。结束当前 WebSocket 会话。")
                            break  # 结束 for step_num 循环，外层 while True 将尝试重连/新会话

                        # 1. 准备并发送状态信息到服务器
                        state_payload = {
                            "step": step_num,
                            "observations": obs,  # MinelandJSONEncoder 会处理内部 NumPy 类型等
                            "code_infos": code_info,  # MinelandJSONEncoder 会处理
                            "events": event,  # MinelandJSONEncoder 会处理
                            "is_done": done,
                            "task_info": task_info,  # MinelandJSONEncoder 会处理
                            "low_level_action_enabled": ENABLE_LOW_LEVEL_ACTION,
                        }

                        try:
                            json_str = json_serialize_mineland(state_payload)
                            await websocket.send(json_str)
                            logger.debug(f"步骤 {step_num}: 已发送状态到服务器。")
                        except TypeError as e:  # 来自 json_serialize_mineland 的严重错误
                            logger.exception(f"步骤 {step_num}: JSON序列化错误: {e}")
                            # 此错误表示状态无法发送，当前会话无法继续
                            # 抛出一个 WebSocket 相关的异常，由外层捕获以触发重连
                            raise websockets.exceptions.AbortHandshake(status=1011, reason=f"Serialization error: {e}")
                        except websockets.exceptions.ConnectionClosed:
                            logger.exception(f"步骤 {step_num}: 发送状态时 WebSocket 连接关闭。")
                            raise  # 重新抛出，由外层 except 处理重连

                        # 2. 从服务器接收动作指令
                        action_response_str = None
                        action_data = None
                        try:
                            action_response_str = await websocket.recv()
                            logger.debug(f"步骤 {step_num}: 从服务器收到响应: {action_response_str}")
                            action_data = json.loads(action_response_str)
                        except websockets.exceptions.ConnectionClosed:
                            logger.exception(f"步骤 {step_num}: 接收动作时 WebSocket 连接关闭。")
                            raise  # 重新抛出，由外层 except 处理重连
                        except json.JSONDecodeError as e:
                            logger.exception(f"步骤 {step_num}: JSON 解码错误: {e}. 收到的数据: {action_response_str}")
                            logger.warning(f"步骤 {step_num}: 跳过损坏的动作消息，将使用 no_op。")
                            # action_data 将保持为 None，后续逻辑会处理并使用 no_op

                        # 解析动作并准备 current_actions
                        current_actions = []
                        if action_data:  # 仅当 action_data 有效 (JSON 解析成功) 时解析
                            if AGENTS_COUNT == 1:
                                # parsed_agent_action_list = None # No longer needed for LLA path
                                parsed_agent_action_obj = None  # 用于高级别单个动作

                                if ENABLE_LOW_LEVEL_ACTION:
                                    agent_action_values = action_data.get("values")
                                    # low_level_action.py shows self.data has 8 components.
                                    if (
                                        agent_action_values
                                        and isinstance(agent_action_values, list)
                                        and len(agent_action_values) == 8
                                    ):
                                        lla = (
                                            mineland.LowLevelAction()
                                        )  # Creates an LLA with self.data = [0,0,0,0,0,0,0,0]
                                        valid_lla_components = True
                                        for i in range(8):  # There are 8 components
                                            try:
                                                component_value = int(agent_action_values[i])
                                                lla[i] = (
                                                    component_value  # Uses LowLevelAction.__setitem__ which validates
                                                )
                                            except ValueError:
                                                logger.warning(
                                                    f"步骤 {step_num}: 低级别动作组件 {i} 值 '{agent_action_values[i]}' 不是有效整数。对该组件使用默认值 0。"
                                                )
                                                # lla[i] will retain its default from LowLevelAction() initialization (0)
                                                # Or, we could decide to invalidate the whole LLA if one component is bad.
                                                # For now, allow partial application with defaults for bad components.
                                            except (
                                                AssertionError
                                            ) as e_assert:  # Catches out-of-range from LowLevelAction.__setitem__
                                                logger.warning(
                                                    f"步骤 {step_num}: 低级别动作组件 {i} 值 ({agent_action_values[i]}) 无效: {e_assert}。对该组件使用默认值 0。"
                                                )
                                                # lla[i] will retain its default.
                                        current_actions = [lla]
                                    else:
                                        if not (agent_action_values and isinstance(agent_action_values, list)):
                                            logger.warning(
                                                f"步骤 {step_num}: 低级别动作数据格式错误 (期望列表，得到 {type(agent_action_values)})，将使用 no_op。 数据: {action_data}"
                                            )
                                        elif not isinstance(agent_action_values, list) or len(agent_action_values) != 8:
                                            logger.warning(
                                                f"步骤 {step_num}: 低级别动作数据长度错误 (期望 8，得到 {len(agent_action_values) if isinstance(agent_action_values, list) else 'N/A'})，将使用 no_op。 数据: {agent_action_values}"
                                            )
                                        current_actions = mineland.LowLevelAction.no_op(AGENTS_COUNT)
                                else:  # 高级别动作
                                    action_type_str = action_data.get("action_type_name", "NO_OP").upper()

                                    if action_type_str == "NEW":
                                        action_param_code = action_data.get("code", "")
                                        parsed_agent_action_obj = mineland.Action(
                                            type=mineland.Action.NEW, code=action_param_code
                                        )
                                    elif action_type_str == "RESUME":
                                        parsed_agent_action_obj = mineland.Action(type=mineland.Action.RESUME, code="")
                                    elif action_type_str == "CHAT_OP" or action_type_str == "CHAT":
                                        chat_message = action_data.get("message", "")
                                        current_actions = mineland.Action.chat_op(
                                            AGENTS_COUNT, chat_message
                                        )  # 直接赋值给 current_actions
                                        logger.info(f"步骤 {step_num}: 为智能体创建聊天动作: {chat_message}")
                                    else:  # NO_OP 或未知
                                        if action_type_str != "NO_OP":  # 如果是未知类型
                                            logger.info(
                                                f"步骤 {step_num}: 未知高级动作类型 '{action_type_str}'，使用 no_op。"
                                            )
                                        # parsed_agent_action_obj 保持 None，后续逻辑会生成 no_op

                                    if parsed_agent_action_obj:  # 如果是 NEW 或 RESUME
                                        current_actions = [parsed_agent_action_obj]
                                    elif (
                                        not current_actions
                                    ):  # 如果不是 CHAT_OP 且 parsed_agent_action_obj 未设置 (即 NO_OP 或未知)
                                        current_actions = mineland.Action.no_op(AGENTS_COUNT)

                                # Corrected logging logic for single agent actions
                                if current_actions:  # Only log if there are actions determined
                                    log_this_specific_action = True  # Default to logging the action
                                    if not ENABLE_LOW_LEVEL_ACTION:
                                        # This suppression logic is only for high-level actions.
                                        # action_type_str is defined in the high-level action parsing path.
                                        # current_actions[0] is expected to be a mineland.Action instance.
                                        if (
                                            len(current_actions) == 1
                                            and isinstance(current_actions[0], mineland.Action)  # Safety check
                                            and current_actions[0].type == mineland.Action.NO_OP
                                            and action_type_str == "NO_OP"
                                        ):  # action_type_str is in scope here
                                            log_this_specific_action = False
                                    # For low-level actions, log_this_specific_action remains True by default,
                                    # so they are always logged if present (matching previous implicit behavior).

                                    if log_this_specific_action:
                                        logger.info(f"步骤 {step_num}: 为智能体 0 解析的动作: {current_actions}")

                            else:  # 多智能体 (AGENTS_COUNT > 1)
                                logger.warning(
                                    f"步骤 {step_num}: 尚未完全支持 AGENTS_COUNT > 1 的动作解析，将使用 no_op。"
                                )
                                current_actions = (
                                    mineland.Action.no_op(AGENTS_COUNT)
                                    if not ENABLE_LOW_LEVEL_ACTION
                                    else mineland.LowLevelAction.no_op(AGENTS_COUNT)
                                )

                        else:  # action_data 无效 (例如 JSON 解析失败或服务器未发送有效数据)
                            logger.warning(f"步骤 {step_num}: 无有效动作数据或解析失败，将使用 no_op。")
                            current_actions = (
                                mineland.LowLevelAction.no_op(AGENTS_COUNT)
                                if ENABLE_LOW_LEVEL_ACTION
                                else mineland.Action.no_op(AGENTS_COUNT)
                            )

                        # 3. 在 MineLand 环境中执行动作
                        obs, code_info, event, done, task_info = mland.step(action=current_actions)
                        logger.debug(f"步骤 {step_num}: MineLand step 执行完毕。Done: {done}")

                    # for step_num 循环结束 (因 MAX_STEPS 或 done=True)
                    if not done:  # 如果是因为 MAX_STEPS 结束
                        logger.info(f"WebSocket 会话因达到 MAX_STEPS ({MAX_STEPS}) 而结束。")
                    # 不需要 break 或 continue，外层 while True 会使其尝试重连和新会话

            except (
                websockets.exceptions.ConnectionClosed,
                websockets.exceptions.ConnectionClosedError,
                websockets.exceptions.ConnectionClosedOK,  # 正常关闭也应尝试重连，除非脚本主动退出
                websockets.exceptions.WebSocketException,  # 包括 AbortHandshake 等更具体的 WebSocket 错误
                ConnectionRefusedError,  # 连接被拒绝
                OSError,  # 例如: [Errno 10054] 远程主机强迫关闭了一个现有的连接, [Errno 11001] getaddrinfo failed
            ) as e:
                logger.exception(f"WebSocket 连接错误或会话中断: {type(e).__name__} - {e}.")
                logger.info(f"将在 {RECONNECT_DELAY_SECONDS} 秒后尝试重连...")
                await asyncio.sleep(RECONNECT_DELAY_SECONDS)
                # continue 会让外层 while True 循环继续，开始新的连接尝试和 mland.reset()
            # 其他意外错误（例如 Mineland 内部的严重错误）不在此处捕获，它们将导致程序通过
            # __main__ 中的 except Exception 来终止，这样可以暴露更深层次的、非网络相关的问题。

    finally:
        if mland:
            logger.info("正在关闭 MineLand 环境...")
            mland.close()
            logger.info("MineLand 环境已关闭。")
        logger.info("Amaidesu-MineLand Bridge 脚本执行终止。")


if __name__ == "__main__":
    try:
        asyncio.run(run_mineland_bridge())
    except KeyboardInterrupt:
        logger.info("脚本被用户中断 (KeyboardInterrupt)。正在清理并退出...")
    except Exception as e:  # 捕获从 run_mineland_bridge 抛出的未在此处理的意外错误
        logger.exception(f"脚本因意外错误而终止: {e}")
    finally:
        # mland.close() 已经在 run_mineland_bridge 的 finally 中处理
        logger.info("Amaidesu-MineLand Bridge 已关闭。")
