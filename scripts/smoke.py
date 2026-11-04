"""从项目根目录运行：python scripts/smoke.py，不需要模型或正式数据库。"""
import os
from contextlib import contextmanager
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time

import httpx


ROOT = Path(__file__).resolve().parents[1]
DAY = '2026-02-06'


@contextmanager
# 用途：提供冒烟测试专用临时目录，退出时清理；不使用正式数据库。
# 参数：无；产出：临时目录路径。Windows 文件仍被占用时有限重试，最终失败仍抛出。
def temporary_workspace():
    directory = tempfile.TemporaryDirectory(prefix='film-smoke-')
    try:
        yield directory.name
    finally:
        # Windows可能延迟释放已退出进程的文件句柄，有限重试但不吞掉最终失败。
        for attempt in range(5):
            try:
                directory.cleanup()
                break
            except PermissionError:
                if attempt == 4:
                    raise
                time.sleep(0.2)


# 用途：比较实际值和预期值，失败时带步骤说明抛出 AssertionError。
# 参数：actual 为实际结果，expected 为预期结果，description 为检查项名称；返回：无。
def equal(actual, expected, description):
    if actual != expected:
        raise AssertionError(f'{description}：期望 {expected!r}，实际 {actual!r}')


# 用途：输出已通过的步骤说明；参数 description 为说明文本；返回：无。
def passed(description):
    print(f'PASS {description}', flush=True)


# 用途：通过真实 HTTP 请求验证项目、变更、通告和导出等核心工作流。
# 参数：client 为连接临时后端的 httpx 客户端；返回：无，任一步不符即抛出异常。
# 副作用：只在临时测试数据库中创建和修改业务数据，不调用真实模型。
def workflow(client):
    # 参数：method/path 为请求方法和接口，body 为可选 JSON，expected 为预期状态码。
    # 返回：原始 HTTP 响应；错误时报告响应内容，便于定位失败步骤。
    def request(method, path, body=None, expected=200):
        response = client.request(method, '/api' + path, json=body)
        equal(response.status_code, expected,
              f'{method} {path} HTTP 状态，响应内容 {response.text[:500]!r}')
        return response

    health = request('GET', '/health').json()
    equal(health, {'status': 'ok', 'agent_configured': False}, '未配置模型的健康检查')
    passed('健康检查，模型配置已隔离')
    project = request('POST', '/projects', {'name': 'HTTP 冒烟剧组'}).json()
    pid = project['id']
    base = f'/projects/{pid}'
    equal(project['revision'], 0, '新项目版本')
    passed('创建项目')

    # 返回当前测试项目快照，供每一步检查版本和记录是否正确更新。
    def state():
        return request('GET', base).json()

    # 根据当前版本提交并确认一批变更；参数 operations 为操作列表，返回更新后快照。
    def save(operations):
        revision = state()['revision']
        draft = request('POST', base + '/changes', {
            'base_revision': revision, 'reason': '真实 HTTP 冒烟', 'operations': operations}).json()
        equal(draft['status'], 'pending', '新草稿状态')
        result = request('POST', base + f'/changes/{draft["id"]}/confirm').json()
        equal(result['status'], 'confirmed', '确认响应状态')
        current = state()
        equal(current['revision'], revision + 1, '确认后的项目版本')
        return current

    # 任务已统一到 V2 日程；V3 仅补资料和检查，不恢复旧 records.task 写入。
    period = {'start_date': DAY, 'end_date': DAY}
    people = request('POST', base + '/people', {'revision': state()['revision'], 'person': {
        'name': '小王', 'availability': [{**period, 'state': 'available'}]}}).json()
    person_id = people['people'][0]['id']
    resource = {'title': '教学楼302', 'category': 'location', 'preparation': {
        'status': 'confirmed', 'contact_person_id': person_id,
        'availability': [{**period, 'state': 'available'}], 'cost_status': 'free'}}
    resource_result = request('POST', base + '/resources', {
        'revision': state()['revision'], 'resource': resource}).json()
    resource_id = resource_result['resources'][0]['id']
    plan = request('POST', base + '/planning/tasks', {'revision': 0, 'task': {
        'title': '落实教室', 'details': {'requires_people': True, 'person_ids': [person_id],
            'usage_period': period, 'resource_refs': [{'name': '教学楼302', 'record_id': resource_id}]}}}).json()
    equal(request('GET', base + '/preparation').json()['issues'], [], 'V3 已落实资料无缺口')
    resource['preparation']['status'] = 'unavailable'
    request('PUT', base + f'/resources/{resource_id}', {'revision': state()['revision'], 'resource': resource})
    issues = request('GET', base + '/preparation').json()['issues']
    equal(any(i['code'] == 'resource_unavailable' and i['resource_id'] == resource_id for i in issues), True, '资源不可用重新提示')
    equal(request('GET', base + '/planning').json()['revision'], plan['revision'], '落实资料不自动改日程版本')
    request('DELETE', base + f'/people/{person_id}?revision={state()["revision"]}', expected=422)
    request('DELETE', base + f'/resources/{resource_id}?revision={state()["revision"]}', expected=422)
    resource['preparation']['status'] = 'confirmed'
    request('PUT', base + f'/resources/{resource_id}', {'revision': state()['revision'], 'resource': resource})
    equal(request('GET', base + '/preparation').json()['issues'], [], '资源恢复确认后缺口消除')
    passed('V3 人员、资源、日程关联、筹备检查及引用删除保护')

    current = save([{'kind': 'scene', 'data': {'title': title}}
                    for title in ['礼堂场次', '无关场次']])
    scene = next(r for r in current['records'] if r['data']['title'] == '礼堂场次')
    unrelated = next(r for r in current['records'] if r['data']['title'] == '无关场次')
    passed('新增场次并确认草稿')
    current = save([
        {'kind': 'requirement', 'data': {'title': '借用礼堂', 'scene_ids': [scene['id']]}},
        {'kind': 'schedule', 'data': {'title': '礼堂拍摄', 'date': DAY,
            'start': '09:00', 'minutes': 90, 'scene_ids': [scene['id']],
            'resources': ['摄影师'], 'notes': '提前布光'}}])
    requirement = next(r for r in current['records'] if r['kind'] == 'requirement')
    schedule = next(r for r in current['records'] if r['kind'] == 'schedule')
    passed('新增旧业务需求、拍摄安排并确认草稿')
    notice = request('POST', base + '/notices', {
        'date': DAY, 'base_revision': current['revision'], 'notes': '七点集合'}).json()
    equal(notice['version'], 1, '首次通告版本')

    # 参数 stale 为预期失效状态；断言通告保留原快照，且失效提示符合当前变更。
    def check_notice(stale):
        result = next(n for n in state()['notices'] if n['id'] == notice['id'])
        equal(result['stale'], stale, '通告待检查状态')
        equal(bool(result['reasons']), stale, '通告原因是否非空')
        equal(result['snapshot'], notice['snapshot'], '发布快照保持不变')

    check_notice(False)
    passed('发布当天通告，初始有效')
    save([{**requirement, 'data': {**requirement['data'], 'status': '已确认'}}])
    check_notice(True)
    passed('修改关联筹备状态，通告待检查且 reasons 非空')
    save([requirement])
    check_notice(False)
    passed('恢复筹备状态，通告重新有效')
    save([{**unrelated, 'data': {**unrelated['data'], 'title': '无关场次改名'}}])
    check_notice(False)
    passed('修改无关场次，通告仍有效')
    exported = request('GET', base + f'/notices/{notice["id"]}/export')
    equal(exported.headers.get('content-disposition'),
          f'attachment; filename="notice-{DAY}-v1.txt"', '通告导出文件名')
    for content in ['HTTP 冒烟剧组', DAY, '通告 V1', '七点集合', '礼堂拍摄', '摄影师', '提前布光']:
        equal(content in exported.text, True, f'导出内容包含 {content!r}')
    passed('导出通告 TXT，文件名和快照内容正确')
    impact = request('POST', base + '/impact', {
        'base_revision': state()['revision'], 'resources': ['摄影师']}).json()
    equal(schedule['id'] in [r['id'] for r in impact['records']], True, '资源影响包含当天安排')
    equal(notice['id'] in [n['id'] for n in impact['notices']], True, '资源影响包含通告')
    passed('按资源查询影响分析')
    save([{'kind': 'requirement', 'id': requirement['id'], 'delete': True}])
    check_notice(True)
    passed('删除关联筹备后，通告待检查且快照不变')
    request('POST', base + '/agent', {'message': '检查筹备'}, expected=503)
    passed('模型未配置时 Agent 返回 503')
    request('POST', base + '/scripts/parse', {
        'text': '第1场 礼堂 日 内\n学生走上讲台。', 'base_revision': state()['revision']}, expected=503)
    passed('模型未配置时剧本解析返回 503')


