import {useEffect,useRef,type ReactNode} from 'react';
import {createPortal} from 'react-dom';
import {Icon} from './Icon';
export function PanelDialog({open,title,onClose,children}:{open:boolean;title:string;onClose:()=>void;children:ReactNode}){
  const ref=useRef<HTMLDialogElement>(null);
  const trigger=useRef<HTMLElement|null>(null);
  useEffect(()=>{if(open&&!ref.current?.open){trigger.current=document.activeElement as HTMLElement;ref.current?.showModal();}else if(!open){if(ref.current?.open)ref.current.close();trigger.current?.focus();}},[open]);
  return createPortal(<dialog className="management-dialog" ref={ref} aria-label={title} onCancel={onClose} onClose={onClose} onClick={e=>{if(e.target===ref.current){const r=ref.current.getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)onClose();}}}><div className="panel-header"><div><span className="eyebrow">EDUCLAW / WORKSPACE</span><h2>{title}</h2></div><button className="icon-button" aria-label="关闭管理面板" onClick={onClose}><Icon name="close"/></button></div><div className="panel-body">{children}</div></dialog>,document.body);
}
