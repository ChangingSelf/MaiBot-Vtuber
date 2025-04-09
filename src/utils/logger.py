from loguru import logger
import os
from typing import Optional


def setup_logger(
    name: str,
    level: str = "DEBUG",
    log_file: Optional[str] = None,
    log_format: str = "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
) -> logger:
    """
    设置并返回一个配置好的logger实例

    Args:
        name: logger的名称
        level: 日志级别，默认为DEBUG
        log_file: 日志文件路径，如果为None则只输出到控制台
        log_format: 日志格式

    Returns:
        logger: 配置好的logger实例
    """
    # 移除默认的处理器
    logger.remove()

    # 添加控制台处理器
    logger.add(sink=lambda msg: print(msg), format=log_format, level=level, colorize=True)

    # 如果指定了日志文件，添加文件处理器
    if log_file:
        # 确保日志目录存在
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        logger.add(
            sink=log_file,
            format=log_format,
            level=level,
            encoding="utf-8",
            rotation="500 MB",  # 日志文件达到500MB时轮转
            retention="10 days",  # 保留10天的日志
        )

    return logger.bind(name=name)


# 创建默认的logger实例
default_logger = setup_logger("MaiBot-Vtuber")


def get_logger(name: Optional[str] = None) -> logger:
    """
    获取一个logger实例。如果指定了name，则返回对应name的logger；
    否则返回默认logger。

    Args:
        name: logger的名称，如果为None则返回默认logger

    Returns:
        logger: logger实例
    """
    if name is None:
        return default_logger
    return setup_logger(name)
