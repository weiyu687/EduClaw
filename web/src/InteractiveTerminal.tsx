import {useEffect,useRef,useState} from 'react';
import {request,query} from './api';
type TerminalRow={id:string;cwd:string;trust:boolean;alive:boolean;output:string;truncated:boolean;agent:{status:string;goal:string;answer:string;pending:null|{id:string;text:string;reason:string};history:unknown[]}};
const status:Record<string,string>={idle:'待命',running:'正在工作',waiting:'等待确认',completed:'本轮结束',failed:'发生错误',cancelled:'已停止',interrupted:'已中断',needs_attention:'需要继续确认'};
export function InteractiveTerminal({token,session}:{token:string;session:string}){
  const [autonomy,setAutonomy]=useState('balanced');
  const [rows,setRows]=useState<TerminalRow[]>([]);const [selected,setSelected]=useState('');
  const [cwd,setCwd]=useState('');const [trust,setTrust]=useState(false);const [consent,setConsent]=useState(false);
  const [text,setText]=useState('');const [goal,setGoal]=useState('');const [confirmation,setConfirmation]=useState('');
  const [error,setError]=useState('');const [busy,setBusy]=useState(false);
  const generation=useRef(0);const live=useRef(true);const identity=useRef<{key:string;id:string}|null>(null);
  const output=useRef<HTMLPreElement>(null);const follow=useRef(true);
  const current=rows.find(x=>x.id===selected)??rows[0];
  useEffect(()=>{follow.current=true;},[current?.id]);
  useEffect(()=>{if(output.current&&follow.current)output.current.scrollTop=output.current.scrollHeight;},[current?.output]);
  useEffect(()=>{let active=true;live.current=true;setRows([]);setSelected('');const version=++generation.current;
    async function refresh(){if(!session)return;try{const data=await request<TerminalRow[]>(token,'/api/terminals?'+query(session));if(active&&version===generation.current)setRows(data);}catch(e){if(active)setError(e instanceof Error?e.message:'终端读取失败');}}
    void refresh();identity.current=null;setError('');setBusy(false);
    void request<{workspace:string;autonomy:string}>(token,'/api/permissions?'+query(session)).then(x=>{if(active){setCwd(x.workspace);setAutonomy(x.autonomy);}}).catch(()=>{});
    return()=>{active=false;live.current=false;};},[token,session]);
  async function act(action:string,args:Record<string,unknown>){setBusy(true);setError('');const version=generation.current;
    const key=JSON.stringify([session,action,args]);if(identity.current?.key!==key)identity.current={key,id:crypto.randomUUID().replaceAll('-','')};
    try{const data=await request<TerminalRow>(token,'/api/terminals',{session,action,arguments:{...args,...(action==='close'?{}:{request_id:identity.current.id})}});
      if(live.current&&version===generation.current){setRows(old=>[data,...old.filter(x=>x.id!==data.id)]);setSelected(data.id);setConfirmation('');if(action==='input')setText('');identity.current=null;}
    }catch(e){if(live.current&&version===generation.current)setError((e instanceof Error?e.message:'终端操作未确认完成')+'；请先核查输出，避免重复输入。');}
    finally{if(live.current&&version===generation.current)setBusy(false);}
  }
  // Polling updates never steal focus or clear typed commands.
  useEffect(()=>{if(!session)return;let active=true;const timer=setInterval(()=>{
    if(busy)return;void request<{autonomy:string}>(token,'/api/permissions?'+query(session)).then(data=>{if(active)setAutonomy(data.autonomy);}).catch(()=>{});void request<TerminalRow[]>(token,'/api/terminals?'+query(session)).then(data=>{if(active)setRows(data);}).catch(()=>{});
  },1500);return()=>{active=false;clearInterval(timer);};},[token,session,busy]);
  return <section className="terminal-panel interactive-terminal" aria-label="持续终端">
    <p>像使用自己的终端一样读写文件、构建、使用 Git 或诊断网络。PowerShell 保留目录、变量和交互程序；关闭窗口后进程仍在，关闭终端才会结束进程树。</p>
    <details open={!rows.length}><summary>打开终端</summary><label>初始目录<input aria-label="持续终端目录" value={cwd} onChange={e=>setCwd(e.target.value)}/></label>
      <label className="terminal-choice"><input type="checkbox" checked={trust} onChange={e=>setTrust(e.target.checked)}/>允许 Agent 连续控制此终端</label>
      <p className="muted">此选项适用于平衡模式：不勾选则逐次确认，勾选可连续控制，敏感操作仍确认。对话的逐步确认或自主执行模式优先于此选项。</p>
      <label className="terminal-choice"><input aria-label="确认本机终端权限" type="checkbox" checked={consent} onChange={e=>setConsent(e.target.checked)}/>我了解终端使用本机用户权限，初始目录不是沙箱；输入和输出会保存。</label>
      <button className="primary" disabled={!session||busy||!consent||!cwd.trim()} onClick={()=>void act('open',{cwd:cwd.trim(),trust,confirmation:'OPEN'})}>打开持续终端</button>
    </details>
    {error&&<p role="alert" className="alert">{error}</p>}
    {rows.length>0&&<label>终端会话<select aria-label="终端会话" value={current?.id??''} onChange={e=>setSelected(e.target.value)}>{rows.map(r=><option key={r.id} value={r.id}>{r.id.slice(0,8)} · {r.alive?'运行中':'已关闭'} · {r.cwd}</option>)}</select></label>}
    {current&&<><div className="terminal-session-heading"><strong>{current.alive?'终端在线':'终端已关闭'} · Agent {status[current.agent.status]??current.agent.status}</strong><span>{autonomy==='autonomous'?'自主执行 · 在权限管理中可撤销':autonomy==='strict'?'逐步确认':current.trust?'允许自动控制':'逐次审阅'}</span></div>
      <pre ref={output} onScroll={()=>{const node=output.current;if(node)follow.current=node.scrollHeight-node.scrollTop-node.clientHeight<40;}} className="terminal-console" aria-label="实时终端输出" tabIndex={0}>{current.output||'等待终端输出…'}</pre>{current.truncated&&<p className="muted">仅显示最近 128 Ki 字符，早期输出已截断。</p>}
      <button className="secondary" onClick={()=>{follow.current=true;if(output.current)output.current.scrollTop=output.current.scrollHeight;}}>查看最新输出</button>
      {current.alive&&<><div className="terminal-controls"><button className="secondary" disabled={busy} onClick={()=>void act('interrupt',{id:current.id})}>停止 Agent / Ctrl+C</button><button className="danger" disabled={busy} onClick={()=>void act('close',{id:current.id})}>关闭终端及子进程</button>{current.trust&&autonomy==='balanced'&&<button className="secondary" disabled={busy} onClick={()=>void act('trust',{id:current.id,trust:false,confirmation:''})}>撤销自动控制</button>}</div>
      <label>直接输入<textarea aria-label="持续终端输入" rows={3} value={text} onChange={e=>setText(e.target.value)} placeholder="输入命令或交互程序所需的内容"/></label><button className="secondary" disabled={busy||!text||['running','waiting'].includes(current.agent.status)} onClick={()=>void act('input',{id:current.id,text:text.replace(/\r?\n/g,'\r')+'\r'})}>发送输入与回车</button>
      <label>交给 Agent 的目标<textarea aria-label="终端 Agent 目标" rows={3} value={goal} onChange={e=>setGoal(e.target.value)} placeholder="检查这个项目，运行测试，根据报错修复并复测"/></label><button className="primary" disabled={busy||!goal.trim()||['running','waiting'].includes(current.agent.status)} onClick={()=>void act('agent',{id:current.id,goal})}>让 Agent 开始工作</button>
      {current.agent.pending&&<div className="permission-review" aria-label="终端 Agent 审批"><strong>确认下一次输入</strong><p>{current.agent.pending.reason}</p><pre>{current.agent.pending.text}</pre><label>输入 EXECUTE<input aria-label="持续终端执行确认" value={confirmation} onChange={e=>setConfirmation(e.target.value)}/></label><button className="primary" disabled={busy||confirmation!=='EXECUTE'} onClick={()=>void act('approve',{id:current.id,pending_id:current.agent.pending!.id,confirmation})}>确认 Agent 输入</button></div>}
      </>}{current.agent.answer&&<article className="terminal-answer"><h3>Agent 本轮结论</h3><p>{current.agent.answer}</p></article>}
      {!!current.agent.history.length&&<details><summary>查看操作记录</summary><pre>{JSON.stringify(current.agent.history,null,2)}</pre></details>}
    </>}
  </section>;
}
