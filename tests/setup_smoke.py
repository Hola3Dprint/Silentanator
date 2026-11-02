"""Native Setup controls without changing personal settings or opening file dialogs."""
from pathlib import Path
import tempfile
from unittest.mock import patch
from docx import Document
from silentanator import setup, core

with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    folder = root / 'Reference folder'
    folder.mkdir()
    selected = root / 'Formula sheet.txt'
    selected.write_text('Reference material.', encoding='utf-8')
    output = root / 'Existing notes.docx'
    document = Document()
    document.add_paragraph('Keep my original notes.')
    document.save(output)
    original = output.read_bytes()
    settings = {**core.DEFAULTS, 'output': str(output)}
    with patch.object(setup, 'setup_settings', return_value=settings), \
         patch.object(setup, 'DATA', root / 'app-data'), \
         patch.object(setup, 'find_codex', return_value='codex.exe'), \
         patch.object(setup, 'list_codex_models', return_value=[{'model': 'test-model', 'name': 'Test model', 'default': True}]), \
         patch.object(setup, 'save_settings') as save:
        app = setup.Setup()
        try:
            app.root.update()
            import time
            deadline = time.monotonic() + 2
            while not app.model_catalog and time.monotonic() < deadline:
                app.root.update()
                time.sleep(0.01)
            assert 'Codex default' in app.model_labels
            choice = next(label for label, value in app.model_labels.items() if value == 'test-model')
            app.model_choice.set(choice)
            app.select_model()
            assert app.vars['model'].get() == 'test-model'
            assert str(app.model_combo.cget('state')) == 'readonly'
            with patch.object(setup, 'list_codex_models', side_effect=RuntimeError('Offline')):
                app.refresh_models()
                deadline = time.monotonic() + 2
                while 'Could not load models' not in app.status.get() and time.monotonic() < deadline:
                    app.root.update()
                    time.sleep(0.01)
            assert 'Offline' in app.status.get()
            assert app.vars['model'].get() == 'test-model', 'Failed refresh must preserve the selected model'
            from types import SimpleNamespace
            from silentanator.windows import hotkey_recording_active
            previous = app.vars['capture'].get()
            app.record_hotkey('capture', 'Capture hotkey')
            assert hotkey_recording_active()
            app.recorder.keypress(SimpleNamespace(keycode=ord('K'), state=4 | 1))
            assert app.recorder.closed and not hotkey_recording_active()
            assert app.vars['capture'].get() == 'Ctrl+Shift+K'
            app.record_hotkey('capture', 'Capture hotkey')
            app.recorder.keypress(SimpleNamespace(keycode=0x1B, state=0))
            assert app.vars['capture'].get() == 'Ctrl+Shift+K'
            app.record_hotkey('capture', 'Capture hotkey')
            app.recorder.keypress(SimpleNamespace(keycode=ord('2'), state=4))
            assert not app.recorder.closed, 'Reserved batch shortcut must not be accepted'
            app.recorder.close()
            app.vars['capture'].set(previous)
            app.vars['reference_folder'].set('"' + str(folder) + '"')
            with patch.object(setup.filedialog, 'askopenfilenames', return_value=(str(selected),)):
                app.add_reference_files()
            with patch.object(setup.filedialog, 'askopenfilename', return_value=str(output)):
                app.existing_notes()
            assert app.save()
            saved = save.call_args.args[0]
            assert saved['reference_folder'] == str(folder.resolve())
            assert saved['reference_files'] == [str(selected.resolve())]
            assert saved['output'] == str(output.resolve())
            assert saved['reference_revision']
            assert saved['text'] == 'Ctrl+Alt+T'
            app.vars['text'].set(saved['capture'])
            try:
                app.values()
                raise AssertionError('Duplicate text-box hotkey must be rejected')
            except ValueError as exc:
                assert 'four distinct' in str(exc)
            app.vars['text'].set('Ctrl+2')
            try:
                app.values()
                raise AssertionError('Text-box hotkey must respect batch-key reservation')
            except ValueError as exc:
                assert 'reserved' in str(exc)
            app.vars['text'].set('Ctrl+Alt+T')
            revision = saved['reference_revision']
            assert app.save()
            assert save.call_args.args[0]['reference_revision'] == revision, 'Unchanged references must not reset a session'
            assert output.read_bytes() == original, 'Selecting existing notes must not overwrite them'
            app.vars['model'].set('my-unsaved-model-choice')
            app.request_update()
            restored = setup.Setup()
            try:
                assert restored.vars['model'].get() == 'my-unsaved-model-choice'
                assert setup.reference_folder(restored.vars['reference_folder'].get()) == str(folder.resolve())
            finally:
                restored.close()
        finally:
            app.close()
print('Model dropdown, shortcut recording/cancel/conflict checks, Setup references, and draft preservation passed.')
