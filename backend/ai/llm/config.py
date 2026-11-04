"""按服务读取配置，不缓存密钥，不在不同服务之间隐式回退。"""

# 导入核心模块：dataclass 配合 frozen=True 创建不可变配置类，field 设置字段选项，math 检查超时是否为有限数，os 读取环境变量
from dataclasses import dataclass, field
import math
import os


@dataclass(frozen=True)
class ModelConfig:
    """
    模型配置类，包含基础URL、模型名称、超时时间和API密钥
    
    参数:
    base_url (str): 模型服务基础地址
    model (str): 使用的模型名称
    timeout (float): 请求超时时间（秒）
    api_key (str): API密钥（默认空字符串，不在对象的默认打印表示中展示；序列化时仍可能包含）
    """
    base_url: str
    model: str
    timeout: float
    api_key: str = field(default='', repr=False)


def load_config(provider=None):
    """
    根据指定提供者加载模型配置，支持 deepseek 和 qwen3 两种服务
    
    参数:
    provider (str): 模型提供者（可选，默认从环境变量 LLM_PROVIDER 获取）
    
    返回:
    ModelConfig: 配置对象
    """
    
    provider = provider if provider is not None else os.getenv('LLM_PROVIDER', 'deepseek')
    
    # 处理 deepseek 服务配置
    if provider == 'deepseek':
        base = os.getenv('LLM_BASE_URL', 'https://api.deepseek.com')
        model = os.getenv('LLM_MODEL', '')
        key = os.getenv('LLM_API_KEY', '')
        timeout = os.getenv('LLM_TIMEOUT', '60')
        
        # 检查必填参数是否配置
        if not key.strip() or not model.strip():
            raise RuntimeError('请配置 LLM_API_KEY 和 LLM_MODEL 后使用模型功能')

    # 处理 qwen3 服务配置
    elif provider == 'qwen3':
        base = os.getenv('QWEN3_BASE_URL', 'http://localhost:11434/v1')
        model = os.getenv('QWEN3_MODEL', 'qwen3:8b-q4_K_M')
        key = ''  # 本机 Ollama 不需要密钥，禁止沿用云端密钥。
        timeout = os.getenv('QWEN3_TIMEOUT', '180')

    # 不支持的提供者
    else:
        raise RuntimeError('LLM_PROVIDER 仅支持 deepseek 或 qwen3')
    
    # 检查基础地址和模型名称是否配置
    if not base.strip() or not model.strip():
        raise RuntimeError('请配置模型服务地址和模型名称')
    
    # 超时时间校验
    try:
        timeout = float(timeout)
    except ValueError:
        raise RuntimeError('模型超时必须是大于 0 的有限秒数') from None
    
    if not math.isfinite(timeout) or timeout <= 0:
        raise RuntimeError('模型超时必须是大于 0 的有限秒数')
    
    return ModelConfig(base.strip().rstrip('/'), model.strip(), timeout, key.strip())


def is_configured():
    """
    检查默认服务配置是否合法（校验服务名称、必填配置和超时时间，不验证网络连接或模型加载状态）
    
    返回:
    bool: 配置是否合法
    """
    try:
        load_config()
    except RuntimeError:
        return False
    return True
