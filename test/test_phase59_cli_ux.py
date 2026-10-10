import unittest
from core.security.cli_ux import natural_control, route_shortcut, unique_task

class TestCLIUX(unittest.TestCase):
    def setUp(self):
        self.pending = [{'id':'task-a','status':'pending'}]
    def test_continue(self):
        self.assertEqual(route_shortcut('继续刚才的任务', self.pending)[0], '/task-continue task-a')
    def test_approve(self):
        self.assertEqual(route_shortcut('批准', self.pending)[0], '/approve task-a')
    def test_deny(self):
        self.assertEqual(route_shortcut('拒绝', self.pending)[0], '/deny task-a')
    def test_ambiguous(self):
        cmd, err=route_shortcut('批准', self.pending+[{'id':'task-b','status':'pending'}])
        self.assertIsNone(cmd)
        self.assertIn('多个',err)
    def test_no_pending(self):
        cmd, err=route_shortcut('批准', [{'id':'a','status':'claimed'}])
        self.assertIsNone(cmd)
        self.assertIn('没有',err)
    def test_no_unintended_approval(self):
        self.assertIsNone(natural_control('批准后读取 D:\\secret.pdf'))
        self.assertIsNone(natural_control('请批准所有任务'))
        self.assertIsNone(natural_control('继续分析 PDF'))
    def test_only_pending_for_approval(self):
        self.assertIsNone(unique_task([{'id':'a','status':'planning'}], ('pending',)))
    def test_planning_for_continue(self):
        self.assertEqual(route_shortcut('继续任务',[{'id':'a','status':'planning'}])[0],'/task-continue a')

if __name__=='__main__': unittest.main()
