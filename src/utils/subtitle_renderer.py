import customtkinter as ctk
import time
import threading
from typing import Dict, Any
import logging

logger = logging.getLogger(__name__)


class SubtitleRenderer:
    """字幕渲染器 - 封装CustomTkinter字幕显示功能"""

    def __init__(
        self,
        theme: str = "dark",
        font_family: str = "微软雅黑",
        font_size: int = 24,
        text_color: str = "#FFFFFF",
        bg_color: str = "#333333BB",
        opacity: float = 0.8,
        animation_speed: int = 10,
        border_radius: int = 10,
        padding: int = 15,
        max_messages: int = 5,
        show_history: bool = True,
    ):
        """初始化字幕渲染器

        Args:
            theme: 主题，可选 "dark" 或 "light"
            font_family: 字体
            font_size: 字体大小
            text_color: 文字颜色
            bg_color: 背景颜色
            opacity: 初始透明度 (0.0-1.0)
            animation_speed: 动画速度 (1-20)
            border_radius: 边框圆角
            padding: 内边距
            max_messages: 最大消息数量
            show_history: 是否显示历史消息
        """
        self.config = {
            "theme": theme,
            "font_family": font_family,
            "font_size": font_size,
            "text_color": text_color,
            "bg_color": bg_color,
            "opacity": opacity,
            "animation_speed": animation_speed,
            "border_radius": border_radius,
            "padding": padding,
        }

        self.max_messages = max_messages
        self.show_history = show_history
        self.messages = []  # 消息队列
        self.root = None  # Tkinter根窗口
        self.frame = None  # 消息容器
        self.message_labels = []  # 消息标签列表
        self.is_running = False
        self.subtitle_thread = None

    def start(self):
        """启动字幕渲染器"""
        if self.is_running:
            logger.warning("字幕渲染器已经在运行中")
            return

        # 在新线程中启动UI
        self.subtitle_thread = threading.Thread(target=self._run_subtitle_window)
        self.subtitle_thread.daemon = True
        self.subtitle_thread.start()
        self.is_running = True
        logger.info("字幕渲染器已启动")

    def stop(self):
        """停止字幕渲染器"""
        if not self.is_running:
            return

        self.is_running = False
        if self.root:
            try:
                self.root.quit()
                self.root.destroy()
            except Exception as e:
                logger.error(f"关闭字幕窗口时出错: {e}")

        if self.subtitle_thread and self.subtitle_thread.is_alive():
            self.subtitle_thread.join(timeout=1.0)

        self.root = None
        self.frame = None
        self.message_labels = []
        logger.info("字幕渲染器已停止")

    def _run_subtitle_window(self):
        """运行字幕窗口（在新线程中调用）"""
        try:
            # 设置主题
            ctk.set_appearance_mode(self.config["theme"])
            ctk.set_default_color_theme("blue")

            # 创建主窗口
            self.root = ctk.CTk()
            self.root.title("MaiBot字幕")
            self.root.attributes("-topmost", True)  # 窗口置顶
            self.root.overrideredirect(True)  # 无边框窗口
            self.root.resizable(True, True)  # 允许调整大小

            # 设置透明度
            self.root.attributes("-alpha", self.config["opacity"])

            # 创建字幕容器
            self.frame = ctk.CTkFrame(
                self.root, fg_color=self.config["bg_color"], corner_radius=self.config["border_radius"]
            )
            self.frame.pack(fill="both", expand=True, padx=10, pady=10)

            # 初始化消息标签
            for i in range(self.max_messages):
                label = ctk.CTkLabel(
                    self.frame,
                    text="",
                    font=(self.config["font_family"], self.config["font_size"]),
                    text_color=self.config["text_color"],
                    fg_color="transparent",
                    wraplength=600,
                    justify="left",
                    anchor="w",
                )
                label.pack(fill="x", padx=self.config["padding"], pady=5, expand=False)
                self.message_labels.append(label)

            # 设置初始大小和位置
            width = 700
            height = 300
            screen_width = self.root.winfo_screenwidth()
            screen_height = self.root.winfo_screenheight()
            x_pos = (screen_width - width) // 2
            y_pos = screen_height - height - 50  # 靠近底部
            self.root.geometry(f"{width}x{height}+{x_pos}+{y_pos}")

            # 绑定拖拽事件
            self.root.bind("<Button-1>", self._on_drag_start)
            self.root.bind("<B1-Motion>", self._on_drag_motion)
            self.root.bind("<Double-Button-1>", self._on_double_click)

            # 启动主循环
            self.root.mainloop()

        except Exception as e:
            logger.error(f"字幕窗口运行出错: {e}")
            self.is_running = False

    def _on_drag_start(self, event):
        """开始拖拽"""
        self.x = event.x_root
        self.y = event.y_root

    def _on_drag_motion(self, event):
        """拖拽移动"""
        if not self.root:
            return

        delta_x = event.x_root - self.x
        delta_y = event.y_root - self.y
        new_x = self.root.winfo_x() + delta_x
        new_y = self.root.winfo_y() + delta_y
        self.root.geometry(f"+{new_x}+{new_y}")
        self.x, self.y = event.x_root, event.y_root

    def _on_double_click(self, event):
        """双击事件处理"""
        # 双击切换透明度
        current = float(self.root.attributes("-alpha"))
        if current > 0.5:
            self.root.attributes("-alpha", 0.3)
        else:
            self.root.attributes("-alpha", self.config["opacity"])

    def _update_subtitle_display(self):
        """更新字幕显示"""
        if not self.root or not self.is_running:
            return

        try:
            # 清空所有标签
            for label in self.message_labels:
                label.configure(text="")

            # 填充最新的消息
            visible_messages = self.messages[-self.max_messages :] if self.messages else []

            for i, message in enumerate(visible_messages):
                label_index = len(self.message_labels) - len(visible_messages) + i
                if 0 <= label_index < len(self.message_labels):
                    if message["type"] == "output":
                        # 输出消息（机器人回复）
                        text = f"【{message['user']}】{message['text']}"
                        self.message_labels[label_index].configure(text=text, text_color=self.config["text_color"])
                    elif message["type"] == "input":
                        # 输入消息（用户消息）
                        text = f"【{message['user']}】{message['text']}"
                        self.message_labels[label_index].configure(
                            text=text,
                            text_color="#AAFFAA",  # 用户消息使用不同颜色
                        )
                    elif message["type"] == "system":
                        # 系统消息
                        self.message_labels[label_index].configure(
                            text=message["text"],
                            text_color="#AAAAFF",  # 系统消息使用不同颜色
                        )
        except Exception as e:
            logger.error(f"更新字幕显示时出错: {e}")

    def handle_subtitle_data(self, subtitle_data: Dict[str, Any]):
        """处理字幕数据

        Args:
            subtitle_data: 字幕数据，格式为:
                {
                    "type": "subtitle",
                    "action": "show"|"hide"|"update"|"clear",
                    "id": "消息ID",
                    "text": "显示文本",
                    "user": "用户名称",
                    "message_type": "input"|"output"|"system"
                }
        """
        if not self.is_running:
            logger.warning("字幕渲染器未运行，无法处理字幕数据")
            return

        try:
            action = subtitle_data.get("action", "")

            if action == "show":
                # 添加新消息
                message = {
                    "id": subtitle_data.get("id", str(time.time())),
                    "text": subtitle_data.get("text", ""),
                    "user": subtitle_data.get("user", ""),
                    "type": subtitle_data.get("message_type", "system"),
                    "time": time.time(),
                }

                # 如果不显示历史，则清空消息列表
                if not self.show_history:
                    self.messages = []

                self.messages.append(message)

                # 限制消息数量
                if len(self.messages) > self.max_messages * 3:
                    self.messages = self.messages[-self.max_messages * 2 :]

            elif action == "hide":
                # 隐藏指定ID的消息
                message_id = subtitle_data.get("id")
                if message_id:
                    self.messages = [m for m in self.messages if m["id"] != message_id]

            elif action == "clear":
                # 清空所有消息
                self.messages = []

            # 更新显示
            self.root.after(0, self._update_subtitle_display)

        except Exception as e:
            logger.error(f"处理字幕数据时出错: {e}")

    def set_config(self, config_key: str, value: Any):
        """设置配置

        Args:
            config_key: 配置键
            value: 配置值
        """
        if config_key in self.config:
            self.config[config_key] = value

            # 应用某些配置
            if self.root:
                if config_key == "opacity":
                    self.root.attributes("-alpha", value)
                elif config_key == "theme":
                    ctk.set_appearance_mode(value)
                elif config_key in ["font_family", "font_size"]:
                    for label in self.message_labels:
                        label.configure(font=(self.config["font_family"], self.config["font_size"]))
                elif config_key == "text_color":
                    for label in self.message_labels:
                        label.configure(text_color=value)
                elif config_key == "bg_color" and self.frame:
                    self.frame.configure(fg_color=value)

            logger.debug(f"字幕渲染器配置已更新: {config_key} = {value}")

    def get_config(self) -> Dict[str, Any]:
        """获取当前配置

        Returns:
            Dict[str, Any]: 当前配置
        """
        return self.config.copy()

    def set_max_messages(self, max_messages: int):
        """设置最大消息数量

        Args:
            max_messages: 最大消息数量
        """
        self.max_messages = max(1, max_messages)

    def set_show_history(self, show_history: bool):
        """设置是否显示历史消息

        Args:
            show_history: 是否显示历史消息
        """
        self.show_history = show_history
