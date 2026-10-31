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


def equal(actual, expected, description):
    if actual != expected:
        raise AssertionError(f'{description}：期望 {expected!r}，实际 {actual!r}')


def passed(description):
    print(f'PASS {description}', flush=True)


def workflow(client):
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

    def state():
        return request('GET', base).json()

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

    current = save([{'kind': 'scene', 'data': {'title': title}}
                    for title in ['礼堂场次', '无关场次']])
    scene = next(r for r in current['records'] if r['data']['title'] == '礼堂场次')
    unrelated = next(r for r in current['records'] if r['data']['title'] == '无关场次')
    passed('新增场次并确认草稿')
    current = save([
        {'kind': 'task', 'data': {'title': '借用礼堂', 'scene_ids': [scene['id']]}},
        {'kind': 'schedule', 'data': {'title': '礼堂拍摄', 'date': DAY,
            'start': '09:00', 'minutes': 90, 'scene_ids': [scene['id']],
            'resources': ['摄影师'], 'notes': '提前布光'}}])
    task = next(r for r in current['records'] if r['kind'] == 'task')
    schedule = next(r for r in current['records'] if r['kind'] == 'schedule')
    passed('新增关联筹备、拍摄安排并确认草稿')
    notice = request('POST', base + '/notices', {
        'date': DAY, 'base_revision': current['revision'], 'notes': '七点集合'}).json()
    equal(notice['version'], 1, '首次通告版本')

    def check_notice(stale):
        result = next(n for n in state()['notices'] if n['id'] == notice['id'])
        equal(result['stale'], stale, '通告待检查状态')
        equal(bool(result['reasons']), stale, '通告原因是否非空')
        equal(result['snapshot'], notice['snapshot'], '发布快照保持不变')

    check_notice(False)
    passed('发布当天通告，初始有效')
    save([{**task, 'data': {**task['data'], 'status': '已确认'}}])
    check_notice(True)
    passed('修改关联筹备状态，通告待检查且 reasons 非空')
    save([task])
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
    save([{'kind': 'task', 'id': task['id'], 'delete': True}])
    check_notice(True)
    passed('删除关联筹备后，通告待检查且快照不变')
    request('POST', base + '/agent', {'message': '检查筹备'}, expected=503)
    passed('模型未配置时 Agent 返回 503')
    request('POST', base + '/scripts/parse', {
        'text': '第1场 礼堂 日 内\n学生走上讲台。', 'base_revision': state()['revision']}, expected=503)
    passed('模型未配置时剧本解析返回 503')


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
