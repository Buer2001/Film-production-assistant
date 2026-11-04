# 测试职责：验证旧空占位场次可解析，且人工内容和并发新增草稿始终受保护。
import pytest
from fastapi.testclient import TestClient
from backend.main import create_app
from backend.models.script import Script,SceneBreakdown
from backend.schemas.script import SceneData
from backend.dao.script.scene import list_for_script


# 用途：构造版本为3的旧剧本及带人工字段标记的占位场次。
# 参数：client 为客户端，summary/status 控制摘要和剧本状态；返回接口前缀、剧本ID、场次ID。
# 副作用：只向测试数据库提交种子数据，用于复现旧数据的解析保护。
def seed(client, *, summary='', status='review'):
    pid=client.post('/api/projects',json={'name':'历史占位恢复'}).json()['id']
    root=f'/api/projects/{pid}/script-workspace'
    doc=client.post(root,json={'title':'剧本','content':'1 内 日 车内\n晚来握着玉佩。'}).json()
    with client.app.state.sessions() as session:
        script=session.get(Script,doc['id']); script.status=status; script.revision=3
        data=SceneData(summary=summary).model_dump(mode='json')
        row=SceneBreakdown(script_id=doc['id'],sort_order=0,summary=summary,
            details={key:data[key] for key in ('cast','makeup_costume','action_props','other_props')},
            evidence={'text':'','manual_fields':list(SceneData.model_fields)},extracted_data={})
        session.add(row); session.commit(); original=row.id
    return root,doc['id'],original


# 用例：旧空占位场次允许启动解析，但开始解析时保留已有正式数据。
# 参数：tmp_path 为测试专用临时目录；monkeypatch 为临时替换配置或依赖的pytest工具。
# 返回：无；使用断言或预期异常检查上述行为。
def test_empty_legacy_placeholder_allows_parse_without_destroying_existing_data(tmp_path,monkeypatch):
    monkeypatch.setenv('DRAFT_DIR',str(tmp_path/'drafts'))
    async def extracted(source,model=None):
        return {'summary':'模型拆解出的内容','review_issues':[]}
    monkeypatch.setattr('backend.ai.script_extractor.extract_scene',extracted)
    with TestClient(create_app(f"sqlite:///{tmp_path/'legacy.db'}")) as client:
        root,sid,original=seed(client)
        doc=client.get(f'{root}/{sid}').json()
        assert doc['can_start_parse'] is True
        assert doc['scenes'][0]['parse_status']=='pending'
        assert doc['progress']['completed']==0
        response=client.post(f'{root}/{sid}/parse',json={'revision':3})
        assert response.status_code==200,response.text
        client.get(f'{root}/{sid}/events')
        result=client.get(f'{root}/{sid}').json()
        assert result['scenes'][0]['summary']=='模型拆解出的内容'
        assert result['can_start_parse'] is False
        with client.app.state.sessions() as session:
            rows=list_for_script(session,sid)
            assert len(rows)==1 and rows[0].id==original and rows[0].summary==''


# 用例：含人工内容或已确认的旧场次不能被重新解析覆盖。
# 参数：tmp_path 为测试专用临时目录；monkeypatch 为临时替换配置或依赖的pytest工具；summary 为旧场次摘要；status 为旧场次状态。
# 返回：无；使用断言或预期异常检查上述行为。
@pytest.mark.parametrize('summary,status',[('已经填写的人工内容','review'),('','confirmed')])
def test_meaningful_or_confirmed_rows_cannot_be_overwritten(tmp_path,monkeypatch,summary,status):
    monkeypatch.setenv('DRAFT_DIR',str(tmp_path/'drafts'))
    with TestClient(create_app(f"sqlite:///{tmp_path/'protected.db'}")) as client:
        root,sid,original=seed(client,summary=summary,status=status)
        doc=client.get(f'{root}/{sid}').json()
        assert doc['can_start_parse'] is False
        response=client.post(f'{root}/{sid}/parse',json={'revision':3})
        assert response.status_code==409
        with client.app.state.sessions() as session:
            assert session.get(SceneBreakdown,original).summary==summary

# 用例：初次检查后刚保存的人工草稿仍受保护，解析启动不能覆盖它。
# 参数：tmp_path 为测试专用临时目录；monkeypatch 为临时替换配置或依赖的pytest工具。
# 返回：无；使用断言或预期异常检查上述行为。
def test_parse_does_not_overwrite_a_draft_created_after_initial_check(tmp_path,monkeypatch):
    from copy import deepcopy
    from backend.service.script import breakdown
    monkeypatch.setenv('DRAFT_DIR',str(tmp_path/'drafts'))
    with TestClient(create_app(f"sqlite:///{tmp_path/'race.db'}")) as client:
        root,sid,original=seed(client)
        initial=client.get(f'{root}/{sid}').json()
        pid=initial['project_id']
        human=deepcopy(initial)
        human.update(revision=4,status='review',base_revision=3)
        human['scenes'][0]['summary']='检查之后刚保存的人工内容'
        real_claim=breakdown.claim
        def concurrent_save(session,row,revision):
            real_claim(session,row,revision)
            client.app.state.parse_jobs.store.write(pid,sid,human)
        monkeypatch.setattr(breakdown,'claim',concurrent_save)
        response=client.post(f'{root}/{sid}/parse',json={'revision':3})
        assert response.status_code==409
        saved=client.get(f'{root}/{sid}').json()
        assert saved['scenes'][0]['summary']=='检查之后刚保存的人工内容'
        with client.app.state.sessions() as session:
            assert session.get(Script,sid).revision==3
