from pathlib import Path


def test_missing_continue_does_not_reach_agent():
    main = Path(__file__).resolve().parents[1] / 'core' / 'usr' / 'main.py'
    source = main.read_text(encoding='utf-8')
    assert "if command == '/task-continue':" in source
    assert "if len(recoverable) == 1:" in source
    assert "elif not recoverable:" in source
    assert "else:" in source
    assert "if command.startswith('/task-continue ')" in source
