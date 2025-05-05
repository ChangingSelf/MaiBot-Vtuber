# Amaidesu Subtitle Plugin (Screen Display): src/plugins/subtitle/plugin.py

import tomllib
import os
import time
import platform
import threading  # 用于运行 GUI
import queue  # 用于线程间通信
from typing import Any, Dict, Optional

try:
    import tkinter as tk
except ImportError:
    tk = None  # 标记 tkinter 不可用

from core.plugin_manager import BasePlugin
from core.amaidesu_core import AmaidesuCore
from src.utils.logger import get_logger

logger = get_logger("SubtitlePlugin")


# --- Helper Function ---
def load_plugin_config() -> Dict[str, Any]:
    config_path = os.path.join(os.path.dirname(__file__), "config.toml")
    try:
        with open(config_path, "rb") as f:
            if hasattr(tomllib, "load"):
                return tomllib.load(f)
            else:
                try:
                    import toml

                    with open(config_path, "r", encoding="utf-8") as rf:
                        return toml.load(rf)
                except ImportError:
                    logger.error("toml package needed for Python < 3.11.")
                    return {}
                except FileNotFoundError:
                    logger.warning(f"Config file not found: {config_path}")
                    return {}
    except Exception as e:
        logger.error(f"Error loading config: {config_path}: {e}", exc_info=True)
        return {}


