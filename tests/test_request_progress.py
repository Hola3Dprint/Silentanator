import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from silentanator import core
from silentanator.request_progress import RequestProgress

ANSWER = {'sections': [{'heading': 'Result', 'blocks': [{'kind': 'equation', 'content': 'x=4'}]}]}


class RequestProgressTests(unittest.TestCase):
    def test_request_can_run_for_an_hour_without_an_automatic_deadline(self):
        clock = [0]
        class Buffer(io.BytesIO):
            def close(self):
                pass
        process = SimpleNamespace(stdin=Buffer(), returncode=None, killed=False)
        def poll():
            if clock[0] >= 3600:
                process.returncode = 0
            return process.returncode
        process.poll = poll
        process.kill = lambda: setattr(process, 'killed', True)
        process.wait = lambda: None
        def spawn(args, **kwargs):
            Path(args[args.index('--output-last-message') + 1]).write_text(json.dumps(ANSWER), encoding='utf-8')
            kwargs['stdout'].write(b'{"type":"turn.started"}\n')
            return process
        progress = []
        with patch.object(core, 'find_codex', return_value='codex.exe'), patch.object(core, 'require_subscription'), \
             patch.object(core, 'hidden_process', side_effect=spawn), \
             patch('time.monotonic', side_effect=lambda: clock[0]), \
             patch('time.sleep', side_effect=lambda _: clock.__setitem__(0, clock[0] + 600)):
            self.assertEqual(core._solve_request(None, core.DEFAULTS, question='Find x.', on_progress=progress.append), ANSWER)
        self.assertEqual(clock[0], 3600)
        self.assertFalse(process.killed)
        self.assertTrue(any('no automatic time limit' in item for item in progress))

    def test_live_events_support_partial_lines_and_do_not_expose_private_content(self):
        progress = []
        monitor = RequestProgress(progress.append)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'events.jsonl'
            with path.open('wb') as output, path.open('rb') as reader:
                output.write(b'{"type":"turn.started"}\n{"type":"item.started","item":')
                output.flush()
                position = output.tell()
                monitor.drain(reader)
                self.assertEqual(output.tell(), position)
                self.assertIn('accepted', monitor.phase)
                output.write(b'{"id":"web1","type":"web_search","query":"PRIVATE QUERY"}}\n')
                output.flush()
                monitor.drain(reader)
                self.assertIn('web sources', monitor.phase)
                event = {'type': 'item.completed', 'item': {'id': 'web1', 'type': 'web_search', 'status': 'completed'}}
                line = (json.dumps(event) + '\n').encode()
                output.write(line + line + b'{"type":"item.completed","item":{"type":"agent_message","text":"PRIVATE ANSWER"}}')
                output.flush()
                monitor.drain(reader, final=True)
        self.assertEqual(monitor.web_steps, 1)
        self.assertNotIn('PRIVATE', '\n'.join(progress))
        self.assertIn('response activity', monitor.phase)

    def test_reported_provider_error_is_classified_without_logging_raw_text(self):
        progress = []
        monitor = RequestProgress(progress.append)
        monitor.consume(json.dumps({'type': 'turn.failed', 'error': {'message': 'rate limit for PRIVATE USER'}}).encode())
        self.assertIn('usage or rate limit', monitor.last_error)
        self.assertNotIn('PRIVATE', '\n'.join(progress) + monitor.last_error)