# 用途：分配临时数据库和空闲端口，启动后端子进程后执行完整冒烟流程。
# 参数：无；返回：无。成功或失败都会结束子进程，临时目录由上下文负责清理。
# 启动日志写入临时文件，服务启动超时或提前退出时报告实际原因。
def main():
    try:
        with temporary_workspace() as directory:
            temp = Path(directory)
            with socket.socket() as sock:
                sock.bind(('127.0.0.1', 0))
                port = sock.getsockname()[1]
            env = os.environ.copy()
            env['DATABASE_URL'] = f'sqlite:///{(temp / "smoke.db").as_posix()}'
            for key in ('LLM_API_KEY', 'LLM_MODEL'):
                env.pop(key, None)
            # 日志写临时文件，避免子进程输出填满管道阻塞。
            with (temp / 'uvicorn.log').open('w+', encoding='utf-8') as log:
                process = subprocess.Popen([
                    sys.executable, '-m', 'uvicorn', 'backend.main:app',
                    '--host', '127.0.0.1', '--port', str(port), '--log-level', 'warning'],
                    cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
                try:
                    with httpx.Client(base_url=f'http://127.0.0.1:{port}',
                                      timeout=10, trust_env=False) as client:
                        deadline = time.monotonic() + 20
                        last = '尚未收到响应'
                        while time.monotonic() < deadline:
                            if process.poll() is not None:
                                raise RuntimeError(f'服务启动：期望进程运行，实际退出码 {process.returncode}')
                            try:
                                response = client.get('/api/health')
                                if response.status_code == 200:
                                    break
                                last = f'HTTP {response.status_code}: {response.text}'
                            except httpx.TransportError as exc:
                                last = str(exc)
                            time.sleep(0.1)
                        else:
                            raise RuntimeError(f'服务启动：期望 20 秒内 HTTP 200，实际 {last}')
                        workflow(client)
                except Exception:
                    log.flush()
                    log.seek(0)
                    print(f'服务日志：{log.read()[-4000:]}', flush=True)
                    raise
                finally:
                    if process.poll() is None:
                        process.terminate()
                        try:
                            process.wait(timeout=10)
                        except subprocess.TimeoutExpired:
                            process.kill()
                            process.wait(timeout=10)
        passed('服务子进程已退出，临时数据库已删除')
        return 0
    except Exception as exc:
        print(f'FAIL {exc}', flush=True)
        return 1


if __name__ == '__main__':
    sys.exit(main())
