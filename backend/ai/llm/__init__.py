# 统一模型客户端及按提供者读取的运行配置。
"""统一模型入口；业务提示词和结果校验仍由调用方负责。"""
from .client import ModelClient

__all__ = ['ModelClient']
