import type {CSSProperties} from 'react';
const paths:Record<string,string>={
  spark:'M12 3 14.3 9.7 21 12l-6.7 2.3L12 21l-2.3-6.7L3 12l6.7-2.3L12 3Z',
  book:'M12 6C9 3 5 3 3 4v15c3-1 6-1 9 2 3-3 6-3 9-2V4c-2-1-6-1-9 2Zm0 0v15M6 8l3 1M15 9l3-1',
  plus:'M12 5v14M5 12h14',chat:'M21 11a8 8 0 0 1-8 8H8l-5 3V11a9 9 0 0 1 18 0Z',
  tools:'m14 6 4-3a6 6 0 0 1-7 8L5 18a2 2 0 0 1-3-3l7-6a6 6 0 0 1 8-7l-3 4Z',
  shield:'m12 3 8 3v6c0 5-8 9-8 9s-8-4-8-9V6l8-3Zm-4 9 3 3 5-6',
  command:'M8 8V5a2 2 0 1 0-2 2h12a2 2 0 1 0-2-2v13a2 2 0 1 0 2-2H6a2 2 0 1 0 2 2V8Z',
  arrow:'M12 19V5m-6 6 6-6 6 6',close:'m6 6 12 12M6 18 18 6',
  menu:'M4 5h16v14H4V5Zm6 0v14',search:'M17 17 21 21M19 11a8 8 0 1 1-16 0 8 8 0 0 1 16 0Z',
  copy:'M8 8h12v12H8V8ZM16 8V4H4v12h4',check:'m5 12 4 4L19 6',
  chevron:'m9 5 7 7-7 7',refresh:'M20 7v5h-5M4 17v-5h5M5 8a8 8 0 0 1 13-3l2 7M4 12l2 7a8 8 0 0 0 13-3',
  globe:'M3 12h18M12 3c5 5 5 13 0 18-5-5-5-13 0-18Zm9 9a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z',
  file:'M14 3H5v18h14V8l-5-5Zm0 0v6h5M8 13h8M8 17h5',folder:'M3 6h7l2 2h9v11H3V6Z',image:'M4 5h16v14H4V5Zm3 10 3-3 3 3 2-2 3 3M9 9h.01',
};
export function Icon({name,size=18,style}:{name:string;size?:number;style?:CSSProperties}){return <svg aria-hidden="true" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" style={style}><path d={paths[name]??paths.spark}/></svg>;}
