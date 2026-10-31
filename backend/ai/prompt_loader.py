from pathlib import Path


def load_prompt(name, *, directory=None):
    """共用提示词读取；默认读取AI提示词，也允许模块指定专用目录。"""
    folder = Path(directory) if directory is not None else Path(__file__).parent / 'prompts'
    return (folder / name).read_text(encoding='utf-8')
