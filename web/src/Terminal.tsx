import {useRef,useState} from 'react';
import {request} from './api';
export function Terminal({token,session,onTask}:{token:string;session:string;onTask:(number:number)=>void}){
  const [cwd,setCwd]=useState('');const [command,setCommand]=useState('');const [timeout,setTimeoutValue]=useState(60);
  const [busy,setBusy]=useState(false);const [error,setError]=useState('');
  const identity=useRef<{key:string;id:string}|undefined>(undefined);
  async function prepare(){
    setBusy(true);setError('');
    try{
      const args={cwd:cwd.trim(),command,timeout_seconds:timeout};const key=JSON.stringify([session,args]);
      if(identity.current?.key!==key){const bytes=crypto.getRandomValues(new Uint8Array(16));identity.current={key,id:Array.from(bytes,b=>b.toString(16).padStart(2,'0')).join('')};}
      const result=await request<{number:number}>(token,'/api/terminal',{session,arguments:args,request_id:identity.current!.id});
      identity.current=undefined;onTask(result.number);
    }catch(e){setError(e instanceof Error?e.message:'无法准备终端命令。');}finally{setBusy(false);}
  }
  return <section className="terminal-panel"><p>在指定目录运行 Windows PowerShell 命令，适用于检查项目、构建和测试。</p><p className="notice">命令在本机以当前用户权限运行。工作目录是起始位置，不是沙箱；执行前会再次展示命令并请你确认。</p>
    <label>工作目录<input aria-label="终端工作目录" value={cwd} onChange={e=>setCwd(e.target.value)} placeholder="D:\projects\my-project" disabled={busy}/></label>
    <label>PowerShell 命令<textarea aria-label="终端命令" rows={7} maxLength={8000} spellCheck={false} value={command} onChange={e=>setCommand(e.target.value)} placeholder="Get-Location&#10;Get-ChildItem" disabled={busy}/></label>
    <label>超时（秒，1–180）<input aria-label="终端超时" type="number" min={1} max={180} value={timeout} onChange={e=>setTimeoutValue(Number(e.target.value))} disabled={busy}/></label>
    <p className="muted">不支持交互输入或常驻服务。超时、取消或命令结束时会清理本次创建的进程树；已写入的文件等效果不会撤销。每次执行的工作目录和命令独立，不继承上一条命令中的 cd 或变量。</p>
    {error&&<p role="alert" className="alert">{error}</p>}<button className="primary" disabled={!session||busy||!cwd.trim()||!command.trim()||!Number.isInteger(timeout)||timeout<1||timeout>180} onClick={()=>void prepare()}>{busy?'正在准备…':'准备命令并查看审批'}</button>
    {!session&&<p>请先新建或选择对话。</p>}</section>;
}
