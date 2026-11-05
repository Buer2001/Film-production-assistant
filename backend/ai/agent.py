# 文件职责：V5 Agent 的四类结构化模型调用；每次只接受一次工具提交，失败不改正式数据。
"""要求理解、候选生成、要求复核和有限修正；提示词放在 backend/agent/prompts。"""
from pathlib import Path
from backend.ai.planning import _request
from backend.agent.schemas import Candidate, ReflectResult, UnderstandResult

# Agent 专用提示词目录；业务提示词仍在 AI 层，Agent 的不混入。
PROMPT_DIR = Path(__file__).parent.parent / 'agent' / 'prompts'


# 把制片的话解析为工作模式、范围、约束和待确认问题；不生成具体安排。
async def understand(payload, model=None, *, context=None):
    return await _request(payload, model, context, schema=UnderstandResult,
                          tool_name='submit_understanding', prompt_name='understand.txt',
                          label='要求理解', operation='agent.understand', prompt_dir=PROMPT_DIR)


# 按范围、正式资料和约束生成联合候选方案；只提交草稿内容，不执行。
async def propose(payload, model=None, *, context=None):
    return await _request(payload, model, context, schema=Candidate,
                          tool_name='submit_candidate', prompt_name='propose.txt',
                          label='候选方案', operation='agent.propose', prompt_dir=PROMPT_DIR)


# 对照制片要求复核候选：是否满足、遗漏、越界、虚构或解释不足。
async def reflect(payload, model=None, *, context=None):
    return await _request(payload, model, context, schema=ReflectResult,
                          tool_name='submit_review', prompt_name='reflect.txt',
                          label='模型复核', operation='agent.reflect', prompt_dir=PROMPT_DIR)


# 只针对复核发现的问题修正候选；输出仍是完整候选，不能顺手扩大范围。
async def revise(payload, model=None, *, context=None):
    return await _request(payload, model, context, schema=Candidate,
                          tool_name='submit_candidate', prompt_name='revise.txt',
                          label='修正方案', operation='agent.revise', prompt_dir=PROMPT_DIR)
