import io
import json
from pathlib import Path
import queue
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from PIL import Image
from docx import Document
from silentanator import core, runner
from silentanator.course_context import build_references, retrieve

ANSWER = {'sections': [{'heading': 'Worked solution', 'blocks': [
    {'kind': 'text', 'content': '1. Identify the known values and governing equation.'},
    {'kind': 'equation', 'content': 'x=4'},
]}]}


class InputTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        for module in (core, runner):
            patcher = patch.object(module, 'DATA', self.directory / 'data')
            patcher.start()
            self.addCleanup(patcher.stop)

    def app_worker(self):
        app = runner.Runner.__new__(runner.Runner)
        app.settings = {**core.DEFAULTS, 'output': str(self.directory / 'Notes.docx')}
        app.session = core.StudySession(app.settings['output'])
        app.cancel = threading.Event()
        app.events = queue.Queue()
        return app

    def test_typed_request_has_no_image_argument_and_includes_worked_solution_instructions(self):
        received = {}

        class KeepBuffer(io.BytesIO):
            def close(self):
                pass

        def process(args, **kwargs):
            received['args'] = args
            received['stdin'] = KeepBuffer()
            Path(args[args.index('--output-last-message') + 1]).write_text(json.dumps(ANSWER), encoding='utf-8')
            return SimpleNamespace(stdin=received['stdin'], returncode=0, poll=lambda: 0)

        with patch.object(core, 'find_codex', return_value='codex.exe'), \
             patch.object(core, 'require_subscription'), patch.object(core, 'hidden_process', side_effect=process):
            result = core.solve(None, core.DEFAULTS, question='Solve 2x + 6 = 14.', new_image_count=0)
        self.assertEqual(result, ANSWER)
        self.assertNotIn('--image', received['args'])
        prompt = received['stdin'].getvalue().decode()
        self.assertIn('Solve 2x + 6 = 14.', prompt)
        self.assertIn('every meaningful algebraic rearrangement', prompt)
        self.assertIn('intermediate arithmetic', prompt)

    def test_batch_waits_for_all_images_and_survives_restart(self):
        app = self.app_worker()
        app.session.begin_batch(2, 'Solve both screenshots as parts A and B.')
        with patch.object(runner, 'solve', return_value=ANSWER) as solve:
            app.work(Image.new('RGB', (25, 25), 'red'))
            solve.assert_not_called()
            self.assertEqual(app.session.images, [])
            self.assertEqual(app.session.batch_target, 2)
            app.session = core.StudySession(app.settings['output'])
            self.assertEqual(len(app.session.batch_images), 1)
            app.work(Image.new('RGB', (25, 25), 'blue'))
        solve.assert_called_once()
        self.assertEqual(solve.call_args.kwargs['new_image_count'], 2)
        self.assertEqual(solve.call_args.kwargs['question'], 'Solve both screenshots as parts A and B.')
        self.assertEqual(len(solve.call_args.kwargs['history']), 1)
        self.assertEqual(len(app.session.images), 2)
        self.assertEqual(app.session.batch_target, 0)
        self.assertTrue(Path(app.settings['output']).exists())

    def test_cancelled_batch_never_enters_solver_context(self):
        app = self.app_worker()
        app.session.begin_batch(3)
        app.session.collect_batch_image(Image.new('RGB', (25, 25)))
        with self.assertRaises(ValueError):
            app.session.commit_batch()
        app.session.cancel_batch()
        restored = core.StudySession(app.settings['output'])
        self.assertEqual(restored.images, [])
        self.assertEqual(restored.batch_images, [])
        self.assertEqual(restored.batch_target, 0)

    def test_batch_keeps_typed_draft_and_attached_chart_until_complete(self):
        app = self.app_worker()
        chart = self.directory / 'Attached chart.png'
        Image.new('RGB', (20, 20), 'green').save(chart)
        app.session.begin_batch(2, 'Use the chart with both screenshots.', [str(chart)])
        with patch.object(runner, 'solve', return_value=ANSWER) as solve:
            app.work(Image.new('RGB', (20, 20), 'red'))
            solve.assert_not_called()
            app.session = core.StudySession(app.settings['output'])
            self.assertEqual(app.session.batch_attachments, [str(chart)])
            app.work(Image.new('RGB', (20, 20), 'blue'))
        solve.assert_called_once()
        self.assertEqual(solve.call_args.kwargs['new_image_count'], 3)
        self.assertEqual(solve.call_args.kwargs['question'], 'Use the chart with both screenshots.')
        self.assertEqual(len(app.session.images), 3)

    def test_typed_question_and_two_diagrams_are_sent_together(self):
        app = self.app_worker()
        attachments = []
        for number in range(2):
            path = self.directory / f'diagram-{number}.jpg'
            Image.new('RGB', (40, 30), 'white').save(path)
            attachments.append(str(path))
        with patch.object(runner, 'solve', return_value=ANSWER) as solve:
            app.work(question='Use both diagrams to calculate the load.', attachments=attachments)
        solve.assert_called_once()
        self.assertEqual(solve.call_args.kwargs['question'], 'Use both diagrams to calculate the load.')
        self.assertEqual(solve.call_args.kwargs['new_image_count'], 2)
        self.assertEqual(len(solve.call_args.kwargs['history']), 1)
        restored = core.StudySession(app.settings['output'])
        self.assertEqual(restored.questions, ['Use both diagrams to calculate the load.'])
        self.assertEqual(len(restored.images), 2)
        self.assertTrue(all(Path(path).exists() for path in attachments))

    def test_capture_includes_draft_and_attachment_as_one_current_input(self):
        app = self.app_worker()
        old_image = app.session.add_image(Image.new('RGB', (20, 20), 'black'))
        app.session.add_question('Previous problem')
        chart = self.directory / 'chart.png'
        Image.new('RGB', (20, 20), 'green').save(chart)
        with patch.object(runner, 'solve', return_value=ANSWER) as solve:
            app.work(Image.new('RGB', (20, 20), 'blue'),
                     question='Use this screenshot with the chart.', attachments=[str(chart)])
        solve.assert_called_once()
        self.assertEqual(solve.call_args.kwargs['question'], 'Use this screenshot with the chart.')
        self.assertEqual(solve.call_args.kwargs['question_history'], ['Previous problem'])
        self.assertEqual(solve.call_args.kwargs['new_image_count'], 2)
        self.assertEqual(solve.call_args.kwargs['history'][0], old_image)
        self.assertEqual(len(app.session.images), 3)
        with Image.open(solve.call_args.args[0]) as captured:
            self.assertEqual(captured.getpixel((0, 0)), (0, 0, 255))
        self.assertIn(('input_sent', None), list(app.events.queue))

    def test_failed_combined_request_does_not_clear_draft(self):
        app = self.app_worker()
        with patch.object(runner, 'solve', side_effect=RuntimeError('Please retry')):
            app.work(Image.new('RGB', (20, 20)), question='Keep this question')
        self.assertNotIn(('input_sent', None), list(app.events.queue))
        self.assertIn(('error', 'Please retry'), list(app.events.queue))

    def test_selected_files_and_folder_combine_with_real_source_labels(self):
        folder = self.directory / 'course'
        folder.mkdir()
        (folder / 'lecture.md').write_text('Bending stress equals moment times distance divided by inertia.', encoding='utf-8')
        extra = self.directory / 'Formula sheet.txt'
        extra.write_text('Cantilever displacement and tip deflection use the flexural rigidity EI.', encoding='utf-8')
        index = build_references(folder, [str(extra)], self.directory / 'cache')
        results = retrieve(index, 'cantilever deflection bending stress')
        sources = [item['source'] for item in results]
        self.assertIn('lecture.md', sources)
        self.assertTrue(any('Formula sheet.txt' in source for source in sources))
        only_files = build_references(None, [str(extra)], self.directory / 'cache')
        self.assertTrue(retrieve(only_files, 'cantilever'))

    def test_existing_word_notes_preserve_tables_pictures_headers_and_create_exact_backup(self):
        image = self.directory / 'original-picture.png'
        Image.new('RGB', (12, 12), 'green').save(image)
        path = self.directory / 'Existing full notes.docx'
        document = Document()
        document.add_heading('My existing class notes', 0)
        document.add_paragraph('Keep this original explanation and formatting.').runs[0].bold = True
        document.add_table(rows=1, cols=1).cell(0, 0).text = 'Original data table'
        document.add_picture(str(image))
        document.sections[0].header.paragraphs[0].text = 'Original header'
        document.sections[0].footer.paragraphs[0].text = 'Original footer'
        document.save(path)
        original = path.read_bytes()
        with ZipFile(io.BytesIO(original)) as archive:
            preserved = {name: archive.read(name) for name in archive.namelist()
                         if name.startswith(('word/media/', 'word/header', 'word/footer'))}
        core.append_notes(path, ANSWER, session_id='new-study-session')
        core.append_notes(path, ANSWER, session_id='new-study-session')
        updated = Document(path)
        self.assertIn('My existing class notes', '\n'.join(p.text for p in updated.paragraphs))
        self.assertEqual(updated.tables[0].cell(0, 0).text, 'Original data table')
        with ZipFile(path) as archive:
            for name, content in preserved.items():
                self.assertEqual(archive.read(name), content)
            body = archive.read('word/document.xml').decode()
            self.assertEqual(body.count('Worked solution'), 1)
        backups = list((core.DATA / 'backups').rglob('*.docx'))
        self.assertEqual(len(backups), 2)
        self.assertTrue(any(backup.read_bytes() == original for backup in backups))

    def test_setup_reflects_live_references_but_keeps_new_unapplied_choices(self):
        output = self.directory / 'Notes.docx'
        folder = self.directory / 'Course'
        folder.mkdir()
        session = core.StudySession(output, course=folder)
        self.assertFalse(session.restored)
        self.assertTrue(core.StudySession(output).restored)
        settings = {**core.DEFAULTS, 'output': str(output)}
        with patch.object(core, 'load_settings', return_value=dict(settings)):
            self.assertEqual(core.setup_settings()['reference_folder'], str(folder.resolve()))
        settings['reference_folder'] = str(self.directory)
        settings['reference_revision'] = 'new-setup-choice'
        with patch.object(core, 'load_settings', return_value=dict(settings)):
            self.assertEqual(core.setup_settings()['reference_folder'], str(self.directory))

    def test_solver_selects_iteration_automatically_without_an_option(self):
        with patch.object(core, '_solve_request', return_value=ANSWER) as request:
            core.solve(None, core.DEFAULTS,
                       question='Find the positive root of cos(x)=x.', new_image_count=0)
        prompt = request.call_args.kwargs['base_prompt']
        self.assertIn('Automatically determine for EACH', prompt)
        self.assertIn('initial guess or bracket', prompt)
        self.assertIn('one plain-text', prompt)


if __name__ == '__main__':
    unittest.main()
