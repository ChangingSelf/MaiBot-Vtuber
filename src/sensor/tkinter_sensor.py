import tkinter as tk
from tkinter import simpledialog
from maim_message.message_base import UserInfo
from .sensor import Sensor
from ..utils.logger import logger
import asyncio
from ..neuro.core import message_queue
from ..utils.config import global_config


class TkinterSensor(Sensor):
    def __init__(self):
        self.running = False

    async def connect(self):
        """使用 Tkinter 输入框进行交互，并将消息放入 core 队列"""

        await asyncio.sleep(2)  # 给连接一些时间

        logger.info("Tkinter 交互已启动，将弹出输入框获取消息，输入'exit'退出")

        self.running = True

        def ask_string_dialog():
            """在当前线程创建临时 Tk 实例并显示对话框"""
            temp_root = tk.Tk()
            temp_root.withdraw()  # 隐藏主窗口
            # 尝试置顶，确保对话框可见 (可能需要根据系统调整)
            try:
                # 尝试置顶
                temp_root.attributes("-topmost", True)
            except tk.TclError:
                logger.warning("无法设置窗口置顶属性")
            user_input = None
            try:
                # 设置 owner 为当前活动窗口（可能更可靠）
                # try:
                #     # This might still fail if run from a non-GUI thread without proper setup
                #     owner = temp_root.winfo_toplevel()
                #     owner.attributes('-topmost', 1) # Bring owner window to top
                # except Exception as e:
                #     logger.warning(f"Could not set owner window properties: {e}")
                #     owner = temp_root # Fallback

                user_input = simpledialog.askstring("输入", "请输入消息:", parent=temp_root)
            finally:
                # 确保临时窗口总是被销毁
                temp_root.destroy()
            return user_input

        try:
            while self.running:
                # 在单独线程中执行 Tkinter 对话框逻辑
                user_input = await asyncio.to_thread(ask_string_dialog)

                if user_input is None:
                    logger.info("用户取消输入，正在退出 Tkinter 交互...")
                    self.running = False
                    break

                if user_input.lower() == "exit":
                    logger.info("正在退出 Tkinter 交互...")
                    self.running = False
                    break

                # 构造用户信息
                user_info = UserInfo(
                    platform=global_config.platform,
                    user_id=0,
                    user_nickname=global_config.sender_name,
                    user_cardname=global_config.sender_name,
                )

                # 将消息放入 core 的队列，而不是直接发送
                try:
                    # 使用 await 将 put 操作调度回事件循环
                    await message_queue.put((user_input, user_info))
                    logger.debug(f"用户输入已放入队列: {user_input[:20]}...")  # 记录放入成功
                except Exception as e:
                    logger.error(f"无法将消息放入 core 队列: {e}")
                    # 根据情况决定是否停止
                    # self.running = False
                    # break

        except KeyboardInterrupt:
            logger.info("检测到Ctrl+C，正在退出 Tkinter 交互...")
            self.running = False
        except Exception as e:
            # 记录更详细的错误信息，包括类型
            logger.error(f"Tkinter 交互出错: {type(e).__name__} - {str(e)}")
            self.running = False


tkinter_sensor = TkinterSensor()
