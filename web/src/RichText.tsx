import {useState,useRef,type ReactNode} from 'react';
import Markdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import {Icon} from './Icon';

export function CopyButton({text,label='复制内容'}:{text:string;label?:string}){
  const [status,setStatus]=useState('');
  return <button className="copy-button" aria-label={label} title={label} onClick={()=>{void navigator.clipboard.writeText(text).then(()=>setStatus('已复制')).catch(()=>setStatus('复制失败，请选择文字复制'));}}><Icon name={status==='已复制'?'check':'copy'} size={15}/><span role="status">{status||'复制'}</span></button>;
}
function CodeBlock({children}:{children?:ReactNode}){
  const block=useRef<HTMLPreElement>(null);
  const [copied,setCopied]=useState(false);
  return <div className="code-block"><div className="code-toolbar"><span>代码</span><button className="copy-button" onClick={async()=>{try{await navigator.clipboard.writeText(block.current?.innerText??'');setCopied(true);}catch{setCopied(false);}}}>{copied?'已复制':'复制代码'}</button></div><pre ref={block}>{children}</pre></div>;
}
export function safeLink(url:string){return /^(https?:\/\/|mailto:)/i.test(url)?url:'';}
export function RichText({text}:{text:string}){
  return <div className="rich-text"><Markdown remarkPlugins={[remarkGfm]} skipHtml urlTransform={safeLink} components={{
    a:({href,children})=>href?<a href={href} target="_blank" rel="noopener noreferrer">{children}</a>:<span>{children}</span>,
    img:({alt})=><span className="muted">[图片：{alt||'未加载'}]</span>,
    pre:({children})=><CodeBlock>{children}</CodeBlock>,
    table:({children})=><div className="table-scroll"><table>{children}</table></div>,
  }}>{text}</Markdown></div>;
}
export function NewsSummary({text}:{text:string}){
  const formatted=text.replace(/^• /gm,'- ').replace(/^(\s*)https:\/\/[^\s]+/gm,url=>`  [查看报道 ↗](${url.trim()})`);
  return <RichText text={formatted}/>;
}
