import {useEffect,useState} from 'react';
import {request,query} from './api';

interface Project {id:string;name:string;instructions:string;documents:string[];sessions_count:number;documents_count:number}
interface View {projects:Project[];current:Project|null}
interface Document {id:string;name:string;chars:number}

export function Projects({token,session,onChange}:{token:string;session:string;onChange:(project:Project|null)=>void}){
  const [view,setView]=useState<View>();const [documents,setDocuments]=useState<Document[]>([]);
  const [name,setName]=useState('');const [instructions,setInstructions]=useState('');const [selected,setSelected]=useState<string[]>([]);
  const [newName,setNewName]=useState('');const [busy,setBusy]=useState(false);const [error,setError]=useState('');const [notice,setNotice]=useState('');
  async function load(){const [projects,docs]=await Promise.all([request<View>(token,'/api/projects?'+query(session)),request<Document[]>(token,'/api/library?'+query(session))]);setView(projects);setDocuments(docs);setName(projects.current?.name??'');setInstructions(projects.current?.instructions??'');setSelected(projects.current?.documents??[]);onChange(projects.current);}
  useEffect(()=>{void load().catch(e=>setError(e.message));},[session,token]);
  async function act(action:string,arguments_:Record<string,unknown>){setBusy(true);setError('');setNotice('');try{const next=await request<View>(token,'/api/projects',{session,action,arguments:arguments_});setView(next);setName(next.current?.name??'');setInstructions(next.current?.instructions??'');setSelected(next.current?.documents??[]);onChange(next.current);setNotice('项目设置已保存。');}catch(e){setError(e instanceof Error?e.message:'操作失败');}finally{setBusy(false);}}
  return <div className="projects-panel">
    <p>项目把相关对话、共享资料和工作指令放在同一个上下文中。新对话会沿用当前项目。</p>
    {error&&<p className="alert" role="alert">{error}</p>}{notice&&<p className="notice" role="status">{notice}</p>}
    <div className="project-create"><input aria-label="新项目名称" placeholder="新项目名称" maxLength={80} value={newName} onChange={e=>setNewName(e.target.value)}/><button className="secondary" disabled={busy||!newName.trim()} onClick={()=>void act('create',{name:newName.trim()}).then(()=>setNewName(''))}>创建项目</button></div>
    <label>当前会话所属项目<select aria-label="当前项目" value={view?.current?.id??''} disabled={busy} onChange={e=>void act('assign',{id:e.target.value})}><option value="">无项目</option>{view?.projects.map(p=><option key={p.id} value={p.id}>{p.name} · {p.sessions_count} 个对话</option>)}</select></label>
    {view?.current&&<>
      <label>项目名称<input maxLength={80} value={name} onChange={e=>setName(e.target.value)}/></label>
      <label>项目工作指令<textarea maxLength={12000} rows={7} placeholder="例如：回答先给结论；引用项目资料时标明来源。" value={instructions} onChange={e=>setInstructions(e.target.value)}/><small>{instructions.length} / 12000</small></label>
      <button className="primary" disabled={busy||!name.trim()} onClick={()=>void act('update',{id:view.current!.id,name,instructions})}>保存项目设置</button>
      <div className="project-documents"><h3>项目共享资料</h3><p>勾选后，项目内所有对话都能检索这些资料。</p>{documents.length?documents.map(doc=><label key={doc.id}><input type="checkbox" checked={selected.includes(doc.id)} onChange={()=>setSelected(xs=>xs.includes(doc.id)?xs.filter(x=>x!==doc.id):[...xs,doc.id])}/><span>{doc.name}<small>{doc.chars.toLocaleString()} 字</small></span></label>):<p className="muted">资料库为空，请先在“资料库”添加文件。</p>}</div>
      <button className="secondary" disabled={busy} onClick={()=>void act('documents',{id:view.current!.id,documents:selected})}>保存共享资料</button>
    </>}
  </div>;
}
