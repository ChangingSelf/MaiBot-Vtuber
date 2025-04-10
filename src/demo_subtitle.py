import asyncio
import sys
import os

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.neuro.synapse import synapse
from src.neuro.core import core
from src.sensor.demo_sensor import DemoSensor
from src.utils.logger import logger


async def main():
    """
    主函数
    """
    logger.info("启动字幕演示...")

    # 创建示例传感器
    demo_sensor = DemoSensor(synapse)

    # 设置字幕执行器
    demo_sensor.set_subtitle_actuator(core.subtitle_actuator)

    try:
        # 连接核心
        await core.connect()

        # 启动输入处理
        input_task = asyncio.create_task(core.process_input())

        # 运行示例传感器
        sensor_task = asyncio.create_task(demo_sensor.run())

        # 等待任务完成
        await asyncio.gather(input_task, sensor_task)

    except KeyboardInterrupt:
        logger.info("收到中断信号，正在关闭...")
    except Exception as e:
        logger.error(f"运行出错: {e}", exc_info=True)
    finally:
        # 断开连接
        await core.disconnect()
        logger.info("字幕演示已结束")


if __name__ == "__main__":
    # 运行主函数
    asyncio.run(main())
