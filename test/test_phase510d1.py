import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from core.security.tool_results import ToolResultStore, normalize_response, compact_preview, report_context


class ResultTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'results.sqlite3'
        self.store = ToolResultStore(self.path)
    def tearDown(self): self.tmp.cleanup()
    def test_mcp_content(self):
        r = SimpleNamespace(content=[SimpleNamespace(type='text',text='hello'),SimpleNamespace(type='image',data='ignored')])
        self.assertEqual(normalize_response(r),'hello')
    def test_structured_content(self):
        self.assertIn('"a": 1',normalize_response(SimpleNamespace(content=[],structuredContent={'a':1})))
    def test_store_read_restart(self):
        saved = self.store.put('s','task',0,'extract_pdf','completed','表格\n结果')
        fresh = ToolResultStore(self.path)
        self.assertEqual(fresh.get('s','task',0)['payload'],'表格\n结果')
        self.assertEqual(len(saved['digest']),64)
    def test_session_isolation(self):
        self.store.put('s','task',0,'extract_pdf','completed','private')
        with self.assertRaises(LookupError): self.store.get('other','task',0)
        self.assertEqual(self.store.list('other','task'),[])
    def test_no_overwrite(self):
        self.store.put('s','task',0,'extract_pdf','completed','first')
        with self.assertRaises(PermissionError): self.store.put('s','task',0,'extract_pdf','completed','second')
        self.assertEqual(self.store.get('s','task',0)['payload'],'first')
    def test_list_order(self):
        self.store.put('s','task',1,'extract_word','completed','b')
        self.store.put('s','task',0,'extract_pdf','completed','a')
        self.assertEqual([x['idx'] for x in self.store.list('s','task')],[0,1])
    def test_invalid_status(self):
        with self.assertRaises(ValueError): self.store.put('s','t',0,'x','waiting','data')
    def test_preview_bounded(self):
        self.assertLessEqual(len(compact_preview('x'*1000,100)),101)
    def test_context_bounded(self):
        rows=[{'idx':i,'tool':'extract_pdf','status':'completed','payload':'x'*12000,'truncated':False} for i in range(5)]
        self.assertLessEqual(len(report_context('goal',rows)),24000)
    def test_truncated(self):
        from core.security import tool_results
        original=tool_results.MAX_RAW
        try:
            tool_results.MAX_RAW=10
            self.store.put('s','task',0,'extract_pdf','completed','中文abcde')
            row=self.store.get('s','task',0)
            self.assertTrue(row['truncated'])
            self.assertLessEqual(len(row['payload'].encode('utf-8')),10)
        finally: tool_results.MAX_RAW=original

if __name__=='__main__': unittest.main()
