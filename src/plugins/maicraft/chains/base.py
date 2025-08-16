from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from langchain_core.runnables import Runnable
from src.utils.logger import get_logger


class BaseChain(ABC):
    """LCEL链基类"""

    def __init__(self, name: str):
        self.name = name
        self.logger = get_logger(f"Chain.{name}")
        self._chain: Optional[Runnable] = None

    @abstractmethod
    def build(self) -> Runnable:
        """构建LCEL链"""
        pass

    @abstractmethod
    async def execute(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """执行链"""
        pass

    def get_chain(self) -> Runnable:
        """获取构建的链"""
        if self._chain is None:
            self._chain = self.build()
            self.logger.info(f"[{self.name}] 链构建完成")
        return self._chain

    def reset_chain(self):
        """重置链"""
        self._chain = None
        self.logger.info(f"[{self.name}] 链已重置")

    def log_execution(self, input_data: Dict[str, Any], result: Dict[str, Any]):
        """记录执行日志"""
        self.logger.info(f"[{self.name}] 执行完成 - 输入: {len(str(input_data))} 字符, 输出: {len(str(result))} 字符")
