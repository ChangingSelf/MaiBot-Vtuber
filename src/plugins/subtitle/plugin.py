# Amaidesu Subtitle Plugin (Screen Display): src/plugins/subtitle/plugin.py

import contextlib
import time
import threading  # 用于运行 GUI
import queue  # 用于线程间通信
from typing import Any, Dict, Optional
import tkinter as tk

try:
    import customtkinter as ctk

    CTK_AVAILABLE = True
except ImportError:
    ctk = None
    CTK_AVAILABLE = False

from src.core.plugin_manager import BasePlugin
from src.core.amaidesu_core import AmaidesuCore


class OutlineLabel:
    """自定义标签，支持文字描边效果"""

    def __init__(
        self,
        master,
        text="",
        font=None,
        text_color="white",
        outline_color="black",
        outline_width=2,
        outline_enabled=True,
        **kwargs,
    ):
        if not CTK_AVAILABLE or ctk is None:
            raise ImportError("CustomTkinter not available")

        # 移除描边相关参数，避免传递给父类
        kwargs.pop("outline_color", None)
        kwargs.pop("outline_width", None)
        kwargs.pop("outline_enabled", None)

        # 过滤掉可能导致问题的参数
        safe_kwargs = {k: v for k, v in kwargs.items() if k not in ["bg_color", "text_color"]}

        # 使用 CTkFrame 作为容器而不是 CTkLabel 来避免布局冲突
        self.container_frame = ctk.CTkFrame(master, **safe_kwargs)

        self.display_text = text
        self.text_color = text_color
        self.outline_color = outline_color
        self.outline_width = outline_width
        self.outline_enabled = outline_enabled
        self.font_obj = font

        # 创建 Canvas 来绘制带描边的文字
        self.canvas = tk.Canvas(self.container_frame, highlightthickness=0, bd=0)
        self.canvas.pack(fill="both", expand=True)

        # 绑定重绘事件
        self.canvas.bind("<Configure>", self._on_canvas_configure)

        # 初始绘制
        self.container_frame.after(1, self._draw_text)

    def pack(self, **kwargs):
        """包装 pack 方法"""
        self.container_frame.pack(**kwargs)

    def bind(self, event, callback):
        """包装 bind 方法"""
        self.container_frame.bind(event, callback)

    def cget(self, option):
        """包装 cget 方法"""
        try:
            return self.container_frame.cget(option)
        except Exception:
            return None

    def after(self, delay, callback):
        """包装 after 方法"""
        return self.container_frame.after(delay, callback)

    def _on_canvas_configure(self, event):
        """Canvas 尺寸改变时重绘文字"""
        self._draw_text()

    def _draw_text(self):
        """绘制带描边的文字"""
        if not self.display_text:
            return

        self.canvas.delete("all")

        # 设置 Canvas 背景
        try:
            bg_color = self.cget("bg")
            if bg_color and bg_color != "transparent":
                self.canvas.configure(bg=bg_color)
            else:
                # 使用默认背景
                self.canvas.configure(bg="gray15")
        except Exception:
            self.canvas.configure(bg="gray15")

        # 获取 Canvas 尺寸
        canvas_width = self.canvas.winfo_width()
        canvas_height = self.canvas.winfo_height()

        if canvas_width <= 1 or canvas_height <= 1:
            return

        # 计算文字位置 (居中)
        x = canvas_width // 2
        y = canvas_height // 2

        # 绘制描边 (如果启用)
        if self.outline_enabled and self.outline_width > 0:
            for dx in range(-self.outline_width, self.outline_width + 1):
                for dy in range(-self.outline_width, self.outline_width + 1):
                    if dx == 0 and dy == 0:
                        continue
                    if dx * dx + dy * dy <= self.outline_width * self.outline_width:
                        if self.font_obj:
                            self.canvas.create_text(
                                x + dx,
                                y + dy,
                                text=self.display_text,
                                font=self.font_obj,
                                fill=self.outline_color,
                                anchor="center",
                                width=canvas_width - 20,
                            )
                        else:
                            self.canvas.create_text(
                                x + dx,
                                y + dy,
                                text=self.display_text,
                                fill=self.outline_color,
                                anchor="center",
                                width=canvas_width - 20,
                            )

        # 绘制主文字
        if self.font_obj:
            self.canvas.create_text(
                x,
                y,
                text=self.display_text,
                font=self.font_obj,
                fill=self.text_color,
                anchor="center",
                width=canvas_width - 20,
            )
        else:
            self.canvas.create_text(
                x, y, text=self.display_text, fill=self.text_color, anchor="center", width=canvas_width - 20
            )

    def configure_text(self, text="", **kwargs):
        """更新文字内容和样式"""
        if text != "":
            self.display_text = text

        if "text_color" in kwargs:
            self.text_color = kwargs["text_color"]
        if "outline_color" in kwargs:
            self.outline_color = kwargs["outline_color"]
        if "outline_width" in kwargs:
            self.outline_width = kwargs["outline_width"]
        if "outline_enabled" in kwargs:
            self.outline_enabled = kwargs["outline_enabled"]
        if "font" in kwargs:
            self.font_obj = kwargs["font"]

        self._draw_text()


