import tkinter as tk
import time  # 导入 time 模块


class TransparentSubtitle:
    def __init__(self, text):
        self.root = tk.Tk()
        self.root.overrideredirect(True)  # 移除窗口边框
        self.root.wm_attributes("-topmost", 1)  # 置顶显示
        self.root.wm_attributes("-transparentcolor", "gray10")  # 设置透明背景色为深灰色
        self.root.config(bg="gray10")  # 窗口背景设为深灰色

        self.label = tk.Label(
            self.root, text=text, bg="gray10", font=("Arial", 24), fg="white", justify=tk.LEFT, wraplength=500
        )  # 文字改为白色，背景改为深灰色
        self.label.pack(padx=20, pady=20)  # 增加内边距

        # 设置窗口大小和初始位置
        self._update_geometry()  # 调用更新几何尺寸的方法

        # 拖拽相关变量
        self.x = 0
        self.y = 0

        # 绑定鼠标事件
        self.root.bind("<Button-1>", self.on_drag_start)  # 单击开始拖拽
        self.root.bind("<B1-Motion>", self.on_drag_motion)  # 按住鼠标移动
        self.root.bind("<Double-Button-1>", self.on_close)  # 双击关闭

        # self.root.mainloop() # 移动到 __main__ 部分，以便于外部控制

    def _update_geometry(self):
        """更新窗口的几何尺寸和位置"""
        self.root.update_idletasks()  # 等待 Tkinter 完成内部更新
        width = self.label.winfo_reqwidth() + 40  # 增加宽度填充
        height = self.label.winfo_reqheight() + 40  # 增加高度填充
        # 初始位置居中
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        x_pos = (screen_width // 2) - (width // 2)
        y_pos = screen_height - height - 50  # 修改为屏幕底部向上偏移50像素
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
        self.root.quit()  # 使用 quit() 代替 destroy() 以便在 mainloop 外处理

    def update_text(self, new_text):
        """动态更新字幕文本"""
        self.label.config(text=new_text)
        self._update_geometry()  # 更新文本后重新计算窗口大小

    def run(self):
        """启动 Tkinter 主循环"""
        self.root.mainloop()

    def close(self):
        """关闭窗口"""
        self.root.destroy()


if __name__ == "__main__":
    initial_text = "你好，这是一个透明字幕！"
    app = TransparentSubtitle(initial_text)

    # 示例：3秒后更新字幕内容
    app.root.after(3000, lambda: app.update_text("字幕已更新：现在显示的是新的内容。"))

    # 示例：6秒后再次更新，显示更长的文本以测试换行
    long_text = "这是另一段更长的文本，用于测试自动换行功能是否正常工作，以及窗口大小是否会相应调整。"
    app.root.after(6000, lambda: app.update_text(long_text))

    # 示例：9秒后关闭
    # app.root.after(9000, app.close) # 如果需要自动关闭，取消注释此行

    app.run()  # 启动主循环
