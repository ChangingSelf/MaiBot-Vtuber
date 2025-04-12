#!/usr/bin/env python3
import asyncio
import logging
import sys
import argparse
from typing import Optional

from src.core.brain_context import BrainContext
from src.sensors.danmaku_sensor import DanmakuSensor
from src.sensors.command_sensor import CommandSensor
from src.actuators.subtitle_actuator import SubtitleActuator
from src.actuators.live2d_actuator import Live2DActuator
from src.connectors.maibot_core_connector import MaiBotCoreConnector

# 设置根日志器
logging.basicConfig(
    level=logging.DEBUG,  # 改为DEBUG级别
    format="%(asctime)s - %(levelname)s - [%(name)s] - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler()],
)

logger = logging.getLogger(__name__)


async def setup_system(config_path: Optional[str] = None) -> BrainContext:
    """设置系统并注册组件

    Args:
        config_path: 配置文件路径

    Returns:
        BrainContext实例
    """
    # 创建大脑上下文
    context = BrainContext(config_path)

    # 创建并注册传感器
    try:
        danmaku_sensor = await context.create_neuron(DanmakuSensor)
        logger.debug(f"已创建弹幕传感器: {danmaku_sensor.name}")
    except Exception as e:
        logger.error(f"创建弹幕传感器失败: {e}")

    try:
        command_sensor = await context.create_neuron(CommandSensor)
        logger.debug(f"已创建命令传感器: {command_sensor.name}")
    except Exception as e:
        logger.error(f"创建命令传感器失败: {e}")

    # 创建并注册执行器
    try:
        subtitle_actuator = await context.create_neuron(SubtitleActuator)
        logger.debug(f"已创建字幕执行器: {subtitle_actuator.name}")
    except Exception as e:
        logger.error(f"创建字幕执行器失败: {e}")

    try:
        live2d_actuator = await context.create_neuron(Live2DActuator)
        logger.debug(f"已创建Live2D执行器: {live2d_actuator.name}")
    except Exception as e:
        logger.error(f"创建Live2D执行器失败: {e}")

    # 创建并注册MaiBot Core连接器
    try:
        logger.debug("开始创建MaiBot Core连接器...")
        core_connector = await context.create_neuron(MaiBotCoreConnector)
        logger.debug(f"已创建MaiBot Core连接器: {core_connector.name}")
    except Exception as e:
        logger.error(f"创建MaiBot Core连接器失败: {e}")

    return context


async def simulate_input(context: BrainContext) -> None:
    """模拟输入测试

    Args:
        context: BrainContext实例
    """
    # 获取传感器
    for neuron in context.neurons:
        if isinstance(neuron, DanmakuSensor):
            danmaku_sensor = neuron
            break
    else:
        logger.error("未找到DanmakuSensor")
        return

    # 模拟弹幕输入
    logger.info("模拟弹幕输入...")
    test_messages = [
        {"user": "用户1", "content": "你好，MaiBot！", "platform": "test"},
        {"user": "用户2", "content": "这是一条测试弹幕", "platform": "test"},
        {"user": "用户3", "content": "我好开心啊！", "platform": "test"},
        {"user": "管理员", "content": "!status", "platform": "test"},
    ]

    for msg in test_messages:
        logger.info(f"发送测试弹幕: {msg}")
        await danmaku_sensor.process_input(msg)
        await asyncio.sleep(1)


async def main() -> None:
    """主函数"""
    parser = argparse.ArgumentParser(description="MaiBot VTuber")
    parser.add_argument("--config", type=str, help="配置文件路径")
    parser.add_argument("--test", action="store_true", help="运行测试模式")
    parser.add_argument("--debug", action="store_true", help="启用调试模式")
    args = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
        logger.debug("已启用调试模式")

    try:
        # 设置系统
        context = await setup_system(args.config)

        # 启动系统
        await context.start()
        logger.info("系统启动成功！")

        # 测试模式
        if args.test:
            await simulate_input(context)
            await asyncio.sleep(5)  # 等待测试完成
            # await context.stop()
            # return

        # 等待系统运行
        try:
            # 保持程序运行
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            logger.info("收到停止信号，正在关闭系统...")
        finally:
            # 停止系统
            await context.stop()
    except Exception as e:
        logger.error(f"运行系统时出错: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
