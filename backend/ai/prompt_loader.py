# 按模块指定目录读取 UTF-8 提示词，默认使用 AI 层提示词目录。
from pathlib import Path


# 按 name 和可选 directory 读取提示词并返回文本；文件不存在或读取失败由调用方处理。
def load_prompt(name, *, directory=None):
    """共用提示词读取；默认读取AI提示词，也允许模块指定专用目录。"""
    folder = Path(directory) if directory is not None else Path(__file__).parent / 'prompts'
    return (folder / name).read_text(encoding='utf-8')
