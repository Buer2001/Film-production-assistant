// 应用入口：加载项目列表，组合剧本、日程和制片工作区，并挂载 React 根组件。
import React, { useState, useEffect } from 'react';
import { createRoot } from 'react-dom/client';
import { api } from './api/client';
import ScriptWorkspace from './features/scripts/ScriptWorkspace';
import PlanningWorkspace from './features/planning/PlanningWorkspace';
import ShootingWorkspace from './features/shooting/ShootingWorkspace';
import NoticeWorkspace from './features/shooting/NoticeWorkspace';
import AgentWorkspace from './features/agent/AgentWorkspace';
import useProductionWorkspace from './features/production/useProductionWorkspace';
import { ProductionPages, RecordEditor } from './features/production/ProductionPages';
import { navigation, sectionFor } from './workspace';
import './style.css';
import './workspace.css';

/**
 * 渲染应用导航和当前项目；无参数，返回页面 JSX。
 * 首次挂载读取项目列表；子工作区通过 scriptBlocked 锁定项目切换、导航和新建，保护未保存输入。
 */
function App() {
  const [projects, setProjects] = useState([]), [pid, setPid] = useState('');
  const [tab, setTab] = useState('项目概览'), [name, setName] = useState('');
  const [scriptBlocked, setScriptBlocked] = useState(false);
  const workspace = useProductionWorkspace(pid, tab, setTab);
  const { state, busy, error, setError, act, load, setFilter, modelNotice, setModelNotice } = workspace;
  const shootingPage = tab === '拍摄安排' || tab === '通告';
  const section = sectionFor(tab);
  const [assistantIntent, setAssistantIntent] = useState('');
  const [assistantRunId, setAssistantRunId] = useState('');
  function goAssistant(intent = '', runId = '') { if (scriptBlocked) return; setAssistantIntent(intent); setAssistantRunId(runId); setTab('制片助手'); }
  useEffect(() => {
    api('/projects').then(items => { setProjects(items); if (items.length) setPid(items[0].id); }).catch(e => setError(e.message));
  }, []);
  /**
   * 提交项目名称并选中新项目；参数 e 为表单事件。通过工作区 act 统一处理忙碌状态和失败提示。
   */
  async function createProject(e) { e.preventDefault(); if (scriptBlocked) return; await act(async () => { const p = await api('/projects', { name }); setProjects([...projects, p]); setPid(p.id); setName(''); }); }
  return <div className={`app monochrome ${shootingPage ? 'shooting-mode' : tab === '剧本' ? 'script-mode' : tab === '项目日程' ? 'planning-mode' : ''}`}>
    <aside className="sidebar"><div className="brand">片场<span>学生制片工作台</span></div>
      <label>当前项目<select disabled={busy || scriptBlocked} value={pid} onChange={e => setPid(e.target.value)}><option value="">选择项目</option>{projects.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}</select></label>
      <nav aria-label="主要工作区">{navigation.map(item => <button key={item.label} disabled={scriptBlocked || busy} aria-current={section === item.label ? 'page' : undefined} className={section === item.label ? 'active' : ''} onClick={() => { setTab(item.tab); setFilter(''); if (item.tab === '制片助手') { setAssistantIntent(''); setAssistantRunId(''); } }}>{item.label}</button>)}</nav>
      <details className="project-menu"><summary>项目操作</summary><form onSubmit={createProject}><input aria-label="新项目名称" placeholder="新项目名称" value={name} onChange={e => setName(e.target.value)} required maxLength={200}/><button disabled={busy || scriptBlocked}>创建项目</button></form><p>开拍等项目节点在筹备日程的设置中维护。</p></details>
      <small>单制片维护 · 正式修改需确认</small>
    </aside>
    <main>{modelNotice && !shootingPage && <div className="warning" role="status">模型未配置，Agent 与剧本解析不可用，其余功能正常；配置方法见 README。 <button type="button" onClick={() => setModelNotice(false)} aria-label="关闭模型配置提示">关闭</button></div>}<header><div><small>PRODUCTION WORKSPACE</small><h1>{section}</h1><p>{state ? state.name : '创建项目，开始整理你的拍摄。'}</p></div>{tab !== '项目日程' && tab !== '制片助手' && !shootingPage && <button disabled={busy || scriptBlocked || !pid} onClick={() => act(() => load())}>刷新数据</button>}</header>
      {error && <div role="alert" className="error">{error}<button onClick={() => setError('')}>关闭</button></div>}
      {busy && <p role="status">处理中，请稍候…</p>}
      {state && <>
        {section === '项目记录' && <nav className="workspace-tabs" aria-label="项目记录分类">{['费用', '变更记录'].map(item => <button key={item} aria-pressed={tab === item} disabled={scriptBlocked} onClick={() => setTab(item)}>{item}</button>)}</nav>}
        {tab === '项目概览' && <OverviewFocus key={pid} pid={pid} onNavigate={setTab} onAssistant={goAssistant}/>}

        {tab === '剧本' && <ScriptWorkspace key={pid} pid={pid} onLockChange={setScriptBlocked}/>}
        {tab === '项目日程' ? <PlanningWorkspace key={pid} pid={pid} onLockChange={setScriptBlocked}/>
          : tab === '拍摄安排' ? <ShootingWorkspace key={pid} pid={pid} onLockChange={setScriptBlocked} onChanged={load} onGenerate={() => goAssistant("生成拍摄大计划")} published={state.notices} initialView={tab === "通告" ? "notice" : "plan"} legacy={state.records.filter(r => r.kind === 'schedule')}/>
          : tab === '通告' ? <NoticeWorkspace key={pid} pid={pid} onLockChange={setScriptBlocked} onChanged={load} published={state.notices}/>
          : tab === '制片助手' ? <AgentWorkspace key={pid + assistantIntent + assistantRunId} pid={pid} initialIntent={assistantIntent} initialRunId={assistantRunId} onLockChange={setScriptBlocked} onChanged={load}/>
          : tab !== '项目概览' && <ProductionPages workspace={workspace}/>}
      </>}
    </main>

    <RecordEditor workspace={workspace}/>
  </div>;
}


