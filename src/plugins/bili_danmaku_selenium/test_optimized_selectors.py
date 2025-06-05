#!/usr/bin/env python3
"""
优化后的选择器测试脚本
基于HTML分析结果验证新的CSS选择器
"""

import time
import sys
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import NoSuchElementException, WebDriverException


def test_optimized_selectors(room_id=22603245):
    """测试优化后的B站直播间CSS选择器"""

    # 设置Chrome选项
    options = Options()
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument(
        "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    )

    driver = None
    try:
        print("正在启动Chrome浏览器...")
        driver = webdriver.Chrome(options=options)
        driver.set_page_load_timeout(30)
        driver.implicitly_wait(5)

        # 访问直播间
        url = f"https://live.bilibili.com/{room_id}"
        print(f"正在访问: {url}")
        driver.get(url)

        # 等待页面加载
        print("等待页面加载...")
        time.sleep(8)

        # 测试优化后的选择器
        optimized_selectors = {
            "弹幕容器": "#chat-items",
            "弹幕项目(优化)": ".chat-item.danmaku-item",
            "用户名(优化)": ".user-name",
            "弹幕内容": ".danmaku-item-right",
            "弹幕左侧": ".danmaku-item-left",
            "昵称包装器": ".common-nickname-wrapper",
            "data属性用户名": "[data-uname]",
            "data属性弹幕": "[data-danmaku]",
        }

        print("\n=== 优化后选择器测试结果 ===")
        working_selectors = {}

        for desc, selector in optimized_selectors.items():
            try:
                elements = driver.find_elements(By.CSS_SELECTOR, selector)
                if elements:
                    print(f"✅ {desc}: {selector} (找到 {len(elements)} 个元素)")
                    working_selectors[desc] = selector

                    # 获取示例内容
                    sample_texts = []
                    for elem in elements[:3]:
                        try:
                            text = elem.text.strip()
                            if text and len(text) < 100:
                                sample_texts.append(text)
                        except Exception:
                            pass

                    if sample_texts:
                        print(f"   示例内容: {sample_texts}")

                else:
                    print(f"❌ {desc}: {selector} (未找到元素)")
            except Exception as e:
                print(f"⚠️  {desc}: {selector} (出错: {str(e)[:50]}...)")

        # 测试组合选择器的效果
        print(f"\n=== 组合选择器测试 ===")
        try:
            # 测试具体的弹幕抓取逻辑
            danmaku_items = driver.find_elements(By.CSS_SELECTOR, ".chat-item.danmaku-item")
            print(f"找到 {len(danmaku_items)} 个弹幕项目")

            successful_extracts = 0
            for i, item in enumerate(danmaku_items[:5]):  # 测试前5个
                try:
                    # 提取用户名
                    username_elem = item.find_element(By.CSS_SELECTOR, ".user-name")
                    username = username_elem.text.strip()

                    # 提取弹幕文本
                    text_elem = item.find_element(By.CSS_SELECTOR, ".danmaku-item-right")
                    text = text_elem.text.strip()

                    # 提取data属性
                    data_uname = item.get_attribute("data-uname")
                    data_danmaku = item.get_attribute("data-danmaku")

                    print(f"  弹幕 {i + 1}:")
                    print(f"    用户名: {username}")
                    print(f"    内容: {text}")
                    print(f"    data-uname: {data_uname}")
                    print(f"    data-danmaku: {data_danmaku}")
                    print()

                    if username and text:
                        successful_extracts += 1

                except Exception as e:
                    print(f"  弹幕 {i + 1}: 提取失败 - {e}")

            print(f"成功提取 {successful_extracts}/5 个弹幕")

        except Exception as e:
            print(f"组合选择器测试失败: {e}")

        # 输出推荐配置
        if working_selectors:
            print(f"\n=== 推荐的优化配置 ===")
            print('danmaku_container_selector = "#chat-items"')
            print('danmaku_item_selector = ".chat-item.danmaku-item"')
            print('danmaku_text_selector = ".danmaku-item-right"')
            print('username_selector = ".user-name"')
            print('gift_selector = ".gift-item"')
            print('gift_text_selector = ".gift-item-text"')

        return working_selectors

    except WebDriverException as e:
        print(f"WebDriver错误: {e}")
        print("请确保已安装Chrome浏览器和ChromeDriver")
        return None
    except Exception as e:
        print(f"测试过程中出错: {e}")
        return None
    finally:
        if driver:
            try:
                driver.quit()
                print("浏览器已关闭")
            except Exception:
                pass


if __name__ == "__main__":
    print("Bilibili 直播间优化选择器测试")
    print("=" * 50)

    result = test_optimized_selectors(22603245)

    if result:
        print(f"\n发现 {len(result)} 个可用的优化选择器")
        print("选择器优化成功！")
    else:
        print("\n测试失败或未找到可用选择器")
        sys.exit(1)
