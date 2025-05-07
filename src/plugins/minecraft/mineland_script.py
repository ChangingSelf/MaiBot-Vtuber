import asyncio
import json
import websockets
import mineland
import numpy as np
import logging

# --- Configuration ---
WEBSOCKET_SERVER_URL = "ws://localhost:8766"  # 修改为你的 Amaidesu WebSocket 服务器地址
TASK_ID = "playground"  # 你想运行的 MineLand 任务 ID
AGENTS_COUNT = 1  # 目前脚本主要针对单个智能体进行动作解析
AGENTS_CONFIG = [{"name": f"AmaidesuBot{i}"} for i in range(AGENTS_COUNT)]
HEADLESS = True  # 是否以无头模式运行 (不显示游戏窗口)
IMAGE_SIZE = (180, 320)  # 期望的 RGB 观察图像尺寸 (高, 宽)
ENABLE_LOW_LEVEL_ACTION = False  # True: 使用低级别动作; False: 使用高级别动作
TICKS_PER_STEP = 20  # 每步对应的游戏 tick 数 (Minecraft 默认 20 ticks/秒)
MAX_STEPS = 5000  # 脚本运行的最大步数

# 设置日志级别
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


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
    """主函数，运行 MineLand 环境并与 WebSocket 服务器桥接。"""
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

        obs = mland.reset()
        logger.info(f"环境已重置，收到初始观察: {len(obs)} 个智能体。")

        # 为第一次发送准备初始的 "前一状态" 信息
        code_info = [None] * AGENTS_COUNT
        event = [[] for _ in range(AGENTS_COUNT)]  # 或者 [None] * AGENTS_COUNT
        done = False
        task_info = {}  # 或者 None

        async with websockets.connect(WEBSOCKET_SERVER_URL) as websocket:
            logger.info(f"已成功连接到 WebSocket 服务器: {WEBSOCKET_SERVER_URL}")

            for step_num in range(MAX_STEPS):
                if done:
                    logger.info("任务已完成，正在退出循环。")
                    break

                # 1. 准备并发送状态信息到服务器
                state_payload = {
                    "step": step_num,
                    "observations": numpy_to_list_recursive(obs),
                    "code_infos": numpy_to_list_recursive(code_info),
                    "events": numpy_to_list_recursive(event),
                    "is_done": done,
                    "task_info": numpy_to_list_recursive(task_info),
                    "low_level_action_enabled": ENABLE_LOW_LEVEL_ACTION,
                }

                # 使用自定义序列化方法
                try:
                    json_str = json_serialize_mineland(state_payload)
                    await websocket.send(json_str)
                    logger.debug(f"步骤 {step_num}: 已发送状态到服务器。")
                except TypeError as e:
                    logger.error(f"JSON序列化错误: {e}")
                    # 尝试打印出问题对象的类型信息以帮助调试
                    error_details = f"observations类型: {type(obs)}"
                    if isinstance(obs, list) and obs:
                        error_details += f", 第一个元素类型: {type(obs[0])}"
                    logger.error(error_details)
                    raise

                # 2. 从服务器接收动作指令
                action_response = await websocket.recv()
                logger.debug(f"步骤 {step_num}: 从服务器收到响应: {action_response}")

                action_data = json.loads(action_response)

                actions_for_step = []

                if AGENTS_COUNT == 1:  # 简化处理单个智能体的情况
                    parsed_action_for_agent = None
                    if ENABLE_LOW_LEVEL_ACTION:
                        # 服务器应发送 {"values": [int, int, ...]}
                        # LowLevelAction 通常是一个二维列表 [[act_agent0], [act_agent1]]
                        # 这里我们假设服务器为单个智能体发送其动作列表
                        agent_action_values = action_data.get("values")
                        if agent_action_values and isinstance(agent_action_values, list):
                            temp_actions = mineland.LowLevelAction.no_op(AGENTS_COUNT)
                            temp_actions[0] = agent_action_values  # 直接赋值给第一个智能体
                            parsed_action_for_agent = temp_actions  # 这是整个动作列表
                        else:
                            logger.warning(
                                f"步骤 {step_num}: 低级别动作数据格式错误，将使用 no_op。 数据: {action_data}"
                            )
                            parsed_action_for_agent = mineland.LowLevelAction.no_op(AGENTS_COUNT)
                        actions_for_step = parsed_action_for_agent  # LowLevelAction 本身就是列表
                    else:  # 高级别动作
                        # 服务器应发送 {"action_type_name": "NEW/RESUME/CHAT_OP/NO_OP", "code": "...", "message": "..."}
                        action_type_str = action_data.get("action_type_name", "NO_OP").upper()

                        # 使用字符串比较而不是直接访问可能不存在的属性
                        if action_type_str == "NEW":
                            # 创建一个NEW类型的动作，代码由code字段提供
                            action_param_code = action_data.get("code", "")
                            parsed_action_for_agent = mineland.Action(type=mineland.Action.NEW, code=action_param_code)
                        elif action_type_str == "RESUME":
                            # 创建一个RESUME类型的动作
                            parsed_action_for_agent = mineland.Action(type=mineland.Action.RESUME, code="")
                        elif action_type_str == "CHAT_OP" or action_type_str == "CHAT":
                            # 使用chat_op工厂方法创建聊天动作
                            chat_message = action_data.get("message", "")
                            # 对于一个智能体，我们直接返回一个动作列表
                            actions_for_step = mineland.Action.chat_op(AGENTS_COUNT, chat_message)
                            logger.info(f"步骤 {step_num}: 为智能体 0 创建聊天动作: {chat_message}")
                            # 继续下一个迭代，因为actions_for_step已经设置好了
                            continue
                        else:
                            # 默认使用no_op
                            actions_for_step = mineland.Action.no_op(AGENTS_COUNT)
                            logger.info(f"步骤 {step_num}: 未知动作类型 {action_type_str}，使用 no_op。")
                            # 继续下一个迭代，因为actions_for_step已经设置好了
                            continue

                        actions_for_step = [parsed_action_for_agent]

                    logger.info(f"步骤 {step_num}: 为智能体 0 解析的动作: {actions_for_step}")

                else:
                    # TODO: 实现多智能体动作的接收和解析逻辑
                    # 服务器需要发送一个动作列表，或者为每个智能体指定动作
                    logger.warning(f"步骤 {step_num}: 尚未完全支持 AGENTS_COUNT > 1 的动作解析，将使用 no_op。")
                    actions_for_step = (
                        mineland.Action.no_op(AGENTS_COUNT)
                        if not ENABLE_LOW_LEVEL_ACTION
                        else mineland.LowLevelAction.no_op(AGENTS_COUNT)
                    )

                # 3. 在 MineLand 环境中执行动作
                obs, code_info, event, done, task_info = mland.step(action=actions_for_step)
                logger.debug(f"步骤 {step_num}: MineLand step 执行完毕。Done: {done}")

            logger.info("已达到最大步数或任务已完成。")

    except websockets.exceptions.ConnectionClosedError as e:
        logger.error(f"WebSocket 连接关闭错误: {e}")
    except websockets.exceptions.WebSocketException as e:
        logger.error(f"WebSocket 错误: {e}")
    except ConnectionRefusedError:
        logger.error(f"无法连接到 WebSocket 服务器 {WEBSOCKET_SERVER_URL}。请确保服务器正在运行。")
    except json.JSONDecodeError as e:
        logger.error(f"JSON 解码错误: {e}. 收到的数据: {action_response if 'action_response' in locals() else 'N/A'}")
    except Exception as e:
        logger.error(f"发生意外错误: {e}", exc_info=True)
    finally:
        if mland:
            logger.info("正在关闭 MineLand 环境...")
            mland.close()
            logger.info("MineLand 环境已关闭。")
        logger.info("脚本执行完毕。")


if __name__ == "__main__":
    try:
        asyncio.run(run_mineland_bridge())
    except KeyboardInterrupt:
        logger.info("脚本被用户中断。")
