"""Exercise the native event loop without capturing or uploading the desktop."""
import json
from pathlib import Path
from unittest.mock import patch
from silentanator import runner
from silentanator import core
from silentanator.core import DEFAULTS

qa = Path('.qa').resolve()
qa.mkdir(exist_ok=True)
settings = {**DEFAULTS, 'silent': False, 'cues': True, 'capture': 'Ctrl+Alt+F21', 'toggle': 'Ctrl+Alt+F22', 'quit': 'Ctrl+Alt+F23'}
with patch.object(runner, 'load_settings', return_value=settings), patch.object(runner, 'DATA', qa), \
     patch.object(core, 'DATA', qa), patch.object(runner, 'SingleInstance'):
    app = runner.Runner()
    errors = []
    app.root.report_callback_exception = lambda *args: errors.append(str(args))
    def after_notice():
        try:
            assert app.root.state() == 'normal', 'Activity window must remain visible'
            for control in (app.capture_button, app.new_session_button, app.course_picker):
                assert control.winfo_ismapped(), 'Session controls must remain visible'
                assert control.winfo_rooty() + control.winfo_height() <= app.root.winfo_rooty() + app.root.winfo_height(), 'Session controls must fit inside the window'
            assert not app.notice.winfo_exists(), 'Startup notice lasted more than a second'
            app.set_silent(True)
            assert app.root.state() == 'withdrawn'
            assert app.dot.state() == 'normal'
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
