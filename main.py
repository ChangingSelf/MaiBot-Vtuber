import asyncio
from src.sensor.danmaku_mock_sensor import danmaku_mock_sensor
from src.utils.logger import get_logger
import sys
from src.neuro.core import core

logger = get_logger("main")


async def boot():
    await asyncio.gather(
        core.connect(),
        core.process_input(),
        danmaku_mock_sensor.connect(),
    )


async def halt():
    try:
        logger.info("正在关闭Adapter...")
        await core.disconnect()
        tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    except Exception as e:
        logger.error(f"Adapter关闭失败: {e}")


if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(boot())
    except KeyboardInterrupt:
        logger.warning("收到中断信号，正在关闭...")
        loop.run_until_complete(halt())
    except Exception as e:
        logger.error(f"主程序异常: {str(e)}")
        if loop and not loop.is_closed():
            loop.run_until_complete(halt())
            loop.close()
        sys.exit(1)
