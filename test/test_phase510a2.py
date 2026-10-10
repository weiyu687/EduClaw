import sqlite3
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from core.security.safe_delete import SafeDelete
from core.security.task_catalog import TaskCatalog
from core.security.autonomous_agent import AutonomousStore


@contextmanager
def closed_sqlite(path):
    """Commit/rollback and always release Windows SQLite file handles."""
    db = sqlite3.connect(path)
    try:
        with db:
            yield db
    finally:
        db.close()


class SafeDeleteTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.state=Path(self.tmp.name)/'state.db'
        self.task_db=Path(self.tmp.name)/'task.db'
        with closed_sqlite(self.state) as db:
            db.execute('CREATE TABLE sessions (id TEXT PRIMARY KEY, user_id TEXT, title TEXT, updated_at TEXT)')
            db.executemany('INSERT INTO sessions VALUES (?,?,?,?)', [('s1',None,'科研实验','2026-01-01'),('s2',None,'其他','2026-01-02')])
        self.store=AutonomousStore(self.task_db)
        self.catalog=TaskCatalog(self.state,self.task_db)
        self.delete=SafeDelete(self.state,self.task_db)

    def task(self,session='s1',status='pending'):
        tid=self.store.create(session,'calculate')
        with closed_sqlite(self.task_db) as db:
            db.execute('UPDATE autonomous_tasks SET status=? WHERE id=?',(status,tid))
        return tid

    def test_preview_no_mutation_and_one_shot(self):
        tid=self.task()
        preview=self.delete.preview_task('s1',tid)
        self.assertIn('删除影响预览',preview)
        self.assertEqual(len(self.catalog.tasks('s1')),1)
        token=self.delete.pending['token']
        self.assertEqual(self.delete.confirm(token)['kind'],'task')
        self.assertEqual(self.catalog.tasks('s1'),[])
        with self.assertRaises(LookupError): self.store.get('s1',tid)
        with self.assertRaises(PermissionError): self.delete.confirm(token)

    def test_wrong_token_consumes_preview(self):
        tid=self.task()
        self.delete.preview_task('s1',tid)
        token=self.delete.pending['token']
        with self.assertRaises(PermissionError): self.delete.confirm('wrong')
        with self.assertRaises(PermissionError): self.delete.confirm(token)
        self.assertEqual(len(self.catalog.tasks('s1')),1)

    def test_changed_task_invalidates(self):
        tid=self.task()
        self.delete.preview_task('s1',tid)
        token=self.delete.pending['token']
        self.catalog.set_task_title('s1',tid,'changed')
        with self.assertRaises(PermissionError): self.delete.confirm(token)
        self.assertEqual(len(self.catalog.tasks('s1')),1)

    def test_claimed_or_planning_refused(self):
        for status in ('claimed','planning'):
            tid=self.task(status=status)
            with self.assertRaises(PermissionError): self.delete.preview_task('s1',tid)
            with self.assertRaises(PermissionError): self.delete.preview_session('s1')
            with closed_sqlite(self.task_db) as db: db.execute("UPDATE autonomous_tasks SET status='denied' WHERE id=?",(tid,))

    def test_session_delete_hides_tasks(self):
        tid=self.task(status='pending')
        self.delete.preview_session('s1',current_session='s1')
        token=self.delete.pending['token']
        self.delete.confirm(token)
        self.assertEqual([r['id'] for r in self.catalog.sessions()],['s2'])
        self.assertEqual(self.catalog.tasks('s1'),[])
        self.assertEqual(self.store.recoverable('s1'),[])
        with self.assertRaises(LookupError): self.store.get('s1',tid)
        with closed_sqlite(self.state) as db:
            self.assertIsNotNone(db.execute("SELECT deleted_at FROM sessions WHERE id='s1'").fetchone()[0])

    def test_cancel_and_repreview(self):
        tid=self.task()
        self.delete.preview_task('s1',tid)
        self.delete.cancel()
        with self.assertRaises(PermissionError): self.delete.confirm('bad')
        self.assertEqual(len(self.catalog.tasks('s1')),1)

if __name__=='__main__': unittest.main()
