import customtkinter as ctk
import time


class CustomSubtitle:
    def __init__(self, text="", theme="dark"):
        """
        初始化CustomTkinter字幕窗口

        参数:
            text (str): 初始字幕文本
            theme (str): 主题，可选 "dark" 或 "light"
        """
        # 设置主题
        ctk.set_appearance_mode(theme)
        ctk.set_default_color_theme("blue")

        # 创建主窗口
        self.root = ctk.CTk()
        self.root.title("字幕")
        self.root.attributes("-topmost", True)  # 窗口置顶
        self.root.overrideredirect(True)  # 无边框窗口

        # 创建字幕标签
        self.label = ctk.CTkLabel(self.root, text=text, font=("Arial", 24), wraplength=500, justify="left")
        self.label.pack(padx=20, pady=20)

        # 设置窗口大小和初始位置
        self._update_geometry()

        # 拖拽相关变量
        self.x = 0
        self.y = 0

        # 绑定鼠标事件
        self.root.bind("<Button-1>", self.on_drag_start)
        self.root.bind("<B1-Motion>", self.on_drag_motion)
        self.root.bind("<Double-Button-1>", self.on_close)

        # 设置透明度
        self.root.attributes("-alpha", 0.9)

    def _update_geometry(self):
        """更新窗口的几何尺寸和位置"""
        self.root.update_idletasks()
        width = self.label.winfo_reqwidth() + 40
        height = self.label.winfo_reqheight() + 40

        # 初始位置居中
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        x_pos = (screen_width // 2) - (width // 2)
        y_pos = screen_height - height - 50  # 屏幕底部向上偏移50像素

        self.root.geometry(f"{width}x{height}+{x_pos}+{y_pos}")

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

        # 限制窗口在屏幕内移动
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        win_width = self.root.winfo_width()
        win_height = self.root.winfo_height()

        new_x = max(0, min(new_x, screen_width - win_width))
        new_y = max(0, min(new_y, screen_height - win_height))

        self.root.geometry(f"+{new_x}+{new_y}")
        self.x, self.y = event.x_root, event.y_root

    def on_close(self, event):
        """双击关闭窗口"""
        self.root.quit()

    def update_text(self, new_text):
        """动态更新字幕文本"""
        self.label.configure(text=new_text)
        self._update_geometry()

    def set_theme(self, theme):
        """设置主题 (dark/light)"""
        ctk.set_appearance_mode(theme)

    def set_opacity(self, opacity):
        """设置窗口透明度 (0.0-1.0)"""
        self.root.attributes("-alpha", max(0.1, min(1.0, opacity)))

    def run(self):
        """启动CustomTkinter主循环"""
        self.root.mainloop()

    def close(self):
        """关闭窗口"""
        self.root.destroy()


if __name__ == "__main__":
    # 示例用法
    initial_text = "你好，这是一个CustomTkinter字幕！"
    app = CustomSubtitle(initial_text, theme="dark")

    # 示例：3秒后更新字幕内容
    app.root.after(3000, lambda: app.update_text("字幕已更新：现在显示的是新的内容。"))

    # 示例：6秒后再次更新，显示更长的文本以测试换行
    long_text = "这是另一段更长的文本，用于测试自动换行功能是否正常工作，以及窗口大小是否会相应调整。"
    app.root.after(6000, lambda: app.update_text(long_text))

    # 示例：9秒后切换主题
    app.root.after(9000, lambda: app.set_theme("light"))

    # 示例：12秒后调整透明度
    app.root.after(12000, lambda: app.set_opacity(0.7))

    # 示例：15秒后关闭
    # app.root.after(15000, app.close)  # 如果需要自动关闭，取消注释此行

    app.run()  # 启动主循环
