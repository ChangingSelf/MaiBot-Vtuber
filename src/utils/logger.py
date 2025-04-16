import sys
from loguru import logger

# 移除默认的 handler
logger.remove()

# 添加一个新的 handler，输出到 stderr，并启用颜色
logger.add(
    sys.stderr,
    level="INFO",  # 可以根据需要调整日志级别
    colorize=True,
    format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
)

# 可以在这里添加其他的 handler，比如写入文件
# logger.add("file_{time}.log", rotation="1 week") # 例如：每周轮换日志文件

# 导出配置好的 logger 实例
__all__ = ["logger"]
