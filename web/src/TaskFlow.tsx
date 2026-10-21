import {useEffect,useState} from 'react';
import type {Detail} from './api';

type Step=Detail['steps'][number];
type Result=Detail['results'][number];

export function flowState(step:Step,result?:Result):{kind:string;label:string}{
  if(result&&(!result.intact||result.truncated||result.status!=='completed'))return {kind:'attention',label:'结果需核查'};
  if(step.status==='completed')return result?{kind:'success',label:'成功'}:{kind:'attention',label:'缺少结果'};
  if(['uncertain','denied','failed','cancelled'].includes(step.status))return {kind:'attention',label:step.status==='denied'?'已拒绝':step.status==='cancelled'?'已取消':'需要核查'};
  if(step.status==='executing')return {kind:'active',label:'执行中'};
  if(step.status==='approved')return {kind:'active',label:'已批准'};
  if(step.status==='waiting')return {kind:'queued',label:'等待前序'};
  return {kind:'queued',label:'等待确认'};
}

function Output({result}:{result?:Result}){
  if(!result)return <p className="flow-no-output">这一步还没有保存输出。执行完成后会在此显示。</p>;
  return <><div className={'flow-evidence '+(result.intact&&!result.truncated?'valid':'attention')}>
    <strong>{result.intact&&!result.truncated?'结果已保存并通过校验':'结果不完整或校验未通过'}</strong>
    <span>状态：{result.status}</span>
  </div>{result.terminal?<div className="flow-terminal"><div><strong>{({completed:'命令完成',nonzero_exit:'命令返回错误',timed_out:'执行超时',cancelled:'已取消'} as Record<string,string>)[result.terminal.execution_status]??result.terminal.execution_status}</strong><span>退出码 {result.terminal.exit_code} · {result.terminal.duration_seconds} 秒</span></div><small>{result.terminal.cwd}</small><label>标准输出</label><pre>{result.terminal.stdout||'（无输出）'}</pre><label>错误输出</label><pre>{result.terminal.stderr||'（无错误输出）'}</pre>{result.terminal.truncated&&<small>输出已截断，完整记录请在 CLI 查看。</small>}</div>:<pre>{result.summary||'（无可展示的摘要）'}</pre>}
    <details className="flow-raw"><summary>查看保存的原始结果与摘要</summary><pre>{result.content}</pre>{result.preview_truncated&&<p>页面仅展示前 20000 个字符。</p>}<code>SHA256 {result.digest}</code></details></>;
}

export function TaskFlow({detail}:{detail:Detail}){
  const [selected,setSelected]=useState(()=>detail.steps.find(step=>!['completed','waiting'].includes(step.status))?.number??detail.steps.at(-1)?.number??1);
  useEffect(()=>{if(!detail.steps.some(step=>step.number===selected))setSelected(detail.steps[0]?.number??1);},[detail.steps,selected]);
  const step=detail.steps.find(row=>row.number===selected)??detail.steps[0];
  const result=detail.results.find(row=>row.step===step?.number);
  const counts={success:0,active:0,attention:0,queued:0};
  for(const row of detail.steps)counts[flowState(row,detail.results.find(result=>result.step===row.number)).kind as keyof typeof counts]++;
  if(!step)return <p className="empty">当前任务没有步骤。</p>;
  const state=flowState(step,result);
  return <section className="task-flow" aria-label="任务可视化流程">
    <div className="flow-overview"><div><span className="eyebrow">WORKFLOW</span><h3>执行流程</h3><p>按顺序查看步骤。选中节点可核对输入、输出与结果状态。</p></div><div className="flow-counts" aria-label="流程状态统计"><span>{counts.success} 成功</span><span>{counts.active} 进行中</span><span>{counts.attention} 需核查</span><span>{counts.queued} 等待</span></div></div>
    <div className="flow-rail" role="list" aria-label="执行顺序">{detail.steps.map((row,index)=>{const output=detail.results.find(item=>item.step===row.number);const current=flowState(row,output);return <div className="flow-node-wrap" role="listitem" key={row.number}>{index>0&&<span className="flow-arrow" aria-hidden="true">→</span>}<button type="button" className={'flow-node '+current.kind+(selected===row.number?' selected':'')} aria-current={selected===row.number?'step':undefined} aria-label={`第 ${row.number} 步 ${row.tool}：${current.label}`} onClick={()=>setSelected(row.number)}><span className="flow-node-top"><b>{current.kind==='success'?'✓':String(row.number).padStart(2,'0')}</b><small>{current.label}</small></span><strong>{row.tool}</strong><span>第 {row.number} 步</span></button></div>;})}</div>
    <article className="flow-inspector" aria-label={`第 ${step.number} 步详情`}><div className="flow-inspector-heading"><div><span className="eyebrow">STEP {String(step.number).padStart(2,'0')}</span><h4>{step.tool}</h4></div><span className={'flow-state '+state.kind}>{state.label}</span></div>
      <p className="flow-dependencies">{step.dependencies.length?`依赖第 ${step.dependencies.join('、')} 步的结果`:'此步骤没有显式依赖'} · 第 {step.number} / {detail.total} 步</p>
      <div className="flow-io"><section><h5>输入参数</h5><pre>{JSON.stringify(step.arguments,null,2)}</pre></section><section><h5>输出与证据</h5><Output result={result}/></section></div>
    </article>
  </section>;
}
