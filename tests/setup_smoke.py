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
         patch.object(setup, 'save_settings') as save:
        app = setup.Setup()
        try:
            app.root.update()
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
print('Setup references, existing Word selection, and unchanged-reference preservation passed.')
