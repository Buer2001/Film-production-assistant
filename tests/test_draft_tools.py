# 测试职责：验证分场证据定位、草稿文件原子更新及单场模型提取边界。
from concurrent.futures import ThreadPoolExecutor
import pytest


# 用例：分场保留原文位置，跳过演职人员表，并提示异常边界。
# 返回：无；使用断言或预期异常检查上述行为。
def test_split_scenes_preserves_original_and_skips_credits():
    from backend.tools.script.splitter import split_scenes
    text='《测试》\n1 内 日 车内\n晚来握着玉佩。\n2、出租屋 夜 内\n晚来拿起手机。\n3、演职人员表\n导演某某\n4 外 日 街头\n晚来走远。'
    result=split_scenes(text)
    assert [r['scene_number'] for r in result['scenes']] == ['1','2','4']
    assert all(text[r['source_start']:r['source_end']] == r['evidence']['text'] for r in result['scenes'])
    assert '演职人员表' not in result['scenes'][1]['evidence']['text']
    assert result['warnings']


# 用例：无法识别场次边界时保留完整原文，交由人工复核。
# 返回：无；使用断言或预期异常检查上述行为。
def test_unknown_boundaries_are_kept_for_manual_review():
    from backend.tools.script.splitter import split_scenes
    result=split_scenes('没有场次标题的一整段正文')
    assert len(result['scenes']) == 1 and result['scenes'][0]['evidence']['text'] == '没有场次标题的一整段正文'
    assert result['warnings']


# 用例：并发更新不丢计数，异常标识不能越出草稿目录，序列化失败不损坏原文件。
# 参数：tmp_path 为测试专用临时目录。
# 返回：无；使用断言或预期异常检查上述行为。
def test_draft_store_atomic_update_and_path_safety(tmp_path):
    from backend.tools.script.draft_store import DraftStore
    store=DraftStore(tmp_path)
    store.write('../project','../../script', {'count':0})
    def increment(_):
        def change(doc):
            doc['count'] += 1
            return doc
        return DraftStore(tmp_path).update('../project','../../script',change)
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(increment,range(20)))
    assert store.load('../project','../../script')['count'] == 20
    assert len(list(tmp_path.glob('*.json'))) == 1
    before=store.load('../project','../../script')
    with pytest.raises(TypeError):
        store.write('../project','../../script', {'bad':object()})
    assert store.load('../project','../../script') == before

# 用例：单场模型提取保留全文中的原始证据偏移，不使用片段相对位置。
# 返回：无；使用断言或预期异常检查上述行为。
def test_single_scene_extraction_keeps_global_source_location():
    import asyncio, json
    from backend.ai.script_extractor import extract_scene
    from backend.tools.script.splitter import split_scenes
    text='片名\n1 内 日 车内\n晚来握着玉佩。'
    source=split_scenes(text)['scenes'][0]
    class Model:
        async def chat(self,messages,tools):
            assert 'scenes必须恰好一条' in messages[0]['content']
            return {'tool_calls':[{'function':{'name':'submit_breakdown','arguments':json.dumps({'scenes':[{
                'scene_number':'1','location':'车内','summary':'晚来握着玉佩','evidence_text':source['evidence']['text']
            }]},ensure_ascii=False)}}]}
    row=asyncio.run(extract_scene(source,Model()))
    assert row['evidence']['start'] == 3
    assert row['evidence']['text'] == text[3:]
    assert row['extracted_data']['location'] == '车内'
