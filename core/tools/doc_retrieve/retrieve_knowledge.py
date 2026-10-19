"""Read-only compatibility adapter for current-session mounted library sources."""
import json

def retrieve_knowledge(query: str, top_k: int = 5) -> str:
    from core.security.read_grants import current_session,db_path
    from core.state.library import Library
    session=current_session()
    if not session:raise PermissionError('检索资料需要当前对话。')
    return json.dumps(Library(db_path().parent).search(session,query,top_k),ensure_ascii=False)
