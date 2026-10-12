import {afterEach,expect,it,vi} from 'vitest';
import {query,request} from './api';
afterEach(()=>{vi.unstubAllGlobals();vi.useRealTimers();});
it('encodes session identity without adding query parameters',()=>{
  const value=new URLSearchParams(query('a&number=9',2));
  expect(value.get('session')).toBe('a&number=9');expect(value.get('number')).toBe('2');
});
it('uses explicit auth and does not retry a rejected confirmation',async()=>{
  const fetch=vi.fn().mockResolvedValue({ok:false,json:async()=>({error:'已消耗'})});vi.stubGlobal('fetch',fetch);
  await expect(request('credential','/api/confirm',{ticket:'once',confirmation:'CONFIRM'})).rejects.toThrow('已消耗');
  expect(fetch).toHaveBeenCalledTimes(1);
  const options=fetch.mock.calls[0][1];
  expect(options.credentials).toBe('omit');expect(options.headers.Authorization).toBe('Bearer credential');
});
it('reports transport failure without replaying the request',async()=>{
  const fetch=vi.fn().mockRejectedValue(new Error('offline'));vi.stubGlobal('fetch',fetch);
  await expect(request('x','/api/confirm',{})).rejects.toThrow('offline');expect(fetch).toHaveBeenCalledTimes(1);
});
it('aborts timed out requests on browsers without AbortSignal.timeout',async()=>{
  vi.useFakeTimers();
  const fetch=vi.fn().mockImplementation((_url,options)=>new Promise((_resolve,reject)=>{
    options.signal.addEventListener('abort',()=>reject(new Error('aborted')));
  }));vi.stubGlobal('fetch',fetch);
  const check=expect(request('x','/api/confirm',{})).rejects.toThrow('连接超时');
  await vi.advanceTimersByTimeAsync(10000);await check;
  expect(fetch).toHaveBeenCalledTimes(1);expect(vi.getTimerCount()).toBe(0);
});
