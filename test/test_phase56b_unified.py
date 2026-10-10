"""Phase 5.6b regression tests. Requires LangGraph and SQLite checkpoint package."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.security.interrupt_flow import InterruptFlow
from core.security.code_approval import fingerprint


class TestUnifiedInterrupt(unittest.TestCase):
    def test_read_interrupt_and_resume(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdf = Path(tmp) / 'report.pdf'
            pdf.write_bytes(b'%PDF-1.4\n')
            flow = InterruptFlow(Path(tmp) / 'checkpoints.sqlite3')
            try:
                request = flow.begin_read('session-A', 'read-token', 'extract_pdf', str(pdf))
                self.assertEqual(request['tool'], 'extract_pdf')
                self.assertEqual(request['arguments'], {'pdf_path': str(pdf.resolve())})
                self.assertEqual(request['digest'], fingerprint('extract_pdf', request['arguments']))
                with self.assertRaises(LookupError):
                    flow.pending('session-B', 'read-token')
                flow.finish('session-A', 'read-token', {'status': 'completed'})
                with self.assertRaises(PermissionError):
                    flow.pending('session-A', 'read-token')
            finally:
                flow.close()

    def test_dangerous_read_tool_denied(self):
        with tempfile.TemporaryDirectory() as tmp:
            flow = InterruptFlow(Path(tmp) / 'checkpoints.sqlite3')
            try:
                with self.assertRaises(PermissionError):
                    flow.begin_read('s', 't', 'run_python_file', str(Path(tmp)))
            finally:
                flow.close()

    def test_missing_file_denied(self):
        with tempfile.TemporaryDirectory() as tmp:
            flow = InterruptFlow(Path(tmp) / 'checkpoints.sqlite3')
            try:
                with self.assertRaises((OSError, ValueError)):
                    flow.begin_read('s', 't', 'extract_pdf', str(Path(tmp) / 'missing.pdf'))
            finally:
                flow.close()


if __name__ == '__main__':
    unittest.main()
