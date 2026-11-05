# 测试职责：用模拟模型验证 V5 的要求理解、候选生成、模型复核与有限修正，不调用真实模型。
import json
from backend.ai.client import ModelClient
from test_agent_v5 import SCOPE, candidate, client, setup  # noqa: F401  复用夹具与构造
from backend.models.script import Script, SceneBreakdown


# 按调用序号和工具名返回预设结构化结果；记录实际调用顺序，便于断言。
def fake_model(monkeypatch, responder):
    calls = []

    async def chat(self, messages, tools):
        name = tools[0]['function']['name']
        payload = responder(len(calls), name)
        calls.append(name)
        return {'role': 'assistant', 'content': '',
                'tool_calls': [{'id': f'call-{len(calls)}',
                                'function': {'name': name, 'arguments': json.dumps(payload, ensure_ascii=False)}}]}

    monkeypatch.setattr(ModelClient, 'chat', chat)
    return calls


# 模型理解结果：把制片的一句话解析成范围和空问题单。
UNDERSTANDING = {'mode': 'compose', 'scope': SCOPE, 'constraints': [], 'assumptions': ['按开拍期推断'],
                 'questions': [], 'reason': ''}
# 复核通过，不再要求修正。
APPROVED = {'verdict': 'ok', 'findings': [], 'summary': ''}


# 自然语言发起：理解范围、生成候选、复核通过后进入待审阅。
def test_natural_language_run_creates_model_draft(client, monkeypatch):
    pid, root, scenes = setup(client)
    calls = fake_model(monkeypatch, lambda index, name: {
        'submit_understanding': UNDERSTANDING,
        'submit_candidate': candidate(scenes),
        'submit_review': APPROVED}[name])

    response = client.post(root + '/runs', json={'message': '帮我排开拍第一周'})
    assert response.status_code == 200, response.text
    run = response.json()
    assert run['status'] == 'waiting_review'
    assert run['scope']['phase'] == SCOPE['phase']
    assert run['scope']['start_date'] == SCOPE['start_date']
    assert calls == ['submit_understanding', 'submit_candidate', 'submit_review']
    assert run['draft']['validation']['origin'] == 'model'
    assert run['draft']['validation']['counts'] == {'task': 1, 'shooting': 1}


# 复核发现问题后修正一轮，修正结果重新走程序检查并再次复核。
def test_review_findings_trigger_single_revision(client, monkeypatch):
    pid, root, scenes = setup(client)
    first = candidate(scenes)
    revised = candidate(scenes)
    revised['operations'].append({'op_id': 'op-3', 'entity': 'project_task', 'action': 'add',
                                  'temp_id': 't2', 'patch': {'title': '结清器材租金', 'phase': 'closing'},
                                  'reason': '复核提出的收尾遗漏'})
    finding = {'verdict': 'fixable', 'summary': '缺少收尾任务',
               'findings': [{'kind': 'omission', 'message': '缺少收尾任务', 'operation_ids': [],
                             'needs_user': False}]}

    def responder(index, name):
        if name == 'submit_understanding':
            return UNDERSTANDING
        if name == 'submit_candidate':
            return first if index == 1 else revised
        return finding if index == 2 else APPROVED

    calls = fake_model(monkeypatch, responder)
    run = client.post(root + '/runs', json={'message': '排开拍第一周'}).json()
    assert run['status'] == 'waiting_review'
    assert calls == ['submit_understanding', 'submit_candidate', 'submit_review',
                     'submit_candidate', 'submit_review']
    assert run['draft']['validation']['counts']['task'] == 2
    assert run['draft']['validation']['origin'] == 'model'


# 制片自己提交的候选不做模型复核，不产生任何模型调用。
def test_manual_candidate_skips_model(client, monkeypatch):
    pid, root, scenes = setup(client)

    async def never(*args, **kwargs):
        raise AssertionError('制片提交的候选不应调用模型')

    monkeypatch.setattr(ModelClient, 'chat', never)
    response = client.post(root + '/runs', json={'mode': 'compose', 'message': '按范围编排',
                                                 'scope': SCOPE, 'candidate': candidate(scenes)})
    assert response.status_code == 200, response.text
    assert response.json()['reflect_status'] == 'skipped_manual'


# 修正达到上限后不再自动改，转人工决定，运行停在等待补充。
def test_revision_budget_stops_and_asks_user(client, monkeypatch):
    pid, root, scenes = setup(client)
    proposal = candidate(scenes)
    finding = {'verdict': 'fixable', 'summary': '仍需调整',
               'findings': [{'kind': 'requirement', 'message': '缺少用餐安排', 'operation_ids': [],
                             'needs_user': False}]}

    def responder(index, name):
        return proposal if name == 'submit_candidate' else finding

    calls = fake_model(monkeypatch, responder)
    run = client.post(root + '/runs', json={'message': '排开拍第一周', 'scope': SCOPE,
                                            'mode': 'compose'}).json()
    assert run['status'] == 'waiting_input'
    assert run['draft'] is None
    assert any('用餐' in question for question in run['questions'])
    assert calls.count('submit_review') == 3


# 模型通信失败转成业务错误，不把半成品当成功。
def test_model_failure_returns_business_error(client, monkeypatch):
    pid, root, scenes = setup(client)

    async def broken(*args, **kwargs):
        raise RuntimeError('模型未配置')

    monkeypatch.setattr(ModelClient, 'chat', broken)
    response = client.post(root + '/runs', json={'message': '排开拍第一周'})
    assert response.status_code == 502
