# 文件职责：定义 V5 运行状态的结构与默认值；状态写入数据库，不依赖进程内存。
"""运行状态只保存本次工作所需信息，不复制整套项目事实。"""
STATE_VERSION = 1


# 新建状态：范围、候选、问题、检查结果和计数；大对象通过引用按需重新读取。
def new_state(*, message='', scope=None, candidate=None):
    return {'scope': scope, 'candidate': candidate, 'message': message,
            'questions': [], 'assumptions': [], 'validation': None, 'impact': None,
            'source': None, 'draft_id': None,
            # revise/reflect 计数用于限制自检循环，避免无进展时反复调用模型。
            'attempts': {'revise': 0, 'reflect': 0}, 'reflect_status': 'skipped'}
