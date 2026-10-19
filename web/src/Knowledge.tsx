import {useEffect,useState} from 'react';
import {request,query} from './api';
type Document={id:string;name:string;chars:number;chunks:number;mounted:number;expert_mounted?:boolean};
type Match={id:string;text:string;score:number;name?:string;ordinal?:number;turn_id?:string};
type Memory={summary:string;summary_sources:string[];stats:Record<string,string|number>;matches:Match[];last_context:Record<string,unknown>|null};
export function Knowledge({token,session,kind}:{token:string;session:string;kind:'library'|'memory'}){
  const [documents,setDocuments]=useState<Document[]>([]);const [memory,setMemory]=useState<Memory>();
  const [search,setSearch]=useState('');const [matches,setMatches]=useState<Match[]>([]);
  const [busy,setBusy]=useState(false);const [error,setError]=useState('');const [remove,setRemove]=useState('');const [searched,setSearched]=useState(false);
  useEffect(()=>{let live=true;setMemory(undefined);setDocuments([]);setMatches([]);setError('');setSearch('');setRemove('');
    if(session)request<Document[]|Memory>(token,'/api/'+kind+'?'+query(session)).then(data=>{if(live){if(Array.isArray(data))setDocuments(data);else setMemory(data);}}).catch(e=>{if(live)setError(e.message);});
    return()=>{live=false;};},[token,session,kind]);
  async function act(action:string,args:Record<string,unknown>){setBusy(true);setError('');try{
    const data=await request<Document[]|Match[]>(token,'/api/library',{session,action,arguments:args},60000);
    if(action==='search'){setMatches(data as Match[]);setSearched(true);}else{setDocuments(data as Document[]);setMatches([]);setRemove('');setSearched(false);}
  }catch(e){setError(e instanceof Error?e.message:'操作失败');}finally{setBusy(false);}}
  async function upload(file:File){if(file.size>5*1024*1024){setError('每份资料最多 5 MB。');return;}
    const reader=new FileReader();reader.onerror=()=>setError('无法读取选择的文件');
    reader.onload=()=>void act('add',{name:file.name,data:String(reader.result).split(',')[1]});reader.readAsDataURL(file);
  }
  async function retrieve(){if(kind==='library'){await act('search',{query:search});return;}
    setBusy(true);setError('');try{setMemory(await request<Memory>(token,'/api/memory',{session,query:search}));setSearched(true);}catch(e){setError(e instanceof Error?e.message:'检索失败');}finally{setBusy(false);}}
  return <section aria-label={kind==='library'?'资料库管理':'会话记忆管理'}>
    {kind==='library'?<><p>添加学习资料、项目说明或研究笔记。资料目录在本工作空间共享；手动挂载或当前专家模式选中的资料参与检索。相关片段会发送给已配置的模型用于回答。</p>
      <label>添加资料<input aria-label="添加资料文件" type="file" accept=".txt,.md,.csv,.json,.jsonl,.log,.pdf,.docx" disabled={!session||busy} onChange={e=>{const file=e.target.files?.[0];if(file)void upload(file);e.target.value='';}}/></label>
      <p className="muted">UTF-8 文本、PDF、DOCX；每份最多 5 MB / 30 万字，PDF 最多 100 页，不支持扫描件 OCR。添加后自动挂载到当前对话，重复内容不会重复入库。移除只删除资料库副本，不修改原文件。</p>
      {documents.map(doc=><article className="library-document" key={doc.id}><strong>{doc.name}</strong><small>{doc.chars} 字 · {doc.chunks} 个片段</small><label><input type="checkbox" aria-label={'用于当前对话 '+doc.name} checked={!!doc.mounted} disabled={busy} onChange={e=>void act('mount',{id:doc.id,enabled:e.target.checked})}/>用于当前对话</label>
        {doc.expert_mounted&&<small>当前专家模式正在使用此资料。取消手动挂载不会取消领域挂载，请修改领域配置或退出专家模式。</small>}<button className="secondary" disabled={busy} onClick={()=>setRemove(doc.id)}>移除 {doc.name}</button>{remove===doc.id&&<div className="permission-review"><p>从整个资料库移除这份资料及其片段，所有对话停止检索。已保存的聊天引用不会删除。</p><button className="danger" disabled={busy} onClick={()=>void act('remove',{id:doc.id})}>确认移除资料</button><button className="secondary" onClick={()=>setRemove('')}>取消</button></div>}</article>)}
      {!documents.length&&<p>还没有资料。添加后可以直接在普通对话提问，也可以在下面验证检索效果。</p>}</>:<><p>当前对话独立记忆：近期消息＋历史摘要＋相关记忆召回。按相关性排序，仅返回匹配内容，不读取其他对话。</p>
      {memory&&<><div className="memory-stats"><span>完整记录 {memory.stats.total_completed} 轮</span><span>近期窗口 {memory.stats.recent_turns} 轮</span><span>已压缩 {memory.stats.compressed_turns} 轮</span><span>输入上限 {memory.stats.context_budget_chars} 字符</span></div>
        <p>检索引擎：{memory.stats.retrieval==='hybrid-static-rrf'?'本地多语言语义＋关键词混合检索':'关键词回退'} {memory.stats.retrieval_notice}</p><p className="muted">字符预算不是模型精确 token 数。摘要为有损抽取，完整历史保留。本地轻量向量与关键词排名融合、过滤弱匹配并去除近重复；相关性分数不是置信度，仍可能漏召回或误召回。模型不可用时明确显示关键词回退。</p>
        <h3>历史摘要</h3><pre>{memory.summary||'对话尚短，暂不需要压缩。'}</pre><details><summary>上次回答实际使用的上下文</summary><pre>{JSON.stringify(memory.last_context,null,2)}</pre></details></>}
    </>}
    <label>{kind==='library'?'检索已挂载资料':'查找当前对话记忆'}<input aria-label="记忆资料检索词" value={search} maxLength={4000} onChange={e=>setSearch(e.target.value)}/></label>
    <button className="primary" disabled={busy||!search.trim()||!session} onClick={()=>void retrieve()}>{busy?'处理中…':'检索相关内容'}</button>
    {error&&<p className="alert" role="alert">{error}</p>}
    {searched&&!busy&&!error&&!(kind==='library'?matches:memory?.matches??[]).length&&<p role="status">没有匹配的内容。请调整关键词，或检查资料是否已用于当前对话。</p>}
    <div aria-label="检索结果">{(kind==='library'?matches:memory?.matches??[]).map(row=><article className="library-document" key={row.id}><strong>{row.name?row.name+' · 片段 '+row.ordinal:'会话记忆'}</strong><small>相关性分数 {row.score}（非置信度）</small><pre>{row.text}</pre><small>来源 {row.id}</small></article>)}</div>
  </section>;
}
