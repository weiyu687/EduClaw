import {useEffect,useState} from 'react';
import {request,query} from './api';
interface Data {tools:{name:string;mode:string;risk:string}[];files:{id:number;path:string;scope:string;remaining:number|null}[]}
interface Review {ticket:string;path:string;scope:string;directory:boolean}
export function Permissions({token,session}:{token:string;session:string}){
  const [data,setData]=useState<Data>();const [error,setError]=useState('');const [busy,setBusy]=useState(false);
  const [path,setPath]=useState('');const [scope,setScope]=useState('once');const [review,setReview]=useState<Review>();
  useEffect(()=>{let live=true;if(session)request<Data>(token,'/api/permissions?'+query(session)).then(x=>{if(live)setData(x);}).catch(e=>{if(live)setError(e.message);});return()=>{live=false;};},[token,session]);
  async function change(kind:string,value:string|number,mode:string){setBusy(true);setError('');try{const result=await request<Data|Review>(token,'/api/permissions',{session,kind,value,mode});if('ticket' in result)setReview(result);else{setData(result);setReview(undefined);}}catch(e){setError(e instanceof Error?e.message:'权限修改失败');setReview(undefined);}finally{setBusy(false);}}
  return <section className="permissions-panel" aria-label="权限管理"><h2>工具与文件权限</h2><p>工具设置适用于此工作空间的所有会话。启用不会跳过文件授权或代码审批；已开始的调用不受撤销影响。</p>
    {!session&&<p>请先新建或选择对话。</p>}{error&&<p className="alert" role="alert">{error}</p>}
    <h3>工具权限</h3><div className="permission-tools">{data?.tools.map(t=><label key={t.name}><span>{t.name}<small>{t.risk==='path_read'?'读取文件，需路径授权':t.risk==='code_execute'?'运行代码，每步确认':t.risk==='public_read'?'公开信息查询':'遵循底层工具策略'}</small></span><select aria-label={`工具权限 ${t.name}`} value={t.mode} disabled={busy} onChange={e=>void change('tool',t.name,e.target.value)}><option value="ask">按安全策略审批</option><option value="deny">禁用</option></select></label>)}</div>
    <h3>文件访问权限</h3><p>填写本机文件或文件夹的绝对路径。文件夹授权包含其子目录，仅允许读取。</p><label>文件或文件夹路径<input aria-label="授权路径" value={path} onChange={e=>{setPath(e.target.value);setReview(undefined);}} placeholder="D:\\资料\\报告.csv"/></label><div className="permission-actions"><select aria-label="授权范围" value={scope} onChange={e=>{setScope(e.target.value);setReview(undefined);}}><option value="once">仅一次读取</option><option value="session">当前对话</option></select><button className="secondary" disabled={!session||busy||!path.trim()} onClick={()=>void change('file_preview',path,scope)}>预览文件授权</button></div>
    {review&&<div className="permission-review" role="group" aria-label="确认文件授权"><h3>确认授权范围</h3><pre>{review.path}</pre><p>{review.directory?'此文件夹及所有子目录':'仅此文件'} · {review.scope==='once'?'仅一次读取':'当前对话持续有效，直至撤销'} · 只读</p><button className="primary" disabled={busy} onClick={()=>void change('file_confirm',review.ticket,'CONFIRM')}>确认文件授权</button><button className="secondary" disabled={busy} onClick={()=>setReview(undefined)}>取消</button></div>}
    <div className="file-grants">{data?.files.map(f=><article key={f.id}><pre>{f.path}</pre><span>{f.scope==='always'?'持久授权（所有会话）':f.scope==='session'?'当前对话':f.remaining?'单次，未使用':'单次，已使用'}</span><button className="danger" disabled={busy} onClick={()=>void change('revoke',f.id,'')}>撤销授权 #{f.id}</button></article>)}{data&&!data.files.length&&<p>暂无文件授权。也可直接在任务中审批单次读取。</p>}</div>
  </section>;
}
