"""Shared GUI/CLI inspection of the actual chat context mechanism."""
from pathlib import Path
from core.state.conversation import Conversation
from core.state.context_memory import build,recall

def inspect(directory,session,query=''):
    if not isinstance(query,str) or len(query)>4000:raise ValueError('检索词不能超过 4000 字。')
    conversation=Conversation(Path(directory)/'educlaw_state.sqlite3')
    rows=conversation.history(session)
    current=next((r['text'] for r in reversed(rows) if r['status']=='completed'),'')
    context=build(conversation.state,session,rows,query or current)
    from core.state.semantic import status
    return {'summary':context['summary'],'summary_sources':context['summary_sources'],'stats':context['stats'],'retrieval':status(),
            'matches':recall([r for r in rows if r['status']=='completed'],query) if query.strip() else [],
            'last_context':next((r.get('context_info') for r in reversed(rows) if r.get('context_info')),None)}

def cli(directory,session,text):
    import json
    from core.state.library import Library,MAX_FILE_BYTES
    parts=text.split(maxsplit=2)
    if parts[0]=='/memory':return json.dumps(inspect(directory,session,text.partition(' ')[2]),ensure_ascii=False,indent=2)
    library=Library(directory)
    action=parts[1] if len(parts)>1 else 'list'
    argument=parts[2] if len(parts)>2 else ''
    if action=='add':
        path=Path(argument.strip('"')).expanduser().resolve(strict=True)
        if not path.is_file() or path.stat().st_size>MAX_FILE_BYTES:raise ValueError('请选择不超过 5 MB 的文件。')
        result=library.add(session,path.name,path.read_bytes())
    elif action in ('mount','unmount'):library.mount(session,argument,action=='mount');result=library.list(session)
    elif action=='remove':library.remove(session,argument);result=library.list(session)
    elif action=='search':result=library.search(session,argument)
    elif action=='list':result=library.list(session)
    else:raise ValueError('/library list | add 路径 | search 问题 | mount ID | unmount ID | remove ID')
    return json.dumps(result,ensure_ascii=False,indent=2)
