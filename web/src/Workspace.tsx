import {Knowledge} from './Knowledge';
import {Experts} from './Experts';
import {Terminal} from './Terminal';
import {createPortal} from 'react-dom';
import {Icon} from './Icon';
import {RichText,CopyButton} from './RichText';
import {PanelDialog} from './PanelDialog';
import {Permissions} from './Permissions';
import {Projects} from './Projects';
import {useEffect,useLayoutEffect,useRef,useState} from 'react';
import {request,query,authorizedBlob} from './api';
import type {Action} from './api';

interface Command {command:string;title:string;description:string;action:string}
interface Catalog {
  skills:{id:string;name:string;description:string;version:string;content:string;truncated:boolean}[];
  tools:{name:string;description:string;version:string;risk:string;plannable:boolean;inputSchema:unknown;output_schema:unknown}[];
  commands:Command[];
}
interface Mounts {skills:string[];tools:string[]}
interface ExpertProfile {id:string;name:string;description:string;version:number;builtin:boolean}
interface ExpertView {profiles:ExpertProfile[]}
interface Attachment {id?:string;name:string;mime:string;bytes:number;data?:string}
interface Turn {id:string;text:string;answer:string|null;status:string;attachments?:Attachment[];proposal?:{goal:string;reason:string;expert?:ExpertProfile}|null;evidence?:{tool:string}|null}
interface Submission {id:string;goal:string;status:string;number:number|null;error:string|null}
interface Props {mode:'chat'|'task';onMode:(m:'chat'|'task')=>void;onRefresh:()=>void;token:string;session:string;onSession:(id:string)=>void;onTask:(n:number)=>void;onAction:(a:Action)=>void;onView:(v:'steps'|'results')=>void}

function ChatImage({token,session,item}:{token:string;session:string;item:Attachment}){
  const [url,setUrl]=useState(item.data?`data:${item.mime};base64,${item.data}`:'');
  useEffect(()=>{if(item.data||!item.id)return;let active=true;let object='';authorizedBlob(token,'/api/chat/attachment?'+new URLSearchParams({session,id:item.id}).toString()).then(blob=>{if(active){object=URL.createObjectURL(blob);setUrl(object);}}).catch(()=>{});return()=>{active=false;if(object)URL.revokeObjectURL(object);};},[token,session,item.id,item.data,item.mime]);
  return url?<img src={url} alt={item.name}/>:<span className="image-loading">正在读取 {item.name}…</span>;
}

