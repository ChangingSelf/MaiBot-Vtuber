import time
import threading
from custom_subtitle import CustomSubtitle
from advanced_subtitle import AdvancedSubtitle


def demo_basic_subtitle():
    """演示基本字幕功能"""
    print("启动基本字幕演示...")

    # 创建基本字幕
    subtitle = CustomSubtitle(text="这是一个基本字幕演示", theme="dark")

    # 创建一个线程来更新字幕
    def update_thread():
        time.sleep(2)
        subtitle.update_text("字幕已更新：这是新的内容")

        time.sleep(2)
        subtitle.update_text("这是另一段文本，用于测试自动换行功能")

        time.sleep(2)
        subtitle.set_theme("light")

        time.sleep(2)
        subtitle.set_opacity(0.7)

        time.sleep(2)
        subtitle.close()

    # 启动更新线程
    thread = threading.Thread(target=update_thread)
    thread.daemon = True
    thread.start()

    # 运行字幕
    subtitle.run()


def demo_advanced_subtitle():
    """演示高级字幕功能"""
    print("启动高级字幕演示...")

    # 创建高级字幕
    subtitle = AdvancedSubtitle(
        text="这是一个高级字幕演示",
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

    # 创建一个线程来更新字幕
    def update_thread():
        time.sleep(2)
        subtitle.update_text("字幕已更新：这是新的内容", animate=True)

        time.sleep(2)
        long_text = "这是另一段更长的文本，用于测试自动换行功能是否正常工作，以及窗口大小是否会相应调整。"
        subtitle.update_text(long_text, animate=True)

        time.sleep(2)
        subtitle.set_theme("light")

        time.sleep(2)
        subtitle.set_opacity(0.7)

        time.sleep(2)
        subtitle.set_font(family="SimHei", size=32)

        time.sleep(2)
        subtitle.set_text_color("#FF9900")

        time.sleep(2)
        subtitle.set_bg_color("#222222")

        time.sleep(2)
        subtitle.set_border_radius(25)

        time.sleep(2)
        subtitle.set_padding(30)

        time.sleep(2)
        subtitle.close()

    # 启动更新线程
    thread = threading.Thread(target=update_thread)
    thread.daemon = True
    thread.start()

    # 运行字幕
    subtitle.run()


if __name__ == "__main__":
    print("字幕演示程序")
    print("1. 基本字幕演示")
    print("2. 高级字幕演示")
    print("请选择演示类型 (1/2):")

    choice = input().strip()

    if choice == "1":
        demo_basic_subtitle()
    elif choice == "2":
        demo_advanced_subtitle()
    else:
        print("无效选择，默认运行高级字幕演示")
        demo_advanced_subtitle()
