# src/plugins/bili_danmaku_selenium/__init__.py

"""
Bilibili 弹幕插件 (Selenium版)

使用 Selenium WebDriver 直接从 Bilibili 直播间页面获取弹幕和礼物消息。
相比 API 版本，具有更好的实时性和更全面的信息获取能力。
"""

from .plugin import BiliDanmakuSeleniumPlugin

__all__ = ["BiliDanmakuSeleniumPlugin"]
