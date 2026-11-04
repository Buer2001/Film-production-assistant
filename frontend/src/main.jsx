// 应用入口：加载项目列表，组合剧本、日程和制片工作区，并挂载 React 根组件。
import React, { useState, useEffect } from 'react';
import { createRoot } from 'react-dom/client';
import { api } from './api/client';
import ScriptWorkspace from './features/scripts/ScriptWorkspace';
import PlanningWorkspace from './features/planning/PlanningWorkspace';
import ShootingWorkspace from './features/shooting/ShootingWorkspace';
import NoticeWorkspace from './features/shooting/NoticeWorkspace';
import useProductionWorkspace from './features/production/useProductionWorkspace';
import { ProductionPages, ProductionAssistant, RecordEditor } from './features/production/ProductionPages';
import { tabs } from './features/production/constants';
import './style.css';

/**
 * 渲染应用导航和当前项目；无参数，返回页面 JSX。
 * 首次挂载读取项目列表；子工作区通过 scriptBlocked 锁定项目切换、导航和新建，保护未保存输入。
 */
function App() {
  const [projects, setProjects] = useState([]), [pid, setPid] = useState('');
  const [tab, setTab] = useState('剧本'), [name, setName] = useState('');
  const [scriptBlocked, setScriptBlocked] = useState(false);
  const workspace = useProductionWorkspace(pid, tab, setTab);
  const { state, busy, error, setError, act, load, setFilter, modelNotice, setModelNotice } = workspace;
  const shootingPage = tab === '拍摄安排' || tab === '通告';
  useEffect(() => {
    api('/projects').then(items => { setProjects(items); if (items.length) setPid(items[0].id); }).catch(e => setError(e.message));
  }, []);
  /**
   * 提交项目名称并选中新项目；参数 e 为表单事件。通过工作区 act 统一处理忙碌状态和失败提示。
   */
  async function createProject(e) { e.preventDefault(); if (scriptBlocked) return; await act(async () => { const p = await api('/projects', { name }); setProjects([...projects, p]); setPid(p.id); setName(''); }); }
  return <div className={shootingPage ? 'app shooting-mode' : tab === '剧本' ? 'app script-mode' : tab === '项目日程' ? 'app planning-mode' : 'app'}>
    <aside className="sidebar"><div className="brand">片场<span>学生制片工作台</span></div>
      <label>当前项目<select disabled={busy || scriptBlocked} value={pid} onChange={e => setPid(e.target.value)}><option value="">选择项目</option>{projects.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}</select></label>
      <nav>{tabs.map(t => <button key={t} disabled={scriptBlocked} className={tab === t ? 'active' : ''} onClick={() => { setTab(t); setFilter(''); }}>{t}</button>)}</nav>
      <form onSubmit={createProject}><input aria-label="新项目名称" placeholder="新项目名称" value={name} onChange={e => setName(e.target.value)} required maxLength={200}/><button disabled={busy || scriptBlocked}>创建项目</button></form>
      <small>单制片维护 · 正式修改需确认</small>
    </aside>
    <main>{modelNotice && !shootingPage && <div className="warning" role="status">模型未配置，Agent 与剧本解析不可用，其余功能正常；配置方法见 README。 <button type="button" onClick={() => setModelNotice(false)} aria-label="关闭模型配置提示">关闭</button></div>}<header><div><small>PRODUCTION WORKSPACE</small><h1>{tab}</h1><p>{state ? `${state.name} · 数据版本 ${state.revision}` : '创建项目，开始整理你的拍摄。'}</p></div>{tab !== '项目日程' && !shootingPage && <button disabled={busy || scriptBlocked || !pid} onClick={() => act(() => load())}>刷新数据</button>}</header>
      {error && <div role="alert" className="error">{error}<button onClick={() => setError('')}>关闭</button></div>}
      {busy && <p role="status">处理中，请稍候…</p>}
      {state && <>
        {tab === '剧本' && <ScriptWorkspace key={pid} pid={pid} onLockChange={setScriptBlocked}/>}
        {tab === '项目日程' ? <PlanningWorkspace key={pid} pid={pid} onLockChange={setScriptBlocked}/>
          : tab === '拍摄安排' ? <ShootingWorkspace key={pid} pid={pid} onLockChange={setScriptBlocked} onChanged={load} legacy={state.records.filter(r => r.kind === 'schedule')}/>
          : tab === '通告' ? <NoticeWorkspace key={pid} pid={pid} onLockChange={setScriptBlocked} onChanged={load} published={state.notices}/>
          : <ProductionPages workspace={workspace}/>}
      </>}
    </main>
    {tab !== '项目日程' && !shootingPage && <ProductionAssistant workspace={workspace}/>}
    <RecordEditor workspace={workspace}/>
  </div>;
}

createRoot(document.getElementById('root')).render(<App/>);
