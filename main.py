import asyncio
import signal
import sys
import os
import argparse  # 导入 argparse
import shutil # <<<<<<<<<<<<<<<<<<<< Added import

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
from src.core.amaidesu_core import AmaidesuCore
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

# <<<<<<<<<<<<<<<<<<<< Added block
# --- 新增：检查并设置插件配置文件的函数 ---
def check_and_setup_plugin_configs(plugin_base_dir: str) -> bool:
    """
    检查插件目录中的 config.toml。如果不存在但存在 config-template.toml，则复制模板。
    返回 True 如果有任何文件被复制，否则返回 False。
    """
    config_copied = False
    logger.info("开始检查插件配置文件...")
    try:
        # 确保插件基础目录存在
        if not os.path.isdir(plugin_base_dir):
             logger.error(f"指定的插件目录 '{plugin_base_dir}' 不存在或不是一个目录。")
             return False # 无法继续

        # 遍历插件基础目录中的所有项目
        for item_name in os.listdir(plugin_base_dir):
            plugin_dir_path = os.path.join(plugin_base_dir, item_name)

            # 检查是否是目录，并且不是像 __pycache__ 这样的特殊目录
            if os.path.isdir(plugin_dir_path) and not item_name.startswith("__"):
                config_path = os.path.join(plugin_dir_path, "config.toml")
                template_path = os.path.join(plugin_dir_path, "config-template.toml")

                logger.debug(f"检查插件目录: {item_name}")

                template_exists = os.path.exists(template_path)
                config_exists = os.path.exists(config_path)

                if template_exists and not config_exists:
                    try:
                        # 使用 copy2 保留元数据（如修改时间），虽然对 toml 可能不重要
                        shutil.copy2(template_path, config_path)
                        logger.info(f"在 '{item_name}' 中: config.toml 不存在，已从 config-template.toml 复制。")
                        config_copied = True # 标记发生了复制
                    except Exception as e:
                        # 如果复制失败，记录错误，但不阻止检查其他插件
                        logger.error(f"在 '{item_name}' 中: 从模板复制配置文件失败: {e}")
                elif not template_exists and not config_exists:
                     # 这种情况可能正常（插件不需要配置），或者是个问题（缺少模板）
                     # 可以选择性地添加更详细的日志
                     logger.debug(f"在 '{item_name}' 中: 未找到 config.toml 或 config-template.toml。")
                elif template_exists and config_exists:
                    # 配置文件已存在，无需操作
                    logger.debug(f"在 '{item_name}' 中: config.toml 已存在。")
                # else: # config_exists and not template_exists - 也无需操作

    except Exception as e:
        logger.error(f"检查插件配置时发生意外错误: {e}", exc_info=True)
        # 出现意外错误时，最好也阻止正常启动，因为它可能表明环境问题
        return False # 返回 False (或可以考虑返回 True 以强制退出)

    logger.info("插件配置文件检查完成。")
    return config_copied

# --- 新增：检查并设置主配置文件的函数 ---
def check_and_setup_main_config(base_dir: str) -> bool:
    """
    检查主 config.toml。如果不存在但存在 config-template.toml，则复制模板。
    返回 True 如果文件被复制，否则返回 False。
    """
    config_path = os.path.join(base_dir, "config.toml")
    template_path = os.path.join(base_dir, "config-template.toml")
    config_copied = False

    logger.info("开始检查主配置文件...")

    template_exists = os.path.exists(template_path)
    config_exists = os.path.exists(config_path)

    if template_exists and not config_exists:
        try:
            shutil.copy2(template_path, config_path)
            logger.info(f"主配置文件 config.toml 不存在，已从 config-template.toml 复制。")
            config_copied = True
        except Exception as e:
            logger.error(f"从模板复制主配置文件失败: {e}")
            # 如果主配置复制失败，应该阻止启动
            return False # 返回 False 可能不直观，但 load_config 会处理 FileNotFoundError
    elif not config_exists:
        # 如果 config.toml 不存在，并且模板也不存在，load_config 会处理错误并退出
        logger.debug("主配置文件 config.toml 不存在，且模板文件 config-template.toml 也不存在。")
        # 让 load_config 去处理 FileNotFoundError
    else:
        logger.debug("主配置文件 config.toml 已存在。")

    logger.info("主配置文件检查完成。")
    return config_copied
# >>>>>>>>>>>>>>>>>>>> Added block

async def main():
    """应用程序主入口点。"""

    # 创建命令行参数解析器
    parser = argparse.ArgumentParser(description="Amaidesu 应用程序")
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

    logger.info("启动 Amaidesu 应用程序...")

    # --- 检查并设置主配置 ---
    main_config_copied = check_and_setup_main_config(_BASE_DIR)
    if main_config_copied:
        logger.warning("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
        logger.warning("!! 主配置文件 config.toml 已根据模板创建。                 !!")
        logger.warning("!! 请检查根目录下的 config.toml 文件，并根据需要进行修改。   !!")
        logger.warning("!! 修改完成后，请重新运行程序。                           !!")
        logger.warning("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
        sys.exit(0) # 正常退出，让用户去修改配置

    # --- 加载主配置 ---
    config = load_config()

    # --- 检查并设置插件配置 ---
    plugin_dir = os.path.join(_BASE_DIR, "src", "plugins")
    plugin_configs_copied = check_and_setup_plugin_configs(plugin_dir)

    if plugin_configs_copied:
        # 如果有任何配置文件是从模板复制的，打印提示并退出
        logger.warning("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
        logger.warning("!! 已根据模板创建了部分插件的 config.toml 文件。          !!")
        logger.warning("!! 请检查 src/plugins/ 下各插件目录中的 config.toml 文件， !!")
        logger.warning("!! 特别是 API 密钥、房间号、设备名称等需要您修改的配置。   !!")
        logger.warning("!! 修改完成后，请重新运行程序。                           !!")
        logger.warning("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
        sys.exit(0) # 正常退出，让用户去修改配置
    else:
        # 如果所有配置文件都已存在，或者无需创建，则继续
        logger.info("所有必要的插件配置文件已存在或已处理。继续正常启动...")

    # 从配置中提取参数，提供默认值或进行错误处理
    general_config = config.get("general", {})
    maicore_config = config.get("maicore", {})
    http_config = config.get("http_server", {})

    platform_id = general_config.get("platform_id", "amaidesu_default")

    maicore_host = maicore_config.get("host", "127.0.0.1")
    maicore_port = maicore_config.get("port", 8000)
    # maicore_token = maicore_config.get("token") # 如果需要 token

    http_enabled = http_config.get("enable", False)
    http_host = http_config.get("host", "127.0.0.1") if http_enabled else None
    http_port = http_config.get("port", 8080) if http_enabled else None
    http_callback_path = http_config.get("callback_path", "/maicore_callback")

    # --- 初始化核心 ---
    core = AmaidesuCore(
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
    # 这里假设 main.py 在 Amaidesu 根目录运行
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
    logger.info("Amaidesu 应用程序已关闭。")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        # 在 asyncio.run 之外捕获 KeyboardInterrupt (尽管上面的信号处理应该先触发)
        logger.info("检测到 KeyboardInterrupt，强制退出。")
