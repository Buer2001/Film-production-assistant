from decimal import Decimal
from backend.common.errors import BusinessError
from backend.models.record import Record
from backend.models.change import Change
from backend.models.notice import Notice
from backend.dao import project as dao
from backend.dao.record import rows
from backend.tools.scheduling import check_schedule
from backend.tools.notice import notice_status


def get_project(s, pid):
    p = dao.get_project(s, pid)
    if not p:
        raise BusinessError(404, '项目不存在')
    return p


def record_dict(r):
    return {'id': r.id, 'kind': r.kind, 'data': r.data}


def change_dict(c):
    return {k: getattr(c, k) for k in ('id', 'base_revision', 'reason', 'operations', 'before', 'status', 'created_at')}


def state(s, pid):
    p = get_project(s, pid)
    records = [record_dict(r) for r in rows(s, Record, pid) if r.kind != 'script_fields']
    notices = [{'id': n.id, 'date': n.date, 'version': n.version, 'revision': n.revision,
                'snapshot': n.snapshot, 'created_at': n.created_at, **notice_status(n, records)}
               for n in rows(s, Notice, pid)]
    return {'id': p.id, 'name': p.name, 'revision': p.revision, 'records': records,
            'changes': [change_dict(c) for c in rows(s, Change, pid)], 'notices': notices,
            'checks': check_schedule(records),
            'totals': {category: str(sum((Decimal(r['data']['amount']) for r in records
                if r['kind'] == 'expense' and r['data']['category'] == category), Decimal(0)))
                for category in ('预算', '报价', '已确定', '实际支出')}}


def project_dict(project):
    return {'id': project.id, 'name': project.name, 'revision': project.revision}


def list_projects(s):
    return [project_dict(project) for project in dao.list_projects(s)]


def create_project(s, name):
    project = dao.add_project(s, name)
    s.commit()
    return project_dict(project)
