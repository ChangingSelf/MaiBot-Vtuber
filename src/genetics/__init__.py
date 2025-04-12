"""
基因模块 - 负责管理机器人的配置和持久化数据。
该模块提供了配置管理、数据存储和环境变量处理功能。
"""

from .genetic_expression import GeneticExpression
from .dna_storage import DNAStorage

__all__ = ["GeneticExpression", "DNAStorage"]
