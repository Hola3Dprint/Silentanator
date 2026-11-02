"""Exercise the native event loop without capturing or uploading the desktop."""
import json
from pathlib import Path
from unittest.mock import patch
from silentanator import runner
from silentanator import core
from silentanator.core import DEFAULTS

qa = Path('.qa').resolve()
qa.mkdir(exist_ok=True)
settings = {**DEFAULTS, 'output': str(qa / 'Notes.docx'), 'batch_hotkeys': False,
            'silent': False, 'cues': True, 'capture': 'Ctrl+Alt+F21', 'toggle': 'Ctrl+Alt+F22', 'quit': 'Ctrl+Alt+F23'}
with patch.object(runner, 'load_settings', return_value=settings), patch.object(runner, 'DATA', qa), \
     patch.object(core, 'DATA', qa), patch.object(runner, 'SingleInstance'):
    app = runner.Runner()
    errors = []
    app.root.report_callback_exception = lambda *args: errors.append(str(args))
    def after_notice():
        try:
            assert app.root.state() == 'normal', 'Activity window must remain visible'
            for control in (app.capture_button, app.new_session_button, app.reference_entry,
                            app.solve_button, app.attach_button, app.batch_button, app.question_input):
                assert control.winfo_ismapped(), 'Session controls must remain visible'
                assert control.winfo_rooty() + control.winfo_height() <= app.root.winfo_rooty() + app.root.winfo_height(), 'Session controls must fit inside the window'
            assert not app.notice.winfo_exists(), 'Startup notice lasted more than a second'
            reference = qa / 'Pasted references'
            reference.mkdir(exist_ok=True)
            original_session = app.session.id
            app.folder_path.set('"' + str(reference) + '"')
            app.reference_entry.focus_force()
            app.root.update()
            app.reference_entry.event_generate('<Return>')
            app.root.update()
            assert app.session.course == str(reference.resolve()), 'Pasted path must apply on Enter'
            assert app.session.id != original_session, 'Changing folder must create a new session'
            restored = core.StudySession(settings['output'])
            assert restored.course == app.session.course, 'Pasted folder must survive restart'
            current_session = app.session.id
            app.folder_path.set(str(qa / 'missing-reference-folder'))
            assert not app.apply_reference_folder(), 'Invalid folder must be rejected'
            assert app.session.id == current_session, 'Invalid folder must preserve current session'
            app.folder_path.set('')
            assert app.apply_reference_folder()
            assert app.session.course is None, 'Blank box must disable folder context'
            from PIL import Image
            chart = qa / 'Test chart.png'
            Image.new('RGB', (20, 20), 'white').save(chart)
            with patch.object(runner.filedialog, 'askopenfilenames', return_value=(str(chart),)):
                app.attach_button.invoke()
            app.question_input.insert('1.0', 'Explain the attached chart step by step.')
            app.question_input.focus_force()
            app.root.update()
            with patch.object(runner.threading, 'Thread') as worker:
                app.solve_button.invoke()
                app.root.update()
                worker.assert_called_once()
                assert worker.call_args.kwargs['args'] == (None, 'Explain the attached chart step by step.', [str(chart)])
                assert app.busy
            app.busy = False
            app.state = 'ready'
            app.progress.stop()
            app.set_input_state('normal')
            app.clear_attachments()
            app.question_input.delete('1.0', 'end')
            app.batch_key_counts[4] = 2
            with patch.object(app, 'capture') as capture:
                app.keys.messages.put(4)
                app.tick()
                capture.assert_called_once()
                assert app.session.batch_target == 2, 'Count hotkey must start a two-image batch'
            with patch.object(runner, 'solve') as solve:
                app.work(Image.new('RGB', (20, 20)))
                app.tick()
                solve.assert_not_called()
                assert not app.busy
                assert str(app.solve_button.cget('state')) == 'disabled'
                app.cancel_batch_button.invoke()
                assert not app.session.batch_target
                assert not app.session.images, 'Cancelled batch must not enter session image history'
            app.set_silent(True)
            assert app.root.state() == 'withdrawn'
            assert app.dot.state() == 'normal'
            app.dot.withdraw()
            app.next_dot_refresh = 0
            app.tick()
            assert app.dot.state() == 'normal', 'The permanent indicator must restore itself if hidden'
            app.root.iconify()
            app.paint()
            app.root.update_idletasks()
            from silentanator.windows import user
            assert user.IsWindowVisible(user.GetParent(app.dot.winfo_id())), 'The permanent dot must remain visible when the owner is minimized'
            app.set_silent(True)
            app.flash('Must not appear in silent mode')
            assert not app.notice.winfo_exists()
            app.cues = False
            app.busy = True
            app.events.put(('progress', 'Waiting for the solution'))
            app.tick()
            assert app.busy, 'Progress must not unlock capture during a request'
            app.state = 'working'
            app.paint()
            assert app.dot.state() == 'normal'
            assert app.canvas.itemcget(app.circle, 'fill') == '#e4ae3d'
            from PIL import Image
            with patch('PIL.ImageGrab.grab', return_value=Image.new('RGB', (20, 20))), \
                 patch.object(runner.threading, 'Thread'):
                app.take_image((0, 0, 20, 20))
            assert app.root.state() == 'withdrawn', 'Capture completion must not show activity'
            assert app.dot.state() == 'normal', 'Dot must stay visible during capture'
            assert 'Waiting for the solution' in app.log.get('1.0', 'end')
            answer = {'sections': [{'heading': 'Solution', 'blocks': [{'kind': 'equation', 'content': 'x=4'}]}]}
            app.events.put(('answer', answer))
            app.events.put(('ready', 'Notes saved'))
            with patch.object(runner.os, 'startfile') as launch, patch.object(Path, 'exists', return_value=True):
                app.tick()
                launch.assert_called_once_with(Path(settings['output']))
            assert not app.busy
            assert 'x=4' in app.answer_view.get('1.0', 'end')
            app.events.put(('error', 'Word document is locked'))
            with patch.object(runner.os, 'startfile') as launch:
                app.tick()
                launch.assert_not_called()
            assert 'Word document is locked' in app.stage.get()
            assert app.root.state() == 'withdrawn'
            assert app.dot.state() == 'normal'
            assert app.canvas.itemcget(app.circle, 'fill') == '#e15759'
            app.set_silent(False)
            assert app.root.state() == 'normal'
            previous_session = app.session.id
            app.new_session()
            assert app.session.id != previous_session
            assert app.session.images == []
        finally:
            app.close()
    app.root.after(1100, after_notice)
    app.run()
    assert not errors, errors
    assert json.loads((qa / 'status.json').read_text())['state'] == 'stopped'
    print('Silent mode stays hidden; dot remains visible in working/error states; activity toggle, Word launch, and shutdown passed.')
