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
            revision = saved['reference_revision']
            assert app.save()
            assert save.call_args.args[0]['reference_revision'] == revision, 'Unchanged references must not reset a session'
            assert output.read_bytes() == original, 'Selecting existing notes must not overwrite them'
        finally:
            app.root.destroy()
print('Setup references, existing Word selection, and unchanged-reference preservation passed.')
