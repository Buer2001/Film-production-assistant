# 提供修改草稿的查询、插入和待确认状态领取，事务提交由服务层负责。
"""草稿读写，不自行提交事务。"""
from sqlalchemy import update
from backend.models.change import Change


# 按 cid 查询草稿，返回对象或 None；s 为调用方管理的会话。
def get_change(s, cid):
    return s.get(Change, cid)


# 将 values 创建为草稿并加入 s、flush 后返回对象；不提交事务。
def add_change(s, **values):
    change = Change(**values)
    s.add(change)
    s.flush()
    return change


# 将 cid 对应 pending 草稿条件更新为 status，可用 pid 限定项目；返回影响行数供服务判定并发结果。
def claim_status(s, cid, status, pid=None):
    # 仅 pending 状态可被领取；并发确认或拒绝由条件更新的影响行数判定。
    query = update(Change).where(Change.id == cid, Change.status == 'pending')
    if pid is not None:
        query = query.where(Change.project_id == pid)
    return s.execute(query.values(status=status)).rowcount
