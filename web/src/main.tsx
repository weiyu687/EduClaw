import './compat';
import React, {useEffect,useRef,useState} from 'react';
import {createRoot} from 'react-dom/client';
import {request,takeCredential,query,labels,actionLabels} from './api';
import type {Session,Task,Detail,Preview,Action} from './api';
import './style.css';
import {SessionActions} from './SessionActions';
import {Workspace} from './Workspace';
import {Icon} from './Icon';
import {NewsSummary} from './RichText';

function App(){
  const [navOpen,setNavOpen]=useState(()=>window.innerWidth>800);
  const [mobile,setMobile]=useState(()=>window.innerWidth<=800);
  const [sessionSearch,setSessionSearch]=useState('');
  const navButton=useRef<HTMLButtonElement>(null);
  const sidebar=useRef<HTMLElement>(null);
  useEffect(()=>{const media=window.matchMedia('(max-width:800px)');const sync=()=>{setMobile(media.matches);setNavOpen(!media.matches);};media.addEventListener('change',sync);return()=>media.removeEventListener('change',sync);},[]);
  useEffect(()=>{if(mobile&&navOpen)sidebar.current?.querySelector<HTMLButtonElement>('button')?.focus();},[mobile,navOpen]);
  function closeNav(){setNavOpen(false);requestAnimationFrame(()=>navButton.current?.focus());}
  const [mode,setMode]=useState<'chat'|'task'>('chat');
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
    const timer=window.setInterval(()=>{request<Session[]>(token,'/api/sessions').then(rows=>{if(!cancelled){setSessions(rows);setSession(current=>rows.some(s=>s.id===current)?current:(rows[0]?.id??''));}}).catch(()=>{});},3000);
    return ()=>{cancelled=true;window.clearInterval(timer);};
  },[token,tick]);
  useEffect(()=>{setSelected(undefined);setDetail(undefined);setPreview(undefined);},[session]);
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
    try{const value=await request<Detail>(token,'/api/confirm',{ticket,confirmation:preview.action==='execute'?executionWord:'CONFIRM'});setDetail(value);setNotice((['execute','read','tool'].includes(preview.action))?'执行已提交，后续按现有权限继续。':'操作已记录。');setTick(x=>x+1);}
    catch(e){setError(e instanceof Error?e.message:'确认结果未知，请刷新核查。');}
    finally{setPreview(undefined);setBusy(false);}
  }
  const live=tasks.filter(t=>t.status==='running').length;
  return <div className={'shell '+(navOpen?'nav-open':'nav-closed')}>
    <a className="skip-link" href="#main-content">跳转到主要内容</a>
    {mobile&&navOpen&&<button className="nav-backdrop" aria-label="关闭侧栏" onClick={closeNav}/>}
    <aside className="sidebar" ref={sidebar} aria-label="主导航" onKeyDown={e=>{if(!mobile)return;if(e.key==='Escape')closeNav();if(e.key==='Tab'){const nodes=Array.from(sidebar.current?.querySelectorAll<HTMLElement>('a,button,input,select')??[]).filter(n=>n.offsetParent!==null&&!n.hasAttribute('disabled'));const first=nodes[0],last=nodes[nodes.length-1];if(e.shiftKey&&document.activeElement===first){e.preventDefault();last?.focus();}else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first?.focus();}}}}><div className="sidebar-brand"><a className="brand" href="/" aria-label="EduClaw 工作台"><span className="brand-mark"><Icon name="book" size={22}/></span><span>EduClaw<small>你的探索伙伴</small></span></a><button className="icon-button" aria-label="收起侧栏" onClick={closeNav}><Icon name="menu" size={17}/></button></div>
      <div id="sidebar-controls"/>
      <div className="workspace-label">最近对话 <span>{sessions.length}</span></div><div className="session-search"><Icon name="search" size={15}/><input aria-label="搜索对话" placeholder="搜索对话…" value={sessionSearch} onChange={e=>setSessionSearch(e.target.value)}/></div>
      <label className="session-picker sr-only">选择会话<select aria-label="选择会话" value={session} onChange={e=>{setSession(e.target.value);setSelected(undefined);setDetail(undefined);setTasks([]);setPreview(undefined);}}>{sessions.map(s=><option key={s.id} value={s.id}>{s.label} · {s.updated_at.slice(0,10)}</option>)}</select></label>
      <SessionActions key={session} token={token} session={session} title={sessions.find(s=>s.id===session)?.label??''} onChange={()=>{setTick(x=>x+1);}} onDeleted={()=>{setSession('');setSelected(undefined);setDetail(undefined);setTick(x=>x+1);}}/>
      <nav className="session-list" aria-label="历史对话">{sessions.filter(s=>s.label.toLowerCase().includes(sessionSearch.toLowerCase())).map(s=><button key={s.id} aria-current={session===s.id?'page':undefined} onClick={()=>{if(mobile)closeNav();setSession(s.id);setSelected(undefined);setDetail(undefined);setTasks([]);setPreview(undefined);}}><Icon name="chat" size={15}/><span>{s.label}<small>{s.updated_at.slice(0,10)}</small></span></button>)}</nav>
      {sessionSearch&&!sessions.some(s=>s.label.toLowerCase().includes(sessionSearch.toLowerCase()))&&<p className="search-empty">没有找到匹配的对话</p>}
      <div className="side-footer"><span className="online-dot"/> 本地工作台<div>由你掌控，为好奇心而生</div></div>
    </aside>
    <main id="main-content" inert={mobile&&navOpen}><header className="topbar"><div className="topbar-title"><button ref={navButton} className="icon-button" aria-label="展开侧栏" aria-expanded={navOpen} onClick={()=>setNavOpen(true)} hidden={navOpen}><Icon name="menu"/></button><div><h1>{sessions.find(s=>s.id===session)?.label||'开始新的探索'}</h1><p>{mode==='chat'?'思考与交流的空间':'你的目标，有迹可循'}</p></div></div><div className="topbar-actions"><span className="connection-status"><span className={error?'status-dot offline':'status-dot'}/>{error?'连接待检查':loading?'连接中':'本地工作空间'}</span><button className="icon-button" aria-label="刷新" title="刷新状态" onClick={()=>{setLoading(true);setTick(x=>x+1);}}><Icon name="refresh" size={17}/></button></div></header>
      {error&&<div className="alert" role="alert">{error}<span>页面不会自动重试操作；请先刷新核查状态。</span></div>}
      {notice&&<div className="notice" role="status">{notice}</div>}
      <Workspace mode={mode} onMode={setMode} onRefresh={()=>setTick(x=>x+1)} key={session} token={token} session={session} onSession={id=>{if(mobile)closeNav();setMode('chat');setSession(id);setSelected(undefined);setDetail(undefined);setTick(x=>x+1);}} onTask={n=>{setMode('task');setSelected(n);setTick(x=>x+1);}} onAction={a=>{setMode('task');void prepare(a);}} onView={v=>{setMode('task');setTab(v);setTick(x=>x+1);}}/>
      {mode==='task'&&<><section className="overview" aria-label="任务概览"><div><span>全部任务</span><strong>{tasks.length}</strong></div><div><span>进行中</span><strong>{live}</strong></div><div><span>已完成</span><strong>{tasks.filter(t=>t.status==='completed').length}</strong></div><div className="overview-note">每一步，都有据可查</div></section>
      <div className="section-heading"><h2>当前对话的任务</h2></div>
      <div className="work-grid"><section className="task-list" aria-label="任务列表">
        {loading&&<p role="status" className="empty">正在读取任务…</p>}
        {!loading&&!tasks.length&&<div className="empty"><span>◇</span><h3>这里还没有任务</h3><p>在上方描述目标，系统会选择合适的工具。</p></div>}
        {tasks.map(task=><button className={'task-card '+(selected===task.number?'selected':'')} key={task.number} onClick={()=>{setSelected(task.number);setDetail(undefined);setNotice('');setPreview(undefined);}}>
          <div className="card-meta"><span>任务 {String(task.number).padStart(2,'0')}</span><span className={'badge '+task.status}>{labels[task.control==='active'?task.status:task.control]??task.status}</span></div>
          <h3>{task.goal}</h3><div className="card-bottom"><span>{task.completed} / {task.total} 步已处理</span><span>查看详情 →</span></div><progress aria-label={`任务 ${task.number} 进度`} value={task.completed} max={task.total}/>
        </button>)}
      </section><section className="detail-panel" aria-label="任务详情">
        {!detail?<div className="empty detail-empty"><span>◎</span><h3>{selected===undefined?'选择一个任务':'正在加载任务'}</h3><p>步骤、依赖和结果证据将在这里展示。</p></div>:<>
          <div className="detail-top"><span className="eyebrow">TASK {String(detail.number).padStart(2,'0')}</span><span className="badge">{labels[detail.control==='active'?detail.status:detail.control]??detail.status}</span></div>
          <h2 className="task-title">{detail.goal.length>160?detail.goal.slice(0,160)+"…":detail.goal}</h2>{detail.goal.length>160&&<details className="full-goal"><summary>查看完整任务要求</summary><pre>{detail.goal}</pre></details>}<div className="next-step"><strong>{detail.status==='completed'?'任务已完成':detail.execution_pending?'正在执行':'下一步'}</strong><p>{detail.status==='completed'?'所有步骤已完成，可在结果证据中查看输出。':detail.execution_pending?'正在连接工具或执行已确认的代码，结果将自动更新。':detail.recovery.message}</p>{detail.status!=='completed'&&<small>需要确认时，核对下方操作内容。关闭页面不会取消任务。</small>}</div>
          {detail.execution_error&&<div className="alert" role="alert">执行进程已退出，请核查结果或在 CLI 使用 /失败 查看原因；不会自动重试。</div>}
          {detail.summary&&<section className="news-summary" aria-label="新闻摘要"><h3>新闻摘要</h3>{detail.summary.status==='generating'?<p className="thinking">正在根据已保存的来源整理摘要…</p>:<NewsSummary text={detail.summary.answer}/>}</section>}<div className="actions">{detail.actions.map(action=><button key={action} className={(['execute','read','tool'].includes(action))?'primary':action==='cancel'?'danger':'secondary'} disabled={busy} onClick={()=>void prepare(action)}>{actionLabels[action]}</button>)}</div>
          <div className="tabs" role="tablist" aria-label="任务内容"><button role="tab" aria-selected={tab==='steps'} onClick={()=>setTab('steps')}>执行步骤 <span>{detail.total}</span></button><button role="tab" aria-selected={tab==='results'} onClick={()=>setTab('results')}>结果证据 <span>{detail.results.length}</span></button></div>
          <div role="tabpanel">{tab==='steps'?<ol className="steps">{detail.steps.map(step=><li key={step.number}><span className={'step-num '+step.status}>{step.status==='completed'?'✓':step.number}</span><div><div className="step-heading"><strong>{step.tool}</strong><span>{step.status==='pending'?(step.number===detail.completed+1?'待审批':'等待前序步骤'):labels[step.status]??step.status}</span></div><p>{step.dependencies.length?`依赖第 ${step.dependencies.join('、')} 步的结果`:'独立步骤'}</p><details><summary>查看输入参数</summary><pre>{JSON.stringify(step.arguments,null,2)}</pre></details></div></li>)}</ol>:<div className="results">{!detail.results.length?<p className="empty">暂时没有结果。工具执行后会保存在这里。</p>:detail.results.map(row=><article key={row.step}><h3>第 {row.step} 步 · {labels[row.status]??row.status}</h3><p className={row.intact&&!row.truncated?'verified':'alert'}>{row.intact&&!row.truncated?'✓ 结果摘要校验通过':'结果不完整或摘要不匹配，请在 CLI 核查'}</p><pre>{row.summary}</pre><details><summary>查看保存内容与校验信息</summary><pre>{row.content}</pre>{row.preview_truncated&&<p>此处只展示前 20000 个字符，完整内容请在 CLI 查看。</p>}<code>SHA256 {row.digest}</code></details></article>)}</div>}</div>
        </>}
      </section></div></>}<footer><span>EDUCLAW <span className="footer-dot">✦</span> 为每一次探索</span><span>AI 可能出错，重要信息请核实</span></footer>
    </main>
    <dialog ref={dialog} onCancel={event=>{if(busy)event.preventDefault();else setPreview(undefined);}} onClose={()=>{if(!busy)setPreview(undefined);}} aria-labelledby="confirm-title">
      {preview&&<><div className="eyebrow">确认操作</div><h2 id="confirm-title">{actionLabels[preview.action]}</h2><p className="dialog-goal">任务 {preview.number}：{preview.goal}</p><p>{preview.message}</p>{preview.arguments&&<div className="read-review"><strong>{preview.tool}</strong><h3>原文件内容</h3><pre>{preview.before||'（新文件或非文件操作）'}</pre><h3>本次参数与写入内容</h3><pre>{JSON.stringify(preview.arguments,null,2)}</pre></div>}{preview.path&&<div className="read-review"><strong>第 {preview.step} 步 · {preview.tool}</strong><pre>{preview.path}</pre><p>仅当前步骤 · 只读 · 不修改文件</p></div>}{preview.code!==undefined&&<><div className="code-heading">PYTHON · 第 {preview.step} 步 · 实际执行代码</div><pre className="code-review">{preview.code}</pre><label className="execute-label">输入 EXECUTE 确认<input aria-label="执行确认" autoComplete="off" spellCheck={false} value={executionWord} onChange={e=>setExecutionWord(e.target.value)} placeholder="EXECUTE"/></label></>}<small>预览有效期 2 分钟。任务变化后需重新确认。</small><div className="dialog-actions"><button className="secondary" disabled={busy} onClick={()=>setPreview(undefined)}>返回</button><button className="primary" disabled={busy||(preview.action==='execute'&&executionWord!=='EXECUTE')} onClick={()=>void confirm()}>{busy?'提交中…':preview.action==='execute'?'确认执行当前步骤':'确认'+actionLabels[preview.action]}</button></div></>}
    </dialog>
  </div>;
}

createRoot(document.getElementById('root')!).render(<React.StrictMode><App/></React.StrictMode>);
