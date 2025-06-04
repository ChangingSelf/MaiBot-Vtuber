#!/usr/bin/env python3
"""
简单的插件功能测试脚本
"""

import asyncio
import sys
import os

# 添加项目根目录到路径
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from src.plugins.bili_danmaku_selenium.plugin import BiliDanmakuSeleniumPlugin
from src.core.amaidesu_core import AmaidesuCore


class MockCore(AmaidesuCore):
    """用于测试的模拟Core"""

    def __init__(self):
        self.platform = "test"
        self.logger = None

    async def send_to_maicore(self, message):
        """模拟发送消息到maicore"""
        print(f"📢 收到消息: [{message.message_info.user_info.user_nickname}] {message.raw_message}")

    def get_service(self, service_name):
        """模拟获取服务"""
        return None


async def test_plugin():
    """测试插件基本功能"""
    print("🧪 开始测试 BiliDanmakuSeleniumPlugin...")

    # 创建模拟的配置
    test_config = {
        "enabled": True,
        "room_id": 22603245,
        "poll_interval": 3.0,
        "max_messages_per_check": 5,
        "headless": True,
        "webdriver_timeout": 30,
        "page_load_timeout": 30,
        "implicit_wait": 5,
        "danmaku_container_selector": "#chat-items",
        "danmaku_item_selector": ".chat-item",
        "danmaku_text_selector": ".danmaku-item-right",
        "username_selector": ".danmaku-item-left .username",
        "gift_selector": ".gift-item",
        "gift_text_selector": ".gift-item-text",
        "default_user_id": "bili_user",
        "default_user_nickname": "B站观众",
        "user_cardname": "",
        "enable_group_info": True,
        "group_id": 22603245,
        "group_name": "bili_live_22603245",
        "content_format": ["text"],
        "accept_format": ["text", "emoji", "reply", "vtb_text"],
        "context_tags": [],
        "enable_template_info": False,
        "additional_config": {"source_platform": "bilibili_live", "source_plugin": "bili_danmaku_selenium"},
    }

    try:
        # 创建插件实例
        core = MockCore()
        plugin = BiliDanmakuSeleniumPlugin(core, test_config)

        print(f"✅ 插件创建成功: {plugin.__class__.__name__}")
        print(f"📋 房间ID: {plugin.room_id}")
        print(f"⏱️  轮询间隔: {plugin.poll_interval}秒")
        print(f"🔧 无头模式: {plugin.headless}")

        if not plugin.enabled:
            print("❌ 插件被禁用，请检查依赖安装")
            return False

        # 测试插件设置
        print("\n🔄 初始化插件...")
        await plugin.setup()

        print("✅ 插件初始化成功")
        print(f"🌐 WebDriver 状态: {'已创建' if plugin.driver else '未创建'}")

        # 运行一小段时间来捕获弹幕
        print(f"\n📡 开始监控弹幕 (20秒)...")
        print("=" * 50)

        await asyncio.sleep(180)

        print("=" * 50)
        print("⏹️  停止监控")

        # 清理
        await plugin.cleanup()
        print("✅ 插件清理完成")

        return True

    except Exception as e:
        print(f"❌ 测试过程中出错: {e}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    print("Bilibili Selenium 弹幕插件测试")
    print("=" * 40)
    print("⚠️  注意：此测试需要安装 selenium 和 chrome/chromedriver")
    print("如果没有安装，请运行: pip install selenium")
    print()

    try:
        # 检查selenium是否可用
        from selenium import webdriver

        print("✅ Selenium 已安装")
    except ImportError:
        print("❌ Selenium 未安装，请运行: pip install selenium")
        sys.exit(1)

    # 运行测试
    result = asyncio.run(test_plugin())

    if result:
        print("\n🎉 测试完成")
    else:
        print("\n💥 测试失败")
        sys.exit(1)
