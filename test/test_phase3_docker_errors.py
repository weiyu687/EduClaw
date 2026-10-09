import unittest
from unittest.mock import Mock, patch
import requests

from core.tools.sandbox.docker_executor import DockerExecutor, ToolExecutionError, ToolExecutionTimeout


class DockerErrorTests(unittest.TestCase):
    def setUp(self):
        self.executor = DockerExecutor.__new__(DockerExecutor)
        self.executor.client = Mock()
        self.executor.image = "python:3.10-slim"
        self.container = Mock()
        self.container.logs.return_value = b"hello\n"
        self.executor.client.containers.run.return_value = self.container

    def test_success(self):
        self.container.wait.return_value = {"StatusCode": 0}
        self.assertEqual(self.executor.run_python_code("print('hello')"), "hello\n")
        self.container.remove.assert_called_once_with(force=True)

    def test_runtime_error(self):
        self.container.wait.return_value = {"StatusCode": 1}
        self.container.logs.return_value = b"Traceback: RuntimeError\n"
        with self.assertRaises(ToolExecutionError) as ctx:
            self.executor.run_python_code("raise RuntimeError()")
        self.assertEqual(ctx.exception.category, "runtime_error")
        self.container.remove.assert_called_once_with(force=True)

    def test_timeout(self):
        self.container.wait.side_effect = requests.exceptions.ReadTimeout("timeout")
        with self.assertRaises(ToolExecutionTimeout) as ctx:
            self.executor.run_python_code("while True: pass")
        self.assertEqual(ctx.exception.category, "timeout")
        self.container.remove.assert_called_once_with(force=True)

    def test_api_error_is_not_timeout(self):
        self.container.wait.side_effect = ValueError("bad docker response")
        with self.assertRaises(ToolExecutionError) as ctx:
            self.executor.run_python_code("print(1)")
        self.assertEqual(ctx.exception.category, "infrastructure_error")

    def test_missing_file(self):
        with self.assertRaises(ToolExecutionError) as ctx:
            self.executor.run_python_file("__missing_file_educlaw_123.py")
        self.assertEqual(ctx.exception.category, "input_error")


if __name__ == "__main__":
    unittest.main()
