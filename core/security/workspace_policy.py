"""Shared capability selection and risk policy; discovery never grants authority."""
from pathlib import Path
import os

def workspace_root():
    from core.security.read_grants import db_path
    path=Path(os.environ.get('EDUCLAW_WORKSPACE_ROOT',str(db_path().parent/'workspace'))).resolve()
    path.mkdir(parents=True,exist_ok=True)
    return path

def workspace_path(value):
    path=Path(value).expanduser()
    if not path.is_absolute() or ':' in path.name or path.name.startswith('.'):
        raise PermissionError('文件路径必须为工作目录内的绝对路径。')
    path=path.resolve()
    if not path.is_relative_to(workspace_root()) or path==workspace_root():
        raise PermissionError('写入仅限 Agent 工作目录。')
    if path.suffix.lower() not in ('.txt','.md','.json','.jsonl','.csv','.tsv','.html','.css','.svg'):
        raise PermissionError('当前写入支持文本、数据和静态文档文件。')
    return path

def automatic(tool,args,session):
    from core.gui.permissions import denied,tool_modes
    from core.security.read_grants import db_path,allowed
    from core.tool_contracts import builtin_registry
    from core.security.dynamic_permissions import enforcement_mode
    if denied(tool) or enforcement_mode(tool)=='deny':return False
    from core.security.autonomy import get_mode
    from core.security.permission_center import CAPABILITIES, get_mode as tool_preference
    if tool in CAPABILITIES and tool_preference(tool)=='deny':return False
    profile=get_mode(session)
    if profile=='strict':return False
    mode=next(x['mode'] for x in tool_modes(db_path().parent) if x['name']==tool)
    if mode!='auto' and profile!='autonomous':return False
    contract=builtin_registry().get(tool)
    if contract['risk']=='public_read':return True
    if contract['risk']=='path_read':
        try:
            path=Path(args[contract['resource_argument']]).resolve(strict=True)
            return profile=='autonomous' or path.is_relative_to(workspace_root()) or allowed(path,session)
        except (ValueError,OSError):return False
    if contract['risk']=='path_write':
        try:return not workspace_path(args['path']).exists() or profile=='autonomous'
        except (ValueError,PermissionError,OSError):return False
    return profile=='autonomous' and tool in ('run_terminal','run_python_code')

def select_capabilities(goal,skills,existing):
    from core.tool_contracts import builtin_registry
    from core.gui.permissions import denied
    tools=[t['name'] for t in builtin_registry().items() if t['plannable'] and not denied(t['name'])]
    selected=list(existing)
    terms={'research-evidence':('搜索','研究','资料','search','research'), 'data-quality':('csv','数据','data'),
           'project-audit':('预算','审计','对账'), 'learning-progress':('学习','成绩'),
           'community-mcp-builder':('开发mcp','构建mcp','mcp服务'), 'community-frontend-design':('网页','界面','html','css')}
    available={s['id'] for s in skills.list()}
    for key,words in terms.items():
        if key in available and key not in selected and any(w in goal.lower() for w in words):selected.append(key)
    return {'tools':tools,'skills':selected}
