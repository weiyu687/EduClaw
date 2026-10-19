"""Compatibility import adapter using the shared document library, not a second corpus."""
import json
from pathlib import Path

def process_doc(doc_path: str) -> str:
    from core.security.read_grants import current_session,db_path
    from core.security.global_gateway import check_and_audit
    from core.state.library import Library,MAX_FILE_BYTES
    session=current_session()
    if not session:raise PermissionError('导入资料需要当前对话；请使用 GUI 资料库或 /library add。')
    path=Path(doc_path).resolve(strict=True)
    tools={'.pdf':('extract_pdf','pdf_path'),'.docx':('extract_word','word_path')}
    tool,key=tools.get(path.suffix.lower(),('extract_text','text_path'))
    check_and_audit(tool,{key:str(path)})
    if path.stat().st_size>MAX_FILE_BYTES:raise ValueError('文件超过 5 MB。')
    return json.dumps(Library(db_path().parent).add(session,path.name,path.read_bytes()),ensure_ascii=False)
