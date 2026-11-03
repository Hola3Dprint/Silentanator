import io
import json
import os
from pathlib import Path
import runpy
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from silentanator import core


ANSWER = {'sections': [{'heading': 'Weight', 'blocks': [
    {'kind': 'text', 'content': 'Standard gravity is 9.80665 metres per second squared.'},
    {'kind': 'equation', 'content': 'W=mg'},
]}]}


class WebSearchTests(unittest.TestCase):
    def request(self, web_search, events=()):
        received = {}
        class Buffer(io.BytesIO):
            def close(self):
                pass
        def process(args, **kwargs):
            received.update(args=args, **kwargs)
            received['stdin'] = Buffer()
            output = ANSWER if web_search else {'query': 'standard gravity weight'}
            Path(args[args.index('--output-last-message') + 1]).write_text(json.dumps(output), encoding='utf-8')
            if web_search:
                for event in events:
                    kwargs['stdout'].write((json.dumps(event) + '\n').encode())
            return SimpleNamespace(stdin=received['stdin'], returncode=0, poll=lambda: 0)
        progress = []
        with patch.object(core, 'find_codex', return_value='codex.exe'), \
             patch.object(core, 'require_subscription'), patch.object(core, 'hidden_process', side_effect=process), \
             patch.dict(os.environ, {'OPENAI_API_KEY': 'test-secret', 'CODEX_API_KEY': 'test-secret'}):
            core._solve_request(None, core.DEFAULTS, on_progress=progress.append,
                                question='Find standard gravity and compute weight.', new_image_count=0,
                                web_search=web_search,
                                schema_value=None if web_search else {'type': 'object'})
        return received, progress

    def test_live_search_is_enabled_without_images_or_local_execution_and_reports_real_events(self):
        received, progress = self.request(True, [
            {'type': 'item.completed', 'item': {'type': 'web_search', 'status': 'completed'}},
            {'type': 'item.completed', 'item': {'type': 'agent_message', 'text': 'Private source content'}},
        ])
        args = received['args']
        self.assertIn('web_search="live"', args)
        self.assertIn('--json', args)
        self.assertNotIn('--image', args)
        self.assertEqual(args[args.index('--sandbox') + 1], 'read-only')
        disabled = [args[index + 1] for index, item in enumerate(args) if item == '--disable']
        self.assertTrue({'shell_tool', 'multi_agent', 'apps', 'plugins', 'hooks'}.issubset(disabled))
        self.assertNotIn('OPENAI_API_KEY', received['env'])
        self.assertNotIn('CODEX_API_KEY', received['env'])
        self.assertTrue(any('1 search/browse step(s)' in message for message in progress))
        self.assertNotIn('Private source content', '\n'.join(progress))
        self.assertIn('do not add source attributions', received['stdin'].getvalue().decode())

    def test_topic_request_disables_web_search_and_does_not_claim_research(self):
        received, progress = self.request(False)
        self.assertIn('web_search="disabled"', received['args'])
        self.assertIn('--json', received['args'])
        self.assertFalse(any('Web research completed' in message for message in progress))

    def test_no_readable_references_does_not_block_web_solving(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(core, 'DATA', Path(directory) / 'data'):
            references = Path(directory) / 'References'
            references.mkdir()
            (references / 'unreadable.pdf').write_bytes(b'not a readable PDF')
            progress = []
            with patch.object(core, '_solve_request', return_value=ANSWER) as request:
                self.assertEqual(core.solve(None, core.DEFAULTS, course=references,
                                           question='Find standard gravity and compute weight.',
                                           new_image_count=0, on_progress=progress.append), ANSWER)
            request.assert_called_once()
            self.assertTrue(request.call_args.kwargs['web_search'])
            self.assertIn('unreadable.pdf', request.call_args.kwargs['base_prompt'])
            self.assertTrue(any('No readable reference excerpts' in message for message in progress))

    def test_failed_or_claimed_search_is_not_counted_as_completed_research(self):
        events = [None, [], {'type': 'item.completed', 'item': 'bad'},
                  {'type': 'item.started', 'item': {'type': 'web_search'}},
                  {'type': 'item.completed', 'item': {'type': 'web_search', 'status': 'failed'}},
                  {'type': 'item.completed', 'item': {'type': 'agent_message', 'text': 'I searched the web'}}]
        stream = io.BytesIO(b'invalid json\n' + b''.join((json.dumps(event) + '\n').encode() for event in events))
        self.assertEqual(core.completed_web_searches(stream), 0)

    def test_cancelling_web_request_terminates_the_child(self):
        cancel = threading.Event()
        cancel.set()
        process = SimpleNamespace(stdin=io.BytesIO(), poll=lambda: None)
        process.kill = lambda: setattr(process, 'killed', True)
        process.wait = lambda: None
        with patch.object(core, 'find_codex', return_value='codex.exe'), \
             patch.object(core, 'require_subscription'), patch.object(core, 'hidden_process', return_value=process):
            with self.assertRaisesRegex(RuntimeError, 'cancelled'):
                core._solve_request(None, core.DEFAULTS, cancel=cancel, question='Find data', web_search=True)
        self.assertTrue(process.killed)

    def test_diagnostic_failure_exits_with_report_without_opening_the_app(self):
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / 'report.json'
            with patch.object(sys, 'argv', ['run_app.py', '--check-install', '--report', str(report)]), \
                 patch.object(core, 'find_codex', side_effect=RuntimeError('Synthetic diagnostic failure')), \
                 patch('silentanator.runner.main') as app:
                with self.assertRaises(SystemExit) as result:
                    runpy.run_path(str(Path(__file__).resolve().parents[1] / 'run_app.py'), run_name='__main__')
                self.assertEqual(result.exception.code, 1)
                app.assert_not_called()
            self.assertFalse(json.loads(report.read_text())['ok'])


if __name__ == '__main__':
    unittest.main()
