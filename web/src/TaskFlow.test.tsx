import {expect,it} from 'vitest';
import {renderToStaticMarkup} from 'react-dom/server';
import {TaskFlow,flowState} from './TaskFlow';
import type {Detail} from './api';

const detail:Detail={number:1,goal:'整理来源',status:'running',control:'active',completed:1,total:2,
  steps:[{number:1,tool:'public_search',arguments:{query:'AI'},status:'completed',dependencies:[]},
         {number:2,tool:'write_text_file',arguments:{path:'report.md'},status:'pending',dependencies:[1]}],
  results:[{step:1,status:'completed',digest:'abc',intact:true,truncated:false,summary:'找到 3 条来源',content:'{"results":3}',preview_truncated:false}],
  recovery:{action:'continue',message:'继续'},actions:[],versions:1,execution_pending:false,execution_error:false};

it('shows step progress, inputs and verified output together',()=>{
  const html=renderToStaticMarkup(<TaskFlow detail={{...detail,steps:detail.steps.slice(0,1),total:1}}/>);
  expect(html).toContain('1 成功');
  expect(html).toContain('输入参数');
  expect(html).toContain('找到 3 条来源');
  expect(html).toContain('结果已保存并通过校验');
  expect(renderToStaticMarkup(<TaskFlow detail={detail}/>)).toContain('1 等待');
});

it('never labels an uncertain or damaged result successful',()=>{
  expect(flowState({...detail.steps[0],status:'uncertain'},detail.results[0]).kind).toBe('attention');
  expect(flowState(detail.steps[0],{...detail.results[0],intact:false}).label).toBe('结果需核查');
  expect(flowState(detail.steps[0],undefined).label).toBe('缺少结果');
});