# --- Plugin Class ---
class SubtitlePlugin(BasePlugin):
    """
    Receives speech text from other services (like TTS)
    and displays it in a dedicated, always-on-top window using Tkinter.
    """

    _is_amaidesu_plugin: bool = True

    def __init__(self, core: AmaidesuCore, plugin_config: Dict[str, Any]):
        super().__init__(core, plugin_config)
        self.logger = logger
        # --- 加载配置 ---
        loaded_config = load_plugin_config()
        self.config = loaded_config.get("subtitle_display", {})  # 使用新的配置段 'subtitle_display'
        self.enabled = self.config.get("enabled", True)

        # --- 检查依赖 ---
        if tk is None:
            self.logger.error("Tkinter library not found or failed to import. SubtitlePlugin disabled.")
            self.enabled = False
            return

        if not self.enabled:
            self.logger.warning("SubtitlePlugin 在配置中被禁用。")
            return

        # --- GUI 配置 ---
        self.window_width = self.config.get("window_width", 800)
        self.window_height = self.config.get("window_height", 100)
        self.window_offset_y = self.config.get("window_offset_y", 100)  # 距离屏幕底部
        self.font_family = self.config.get("font_family", "Arial")
        self.font_size = self.config.get("font_size", 24)
        self.font_weight = self.config.get("font_weight", "bold")
        self.text_color = self.config.get("text_color", "white")
        self.bg_color = self.config.get("bg_color", "black")  # 背景色，用于透明效果
        self.fade_delay_seconds = self.config.get("fade_delay_seconds", 3)  # 淡出延迟
        self.wraplength = self.window_width - 20  # 自动换行宽度

        # --- 线程和状态 ---
        self.text_queue = queue.Queue()  # 用于从 record_speech 发送文本到 GUI 线程
        self.gui_thread: Optional[threading.Thread] = None
        self.root: Optional[tk.Tk] = None
        self.text_label: Optional[tk.Label] = None
        self.last_voice_time = time.time()
        self.is_running = True  # 控制 GUI 线程循环

        self.logger.info("SubtitlePlugin (Screen Display) 初始化完成。")

    # --- Tkinter GUI 运行在单独线程 ---
    def _run_gui(self):
        try:
            self.root = tk.Tk()
            self.root.title("Amaidesu Subtitle")
            self.root.protocol("WM_DELETE_WINDOW", self._on_closing)  # 处理关闭按钮

            # --- 窗口属性 (模仿 voice_subtitle.py) ---
            if platform.system() == "Darwin":  # macOS 特殊处理 (可能仍需调整)
                self.root.attributes("-topmost", 1)
                self.root.attributes("-alpha", 1.0)  # 可能需要调整透明度值
                # self.root.attributes('-transparent', True) # 这个在 macOS 上可能不直接工作
                self.root.configure(bg=self.bg_color)  # 设置背景色
                # macOS 透明可能需要其他方法，例如 NSWindow 设置
            else:  # Windows and others
                self.root.attributes("-topmost", True)
                self.root.attributes("-alpha", 0.8)  # 尝试轻微透明
                self.root.configure(bg=self.bg_color)
                # Windows 透明的关键，将背景色设为透明色
                self.root.attributes("-transparentcolor", self.bg_color)

            self.root.overrideredirect(True)  # 无边框

            # --- 窗口大小和位置 ---
            screen_width = self.root.winfo_screenwidth()
            screen_height = self.root.winfo_screenheight()
            x = (screen_width - self.window_width) // 2
            y = screen_height - self.window_height - self.window_offset_y
            self.root.geometry(f"{self.window_width}x{self.window_height}+{x}+{y}")

            # --- 创建文本标签 ---
            self.text_label = tk.Label(
                self.root,
                text="",
                font=(self.font_family, self.font_size, self.font_weight),
                fg=self.text_color,
                bg=self.bg_color,  # 标签背景也设为透明色
                wraplength=self.wraplength,
                highlightthickness=0,
                borderwidth=0,
            )
            self.text_label.pack(expand=True, fill="both", padx=10, pady=5)

            # --- 绑定事件 ---
            self.text_label.bind("<Button-1>", self._start_move)
            self.text_label.bind("<B1-Motion>", self._on_move)
            self.text_label.bind("<Button-3>", lambda e: self._on_closing())  # 右键退出

            # --- 启动队列检查和淡出循环 ---
            self.root.after(100, self._check_queue)  # 每 100ms 检查一次队列
            self.root.after(100, self._fade_out_text)  # 每 100ms 检查是否需要淡出

            self.logger.info("Subtitle GUI 启动成功。")
            self.root.mainloop()  # 运行 Tkinter 事件循环

        except Exception as e:
            self.logger.error(f"运行 Subtitle GUI 时出错: {e}", exc_info=True)
        finally:
            self.logger.info("Subtitle GUI 线程结束。")
            # 确保即使出错也尝试清理
            if self.root:
                try:
                    self.root.quit()  # 退出 mainloop
                except:
                    pass
            self.is_running = False  # 确保其他部分知道已停止

    def _check_queue(self):
        """在 GUI 线程中定期检查队列，更新文本"""
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
            self.root.after(100, self._check_queue)  # 继续调度

    def _update_subtitle_display(self, text: str):
        """更新 Tkinter Label 的文本并重置淡出计时器"""
        if self.text_label and self.is_running:
            try:
                self.text_label.config(text=text)
                # 重置为完全不透明
                self.text_label.config(fg=self.text_color)
                self.last_voice_time = time.time()
                # self.text_label.update() # 可能不需要显式 update
            except Exception as e:
                self.logger.warning(f"更新字幕显示时出错: {e}", exc_info=True)

    def _fade_out_text(self):
        """在 GUI 线程中处理文字淡出效果 (简化版)"""
        if not self.is_running or not self.text_label:
            return

        try:
            # 仅当 fade_delay_seconds 大于 0 时才启用淡出
            if self.fade_delay_seconds > 0 and time.time() - self.last_voice_time > self.fade_delay_seconds:
                current_text = self.text_label.cget("text")
                if current_text:  # 如果当前有文本，则清空
                    self.logger.debug("淡出时间到，清除字幕。")
                    self.text_label.config(text="")

            # 不论是否淡出，都继续调度下一次检查
            if self.is_running and self.root:
                self.root.after(100, self._fade_out_text)

        except Exception as e:
            self.logger.warning(f"处理字幕淡出时出错: {e}", exc_info=True)
            # 即使出错，也尝试继续调度
            if self.is_running and self.root:
                self.root.after(100, self._fade_out_text)

    # --- 窗口事件处理 ---
    def _start_move(self, event):
        """记录鼠标按下位置"""
        self._move_x = event.x
        self._move_y = event.y

    def _on_move(self, event):
        """计算并移动窗口"""
        if self.root:
            deltax = event.x - self._move_x
            deltay = event.y - self._move_y
            x = self.root.winfo_x() + deltax
            y = self.root.winfo_y() + deltay
            self.root.geometry(f"+{x}+{y}")

    def _on_closing(self):
        """处理窗口关闭事件 (用户点击关闭按钮或右键)"""
        self.logger.info("Subtitle 窗口关闭请求...")
        self.is_running = False  # 停止所有循环
        if self.root:
            try:
                # 尝试销毁窗口，这应该会终止 mainloop
                self.root.destroy()
            except tk.TclError:
                pass  # 可能窗口已经销毁
            except Exception as e:
                self.logger.warning(f"销毁 subtitle 窗口时出错: {e}", exc_info=True)
        self.root = None  # 标记窗口已关闭
        # 注意：这里不直接退出 Amaidesu，只是关闭字幕窗口

    # --- Plugin Lifecycle ---
    async def setup(self):
        await super().setup()
        if not self.enabled:
            return

        # 注册自己为服务，供 TTS 插件调用
        self.core.register_service("subtitle_service", self)
        self.logger.info("SubtitlePlugin 已注册为 'subtitle_service' 服务。")

        # 启动 GUI 线程
        self.is_running = True
        self.gui_thread = threading.Thread(target=self._run_gui, daemon=True)
        self.gui_thread.start()
        self.logger.info("Subtitle GUI 线程已启动。")

    async def cleanup(self):
        self.logger.info("正在清理 SubtitlePlugin...")
        self.is_running = False  # 通知 GUI 线程停止

        # 尝试安全地关闭 Tkinter 窗口
        if self.root:
            try:
                # 使用 after 在 GUI 线程中调用 destroy
                self.root.after(0, self.root.destroy)
            except Exception as e:
                self.logger.warning(f"请求销毁 subtitle 窗口时出错: {e}", exc_info=True)

        # 等待 GUI 线程结束
        if self.gui_thread and self.gui_thread.is_alive():
            self.logger.debug("等待 Subtitle GUI 线程结束...")
            self.gui_thread.join(timeout=2.0)  # 等待最多 2 秒
            if self.gui_thread.is_alive():
                self.logger.warning("Subtitle GUI 线程未能及时结束。")

        # 取消注册服务 (如果 Core 支持)
        # self.core.unregister_service("subtitle_service")

        await super().cleanup()
        self.logger.info("SubtitlePlugin 清理完成。")

    # --- Service Method called by TTSPlugin ---
    async def record_speech(self, text: str, duration: float):
        """
        接收文本和时长 (时长当前未使用)，将其放入队列供 GUI 线程显示。
        """
        if not self.enabled or not self.is_running:
            return

        if not text:
            self.logger.debug("收到空文本，跳过字幕显示。")
            return

        # 清理文本 (移除换行符) - 可选
        cleaned_text = text.replace("\n", " ").replace("\r", "")

        try:
            # 将文本放入队列
            self.text_queue.put(cleaned_text)
            self.logger.debug(f"已将文本放入字幕队列: {cleaned_text[:30]}...")
        except Exception as e:
            self.logger.error(f"放入字幕队列时出错: {e}", exc_info=True)


# --- Plugin Entry Point ---
plugin_entrypoint = SubtitlePlugin