class SubtitlePlugin(BasePlugin):
    """
    接收语音文本并显示在自定义的置顶窗口中，支持描边和半透明背景
    """

    def __init__(self, core: AmaidesuCore, plugin_config: Dict[str, Any]):
        super().__init__(core, plugin_config)
        self.config = self.plugin_config

        # --- 检查依赖 ---
        if not CTK_AVAILABLE:
            self.logger.error("CustomTkinter库不可用,字幕插件已禁用。")
            self.enabled = False
            return

        # --- GUI 配置 ---
        self.window_width = self.config.get("window_width", 800)
        self.window_height = self.config.get("window_height", 100)
        self.window_offset_y = self.config.get("window_offset_y", 100)
        self.font_family = self.config.get("font_family", "Microsoft YaHei UI")
        self.font_size = self.config.get("font_size", 28)
        self.font_weight = self.config.get("font_weight", "bold")
        self.text_color = self.config.get("text_color", "white")

        # --- 描边配置 ---
        self.outline_enabled = self.config.get("outline_enabled", True)
        self.outline_color = self.config.get("outline_color", "black")
        self.outline_width = self.config.get("outline_width", 2)

        # --- 背景配置 ---
        self.background_enabled = self.config.get("background_enabled", True)
        self.background_color = self.config.get("background_color", "#000000")
        self.background_opacity = self.config.get("background_opacity", 0.7)
        self.corner_radius = self.config.get("corner_radius", 15)

        # --- 行为配置 ---
        self.fade_delay_seconds = self.config.get("fade_delay_seconds", 3)
        self.auto_hide = self.config.get("auto_hide", True)
        self.window_alpha = self.config.get("window_alpha", 0.95)

        # --- 线程和状态 ---
        self.text_queue = queue.Queue()
        self.gui_thread: Optional[threading.Thread] = None
        self.root = None  # type: Optional[Any]
        self.text_label = None  # type: Optional[OutlineLabel]
        self.background_frame = None  # type: Optional[Any]
        self.last_voice_time = time.time()
        self.is_running = True
        self.is_visible = False  # 窗口是否可见

        self.logger.info("SubtitlePlugin (CustomTkinter) 初始化完成。")

    def _run_gui(self):
        """运行 GUI 线程"""
        if not CTK_AVAILABLE or ctk is None:
            self.logger.error("CustomTkinter not available")
            return

        try:
            # 设置 CustomTkinter 外观
            ctk.set_appearance_mode("dark")
            ctk.set_default_color_theme("blue")

            self.root = ctk.CTk()
            self.root.title("Amaidesu Subtitle")
            self.root.protocol("WM_DELETE_WINDOW", self._on_closing)

            # --- 窗口属性 ---
            self.root.attributes("-topmost", True)
            self.root.attributes("-alpha", self.window_alpha)
            self.root.overrideredirect(True)  # 无边框

            # --- 窗口大小和位置 ---
            screen_width = self.root.winfo_screenwidth()
            screen_height = self.root.winfo_screenheight()
            x = (screen_width - self.window_width) // 2
            y = screen_height - self.window_height - self.window_offset_y
            self.root.geometry(f"{self.window_width}x{self.window_height}+{x}+{y}")

            # 设置窗口透明背景
            if not self.background_enabled:
                try:
                    # 尝试设置透明色，如果失败就使用默认背景
                    self.root.attributes("-transparentcolor", "black")
                except Exception as e:
                    self.logger.debug(f"无法设置透明背景: {e}")

            # --- 创建背景框架 (如果启用) ---
            if self.background_enabled:
                self.background_frame = ctk.CTkFrame(
                    self.root, fg_color=self.background_color, corner_radius=self.corner_radius
                )
                self.background_frame.pack(fill="both", expand=True, padx=5, pady=5)
                parent = self.background_frame
            else:
                parent = self.root

            # --- 创建自定义文本标签 ---
            font_tuple = (self.font_family, self.font_size, self.font_weight)
            self.text_label = OutlineLabel(
                parent,
                text="",
                font=font_tuple,
                text_color=self.text_color,
                outline_color=self.outline_color,
                outline_width=self.outline_width,
                outline_enabled=self.outline_enabled,
                bg_color=self.background_color if self.background_enabled else None,
            )
            self.text_label.pack(expand=True, fill="both", padx=10, pady=5)

            # --- 绑定事件 ---
            def bind_drag_events(widget):
                widget.bind("<Button-1>", self._start_move)
                widget.bind("<B1-Motion>", self._on_move)
                widget.bind("<Button-3>", lambda e: self._on_closing())

            bind_drag_events(self.root)
            if self.background_frame:
                bind_drag_events(self.background_frame)
            bind_drag_events(self.text_label)
            if hasattr(self.text_label, "canvas"):
                bind_drag_events(self.text_label.canvas)

            # 初始隐藏窗口
            self.root.withdraw()
            self.is_visible = False

            # --- 启动定时任务 ---
            self.root.after(100, self._check_queue)
            self.root.after(100, self._check_auto_hide)

            self.logger.info("Subtitle GUI 启动成功。")
            self.root.mainloop()

        except Exception as e:
            self.logger.error(f"运行 Subtitle GUI 时出错: {e}", exc_info=True)
        finally:
            self.logger.info("Subtitle GUI 线程结束。")
            if self.root:
                with contextlib.suppress(Exception):
                    self.root.quit()
            self.is_running = False

    def _check_queue(self):
        """检查队列中的新文本"""
        if not self.is_running:
            return

        try:
            while not self.text_queue.empty():
                text = self.text_queue.get_nowait()
                self._update_subtitle_display(text)
        except queue.Empty:
            pass
        except Exception as e:
            self.logger.warning(f"检查字幕队列时出错: {e}", exc_info=True)

        if self.is_running and self.root:
            self.root.after(100, self._check_queue)

    def _update_subtitle_display(self, text: str):
        """更新字幕显示"""
        if not self.text_label or not self.is_running:
            return

        try:
            if text:
                # 显示窗口
                if not self.is_visible and self.root:
                    self.root.deiconify()
                    self.is_visible = True

                # 更新文本
                self.text_label.configure_text(text=text)
                self.last_voice_time = time.time()
                self.logger.debug(f"已更新字幕: {text[:30]}...")
            elif self.is_visible and self.auto_hide and self.root:
                self.root.withdraw()
                self.is_visible = False

        except Exception as e:
            self.logger.warning(f"更新字幕显示时出错: {e}", exc_info=True)

    def _check_auto_hide(self):
        """检查是否需要自动隐藏"""
        if not self.is_running:
            return

        try:
            if (
                self.auto_hide
                and self.is_visible
                and self.root
                and self.fade_delay_seconds > 0
                and time.time() - self.last_voice_time > self.fade_delay_seconds
            ):
                self.logger.debug("自动隐藏字幕窗口")
                self.root.withdraw()
                self.is_visible = False
                # 清空文本
                if self.text_label:
                    self.text_label.configure_text(text="")

            if self.is_running and self.root:
                self.root.after(100, self._check_auto_hide)

        except Exception as e:
            self.logger.warning(f"检查自动隐藏时出错: {e}", exc_info=True)
            if self.is_running and self.root:
                self.root.after(100, self._check_auto_hide)

    # --- 窗口事件处理 ---
    def _start_move(self, event):
        """记录鼠标按下位置"""
        self._move_x = event.x
        self._move_y = event.y

    def _on_move(self, event):
        """拖动窗口"""
        if self.root:
            deltax = event.x - self._move_x
            deltay = event.y - self._move_y
            x = self.root.winfo_x() + deltax
            y = self.root.winfo_y() + deltay
            self.root.geometry(f"+{x}+{y}")

    def _on_closing(self):
        """处理窗口关闭事件"""
        self.logger.info("Subtitle 窗口关闭请求...")
        self.is_running = False
        if self.root:
            try:
                self.root.destroy()
            except Exception as e:
                self.logger.warning(f"销毁 subtitle 窗口时出错: {e}", exc_info=True)
        self.root = None

    # --- Plugin Lifecycle ---
    async def setup(self):
        await super().setup()

        # 检查是否被禁用
        if not CTK_AVAILABLE or hasattr(self, "enabled") and not self.enabled:
            self.logger.warning("字幕插件被禁用，跳过设置")
            return

        # 注册服务
        self.core.register_service("subtitle_service", self)
        self.logger.info("SubtitlePlugin 已注册为 'subtitle_service' 服务。")

        # 启动 GUI 线程
        self.is_running = True
        self.gui_thread = threading.Thread(target=self._run_gui, daemon=True)
        self.gui_thread.start()
        self.logger.info("Subtitle GUI 线程已启动。")

    async def cleanup(self):
        self.logger.info("正在清理 SubtitlePlugin...")
        self.is_running = False

        # 等待线程结束 (线程会自己清理窗口)
        if self.gui_thread and self.gui_thread.is_alive():
            self.logger.debug("等待 Subtitle GUI 线程结束...")
            self.gui_thread.join(timeout=3.0)
            if self.gui_thread.is_alive():
                self.logger.warning("Subtitle GUI 线程未能及时结束。")

        await super().cleanup()
        self.logger.info("SubtitlePlugin 清理完成。")

    # --- Service Method ---
    async def record_speech(self, text: str, duration: float):
        """
        接收文本，显示字幕。保持与原接口兼容。
        """
        if not self.is_running:
            self.logger.debug("字幕服务未运行，跳过显示")
            return

        if not CTK_AVAILABLE:
            self.logger.debug("CustomTkinter 不可用，跳过字幕显示")
            return

        if not text:
            # 空文本表示结束，可以选择隐藏
            if self.auto_hide:
                try:
                    self.text_queue.put("")
                except Exception as e:
                    self.logger.debug(f"队列操作失败: {e}")
            return

        # 清理文本
        cleaned_text = text.replace("\n", " ").replace("\r", "")

        try:
            self.text_queue.put(cleaned_text)
            self.logger.debug(f"已将文本放入字幕队列: {cleaned_text[:30]}...")
        except Exception as e:
            self.logger.error(f"放入字幕队列时出错: {e}", exc_info=True)


# --- Plugin Entry Point ---
plugin_entrypoint = SubtitlePlugin
