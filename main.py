import asyncio
from src.sensor.danmaku_mock_sensor import danmaku_mock_sensor
from src.utils.logger import get_logger
import sys
import signal
import os
from src.neuro.core import core

logger = get_logger("main")


async def boot():
    await asyncio.gather(
        core.connect(),  # 建立与MaiMaiCore的连接
        core.process_input(),  # 处理传输给MaiMaiCore的输入
        danmaku_mock_sensor.connect(),  # 连接弹幕传感器
    )


async def halt():
    try:
        logger.info("正在关闭系统...")

        # 先关闭传感器
        await danmaku_mock_sensor.disconnect()
        logger.info("弹幕传感器已关闭")

        # 关闭核心
        await core.disconnect()
        logger.info("核心已关闭")

        # 取消所有剩余任务
        pending_tasks = [task for task in asyncio.all_tasks() if task is not asyncio.current_task()]

        logger.info(f"正在取消 {len(pending_tasks)} 个剩余任务")

        # 打印所有未完成任务的名称，帮助调试
        for i, task in enumerate(pending_tasks):
            logger.info(f"待取消任务 {i + 1}: {task.get_name()} - {task}")

        # 给每个任务发送取消信号
        for task in pending_tasks:
            task.cancel()

        # 设置超时等待所有任务完成
        try:
            await asyncio.wait_for(asyncio.gather(*pending_tasks, return_exceptions=True), timeout=2.0)
        except asyncio.TimeoutError:
            logger.warning("部分任务取消超时，强制退出")
            # 打印超时后仍未完成的任务
            still_pending = [t for t in pending_tasks if not t.done()]
            for i, task in enumerate(still_pending):
                logger.warning(f"超时未取消任务 {i + 1}: {task.get_name()} - {task}")

        logger.info("所有任务已关闭")

    except Exception as e:
        logger.error(f"关闭系统失败: {e}")
        import traceback

        logger.error(traceback.format_exc())


if __name__ == "__main__":
    # 设置信号处理
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        loop.run_until_complete(boot())
        loop.run_forever()
    except KeyboardInterrupt:
        logger.warning("收到中断信号，正在关闭...")
        loop.run_until_complete(halt())
        loop.close()
        logger.info("程序已完全退出，强制结束所有进程")
        # 强制结束程序
        os._exit(0)  # 使用os._exit强制退出，不会等待其他线程
    except Exception as e:
        logger.error(f"主程序异常: {str(e)}")
        if loop and not loop.is_closed():
            loop.run_until_complete(halt())
            loop.close()
        os._exit(1)
