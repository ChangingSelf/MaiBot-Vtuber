import asyncio
import threading
import time
from typing import Optional, Dict, Any, List
from src.actuator.advanced_subtitle import Subtitle
from src.neuro.synapse import Synapse, Neurotransmitter
from src.utils.logger import logger


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
        self.max_messages = 5  # 最多显示的消息数量
        self.messages: List[Dict[str, Any]] = []  # 存储消息历史
        self.show_history = show_history  # 是否显示历史消息

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
        self.running = False

        # 取消订阅
        await self.synapse.unsubscribe_output(self._handle_output)

        # 关闭字幕
        if self.subtitle:
            self.subtitle.close()
            self.subtitle = None

        logger.info("字幕执行器已断开连接")

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
            "time": time.strftime("%H:%M:%S"),
        }

        await self.message_queue.put(message)

    def _run_subtitle(self):
        """
        运行字幕窗口
        """
        # 创建字幕
        self.subtitle = Subtitle(
            text="等待消息...",
            theme="dark",
            font_family="Microsoft YaHei",
            font_size=24,
            text_color="#FFFFFF",
            bg_color="#333333",
            opacity=0.5,
            animation_speed=10,
            border_radius=10,
            padding=15,
        )

        # 设置初始位置（屏幕底部）
        screen_width = self.subtitle.root.winfo_screenwidth()
        screen_height = self.subtitle.root.winfo_screenheight()
        subtitle_width = 600
        subtitle_height = 200
        x_pos = (screen_width - subtitle_width) // 2
        y_pos = screen_height - subtitle_height - 50
        self.subtitle.root.geometry(f"{subtitle_width}x{subtitle_height}+{x_pos}+{y_pos}")

        # 运行字幕
        self.subtitle.run()

    async def _process_messages(self):
        """
        处理消息队列
        """
        while self.running:
            try:
                # 从队列获取消息
                message = await self.message_queue.get()

                # 添加到消息历史
                self.messages.append(message)

                # 如果消息数量超过最大值，移除最旧的消息
                if len(self.messages) > self.max_messages:
                    self.messages.pop(0)

                # 更新字幕
                self._update_subtitle()

                # 标记任务完成
                self.message_queue.task_done()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"处理消息时出错: {e}", exc_info=True)

    def _update_subtitle(self):
        """
        更新字幕内容
        """
        if not self.subtitle:
            return

        # 构建字幕文本
        if self.show_history:
            text = "消息历史:\n\n"
            for msg in self.messages:
                prefix = "→ " if msg["type"] == "output" else "← "
                text += f"{prefix}[{msg['time']}] {msg['user']}: {msg['text']}\n"
        else:
            # 只显示最新一条消息
            if self.messages:
                latest_msg = self.messages[-1]
                prefix = "→ " if latest_msg["type"] == "output" else "← "
                text = f"{prefix}[{latest_msg['time']}] {latest_msg['user']}: {latest_msg['text']}"
            else:
                text = "------"

        # 更新字幕
        self.subtitle.update_text(text, animate=False)

    def add_input_message(self, text: str, user: str):
        """
        添加输入消息

        参数:
            text: 消息文本
            user: 用户名
        """
        message = {"type": "input", "text": text, "user": user, "time": time.strftime("%H:%M:%S")}

        # 添加到消息历史
        self.messages.append(message)

        # 如果消息数量超过最大值，移除最旧的消息
        if len(self.messages) > self.max_messages:
            self.messages.pop(0)

        # 更新字幕
        self._update_subtitle()
