import asyncio
import signal
import sys
import os
import argparse  # 导入 argparse

# 尝试导入 tomllib (Python 3.11+), 否则使用 toml
try:
    import tomllib
except ModuleNotFoundError:
    try:
        import toml as tomllib  # type: ignore
    except ModuleNotFoundError:
        print("错误：需要安装 TOML 解析库。请运行 'pip install toml'", file=sys.stderr)
        sys.exit(1)

# 从 src 目录导入核心类和插件管理器
from src.core.vup_next_core import VupNextCore
from src.core.plugin_manager import PluginManager
from src.utils.logger import logger

# 获取 main.py 文件所在的目录
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def load_config(config_filename: str = "config.toml") -> dict:
    """加载位于脚本同目录下的 TOML 配置文件。"""
    config_path = os.path.join(_BASE_DIR, config_filename)
    logger.debug(f"尝试加载配置文件: {config_path}")
    try:
        with open(config_path, "rb") as f:
            config = tomllib.load(f)
            logger.info(f"成功加载配置文件: {config_path}")
            return config
    except FileNotFoundError:
        logger.error(f"错误：配置文件 '{config_path}' 未找到。请确保它在 main.py 文件的同级目录下。")
        sys.exit(1)
    except tomllib.TOMLDecodeError as e:
        logger.error(f"错误：配置文件 '{config_path}' 格式无效: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"加载配置文件 '{config_path}' 时发生未知错误: {e}", exc_info=True)
        sys.exit(1)


async def main():
    """应用程序主入口点。"""

    # 创建命令行参数解析器
    parser = argparse.ArgumentParser(description="VUP-NEXT 应用程序")
    # 添加 --debug 参数，用于控制日志级别
    parser.add_argument("--debug", action="store_true", help="启用 DEBUG 级别日志输出")
    # 解析命令行参数
    args = parser.parse_args()

    # --- 配置日志 ---
    if args.debug:
        logger.remove()  # 移除之前的handler
        logger.add(
            sys.stderr,
            level="DEBUG",
            colorize=True,
            format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        )
        logger.info("已启用 DEBUG 日志级别。")

    logger.info("启动 VUP-NEXT 应用程序...")

    # --- 加载配置 ---
    config = load_config()

    # 从配置中提取参数，提供默认值或进行错误处理
    general_config = config.get("general", {})
    maicore_config = config.get("maicore", {})
    http_config = config.get("http_server", {})

    platform_id = general_config.get("platform_id", "vup_next_default")

    maicore_host = maicore_config.get("host", "127.0.0.1")
    maicore_port = maicore_config.get("port", 8000)
    # maicore_token = maicore_config.get("token") # 如果需要 token

    http_enabled = http_config.get("enable", False)
    http_host = http_config.get("host", "127.0.0.1") if http_enabled else None
    http_port = http_config.get("port", 8080) if http_enabled else None
    http_callback_path = http_config.get("callback_path", "/maicore_callback")

    # --- 初始化核心 ---
    core = VupNextCore(
        platform=platform_id,
        maicore_host=maicore_host,
        maicore_port=maicore_port,
        http_host=http_host,  # 如果 http_enabled=False, 这里会是 None
        http_port=http_port,
        http_callback_path=http_callback_path,
        # maicore_token=maicore_token # 如果 core 需要 token
    )

    # --- 插件加载 ---
    logger.info("加载插件...")
    plugin_manager = PluginManager(core, config.get("plugins", {}))  # 传入插件全局配置
    # 构建插件目录的绝对或相对路径
    # 这里假设 main.py 在 VUP-NEXT 根目录运行
    plugin_dir = os.path.join(os.path.dirname(__file__), "src", "plugins")
    await plugin_manager.load_plugins(plugin_dir)
    logger.info("插件加载完成。")

    # --- 连接核心服务 ---
    await core.connect()  # 连接 WebSocket 并启动 HTTP 服务器

    # --- 保持运行并处理退出信号 ---
    stop_event = asyncio.Event()

    def signal_handler():
        logger.info("收到退出信号，开始关闭...")
        stop_event.set()

    loop = asyncio.get_running_loop()
    # 在 Windows 上，SIGINT (Ctrl+C) 通常可用
    # 在 Unix/Linux 上，可以添加 SIGTERM
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, signal_handler)
        except NotImplementedError:
            # Windows 可能不支持 add_signal_handler
            # 使用 signal.signal 作为备选方案
            signal.signal(sig, lambda signum, frame: signal_handler())

    logger.info("应用程序正在运行。按 Ctrl+C 退出。")
    await stop_event.wait()

    # --- 执行清理 ---
    logger.info("正在卸载插件...")
    await plugin_manager.unload_plugins()  # 在断开连接前卸载插件

    logger.info("正在关闭核心服务...")
    await core.disconnect()
    logger.info("VUP-NEXT 应用程序已关闭。")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        # 在 asyncio.run 之外捕获 KeyboardInterrupt (尽管上面的信号处理应该先触发)
        logger.info("检测到 KeyboardInterrupt，强制退出。")
