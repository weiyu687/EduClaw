import {createPortal} from 'react-dom';
import {Permissions} from './Permissions';
import {useEffect,useRef,useState} from 'react';
import {request,query} from './api';
import type {Action} from './api';

interface Command {command:string;title:string;description:string;action:string}
interface Catalog {
  skills:{id:string;name:string;description:string;version:string;content:string;truncated:boolean}[];
  tools:{name:string;description:string;version:string;risk:string;plannable:boolean;inputSchema:unknown;output_schema:unknown}[];
  commands:Command[];
}
interface Mounts {skills:string[];tools:string[]}
interface Turn {id:string;text:string;answer:string|null;status:string}
interface Submission {id:string;goal:string;status:string;number:number|null;error:string|null}
interface Props {mode:'chat'|'task';onMode:(m:'chat'|'task')=>void;onRefresh:()=>void;token:string;session:string;onSession:(id:string)=>void;onTask:(n:number)=>void;onAction:(a:Action)=>void;onView:(v:'steps'|'results')=>void}

export function Workspace({token,session,onSession,onTask,onAction,onView,mode,onMode,onRefresh}:Props){
  const [turns,setTurns]=useState<Turn[]>([]);
  const [catalog,setCatalog]=useState<Catalog>();
  const [mounts,setMounts]=useState<Mounts>({skills:[],tools:[]});
  const [saved,setSaved]=useState<Mounts>({skills:[],tools:[]});
  const [panel,setPanel]=useState<'skills'|'tools'|'help'|'permissions'|'none'>('none');
  const [text,setText]=useState('');
  const [error,setError]=useState('');
  const [notice,setNotice]=useState('');
  const [busy,setBusy]=useState(false);
  const [ready,setReady]=useState(false);
  const [submissions,setSubmissions]=useState<Submission[]>([]);
  const [search,setSearch]=useState('');
  const identity=useRef<{session:string;text:string;id:string}|undefined>(undefined);
  useEffect(()=>{let live=true;if(token)request<Catalog>(token,'/api/catalog').then(x=>{if(live)setCatalog(x);}).catch(e=>{if(live)setError(e.message);});return()=>{live=false;};},[token]);
  useEffect(()=>{
    let live=true;setReady(false);setSubmissions([]);setError('');setNotice('');
    if(!session){setMounts({skills:[],tools:[]});setSaved({skills:[],tools:[]});return;}
    request<Mounts>(token,'/api/mounts?'+query(session)).then(x=>{if(live){setMounts(x);setSaved(x);setReady(true);}}).catch(e=>{if(live)setError(e.message);});
    async function poll(){try{const [rows,history]=await Promise.all([request<Submission[]>(token,'/api/submissions?'+query(session)),request<Turn[]>(token,'/api/chat?'+query(session))]);if(live){setSubmissions(rows);setTurns(history);}}catch(e){if(live)setError(e instanceof Error?e.message:'无法读取提交记录');}}
    void poll();const timer=setInterval(poll,2000);
    return()=>{live=false;clearInterval(timer);};
  },[session,token]);
  async function run(action:()=>Promise<void>){setBusy(true);setError('');setNotice('');try{await action();}catch(e){setError(e instanceof Error?e.message:'操作失败，请核查状态。');}finally{setBusy(false);}}
  async function newSession(){await run(async()=>{const row=await request<{session:string}>(token,'/api/session',{});onSession(row.session);});}
  async function save(){await run(async()=>{const row=await request<Mounts>(token,'/api/mounts',{session,...mounts});setSaved(row);setNotice('挂载已保存，应用于之后提交的新任务。');});}
  function toggle(kind:'skills'|'tools',id:string){setMounts(m=>({...m,[kind]:m[kind].includes(id)?m[kind].filter(x=>x!==id):[...m[kind],id]}));}
  const dirty=JSON.stringify(mounts)!==JSON.stringify(saved);
  async function command(c:Command){
    if(c.action==='cli'){setNotice(`${c.command}：${c.description} 此指令目前需在 CLI 使用。`);return;}
    setText('');
    if(c.action==='chat'||c.action==='task_mode'){onMode(c.action==='chat'?'chat':'task');return;}
    if(c.action==='new'){await newSession();return;}
    if(c.action==='skills'||c.action==='tools'||c.action==='help'){setPanel(c.action);return;}
    if(c.action==='tasks'){setPanel('none');onView('steps');return;}
    if(c.action==='steps'||c.action==='results'){onView(c.action);return;}
    onAction(c.action as Action);
  }
  async function submit(){
    if(text.trim().startsWith('/')){
      const c=catalog?.commands.find(c=>c.command===text.trim());
      if(c)await command(c);else setError('未知指令，请从下方指令列表选择。');return;
    }
    await run(async()=>{
      if(mode==='task'&&dirty)throw new Error('有未保存的能力偏好，请先保存。');
      const goal=text.trim();
      if(!identity.current||identity.current.session!==session||identity.current.text!==goal){
        const bytes=crypto.getRandomValues(new Uint8Array(16));
        identity.current={session,text:goal,id:Array.from(bytes,x=>x.toString(16).padStart(2,'0')).join('')};
      }
      if(mode==='chat'){await request(token,'/api/chat',{session,text:goal,request_id:identity.current.id});setText('');identity.current=undefined;setTurns(rows=>[...rows,{id:'pending',text:goal,answer:null,status:'generating'}]);onRefresh();return;}
      const row=await request<Submission>(token,'/api/submit',{session,text:goal,request_id:identity.current.id});
      setSubmissions(rows=>[row,...rows.filter(x=>x.id!==row.id)]);setText('');identity.current=undefined;
      setNotice('目标已提交，自动选择工具并推进低风险步骤；需要额外权限时会暂停。');
    });
  }
  const filtered=(catalog?.commands??[]).filter(c=>(c.command+c.title+c.description).toLowerCase().includes((text.startsWith('/')?text:search).toLowerCase()));
  return <section className="workspace-console" aria-label="任务输入与能力配置">
    {document.getElementById('sidebar-controls')&&createPortal(<nav className="side-controls" aria-label="工作空间管理"><button className="new-chat" disabled={busy} onClick={()=>void newSession()}>＋ 新建对话</button><button aria-pressed={panel==='none'} onClick={()=>setPanel('none')}>◯ 对话与任务</button><button aria-pressed={panel==='skills'} onClick={()=>setPanel('skills')}>◇ 技能管理 · {saved.skills.length}</button><button aria-pressed={panel==='tools'} onClick={()=>setPanel('tools')}>⚒ 工具管理 · 自动</button><button aria-pressed={panel==='permissions'} onClick={()=>setPanel('permissions')}>▣ 工具与文件权限</button><button aria-pressed={panel==='help'} onClick={()=>setPanel('help')}>/ 指令说明</button></nav>,document.getElementById('sidebar-controls')!)}
    {panel==='permissions'&&<Permissions token={token} session={session}/>}
    <div className="mode-picker" role="group" aria-label="对话模式"><button className={mode==='chat'?'primary':'secondary'} onClick={()=>onMode('chat')}>普通对话</button><button className={mode==='task'?'primary':'secondary'} onClick={()=>onMode('task')}>任务模式</button></div>
    {mode==='chat'&&<section className="chat-history" aria-label="对话记录">{!turns.length&&<div className="chat-welcome"><h2>有什么想聊的？</h2><p>提问、写作或讨论想法，支持连续追问。</p></div>}{turns.map(t=><article key={t.id}><div className="chat-user"><strong>你</strong><p>{t.text}</p></div><div className="chat-assistant"><strong>EduClaw</strong><p>{t.answer||(t.status==='generating'?'正在回复…':t.status==='interrupted'?'回复已中断，请重新发送消息。':'回复失败，请检查连接后重新发送。')}</p></div></article>)}</section>}
    <div className="composer-heading"><h2>{mode==='chat'?'继续对话':'今天想完成什么？'}</h2></div>
    <textarea aria-label="任务输入" value={text} maxLength={4000} placeholder={session?'输入消息，或输入 / 选择指令…':'先创建新会话，再描述目标。'} disabled={!session||busy} onChange={e=>setText(e.target.value)}/>
    <div className="composer-toolbar"><div className="capability-buttons" aria-label="快捷挂载"><button className="secondary" onClick={()=>setPanel(panel==='skills'?'none':'skills')}>技能 · {saved.skills.length}</button><button className="secondary" onClick={()=>setPanel(panel==='tools'?'none':'tools')}>工具 · 自动</button><button className="secondary" onClick={()=>setPanel(panel==='help'?'none':'help')}>/ 指令说明</button></div><button className="primary" disabled={!ready||busy||!text.trim()||(mode==='chat'&&turns.some(t=>t.status==='generating'))} onClick={()=>void submit()}>{busy?'提交中…':text.startsWith('/')?'选择指令':mode==='chat'?'发送消息 ↑':'提交任务 ↑'}</button></div>
    {error&&<p role="alert" className="alert">{error}</p>}{notice&&<p role="status" className="notice">{notice}</p>}
    {(panel==='skills'||panel==='tools')&&<div className="capability-panel"><div className="section-heading"><div><h3>{panel==='skills'?'技能库':'工具库'}</h3><p>工具由任务规划自动选择，无需逐次勾选；可以设置偏好的技能，系统也会根据目标自动选择。禁用工具请使用权限设置。</p></div>{panel==='skills'&&<button className="primary" disabled={!ready||busy||!dirty} onClick={()=>void save()}>保存挂载</button>}</div>
      {!session&&<p>请先创建或选择会话。</p>}
      <div className="capability-grid">{panel==='skills'?catalog?.skills.map(s=><article className="capability-card" key={s.id}><label><input type="checkbox" aria-label={`挂载技能 ${s.id}`} disabled={!ready||busy} checked={mounts.skills.includes(s.id)} onChange={()=>toggle('skills',s.id)}/><strong>{s.name}</strong><span>{s.version}</span></label><p>{s.description}</p><details><summary>查看技能内容</summary><pre>{s.content}</pre>{s.truncated&&<p>内容过长，此处展示前 16000 字。</p>}</details></article>):catalog?.tools.map(t=><article className="capability-card" key={t.name}><label><strong>{t.name}</strong></label><p>{t.description}</p><small>v{t.version} · {t.risk} · {t.plannable?'可用于任务规划':'当前规划器暂不支持'}</small><details><summary>查看参数和结果契约</summary><pre>{JSON.stringify({input:t.inputSchema,output:t.output_schema},null,2)}</pre></details></article>)}</div>
      <p className="muted">此处挂载项目已安装的技能与可信工具。第三方技能放入 skills/&lt;id&gt;/SKILL.md；新工具需先按工具 SDK 注册适配器。</p>
    </div>}
    {(panel==='help'||text.startsWith('/'))&&<div className="command-panel"><h3>选择指令</h3>{!text.startsWith('/')&&<input aria-label="搜索指令" placeholder="搜索指令或用途" value={search} onChange={e=>setSearch(e.target.value)}/>}
      <div className="command-list">{filtered.map(c=><button className="command-item" key={c.command} disabled={busy} onClick={()=>void command(c)}><code>{c.command}</code><span><strong>{c.title}</strong><small>{c.description}</small></span><em>{c.action==='cli'?'CLI':'GUI'}</em></button>)}{!filtered.length&&<p>没有匹配指令。</p>}</div></div>}
    {mode==='task'&&!!submissions.length&&<details className="submission-list" open><summary>最近提交</summary>{submissions.slice(0,5).map(s=><div key={s.id}><span>{s.goal}</span><strong>{({planning:'规划中',ready:'计划已创建',failed:'规划失败',interrupted:'规划中断'} as Record<string,string>)[s.status]}</strong>{s.number!==null&&<button className="secondary" onClick={()=>onTask(s.number!)}>查看任务</button>}{s.error&&<p role="alert">{s.error}</p>}{s.status==='interrupted'&&<p>服务已重启，未自动重试。请核查任务列表后再提交。</p>}</div>)}</details>}
  </section>;
}
