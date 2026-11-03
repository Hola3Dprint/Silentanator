from pathlib import Path
import json
import queue
import tempfile
import threading
import unittest
from unittest.mock import patch
from PIL import Image

from silentanator import core, runner

ANSWER = {'sections': [{'heading': 'Result', 'blocks': [{'kind': 'equation', 'content': 'x=4'}]}]}


class RequestRetryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        for module in (core, runner):
            patcher = patch.object(module, 'DATA', self.directory / 'data')
            patcher.start()
            self.addCleanup(patcher.stop)
        self.app = runner.Runner.__new__(runner.Runner)
        self.app.settings = {**core.DEFAULTS, 'output': str(self.directory / 'Notes.docx')}
        self.app.session = core.StudySession(self.app.settings['output'])
        self.app.cancel = threading.Event()
        self.app.events = queue.Queue()

    def retry_and_assert_unchanged(self, expected):
        app = self.app
        app.session = core.StudySession(app.settings['output'])
        images, questions = list(app.session.images), list(app.session.questions)
        app.session.draft_question = 'An unsent new question'
        app.events = queue.Queue()
        with patch.object(runner, 'solve', return_value=ANSWER) as solve, patch.object(runner, 'append_notes'):
            app.work(retry=True)
        solve.assert_called_once()
        actual = solve.call_args
        self.assertEqual(actual.args[0], expected.args[0])
        for key in ('history', 'question', 'question_history', 'new_image_count', 'course', 'reference_files'):
            self.assertEqual(actual.kwargs[key], expected.kwargs[key], key)
        self.assertEqual(app.session.images, images)
        self.assertEqual(app.session.questions, questions)
        self.assertEqual(app.session.draft_question, 'An unsent new question')
        self.assertEqual(app.session.answer, ANSWER)
        self.assertFalse(any(kind == 'input_sent' for kind, _ in app.events.queue))

    def test_failed_mixed_input_retries_exact_saved_copies_after_restart(self):
        app = self.app
        app.session.add_image(Image.new('RGB', (12, 12)))
        app.session.add_question('Earlier question')
        attachment = self.directory / 'Attachment.png'
        Image.new('RGB', (12, 12), 'red').save(attachment)
        with patch.object(runner, 'solve', side_effect=RuntimeError('Temporary failure')) as solve:
            app.work(Image.new('RGB', (12, 12), 'blue'), question='Read the chart', attachments=[str(attachment)])
        expected = solve.call_args
        self.assertEqual(expected.kwargs['new_image_count'], 2)
        attachment.unlink()
        self.retry_and_assert_unchanged(expected)

    def test_batch_retry_keeps_the_original_image_group(self):
        app = self.app
        app.session.begin_batch(2, 'Solve both images')
        with patch.object(runner, 'solve', side_effect=RuntimeError('Temporary failure')) as solve:
            app.work(Image.new('RGB', (12, 12)))
            solve.assert_not_called()
            app.work(Image.new('RGB', (12, 12)))
        self.assertEqual(solve.call_args.kwargs['new_image_count'], 2)
        self.retry_and_assert_unchanged(solve.call_args)

    def test_text_only_retry_does_not_add_images_or_questions(self):
        with patch.object(runner, 'solve', side_effect=RuntimeError('Temporary failure')) as solve:
            self.app.work(question='Solve 2x=8')
        self.assertIsNone(solve.call_args.args[0])
        self.retry_and_assert_unchanged(solve.call_args)

    def test_legacy_four_image_session_recovers_last_capture(self):
        session = self.app.session
        for _ in range(4):
            session.add_image(Image.new('RGB', (12, 12)))
        state_path = session.directory / 'state.json'
        state = json.loads(state_path.read_text())
        state.pop('last_request')
        state_path.write_text(json.dumps(state), encoding='utf-8')
        restored = core.StudySession(session.output)
        request = restored.retry_input()
        self.assertEqual(request['image_path'], restored.images[-1])
        self.assertEqual(request['history'], restored.images[:-1])
        self.assertEqual(request['new_image_count'], 1)
        self.assertIsNone(request['question'])
