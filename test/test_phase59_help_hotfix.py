import unittest
from core.security.cli_ux import help_response, HELP, ADVANCED_HELP

class HelpRoutingTests(unittest.TestCase):
    def test_normal(self):
        self.assertEqual(help_response('/help'), HELP)
        self.assertEqual(help_response('/?'), HELP)
    def test_advanced(self):
        self.assertEqual(help_response('/help advanced'), ADVANCED_HELP)
        self.assertEqual(help_response('/help all'), ADVANCED_HELP)
    def test_invalid_args(self):
        for command in ('/help abc', '/help advanced extra', '/help  ', '/? abc'):
            if command.strip() == '/help':
                continue
            self.assertIn('无效的帮助参数', help_response(command))
    def test_other_inputs(self):
        self.assertIsNone(help_response('/helpful abc'))
        self.assertIsNone(help_response('读取 PDF'))
