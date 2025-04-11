import customtkinter as ctk
import time
import threading
from typing import Optional, Tuple, Dict, Any


class Subtitle:
    def __init__(
        self,
        text: str = "",
        theme: str = "dark",
        font_family: str = "Arial",
        font_size: int = 24,
        text_color: str = "white",
        bg_color: Optional[str] = None,
        position: Tuple[int, int] = None,
        opacity: float = 0.9,
        animation_speed: int = 10,
        border_radius: int = 10,
        padding: int = 10,
    ):
        """
        初始化高级CustomTkinter字幕窗口

        参数:
            text (str): 初始字幕文本
            theme (str): 主题，可选 "dark" 或 "light"
            font_family (str): 字体
            font_size (int): 字体大小
            text_color (str): 文字颜色
            bg_color (str): 背景颜色，None则使用主题默认
            position (tuple): 初始位置 (x, y)，None则自动居中
            opacity (float): 初始透明度 (0.0-1.0)
            animation_speed (int): 动画速度 (1-20)
            border_radius (int): 边框圆角
            padding (int): 内边距
        """
        # 设置主题
        ctk.set_appearance_mode(theme)
        ctk.set_default_color_theme("blue")

        # 保存配置
        self.config = {
            "font_family": font_family,
            "font_size": font_size,
            "text_color": text_color,
            "bg_color": bg_color,
            "border_radius": border_radius,
            "padding": padding,
            "animation_speed": animation_speed,
        }

        # 创建主窗口
        self.root = ctk.CTk()
        self.root.title("高级字幕")
        self.root.attributes("-topmost", True)  # 窗口置顶
        self.root.overrideredirect(True)  # 无边框窗口
        self.root.resizable(True, True)  # 允许调整大小

        # 设置透明度
        self.root.attributes("-alpha", opacity)

        # 设置窗口背景色
        if bg_color:
            self.root.configure(fg_color=bg_color)

        # 创建字幕标签
        self.label = ctk.CTkLabel(
            self.root,
            text=text,
            font=(font_family, font_size),
            text_color=text_color,
            fg_color="transparent",  # 标签背景设为透明
            corner_radius=border_radius,
            wraplength=500,
            justify="left",
        )
        self.label.pack(padx=padding, pady=padding)

        self._update_geometry()

        # 如果指定了位置，则移动到该位置
        if position:
            self.root.geometry(f"+{position[0]}+{position[1]}")

        # 拖拽相关变量
        self.x = 0
        self.y = 0

        # 绑定鼠标事件
        self.root.bind("<Button-1>", self.on_drag_start)
        self.root.bind("<B1-Motion>", self.on_drag_motion)
        self.root.bind("<Double-Button-1>", self.on_close)

        # 动画相关变量
        self.animation_thread = None
        self.animation_running = False
        self.current_animation = None

    def _update_geometry(self):
        """更新窗口的几何尺寸和位置"""
        self.root.update_idletasks()
        width = self.label.winfo_reqwidth() + (self.config["padding"] * 2)
        height = self.label.winfo_reqheight() + (self.config["padding"] * 2)

        # 获取当前位置
        current_x = self.root.winfo_x()
        current_y = self.root.winfo_y()

        # 更新窗口大小和位置
        self.root.geometry(f"{width}x{height}+{current_x}+{current_y}")

    def on_drag_start(self, event):
        """记录初始位置"""
        self.x = event.x_root
        self.y = event.y_root

    def on_drag_motion(self, event):
        """计算并更新窗口位置"""
        delta_x = event.x_root - self.x
        delta_y = event.y_root - self.y
        new_x = self.root.winfo_x() + delta_x
        new_y = self.root.winfo_y() + delta_y
        # 更新窗口位置
        self.root.geometry(f"+{new_x}+{new_y}")
        self.x, self.y = event.x_root, event.y_root

    def on_close(self, event):
        """双击关闭窗口"""
        self.root.quit()

    def update_text(self, new_text: str, animate: bool = False):
        """
        动态更新字幕文本

        参数:
            new_text (str): 新文本
            animate (bool): 是否使用动画效果
        """
        if animate:
            self._animate_text_change(new_text)
        else:
            self.label.configure(text=new_text)
            self._update_geometry()

    def _animate_text_change(self, new_text: str):
        """文本变化动画"""
        if self.animation_running:
            self.animation_running = False
            if self.animation_thread:
                self.animation_thread.join()

        self.animation_running = True
        self.animation_thread = threading.Thread(target=self._text_animation_thread, args=(new_text,))
        self.animation_thread.daemon = True
        self.animation_thread.start()

    def _text_animation_thread(self, new_text: str):
        """文本动画线程"""
        current_text = self.label.cget("text")

        # 淡出效果
        for i in range(10, 0, -1):
            if not self.animation_running:
                return
            opacity = i / 10
            self.root.after(0, lambda o=opacity: self.root.attributes("-alpha", o))
            time.sleep(0.05 * (20 / self.config["animation_speed"]))

        # 更新文本
        self.root.after(0, lambda: self.label.configure(text=new_text))
        self.root.after(0, self._update_geometry)

        # 淡入效果
        for i in range(1, 11):
            if not self.animation_running:
                return
            opacity = i / 10
            self.root.after(0, lambda o=opacity: self.root.attributes("-alpha", o))
            time.sleep(0.05 * (20 / self.config["animation_speed"]))

        self.animation_running = False

    def set_theme(self, theme: str):
        """设置主题 (dark/light)"""
        ctk.set_appearance_mode(theme)

    def set_opacity(self, opacity: float):
        """设置窗口透明度 (0.0-1.0)"""
        self.root.attributes("-alpha", max(0.1, min(1.0, opacity)))

    def set_font(self, family: str = None, size: int = None):
        """设置字体"""
        current_font = self.label.cget("font")
        if isinstance(current_font, tuple):
            current_family, current_size = current_font
        else:
            current_family, current_size = "Arial", 24

        new_family = family if family else current_family
        new_size = size if size else current_size

        self.label.configure(font=(new_family, new_size))
        self._update_geometry()

    def set_text_color(self, color: str):
        """设置文字颜色"""
        self.label.configure(text_color=color)

    def set_bg_color(self, color: str):
        """设置背景颜色"""
        self.root.configure(fg_color=color)

    def set_border_radius(self, radius: int):
        """设置边框圆角"""
        self.label.configure(corner_radius=radius)
        self.config["border_radius"] = radius

    def set_padding(self, padding: int):
        """设置内边距"""
        self.config["padding"] = padding
        self._update_geometry()

    def set_position(self, x: int, y: int):
        """设置窗口位置"""
        self.root.geometry(f"+{x}+{y}")

    def get_position(self) -> Tuple[int, int]:
        """获取窗口位置"""
        return (self.root.winfo_x(), self.root.winfo_y())

    def get_size(self) -> Tuple[int, int]:
        """获取窗口大小"""
        return (self.root.winfo_width(), self.root.winfo_height())

    def run(self):
        """启动CustomTkinter主循环"""
        self.root.mainloop()

    def close(self):
        """关闭窗口"""
        self.animation_running = False
        if self.animation_thread:
            self.animation_thread.join()
        self.root.destroy()


