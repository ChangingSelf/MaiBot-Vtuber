#!/usr/bin/env python3
"""
Bilibili 直播间选择器测试脚本
用于验证和更新CSS选择器
"""

import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import NoSuchElementException


def test_selectors(room_id=22603245):
    """测试B站直播间的CSS选择器"""

    # 设置Chrome选项
    options = Options()
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")

    # 不使用无头模式，方便观察
    # options.add_argument("--headless")

    try:
        driver = webdriver.Chrome(options=options)
        driver.set_page_load_timeout(30)
        driver.implicitly_wait(10)

        # 访问直播间
        url = f"https://live.bilibili.com/{room_id}"
        print(f"正在访问: {url}")
        driver.get(url)

        # 等待页面加载
        time.sleep(5)

        # 测试各种选择器
        selectors_to_test = {
            "弹幕容器": "#chat-items",
            "弹幕项目": ".chat-item",
            "弹幕文本": ".danmaku-item-right",
            "用户名": ".danmaku-item-left .username",
            "礼物项目": ".gift-item",
            "礼物文本": ".gift-item-text",
            # 备用选择器
            "备用弹幕容器1": "#live-chat-items",
            "备用弹幕容器2": ".chat-list",
            "备用弹幕项目1": ".chat-item.danmaku-item",
            "备用弹幕项目2": ".live-chat-item",
            "备用弹幕文本1": ".danmaku-content",
            "备用弹幕文本2": ".chat-item .username ~ span",
            "备用用户名1": ".chat-item .username",
            "备用用户名2": ".danmaku-item .username",
        }

        print("\n=== 选择器测试结果 ===")

        for desc, selector in selectors_to_test.items():
            try:
                elements = driver.find_elements(By.CSS_SELECTOR, selector)
                if elements:
                    print(f"✅ {desc}: {selector} (找到 {len(elements)} 个元素)")
                    # 打印前3个元素的文本
                    for i, elem in enumerate(elements[:3]):
                        try:
                            text = elem.text.strip()
                            if text:
                                print(f"   [{i + 1}] {text[:50]}...")
                        except Exception as e:
                            print(f"   [{i + 1}] (无法获取文本: {e})")
                else:
                    print(f"❌ {desc}: {selector} (未找到元素)")
            except Exception as e:
                print(f"⚠️  {desc}: {selector} (出错: {e})")

        # 尝试获取页面源码中包含弹幕的部分
        print("\n=== 页面源码分析 ===")
        try:
            # 查找可能的弹幕相关元素
            possible_chat_elements = driver.find_elements(
                By.CSS_SELECTOR, "*[class*='chat'], *[class*='danmaku'], *[class*='live']"
            )
            print(f"找到 {len(possible_chat_elements)} 个可能的聊天相关元素")

            for elem in possible_chat_elements[:10]:  # 只显示前10个
                try:
                    class_name = elem.get_attribute("class")
                    tag_name = elem.tag_name
                    print(f"  {tag_name}.{class_name}")
                except:
                    continue

        except Exception as e:
            print(f"分析页面源码时出错: {e}")

        print("\n测试完成，按回车键关闭浏览器...")
        input()

    except Exception as e:
        print(f"测试过程中出错: {e}")
    finally:
        try:
            driver.quit()
        except:
            pass


if __name__ == "__main__":
    print("Bilibili 直播间选择器测试工具")
    print("=" * 40)

    room_id = input("请输入房间号 (默认: 22603245): ").strip()
    if not room_id:
        room_id = 22603245
    else:
        try:
            room_id = int(room_id)
        except ValueError:
            print("房间号格式错误，使用默认值")
            room_id = 22603245

    test_selectors(room_id)
