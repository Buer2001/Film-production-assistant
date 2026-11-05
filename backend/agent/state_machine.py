# 文件职责：集中声明 V5 允许的步骤转换；转换由程序判断，模型不能自行指定节点。
"""状态机：固定步骤、允许转换和等待状态。"""
from backend.common.errors import BusinessError

# 可执行的步骤函数；clarify 和 review 是等待状态，不是步骤。
STEPS = ('understand', 'load', 'impact', 'propose', 'validate', 'reflect', 'revise', 'save_draft')

# 等待状态：结束后释放请求，由制片补充或审阅后再恢复。
HOLDING = {'clarify': 'waiting_input', 'review': 'waiting_review'}

# 允许的转换；任何不在此表中的跳转都视为程序错误，不能绕过检查直接执行。
ALLOWED = frozenset({
    ('understand', 'load'), ('understand', 'clarify'),
    ('clarify', 'understand'), ('clarify', 'load'),
    ('load', 'impact'), ('load', 'propose'),
    ('impact', 'propose'),
    ('propose', 'validate'), ('propose', 'clarify'),
    ('validate', 'reflect'), ('validate', 'clarify'),
    ('reflect', 'save_draft'), ('reflect', 'revise'), ('reflect', 'clarify'),
    ('revise', 'validate'), ('revise', 'clarify'),
    ('save_draft', 'review'),
    ('review', 'clarify'), ('review', 'feedback'),
})


# 由下一个步骤名决定运行状态；普通步骤保持 running。
def status_for(step):
    return HOLDING.get(step, 'running')


# 校验一次转换是否被允许；不允许时抛 BusinessError，不静默改道。
def check(current, target):
    if (current, target) not in ALLOWED:
        raise BusinessError(422, f'不允许的步骤转换：{current} → {target}')