if __name__ == "__main__":
    # 示例用法
    initial_text = "你好，这是一个高级CustomTkinter字幕！"
    app = Subtitle(
        text=initial_text,
        theme="dark",
        font_family="Microsoft YaHei",
        font_size=28,
        text_color="#FFFFFF",
        bg_color="#333333",
        opacity=0.95,
        animation_speed=15,
        border_radius=15,
        padding=25,
    )

    # 示例：3秒后更新字幕内容（带动画）
    app.root.after(3000, lambda: app.update_text("字幕已更新：现在显示的是新的内容。", animate=True))

    # 示例：6秒后再次更新，显示更长的文本以测试换行
    long_text = "这是另一段更长的文本，用于测试自动换行功能是否正常工作，以及窗口大小是否会相应调整。这是另一段更长的文本，用于测试自动换行功能是否正常工作，以及窗口大小是否会相应调整。这是另一段更长的文本，用于测试自动换行功能是否正常工作，以及窗口大小是否会相应调整。这是另一段更长的文本，用于测试自动换行功能是否正常工作，以及窗口大小是否会相应调整。"
    app.root.after(6000, lambda: app.update_text(long_text, animate=True))

    # 示例：9秒后切换主题
    app.root.after(9000, lambda: app.set_theme("light"))

    # 示例：12秒后调整透明度
    app.root.after(12000, lambda: app.set_opacity(0.7))

    # 示例：15秒后更改字体
    app.root.after(15000, lambda: app.set_font(family="SimHei", size=32))

    # 示例：18秒后更改颜色
    app.root.after(18000, lambda: app.set_text_color("#FF9900"))

    # 示例：21秒后更改背景色
    app.root.after(21000, lambda: app.set_bg_color("#222222"))

    # 示例：24秒后更改边框圆角
    app.root.after(24000, lambda: app.set_border_radius(25))

    # 示例：27秒后更改内边距
    app.root.after(27000, lambda: app.set_padding(30))

    # 示例：30秒后关闭
    # app.root.after(30000, app.close)  # 如果需要自动关闭，取消注释此行

    app.run()  # 启动主循环
