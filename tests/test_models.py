import io
import json
import unittest
from unittest.mock import patch

from silentanator.models import image_models, list_codex_models


class FakeServer:
    def __init__(self, replies):
        self.stdin = io.StringIO()
        self.stdout = io.StringIO(''.join(json.dumps(item) + '\n' for item in replies))
        self.sent = ''
    def wait(self, timeout=None):
        if not self.stdin.closed:
            self.sent = self.stdin.getvalue()
        return 0


class ModelTests(unittest.TestCase):
    def test_catalog_filters_hidden_text_only_and_duplicates(self):
        entries = [
            {'model': 'visible', 'displayName': 'Visible', 'inputModalities': ['text', 'image'], 'isDefault': True},
            {'model': 'hidden', 'hidden': True},
            {'model': 'text-only', 'inputModalities': ['text']},
            {'id': 'legacy'}, {'model': 'visible'},
        ]
        self.assertEqual(image_models(entries), [
            {'model': 'visible', 'name': 'Visible', 'default': True},
            {'model': 'legacy', 'name': 'legacy', 'default': False},
        ])

    def test_rpc_handshake_and_pagination(self):
        server = FakeServer([
            {'id': 0, 'result': {}},
            {'method': 'account/updated', 'params': {}},
            {'id': 1, 'result': {'data': [{'model': 'first'}], 'nextCursor': 'page2'}},
            {'id': 2, 'result': {'data': [{'model': 'second'}], 'nextCursor': None}},
        ])
        # Keep sent messages for assertions even when the real client closes stdin.
        class Input(io.StringIO):
            def close(inner):
                server.sent = inner.getvalue()
                super().close()
        server.stdin = Input()
        with patch('silentanator.models.find_codex', return_value='codex.exe'), \
             patch('silentanator.models.require_subscription'), \
             patch('silentanator.models.hidden_process', return_value=server) as spawn:
            self.assertEqual([item['model'] for item in list_codex_models()], ['first', 'second'])
        sent = [json.loads(line) for line in server.sent.splitlines()]
        self.assertEqual([item['method'] for item in sent], ['initialize', 'initialized', 'model/list', 'model/list'])
        self.assertEqual(sent[-1]['params']['cursor'], 'page2')
        self.assertNotIn('OPENAI_API_KEY', spawn.call_args.kwargs['env'])
        self.assertTrue(server.stdin.closed and server.stdout.closed)

    def test_rpc_failure_keeps_no_process_or_threads_open(self):
        server = FakeServer([{'id': 0, 'result': {}}, {'id': 1, 'error': {'message': 'Sign-in required'}}])
        with patch('silentanator.models.find_codex', return_value='codex.exe'), \
             patch('silentanator.models.require_subscription'), \
             patch('silentanator.models.hidden_process', return_value=server):
            with self.assertRaisesRegex(RuntimeError, 'Sign-in required'):
                list_codex_models()
        self.assertTrue(server.stdin.closed and server.stdout.closed)
