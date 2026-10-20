import asyncio
import base64
import json
from types import SimpleNamespace

import pytest

from core.state.conversation import Conversation


PNG = base64.b64decode(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII='
)


def image(name='sample.png', data=PNG):
    return {'name': name, 'mime': 'image/png', 'data': base64.b64encode(data).decode()}


class VisionModel:
    def __init__(self):
        self.messages = None

    async def ainvoke(self, messages):
        self.messages = messages
        current = messages[-1].content
        assert current[0] == {'type': 'text', 'text': '分析这张图片'}
        assert current[1]['type'] == 'image_url'
        assert current[1]['image_url']['url'].startswith('data:image/png;base64,')
        return SimpleNamespace(content=json.dumps({'reply': '已收到图片。', 'title': '图片分析'}))


def setup(tmp_path):
    chat = Conversation(tmp_path / 'educlaw_state.sqlite3')
    chat.state.ensure_session('a')
    chat.state.ensure_session('b')
    return chat


def test_image_reaches_model_and_history_only_exposes_metadata(tmp_path):
    chat = setup(tmp_path)
    rid, fresh = chat.begin('a', '分析这张图片', 'a' * 32, attachments=[image()])
    assert fresh
    model = VisionModel()
    asyncio.run(chat.complete('a', rid, model))
    row = chat.history('a')[0]
    assert row['answer'] == '已收到图片。'
    assert row['attachments'][0]['name'] == 'sample.png'
    assert set(row['attachments'][0]) == {'id', 'name', 'mime', 'bytes'}
    assert row['context_info']['image_attachments'] == 1
    stored = chat.attachment('a', row['attachments'][0]['id'])
    assert stored == {'mime': 'image/png', 'data': PNG}
    with pytest.raises(LookupError):
        chat.attachment('b', row['attachments'][0]['id'])


def test_image_validation_and_idempotency(tmp_path):
    chat = setup(tmp_path)
    rid, _ = chat.begin('a', '图片', 'b' * 32, attachments=[image()])
    assert chat.begin('a', '图片', rid, attachments=[image()]) == (rid, False)
    with pytest.raises(PermissionError):
        chat.begin('a', '图片', rid, attachments=[image('changed.png')])
    with pytest.raises(ValueError, match='格式'):
        chat.begin('a', '图片', attachments=[{'name': 'x.txt', 'mime': 'text/plain', 'data': 'eA=='}])
    with pytest.raises(ValueError, match='内容'):
        chat.begin('a', '图片', attachments=[image(data=b'not-png')])
    with pytest.raises(ValueError, match='最多'):
        chat.begin('a', '图片', attachments=[image(str(i) + '.png') for i in range(5)])
