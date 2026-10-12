const input=document.getElementById('search');
const output=document.getElementById('search-results');
let index;
input.addEventListener('input',async()=>{
  const term=input.value.trim().toLowerCase();
  output.replaceChildren();
  if(!term)return;
  try{
    index??=await fetch('search-index.json').then(r=>{if(!r.ok)throw new Error('search');return r.json();});
    if(input.value.trim().toLowerCase()!==term)return;
    const matches=index.filter(p=>(p.title+' '+p.text).toLowerCase().includes(term));
    const heading=document.createElement('strong');heading.textContent=`找到 ${matches.length} 篇文档`;output.append(heading);
    for(const page of matches){const link=document.createElement('a');link.href=page.url;link.textContent=page.title;output.append(link);}
  }catch{const message=document.createElement('p');message.textContent='搜索暂不可用，请使用左侧目录。';output.append(message);}
});
