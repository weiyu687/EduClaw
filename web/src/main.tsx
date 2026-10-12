import React, {useEffect,useRef,useState} from 'react';
import {createRoot} from 'react-dom/client';
import {request,takeCredential,query,labels,actionLabels} from './api';
import type {Session,Task,Detail,Preview,Action} from './api';
import './style.css';
import {Workspace} from './Workspace';

function App(){
  const [token] = useState(takeCredential);
  const [sessions,setSessions] = useState<Session[]>([]);
  const [session,setSession] = useState('');
  const [tasks,setTasks] = useState<Task[]>([]);
  const [selected,setSelected] = useState<number>();
  const [detail,setDetail] = useState<Detail>();
  const [preview,setPreview] = useState<Preview>();
  const [error,setError] = useState('');
  const [notice,setNotice] = useState('');
  const [loading,setLoading] = useState(true);
  const [busy,setBusy] = useState(false);
  const [executionWord,setExecutionWord] = useState('');
  const [tab,setTab] = useState<'steps'|'results'>('steps');
  const [tick,setTick] = useState(0);
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(()=>{
    let cancelled=false;
    if(!token){setLoading(false);setError('请使用终端显示的本次启动地址打开工作台。');return;}
    request<Session[]>(token,'/api/sessions').then(rows=>{if(!cancelled){setSessions(rows);setSession(current=>rows.some(s=>s.id===current)?current:(rows[0]?.id??''));setLoading(false);}})
      .catch(e=>{if(!cancelled){setError(String(e.message));setLoading(false);}});
    return ()=>{cancelled=true;};
  },[token,tick]);
  useEffect(()=>{
    if(!session){setTasks([]);setDetail(undefined);return;}
    let cancelled=false;let inFlight=false;
    async function refresh(){
      if(inFlight)return;inFlight=true;
      try {
        const rows=await request<Task[]>(token,'/api/tasks?'+query(session));
        const value=selected===undefined?undefined:await request<Detail>(token,'/api/task?'+query(session,selected));
        if(!cancelled){setTasks(rows);setDetail(value);setError('');setLoading(false);}
      }catch(e){if(!cancelled){setError(e instanceof Error?e.message:'连接中断');setLoading(false);}}finally{inFlight=false;}
    }
    void refresh();const timer=window.setInterval(refresh,3000);
    return ()=>{cancelled=true;window.clearInterval(timer);};
  },[session,selected,token,tick]);
  useEffect(()=>{if(preview)dialog.current?.showModal();else dialog.current?.close();},[preview]);
  async function prepare(action:Action){
    if(selected===undefined){setError('请先选择一个任务。');return;}setBusy(true);setError('');setExecutionWord('');
    try{setPreview(await request<Preview>(token,'/api/preview',{session,number:selected,action}));}
    catch(e){setError(e instanceof Error?e.message:'预览失败');}finally{setBusy(false);}
  }
  async function confirm(){
    if(!preview)return;setBusy(true);setError('');
    const ticket=preview.ticket;
    try{const value=await request<Detail>(token,'/api/confirm',{ticket,confirmation:preview.action==='execute'?executionWord:'CONFIRM'});setDetail(value);setNotice(preview.action==='execute'?'执行已提交。可在此查看进度，后续步骤需再次审批。':'操作已记录。后续工具仍需独立审批。');setTick(x=>x+1);}
    catch(e){setError(e instanceof Error?e.message:'确认结果未知，请刷新核查。');}
    finally{setPreview(undefined);setBusy(false);}
  }
  const live=tasks.filter(t=>t.status==='running').length;
  return <div className="shell">
    <aside className="sidebar"><a className="brand" href="/" aria-label="EduClaw 工作台"><span className="brand-mark">E</span> EduClaw<span className="brand-dot">●</span></a>
      <div className="workspace-label">个人工作空间</div><div className="nav-active">▦ <span>任务工作台</span><span className="count">{tasks.length}</span></div>
      <div className="nav-hint">学习、研究与日常工作的<br/>每一步，都有迹可循。</div>
      <div className="side-footer"><span className="online-dot"/> 本地工作台<div>所有操作，清楚可控</div></div>
    </aside>
    <main><header><div><div className="eyebrow">WORKSPACE / TASKS</div><h1>任务工作台</h1><p>查看进度，核对结果，掌握下一步。</p></div><button className="secondary" onClick={()=>{setLoading(true);setTick(x=>x+1);}}>↻ 刷新</button></header>
      {error&&<div className="alert" role="alert">{error}<span>页面不会自动重试操作；请先刷新核查状态。</span></div>}
      {notice&&<div className="notice" role="status">{notice}</div>}
      <Workspace key={session} token={token} session={session} onSession={id=>{setSession(id);setSelected(undefined);setDetail(undefined);setTick(x=>x+1);}} onTask={n=>{setSelected(n);setTick(x=>x+1);}} onAction={a=>void prepare(a)} onView={v=>{setTab(v);setTick(x=>x+1);}}/>
      <section className="overview" aria-label="任务概览"><div><span>全部任务</span><strong>{tasks.length}</strong></div><div><span>进行中</span><strong>{live}</strong></div><div><span>已完成</span><strong>{tasks.filter(t=>t.status==='completed').length}</strong></div><div className="overview-note">每一步，都有据可查</div></section>
      <div className="section-heading"><h2>我的任务</h2><label>会话 <select aria-label="选择会话" value={session} onChange={e=>{setSession(e.target.value);setSelected(undefined);setDetail(undefined);setTasks([]);setPreview(undefined);}}>{sessions.map(s=><option key={s.id} value={s.id}>{s.label} · {s.updated_at.slice(0,10)}</option>)}</select></label></div>
      <div className="work-grid"><section className="task-list" aria-label="任务列表">
        {loading&&<p role="status" className="empty">正在读取任务…</p>}
        {!loading&&!tasks.length&&<div className="empty"><span>◇</span><h3>这里还没有任务</h3><p>选择技能和工具，在上方输入目标创建第一个任务。</p></div>}
        {tasks.map(task=><button className={'task-card '+(selected===task.number?'selected':'')} key={task.number} onClick={()=>{setSelected(task.number);setDetail(undefined);setNotice('');setPreview(undefined);}}>
          <div className="card-meta"><span>任务 {String(task.number).padStart(2,'0')}</span><span className={'badge '+task.status}>{labels[task.control==='active'?task.status:task.control]??task.status}</span></div>
          <h3>{task.goal}</h3><div className="card-bottom"><span>{task.completed} / {task.total} 步已处理</span><span>查看详情 →</span></div><progress aria-label={`任务 ${task.number} 进度`} value={task.completed} max={task.total}/>
        </button>)}
      </section><section className="detail-panel" aria-label="任务详情">
        {!detail?<div className="empty detail-empty"><span>◎</span><h3>{selected===undefined?'选择一个任务':'正在加载任务'}</h3><p>步骤、依赖和结果证据将在这里展示。</p></div>:<>
          <div className="detail-top"><span className="eyebrow">TASK {String(detail.number).padStart(2,'0')}</span><span className="badge">{labels[detail.control==='active'?detail.status:detail.control]??detail.status}</span></div>
          <h2 className="task-title">{detail.goal}</h2><div className="next-step"><strong>{detail.status==='completed'?'任务已完成':detail.execution_pending?'正在执行':'下一步'}</strong><p>{detail.status==='completed'?'所有步骤已完成，可在结果证据中查看输出。':detail.execution_pending?'正在连接工具或执行已确认的代码，结果将自动更新。':detail.recovery.message}</p><small>Python 代码可在此审阅执行；文件授权与重规划仍在 CLI 完成。关闭页面不会取消任务。</small></div>
          {detail.execution_error&&<div className="alert" role="alert">执行进程已退出，请核查结果或在 CLI 使用 /失败 查看原因；不会自动重试。</div>}
          <div className="actions">{detail.actions.map(action=><button key={action} className={action==='execute'?'primary':action==='cancel'?'danger':'secondary'} disabled={busy} onClick={()=>void prepare(action)}>{actionLabels[action]}</button>)}</div>
          <div className="tabs" role="tablist" aria-label="任务内容"><button role="tab" aria-selected={tab==='steps'} onClick={()=>setTab('steps')}>执行步骤 <span>{detail.total}</span></button><button role="tab" aria-selected={tab==='results'} onClick={()=>setTab('results')}>结果证据 <span>{detail.results.length}</span></button></div>
          <div role="tabpanel">{tab==='steps'?<ol className="steps">{detail.steps.map(step=><li key={step.number}><span className={'step-num '+step.status}>{step.status==='completed'?'✓':step.number}</span><div><div className="step-heading"><strong>{step.tool}</strong><span>{labels[step.status]??step.status}</span></div><p>{step.dependencies.length?`依赖第 ${step.dependencies.join('、')} 步的结果`:'独立步骤'}</p><details><summary>查看输入参数</summary><pre>{JSON.stringify(step.arguments,null,2)}</pre></details></div></li>)}</ol>:<div className="results">{!detail.results.length?<p className="empty">暂时没有结果。工具执行后会保存在这里。</p>:detail.results.map(row=><article key={row.step}><h3>第 {row.step} 步 · {labels[row.status]??row.status}</h3><p className={row.intact&&!row.truncated?'verified':'alert'}>{row.intact&&!row.truncated?'✓ 结果摘要校验通过':'结果不完整或摘要不匹配，请在 CLI 核查'}</p><pre>{row.summary}</pre><details><summary>查看保存内容与校验信息</summary><pre>{row.content}</pre>{row.preview_truncated&&<p>此处只展示前 20000 个字符，完整内容请在 CLI 查看。</p>}<code>SHA256 {row.digest}</code></details></article>)}</div>}</div>
        </>}
      </section></div><footer>EduClaw 本地任务工作台 <span>状态每 3 秒同步 · 工具输出仅作为数据展示</span></footer>
    </main>
    <dialog ref={dialog} onCancel={event=>{if(busy)event.preventDefault();else setPreview(undefined);}} onClose={()=>{if(!busy)setPreview(undefined);}} aria-labelledby="confirm-title">
      {preview&&<><div className="eyebrow">确认操作</div><h2 id="confirm-title">{actionLabels[preview.action]}</h2><p className="dialog-goal">任务 {preview.number}：{preview.goal}</p><p>{preview.message}</p>{preview.code!==undefined&&<><div className="code-heading">PYTHON · 第 {preview.step} 步 · 实际执行代码</div><pre className="code-review">{preview.code}</pre><label className="execute-label">输入 EXECUTE 确认<input aria-label="执行确认" autoComplete="off" spellCheck={false} value={executionWord} onChange={e=>setExecutionWord(e.target.value)} placeholder="EXECUTE"/></label></>}<small>预览有效期 2 分钟。任务变化后需重新确认。</small><div className="dialog-actions"><button className="secondary" disabled={busy} onClick={()=>setPreview(undefined)}>返回</button><button className="primary" disabled={busy||(preview.action==='execute'&&executionWord!=='EXECUTE')} onClick={()=>void confirm()}>{busy?'提交中…':preview.action==='execute'?'确认执行当前步骤':'确认'+actionLabels[preview.action]}</button></div></>}
    </dialog>
  </div>;
}

createRoot(document.getElementById('root')!).render(<React.StrictMode><App/></React.StrictMode>);
