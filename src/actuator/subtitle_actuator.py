import asyncio
import threading
import time
from typing import Optional, Dict, Any, List
from ..utils.subtitle import MultiMessageSubtitle
from ..neuro.synapse import Synapse, Neurotransmitter
from ..utils.logger import logger


class SubtitleActuator:
    """
    字幕执行器，用于在屏幕上显示输入输出过程
    """

    def __init__(self, synapse: Synapse, show_history: bool = True):
        """
        初始化字幕执行器

        参数:
            synapse: 突触对象，用于接收神经递质
            show_history: 是否显示历史消息，默认为True
        """
        self.synapse = synapse
        self.subtitle = None
        self.subtitle_thread = None
        self.running = False
        self.message_queue = asyncio.Queue()
        self.show_history = show_history

    async def connect(self):
        """
        连接突触，开始接收神经递质
        """
        logger.info("字幕执行器正在连接...")
        self.running = True

        # 启动字幕线程
        self.subtitle_thread = threading.Thread(target=self._run_subtitle)
        self.subtitle_thread.daemon = True
        self.subtitle_thread.start()

        # 启动消息处理循环
        asyncio.create_task(self._process_messages())

        # 订阅输出神经递质
        await self.synapse.subscribe_output(self._handle_output)

        logger.info("字幕执行器已连接")

    async def disconnect(self):
        """
        断开连接
        """
        logger.info("字幕执行器正在断开连接...")
        # 先取消订阅，这样不会再有新消息
        await self.synapse.unsubscribe_output(self._handle_output)
        logger.info("字幕执行器已取消订阅输出")

        # 停止处理消息的循环
        self.running = False

        # 关闭字幕
        try:
            if self.subtitle and hasattr(self.subtitle, "close"):
                self.subtitle.close()
                self.subtitle = None
                logger.info("字幕窗口已关闭")
        except Exception as e:
            logger.error(f"关闭字幕窗口时出错: {e}")

        # 最多等待1秒让线程自行结束
        if self.subtitle_thread and self.subtitle_thread.is_alive():
            logger.info("等待字幕线程结束...")
            self.subtitle_thread.join(timeout=1.0)
            if self.subtitle_thread.is_alive():
                logger.warning("字幕线程未能正常结束，但将继续关闭流程")

        logger.info("字幕执行器已完全断开连接")

    async def _handle_output(self, neurotransmitter: Neurotransmitter):
        """
        处理输出神经递质

        参数:
            neurotransmitter: 神经递质对象
        """
        # 将消息添加到队列
        message = {
            "type": "output",
            "text": neurotransmitter.raw_message,
            "user": neurotransmitter.user_info.user_nickname if neurotransmitter.user_info else "未知用户",
        }

        await self.message_queue.put(message)

    def _run_subtitle(self):
        """
        运行字幕窗口
        """
        try:
            # 创建字幕
            self.subtitle = MultiMessageSubtitle(
                text="等待消息...",
                theme="dark",
                font_family="Microsoft YaHei",
                font_size=24,
                text_color="#FFFFFF",
                bg_color="#333333",
                opacity=0.7,
                animation_speed=10,
                border_radius=10,
                padding=15,
                show_history=self.show_history,
            )

            # 设置初始位置（屏幕底部）
            screen_width = self.subtitle.root.winfo_screenwidth()
            screen_height = self.subtitle.root.winfo_screenheight()
            subtitle_width = 600
            subtitle_height = 200
            x_pos = (screen_width - subtitle_width) // 2
            y_pos = screen_height - subtitle_height - 50
            self.subtitle.root.geometry(f"{subtitle_width}x{subtitle_height}+{x_pos}+{y_pos}")

            # 添加周期性检查，当running变为False时退出循环
            def check_running():
                if not self.running and self.subtitle and self.subtitle.root:
                    try:
                        self.subtitle.root.quit()
                        return  # 不再继续调度
                    except Exception as e:
                        logger.error(f"退出字幕循环时出错: {e}")

                # 如果仍在运行，继续检查
                if self.subtitle and self.subtitle.root:
                    self.subtitle.root.after(100, check_running)

            # 开始检查循环
            self.subtitle.root.after(100, check_running)

            # 运行字幕
            self.subtitle.run()

        except Exception as e:
            logger.error(f"字幕线程出错: {e}", exc_info=True)

    async def _process_messages(self):
        """
        处理消息队列
        """
        while self.running:
            try:
                # 从队列获取消息
                message = await self.message_queue.get()

                # 只处理输出类型的消息
                if message["type"] == "output":
                    self.subtitle.add_message(message_type=message["type"], text=message["text"], user=message["user"])

                # 标记任务完成
                self.message_queue.task_done()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"处理消息时出错: {e}", exc_info=True)
