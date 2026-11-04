# 保留模型客户端的兼容导入入口，通信实现集中在 ai.llm。
"""兼容旧导入路径；新调用请从 backend.ai.llm 导入。"""
from backend.ai.llm import ModelClient

__all__ = ['ModelClient']
