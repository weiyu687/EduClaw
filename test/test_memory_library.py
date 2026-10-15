import asyncio
import json
from types import SimpleNamespace
import pytest
from core.state.library import Library,extract
from core.state.conversation import Conversation
from core.state.context_memory import build,recall,MAX_CONTEXT_CHARS
from core.state.retrieval import rank

def seed(c,session,text,answer='已记录'):
    c.state.ensure_session(session)
    rid,_=c.begin(session,text)
    with c.state._connection() as db:db.execute("UPDATE chat_turns SET status='completed',answer=? WHERE id=?",(answer,rid))
    return rid

def test_rank_returns_relevant_chinese_english_not_first_insert():
    rows=[{'id':'a','text':'天气晴朗，散步很好。'}, {'id':'b','text':'项目预算是8500元，截止日期周五。'}, {'id':'c','text':'Python test commands and pytest fixtures'}]
    assert rank('项目预算是多少',rows)[0]['id']=='b'
    assert rank('pytest fixtures',rows)[0]['id']=='c'
    assert rank('unmatchedword',rows)==[]

def test_compression_and_recall_keep_old_facts_and_bound_context(tmp_path):
    c=Conversation(tmp_path/'educlaw_state.sqlite3')
    old=seed(c,'s','我的项目代号是北极星，预算8500元。')
    for i in range(35):seed(c,'s',f'第{i}次讨论普通内容', '普通说明。'*1200)
    context=build(c.state,'s',c.history('s'),'北极星预算')
    assert context['stats']['recent_chars']<=12000
    assert context['stats']['compressed_turns']>24
    assert len(context['summary'])<=3200
    assert context['recall'][0]['turn_id']==old
    assert len(c.history('s'))==36
    assert build(c.state,'s',c.history('s'),'北极星预算')['summary']==context['summary']

def test_library_mounts_ranking_duplicate_remove_and_restart(tmp_path):
    c=Conversation(tmp_path/'educlaw_state.sqlite3');c.state.ensure_session('a');c.state.ensure_session('b')
    library=Library(tmp_path)
    first=library.add('a','预算.md','北极星项目预算8500元。'.encode())
    library.add('a','其他.md','这里是关于园艺种植的讨论。'.encode())
    assert library.add('a','重命名.md','北极星项目预算8500元。'.encode())['duplicate']
    assert len(library.list('a'))==2
    assert library.search('a','北极星预算')[0]['document']==first['id']
    assert library.search('b','北极星预算')==[]
    library.mount('b',first['id'],True)
    assert Library(tmp_path).search('b','北极星预算')
    library.mount('b',first['id'],False);assert library.search('b','北极星预算')==[]
    library.remove('a',first['id']);assert library.search('a','北极星预算')==[]
    with pytest.raises(PermissionError):library.list('missing')

def test_completed_reply_uses_memory_and_real_source_identifiers(tmp_path):
    c=Conversation(tmp_path/'educlaw_state.sqlite3');old=seed(c,'s','项目口令是 ORBIT742。')
    seed(c,'other','绝密其他会话 NEVERLEAK')
    for i in range(30):seed(c,'s',f'讨论不同话题{i}')
    library=Library(tmp_path);library.add('s','项目.md','项目预算是8500元。'.encode())
    class Model:
        async def ainvoke(self,messages):
            joined=''.join(str(m.content) for m in messages)
            assert 'ORBIT742' in joined and 'NEVERLEAK' not in joined
            assert len(joined)<=MAX_CONTEXT_CHARS
            data=json.loads(messages[1].content.split('：',1)[1])
            return SimpleNamespace(content=json.dumps({'reply':'项目预算8500元。','source_ids':[data['library_sources'][0]['id']]}))
    answer=asyncio.run(c.reply('s','项目口令和项目预算是什么',Model()))
    assert '资料来源' in answer and '项目.md' in answer
    last=c.history('s')[-1]
    assert last['evidence']['results'][0]['name']=='项目.md'
    assert old in last['context_info']['recalled_ids']

@pytest.mark.parametrize('name,data',[('bad.exe',b'test'),('empty.txt',b''),('bad.txt',b'\xff'),('big.txt',b'a'*(5*1024*1024+1))], ids=['unsupported','empty','invalid-utf8','oversize'])
def test_upload_limits(name,data):
    with pytest.raises(ValueError):extract(name,data)

def test_compatibility_retrieval_shares_mounts_and_session(tmp_path):
    from core.security.read_grants import session_context,permission_database
    from core.tools.doc_retrieve.retrieve_knowledge import retrieve_knowledge
    c=Conversation(tmp_path/'educlaw_state.sqlite3');c.state.ensure_session('s')
    Library(tmp_path).add('s','note.txt',b'project ORBIT budget 8500')
    with permission_database(tmp_path/'educlaw_permissions.sqlite3'),session_context('s'):
        assert json.loads(retrieve_knowledge('ORBIT'))[0]['name']=='note.txt'

def test_pdf_docx_actual_parsers_and_short_pdf_text():
    import io
    from docx import Document
    from pypdf import PdfWriter
    from pypdf.generic import DictionaryObject,NameObject,DecodedStreamObject
    document=Document();document.add_paragraph('LIB903 project budget 8537')
    output=io.BytesIO();document.save(output)
    assert 'LIB903' in extract('project.docx',output.getvalue())
    output=io.BytesIO();writer=PdfWriter();page=writer.add_blank_page(width=600,height=800)
    font=DictionaryObject({NameObject('/Type'):NameObject('/Font'),NameObject('/Subtype'):NameObject('/Type1'),NameObject('/BaseFont'):NameObject('/Helvetica')})
    page[NameObject('/Resources')]=DictionaryObject({NameObject('/Font'):DictionaryObject({NameObject('/F1'):font})})
    stream=DecodedStreamObject();stream.set_data(b'BT /F1 12 Tf 50 750 Td (42) Tj ET')
    page[NameObject('/Contents')]=writer._add_object(stream);writer.write(output)
    assert '42' in extract('short.pdf',output.getvalue())
    output=io.BytesIO();writer=PdfWriter();writer.add_blank_page(width=600,height=800);writer.write(output)
    with pytest.raises(ValueError,match='OCR'):extract('scan.pdf',output.getvalue())
    with pytest.raises(ValueError):extract('broken.docx',b'not a zip')

def test_long_recent_reply_tail_is_recalled(tmp_path):
    c=Conversation(tmp_path/'educlaw_state.sqlite3')
    old=seed(c,'s','记录项目', 'ordinary text '*500+' tailsecret742')
    context=build(c.state,'s',c.history('s'),'tailsecret742')
    assert context['recall'][0]['turn_id']==old
    assert 'tailsecret742' in context['recall'][0]['text']
