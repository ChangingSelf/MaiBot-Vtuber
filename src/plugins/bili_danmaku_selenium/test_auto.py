#!/usr/bin/env python3
"""
简化的选择器测试脚本（自动运行）
"""

import time
import sys
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import NoSuchElementException, WebDriverException


def test_selectors_auto(room_id=22603245):
    """自动测试B站直播间的CSS选择器"""

    # 设置Chrome选项
    options = Options()
    # options.add_argument("--headless")  # 无头模式
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    # options.add_argument("--disable-gpu")
    options.add_argument(
        "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    )

    driver = None
    try:
        print(f"正在启动Chrome浏览器...")
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

        # 测试关键选择器
        selectors_to_test = {
            "弹幕容器": "#chat-items",
            "弹幕列表": ".chat-items",
            "聊天项目": ".chat-item",
            "弹幕项目": ".danmaku-item",
            "用户名": ".username",
            "弹幕内容": ".danmaku-item-right",
        }

        print("\n=== 选择器测试结果 ===")

        working_selectors = {}

        for desc, selector in selectors_to_test.items():
            try:
                elements = driver.find_elements(By.CSS_SELECTOR, selector)
                if elements:
                    print(f"✅ {desc}: {selector} (找到 {len(elements)} 个元素)")
                    working_selectors[desc] = selector

                    # 尝试获取文本内容
                    sample_texts = []
                    for elem in elements[:3]:
                        try:
                            text = elem.text.strip()
                            if text and len(text) < 100:
                                sample_texts.append(text)
                        except:
                            pass

                    if sample_texts:
                        print(f"   示例内容: {sample_texts}")

                else:
                    print(f"❌ {desc}: {selector} (未找到元素)")
            except Exception as e:
                print(f"⚠️  {desc}: {selector} (出错: {str(e)[:50]}...)")

        # 输出推荐配置
        if working_selectors:
            print(f"\n=== 推荐配置 ===")
            for desc, selector in working_selectors.items():
                print(f'{desc.lower().replace(" ", "_")}_selector = "{selector}"')

        print(f"\n测试完成！")
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
            except:
                pass


if __name__ == "__main__":
    print("Bilibili 直播间选择器自动测试")
    print("=" * 40)

    # 使用默认房间号
    result = test_selectors_auto(22603245)

    if result:
        print(f"\n发现 {len(result)} 个可用的选择器")
    else:
        print("\n测试失败或未找到可用选择器")
        sys.exit(1)