function OverviewFocus({ pid, onNavigate, onAssistant }) {
  const [data, setData] = useState(null), [error, setError] = useState('');
  useEffect(() => { let alive = true;
    Promise.all([api(`/projects/${pid}/planning`), api(`/projects/${pid}/agent/runs`), api(`/projects/${pid}/preparation`)])
      .then(([plan, runs, preparation]) => { if (alive) setData({plan, runs, preparation}); })
      .catch(e => { if (alive) setError(e.message); });
    return () => { alive = false; };
  }, [pid]);
  if (error) return <p className="error" role="alert">概览读取失败：{error}</p>;
  if (!data) return <p role="status">读取项目重点…</p>;
  const tasks = data.plan.tasks.filter(t => !['completed','cancelled'].includes(t.status))
    .sort((a,b) => (a.planned_end || '9999').localeCompare(b.planned_end || '9999')).slice(0,5);
  const pending = data.runs.filter(r => ['waiting_input','waiting_review'].includes(r.status));
  const settings = data.plan.settings;
  return <div className="overview-focus">
    <section className="project-milestones"><h2>项目节点</h2><div className="milestone-grid">{[['开拍',settings.shoot_start],['杀青',settings.shoot_end],['收尾',settings.close_date]].map(([name,date]) => <div key={name}><small>{name}</small><strong>{date || '待设置'}</strong></div>)}</div><button onClick={() => onNavigate('项目日程')}>管理项目日程</button></section>
    <div className="overview-columns"><section><div className="section-heading"><h2>近期要做</h2><button onClick={() => onNavigate('项目日程')}>全部任务</button></div>{tasks.map(t => <div className="focus-row" key={t.id}><strong>{t.title}</strong><span>{t.planned_end || '日期待定'} · {t.status === 'in_progress' ? '进行中' : '待处理'}</span></div>)}{!tasks.length && <p>暂无未完成任务，可以先让助手生成计划。</p>}</section>
    <section><h2>需要你决定</h2>{pending.map(r => <button className="pending-work" key={r.id} onClick={() => onAssistant('', r.id)}><strong>{r.message || '计划调整'}</strong><span>{r.status === 'waiting_review' ? '草稿待审阅' : '需要补充信息'}</span></button>)}{!pending.length && <p>暂无待确认工作。</p>}<button className="primary" onClick={() => onAssistant()}>打开制片助手</button></section></div>
    <section><div className="section-heading"><h2>筹备缺口 · {data.preparation.issues.length}</h2><button onClick={() => onNavigate('项目日程')}>检查人员资源</button></div>{data.preparation.issues.slice(0,4).map((issue,index) => <p key={index}>{issue.message}</p>)}{!data.preparation.issues.length && <p>已关联资料暂未发现缺口，未知资料仍需人工核实。</p>}{data.preparation.issues.length > 4 && <p>还有 {data.preparation.issues.length - 4} 条提示，在筹备日程查看。</p>}</section>
  </div>;
}

createRoot(document.getElementById('root')).render(<App/>);