export function Workspace({token,session,onSession,onTask,onAction,onView,mode,onMode,onRefresh}:Props){
  const [experts,setExperts]=useState<ExpertProfile[]>([]);
  const [selectedExpert,setSelectedExpert]=useState('');
  const [turns,setTurns]=useState<Turn[]>([]);
  const [catalog,setCatalog]=useState<Catalog>();
  const [mounts,setMounts]=useState<Mounts>({skills:[],tools:[]});
  const [saved,setSaved]=useState<Mounts>({skills:[],tools:[]});
  const [panel,setPanel]=useState<'projects'|'skills'|'tools'|'help'|'permissions'|'terminal'|'library'|'memory'|'experts'|'none'>('none');
  const [project,setProject]=useState<{id:string;name:string}|null>(null);
  const [text,setText]=useState('');
  const [attachments,setAttachments]=useState<Attachment[]>([]);
  const [error,setError]=useState('');
  const [notice,setNotice]=useState('');
  const [busy,setBusy]=useState(false);
  const [ready,setReady]=useState(false);
  const [submissions,setSubmissions]=useState<Submission[]>([]);
  const [search,setSearch]=useState('');
  const [catalogSearch,setCatalogSearch]=useState('');
  const input=useRef<HTMLTextAreaElement>(null);
  const followReply=useRef(true);
  const lastRendered=useRef('');
  const chatScroll=useRef(0);
  const visibleMode=useRef(mode);
  const focusTask=useRef(false);
  useLayoutEffect(()=>{
    visibleMode.current=mode;
    if(mode==='chat')window.scrollTo({top:followReply.current?document.documentElement.scrollHeight:chatScroll.current,behavior:'instant'});
    if(mode==='task'&&focusTask.current){focusTask.current=false;input.current?.focus({preventScroll:true});input.current?.scrollIntoView({block:'center',behavior:'instant'});}
  },[mode]);
  useEffect(()=>{const update=()=>{if(visibleMode.current!=='chat')return;chatScroll.current=window.scrollY;followReply.current=document.documentElement.scrollHeight-window.scrollY-window.innerHeight<240;};window.addEventListener('scroll',update,{passive:true});return()=>window.removeEventListener('scroll',update);},[]);
  useEffect(()=>{const last=turns[turns.length-1];const signature=last?last.id+last.status+(last.answer??''):'';if(signature!==lastRendered.current){lastRendered.current=signature;if(mode==='chat'&&last&&followReply.current)requestAnimationFrame(()=>input.current?.scrollIntoView({block:'end'}));}},[turns,mode]);
  useEffect(()=>{if(input.current){input.current.style.height='auto';input.current.style.height=Math.min(input.current.scrollHeight,220)+'px';}},[text]);
  useEffect(()=>{setCatalogSearch('');},[panel]);
  const identity=useRef<{session:string;text:string;expert:string;images:string;id:string}|undefined>(undefined);
  useEffect(()=>{let live=true;if(token)request<Catalog>(token,'/api/catalog').then(x=>{if(live)setCatalog(x);}).catch(e=>{if(live)setError(e.message);});return()=>{live=false;};},[token]);
  useEffect(()=>{
    let live=true;setSelectedExpert('');setExperts([]);setAttachments([]);setReady(false);setSubmissions([]);setError('');setNotice('');
    if(!session){setProject(null);setMounts({skills:[],tools:[]});setSaved({skills:[],tools:[]});return;}
    request<Mounts>(token,'/api/mounts?'+query(session)).then(x=>{if(live){setMounts(x);setSaved(x);setReady(true);}}).catch(e=>{if(live)setError(e.message);});
    request<{current:{id:string;name:string}|null}>(token,'/api/projects?'+query(session)).then(x=>{if(live)setProject(x.current);}).catch(e=>{if(live)setError(e.message);});
    request<ExpertView>(token,'/api/experts?'+query(session)).then(x=>{if(live)setExperts(x.profiles);}).catch(e=>{if(live)setError(e.message);});
    async function poll(){try{const [rows,history]=await Promise.all([request<Submission[]>(token,'/api/submissions?'+query(session)),request<Turn[]>(token,'/api/chat?'+query(session))]);if(live){setSubmissions(rows);setTurns(history);}}catch(e){if(live)setError(e instanceof Error?e.message:'无法读取提交记录');}}
    void poll();const timer=setInterval(poll,2000);
    return()=>{live=false;clearInterval(timer);};
  },[session,token]);
  async function run(action:()=>Promise<void>){setBusy(true);setError('');setNotice('');try{await action();}catch(e){setError(e instanceof Error?e.message:'操作失败，请核查状态。');}finally{setBusy(false);}}
  async function newSession(){await run(async()=>{const row=await request<{session:string}>(token,'/api/session',{project_id:project?.id??null});onSession(row.session);});}
  async function refreshExperts(){const row=await request<ExpertView>(token,'/api/experts?'+query(session));setExperts(row.profiles);if(selectedExpert&&!row.profiles.some(x=>x.id===selectedExpert))setSelectedExpert('');onRefresh();}
  async function save(){await run(async()=>{const row=await request<Mounts>(token,'/api/mounts',{session,...mounts});setSaved(row);setNotice('挂载已保存，应用于之后提交的新任务。');});}
  function toggle(kind:'skills'|'tools',id:string){setMounts(m=>({...m,[kind]:m[kind].includes(id)?m[kind].filter(x=>x!==id):[...m[kind],id]}));}
  async function addImages(files:FileList|null){
    if(!files?.length)return;
    setError('');
    try{
      const chosen=Array.from(files);
      if(attachments.length+chosen.length>4)throw new Error('每次最多上传 4 张图片。');
      const allowed=new Set(['image/png','image/jpeg','image/webp','image/gif']);
      if(chosen.some(file=>!allowed.has(file.type)))throw new Error('仅支持 PNG、JPEG、WebP 和 GIF 图片。');
      if(chosen.some(file=>file.size>5*1024*1024))throw new Error('每张图片须小于 5 MB。');
      if(attachments.reduce((sum,item)=>sum+item.bytes,0)+chosen.reduce((sum,file)=>sum+file.size,0)>8*1024*1024)throw new Error('本次图片总大小不能超过 8 MB。');
      const next=await Promise.all(chosen.map(file=>new Promise<Attachment>((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve({name:file.name,mime:file.type,bytes:file.size,data:String(reader.result).split(',',2)[1]});reader.onerror=()=>reject(new Error('无法读取图片。'));reader.readAsDataURL(file);})));
      setAttachments(current=>[...current,...next]);identity.current=undefined;
    }catch(e){setError(e instanceof Error?e.message:'无法添加图片。');}
  }
  const dirty=JSON.stringify(mounts)!==JSON.stringify(saved);
  async function command(c:Command){
    if(c.action==='cli'){setNotice(`${c.command}：${c.description} 此指令目前需在 CLI 使用。`);return;}
    setText('');
    if(c.action==='chat'||c.action==='task_mode'){setPanel('none');onMode(c.action==='chat'?'chat':'task');return;}
    if(c.action==='new'){setPanel('none');await newSession();return;}
    if(c.action==='skills'||c.action==='tools'||c.action==='help'||c.action==='terminal'){setPanel(c.action);return;}
    if(c.action==='tasks'){setPanel('none');onView('steps');return;}
    if(c.action==='steps'||c.action==='results'){setPanel('none');onView(c.action);return;}
    setPanel('none');onAction(c.action as Action);
  }
  async function submit(){
    followReply.current=true;
    if(text.trim().startsWith('/')){
      const c=catalog?.commands.find(c=>c.command===text.trim());
      if(c)await command(c);else setError('未知指令，请从下方指令列表选择。');return;
    }
    await run(async()=>{
      if(mode==='task'&&dirty)throw new Error('有未保存的能力偏好，请先保存。');
      const goal=text.trim()||(attachments.length?'请分析这些图片。':'');
      const images=attachments.map(item=>`${item.name}:${item.bytes}:${item.data?.slice(-24)}`).join('|');
      if(!identity.current||identity.current.session!==session||identity.current.text!==goal||identity.current.expert!==selectedExpert||identity.current.images!==images){
        const bytes=crypto.getRandomValues(new Uint8Array(16));
        identity.current={session,text:goal,expert:selectedExpert,images,id:Array.from(bytes,x=>x.toString(16).padStart(2,'0')).join('')};
      }
      const expert_id=selectedExpert||null;
      if(mode==='chat'){const sent=attachments;await request(token,'/api/chat',{session,text:goal,request_id:identity.current.id,expert_id,attachments:sent.map(({name,mime,data})=>({name,mime,data}))},30000);setText('');setAttachments([]);identity.current=undefined;setTurns(rows=>[...rows,{id:'pending',text:goal,answer:null,status:'generating',attachments:sent}]);onRefresh();return;}
      const row=await request<Submission>(token,'/api/submit',{session,text:goal,request_id:identity.current.id,expert_id});
      setSubmissions(rows=>[row,...rows.filter(x=>x.id!==row.id)]);setText('');identity.current=undefined;
      setNotice('目标已提交，自动选择工具并推进低风险步骤；需要额外权限时会暂停。');
    });
  }
  const filtered=(catalog?.commands??[]).filter(c=>(c.command+c.title+c.description).toLowerCase().includes((text.startsWith('/')?text:search).toLowerCase()));
  const matches=(value:string)=>value.toLowerCase().includes(catalogSearch.toLowerCase());
  const pending=turns.some(t=>t.status==='generating');
  const sendDisabled=!ready||busy||(mode==='task'?!text.trim():(!text.trim()&&!attachments.length)||pending);
  function prepareTask(proposal:NonNullable<Turn['proposal']>,expertId=''){setText(proposal.goal);setSelectedExpert(expertId);identity.current=undefined;focusTask.current=true;onMode('task');}
  const prompts=[{icon:'spark',title:'分析一个问题',description:'从现象到原因和可行方案',text:'帮我分析这个问题。先梳理已知信息、关键假设和下一步。',mode:'chat'},
    {icon:'globe',title:'追踪 AI 新动态',description:'收集资讯，保留可靠来源',text:'给我昨天的 AI 新闻资讯，归纳重点并列出来源。',mode:'chat'},
    {icon:'image',title:'分析文件或图片',description:'提取信息、解释界面与视觉内容',text:'请分析我上传的图片，说明你观察到的内容和可以采取的下一步。',mode:'chat'},
    {icon:'folder',title:'推进本机项目',description:'使用工具执行并验证复杂工作',text:'检查当前工作目录，理解项目现状，选择下一项重要改进并在测试通过后交付。',mode:'task'}];
  return <section className={'workspace-console mode-'+mode} aria-label="任务输入与能力配置">
    {document.getElementById('sidebar-controls')&&createPortal(<nav className="side-controls" aria-label="工作空间管理">
      <button className="new-chat" aria-label="＋ 新建对话" disabled={busy} onClick={()=>void newSession()}><Icon name="plus"/><span>新建对话</span><kbd>NEW</kbd></button>
      <button aria-label="◯ 对话与任务" aria-pressed={panel==='none'} onClick={()=>setPanel('none')}><Icon name="chat"/><span>对话与任务</span></button>
      <div className="nav-section-label">工作空间</div>
      <button aria-label="项目工作区" aria-pressed={panel==='projects'} onClick={()=>setPanel('projects')}><Icon name="folder"/><span>项目</span><small>{project?.name??'未加入'}</small></button>
      <button aria-label="资料库" aria-pressed={panel==='library'} onClick={()=>setPanel('library')}><Icon name="book"/><span>资料库</span></button>
      <button aria-label="会话记忆" aria-pressed={panel==='memory'} onClick={()=>setPanel('memory')}><Icon name="chat"/><span>会话记忆</span></button>
      <button aria-label="专家配置" aria-pressed={panel==='experts'} disabled={!session} onClick={()=>setPanel('experts')}><Icon name="spark"/><span>专家配置</span></button>
      <button aria-label={'◇ 技能管理 · '+saved.skills.length} aria-pressed={panel==='skills'} onClick={()=>setPanel('skills')}><Icon name="spark"/><span>技能库</span><small>{saved.skills.length||'发现'}</small></button>
      <button aria-label="⚒ 工具管理 · 自动" aria-pressed={panel==='tools'} onClick={()=>setPanel('tools')}><Icon name="tools"/><span>工具库</span><small>自动</small></button>
      <button aria-label="终端" aria-pressed={panel==='terminal'} onClick={()=>setPanel('terminal')}><Icon name="command"/><span>终端</span><small>PowerShell</small></button>
      <button aria-label="▣ 工具与文件权限" aria-pressed={panel==='permissions'} onClick={()=>setPanel('permissions')}><Icon name="shield"/><span>权限与文件</span></button>
      <button aria-label="/ 指令说明" aria-pressed={panel==='help'} onClick={()=>setPanel('help')}><Icon name="command"/><span>指令指南</span></button>
    </nav>,document.getElementById('sidebar-controls')!)}
    {mode==='chat'&&<section className="chat-history" aria-label="对话记录">{!turns.length&&<div className="chat-welcome"><div className="welcome-emblem"><Icon name="spark" size={30}/></div><span className="eyebrow">CHAT. ACT. VERIFY.</span><h2>一个能对话，也能行动的 Agent。</h2><p>连接上下文、工具和本机环境，把请求推进到可验证的结果。</p><div className="starter-grid">{prompts.map(p=><button key={p.title} disabled={!session} onClick={()=>{setText(p.text);onMode(p.mode as 'chat'|'task');input.current?.focus();}}><Icon name={p.icon}/><strong>{p.title}</strong><span>{p.description}</span><Icon name="chevron" size={15}/></button>)}</div></div>}{turns.map(t=><article key={t.id}><div className="chat-user"><strong className="sr-only">你</strong>{!!t.attachments?.length&&<div className="chat-images">{t.attachments.map((item,index)=><ChatImage key={item.id??item.name+index} token={token} session={session} item={item}/>)}</div>}<p>{t.text}</p></div><div className="chat-assistant"><div className="assistant-identity"><span><Icon name="spark" size={18}/></span><strong>EduClaw</strong><small>本地智能 Agent</small></div>{t.answer?<>{t.evidence&&<span className="search-badge"><Icon name="globe" size={14}/>{t.evidence.tool==='library_search'?'已检索资料库':'已检索公开资料'}</span>}<RichText text={t.answer}/>{t.proposal&&<div className="task-proposal"><strong>建议创建任务</strong><p>{t.proposal.reason}</p><pre className="proposal-goal" aria-label="建议任务内容">{t.proposal.goal}</pre><div className="proposal-actions">{t.proposal.expert&&<button className="primary" onClick={()=>prepareTask(t.proposal!,t.proposal!.expert!.id)}>使用{t.proposal.expert.name}开始任务</button>}<button className="secondary" onClick={()=>prepareTask(t.proposal!)}>以通用模式准备任务</button></div>{t.proposal.expert&&<small>推荐专家：{t.proposal.expert.description}</small>}<small>不会自动执行，你可以先修改目标和专家模式。</small></div>}<CopyButton text={t.answer} label="复制回复"/></>:<p className={t.status==='generating'?'thinking':''} role="status">{t.status==='generating'?'正在回复…':t.status==='interrupted'?'回复已中断，请重新发送消息。':'回复失败，请检查连接后重新发送。'}</p>}</div></article>)}</section>}
    {mode==='task'&&<div className="task-intro"><span className="eyebrow">FROM IDEA TO DONE</span><h2>把想法，变成成果。</h2><p>描述你的目标，EduClaw 会选择工具、推进步骤，并在需要时请你确认。</p></div>}
    {project&&<div className="project-context"><Icon name="folder" size={14}/><span>{project.name}</span><button onClick={()=>setPanel('projects')}>项目设置</button></div>}
    <label className="expert-picker"><span>专家模式</span><select aria-label={mode==='chat'?'本次对话专家模式':'本次任务专家模式'} disabled={!session||busy} value={selectedExpert} onChange={e=>{setSelectedExpert(e.target.value);identity.current=undefined;}}><option value="">通用模式</option>{experts.map(profile=><option key={profile.id} value={profile.id}>{profile.name} · v{profile.version}</option>)}</select><button type="button" className="secondary" onClick={()=>setPanel('experts')}>管理配置</button></label>
    <div className="composer"><div className="composer-heading"><span><Icon name={mode==='chat'?'chat':'spark'} size={15}/>{mode==='chat'?'向 Agent 提出请求':'描述要完成的目标'}</span><span className="composer-count">{text.length?text.length+' / 4000':''}</span></div>
    {!!attachments.length&&<div className="attachment-drafts" aria-label="待发送图片">{attachments.map((item,index)=><div className="attachment-draft" key={item.name+index}><ChatImage token={token} session={session} item={item}/><span>{item.name}</span><button type="button" aria-label={'移除 '+item.name} onClick={()=>{setAttachments(rows=>rows.filter((_,i)=>i!==index));identity.current=undefined;}}>×</button></div>)}</div>}
    <textarea ref={input} aria-label="任务输入" value={text} maxLength={4000} rows={2} placeholder={session?(mode==='chat'?'输入消息，或上传图片进行分析…':'描述目标、目录、约束和验收标准…'):'点击“新建对话”开始使用…'} disabled={!session||busy} onChange={e=>setText(e.target.value)} onKeyDown={e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.nativeEvent.isComposing&&e.keyCode!==229){e.preventDefault();if(!sendDisabled)void submit();}}}/>
    <div className="composer-toolbar"><div className="capability-buttons" aria-label="快捷挂载">{mode==='chat'&&<label className="composer-chip image-upload" aria-label="上传图片"><Icon name="image" size={15}/>图片<input type="file" accept=".png,.jpg,.jpeg,.webp,.gif,image/png,image/jpeg,image/webp,image/gif" multiple disabled={!session||busy||attachments.length>=4} onChange={e=>{void addImages(e.currentTarget.files);e.currentTarget.value='';}}/></label>}<button className="composer-chip" aria-label={'技能 · '+saved.skills.length} onClick={()=>setPanel('skills')}><Icon name="spark" size={15}/>技能{saved.skills.length>0&&<small>{saved.skills.length}</small>}</button><button className="composer-chip" aria-label="工具 · 自动" onClick={()=>setPanel('tools')}><Icon name="tools" size={15}/>自动工具</button><button className="composer-chip slash-chip" aria-label="/ 指令说明" onClick={()=>setPanel('help')}>/</button></div><button className="send-button" aria-label={busy?'提交中…':text.startsWith('/')?'选择指令':mode==='chat'?'发送消息 ↑':'提交任务 ↑'} disabled={sendDisabled} onClick={()=>void submit()}><Icon name="arrow" size={20}/></button></div></div>
    <div className="composer-note"><span>{mode==='chat'?'直接提问 · 按需搜索公开资料':'低风险自动执行 · 重要操作由你确认'}</span><span>Enter 发送 · Shift + Enter 换行</span></div>
    {error&&<p role="alert" className="alert">{error}</p>}{notice&&panel==='none'&&<p role="status" className="notice">{notice}</p>}
    <PanelDialog open={panel!=='none'} title={({projects:'项目工作区',skills:'技能库',tools:'工具库',permissions:'权限与文件',terminal:'终端',library:'资料库',memory:'会话记忆',experts:'专家模式',help:'指令指南',none:''})[panel]} onClose={()=>setPanel('none')}>
      {error&&<p role="alert" className="alert">{error}</p>}{notice&&<p role="status" className="notice">{notice}</p>}
      {(panel==='library'||panel==='memory')&&<Knowledge key={session+panel} token={token} session={session} kind={panel}/> }
      {panel==='projects'&&<Projects key={session} token={token} session={session} onChange={value=>{setProject(value);onRefresh();}}/>}
      {panel==='experts'&&<Experts key={session} token={token} session={session} onChange={()=>void refreshExperts()}/>}
      {panel==='terminal'&&<Terminal token={token} session={session} onTask={n=>{setPanel('none');onTask(n);}}/>}
      {panel==='permissions'&&<Permissions token={token} session={session}/>}
      {(panel==='skills'||panel==='tools')&&<div className="capability-panel"><div className="section-heading"><p>{panel==='skills'?'为你的助手选择擅长的领域，也可由任务自动匹配。':'按任务自动选择工具。你始终可以在权限设置中管理它们。'}</p>{panel==='skills'&&<button className="primary" disabled={!ready||busy||!dirty} onClick={()=>void save()}>保存挂载{dirty?' · 未保存':''}</button>}</div>
        <div className="catalog-search"><Icon name="search"/><input aria-label="搜索能力" placeholder={panel==='skills'?'搜索技能名称或用途':'搜索工具名称或用途'} value={catalogSearch} onChange={e=>setCatalogSearch(e.target.value)}/></div>
        <div className="capability-grid">{panel==='skills'?catalog?.skills.filter(s=>matches(s.name+s.id+s.description)).map(s=><article className={'capability-card '+(mounts.skills.includes(s.id)?'is-selected':'')} key={s.id}><div className="capability-top"><span className="capability-symbol"><Icon name="spark"/></span><label><input type="checkbox" aria-label={`挂载技能 ${s.id}`} disabled={!ready||busy} checked={mounts.skills.includes(s.id)} onChange={()=>toggle('skills',s.id)}/><span>偏好</span></label></div><h3>{s.name}</h3><p>{s.description}</p><details><summary>查看技能内容</summary><RichText text={s.content}/>{s.truncated&&<p>展示前 16000 字。</p>}</details></article>):catalog?.tools.filter(t=>matches(t.name+t.description)).map(t=><article className="capability-card" key={t.name}><div className="capability-top"><span className="capability-symbol"><Icon name={t.risk==='public_read'?'globe':t.risk==='path_read'?'file':'tools'}/></span><span className="pill">{t.plannable?'自动选择':'扩展能力'}</span></div><h3>{t.name}</h3><p>{t.description}</p><details><summary>参数与结果格式</summary><pre>{JSON.stringify({input:t.inputSchema,output:t.output_schema},null,2)}</pre></details></article>)}</div>
        {catalog&&!((panel==='skills'?catalog.skills:catalog.tools).some(x=>matches(x.name+('id' in x?x.id:'')+x.description)))&&<div className="empty">没有匹配的能力，试试其他关键词。</div>}
        <p className="muted">技能提供工作方法，工具提供执行能力。启用技能不会改变文件或代码权限。</p></div>}
      {panel==='help'&&<div className="command-panel"><p className="muted">更快地找到操作，不必记住所有指令。</p><input aria-label="搜索指令" placeholder="搜索指令或用途…" value={search} onChange={e=>setSearch(e.target.value)}/><div className="command-list">{filtered.map(c=><button className="command-item" key={c.command} disabled={busy} onClick={()=>void command(c)}><code>{c.command}</code><span><strong>{c.title}</strong><small>{c.description}</small></span><em>{c.action==='cli'?'CLI':'工作台'}</em></button>)}{!filtered.length&&<p className="empty">没有匹配指令。</p>}</div></div>}
    </PanelDialog>
    {text.startsWith('/')&&panel==='none'&&<div className="command-panel inline-commands"><h3>选择指令</h3><div className="command-list">{filtered.map(c=><button className="command-item" key={c.command} onClick={()=>void command(c)}><code>{c.command}</code><span>{c.title}</span></button>)}</div></div>}
    {mode==='task'&&!!submissions.length&&<details className="submission-list" open><summary>最近提交 <span>{submissions.length}</span></summary>{submissions.slice(0,5).map(s=><div key={s.id}><span>{s.goal}</span><strong className={'submission-state '+s.status}>{({planning:'规划中',ready:'计划已创建',failed:'规划失败',interrupted:'规划中断'} as Record<string,string>)[s.status]}</strong>{s.number!==null&&<button className="secondary" onClick={()=>onTask(s.number!)}>查看任务</button>}{s.error&&<p role="alert">{s.error}</p>}{s.status==='interrupted'&&<p>服务已重启，未自动重试。请核查任务列表后再提交。</p>}</div>)}</details>}
  </section>;
}
