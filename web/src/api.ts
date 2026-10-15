export interface Session {id:string;label:string;updated_at:string}
export type Action = 'pause' | 'resume' | 'cancel' | 'execute' | 'read' | 'tool';
export interface Task {number:number;goal:string;status:string;control:string;completed:number;total:number}
export interface Detail extends Task {
  summary?:{status:string;answer:string}|null;
  steps:{number:number;tool:string;arguments:Record<string,unknown>;status:string;dependencies:number[]}[];
  results:{step:number;status:string;digest:string;intact:boolean;truncated:boolean;summary:string;content:string;preview_truncated:boolean;terminal?:{cwd:string;command:string;exit_code:number;execution_status:string;stdout:string;stderr:string;duration_seconds:number;truncated:boolean}}[];
  recovery:{action:string;message:string};actions:Action[];versions:number;execution_pending:boolean;execution_error:boolean;
}
export interface Preview {ticket:string;number:number;action:Action;goal:string;message:string;expires_in:number;confirmation?:string;code?:string;step?:number;path?:string;tool?:string;arguments?:Record<string,unknown>;before?:string}
export function takeCredential():string {
  const token = new URLSearchParams(location.hash.slice(1)).get('token');
  if (token) {sessionStorage.setItem('educlaw-token',token);history.replaceState(null,'',location.pathname);}
  return sessionStorage.getItem('educlaw-token') ?? '';
}
export async function request<T>(token:string,path:string,body?:unknown,timeoutMs=10000):Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(()=>controller.abort(),timeoutMs);
  try {
  const response = await fetch(path,{method:body===undefined?'GET':'POST',cache:'no-store',credentials:'omit',
    headers:{Authorization:`Bearer ${token}`,...(body===undefined?{}:{'Content-Type':'application/json'})},
    body:body===undefined?undefined:JSON.stringify(body),signal:controller.signal});
  const value = await response.json();
  if (!response.ok) throw new Error(value.error ?? '连接失败，请刷新后核查。');
  return value as T;
  } catch(error) {
    if(controller.signal.aborted) throw new Error('连接超时，请刷新核查状态。');
    throw error;
  } finally {clearTimeout(timer);}
}
export function query(session:string,number?:number):string {
  return new URLSearchParams({session,...(number===undefined?{}:{number:String(number)})}).toString();
}
export const labels:Record<string,string> = {running:'进行中',completed:'已完成',denied:'已结束',uncertain:'需要核查',approved:'准备执行',executing:'执行中',waiting:'等待前序步骤',pending:'待审批',active:'可继续',paused:'已暂停',cancelled:'已取消',cancel_requested:'正在取消'};
export const actionLabels:Record<Action,string> = {pause:'暂停任务',resume:'恢复任务',cancel:'取消任务',execute:'审阅并执行',read:'审批文件读取',tool:'审批工具操作'};
