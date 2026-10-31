"""Exercise save-and-close on an isolated document in a separate Word instance."""
from pathlib import Path
from zipfile import ZipFile
import pythoncom
import win32com.client
from silentanator.core import append_notes

path = Path('.qa/WordRefresh.docx').resolve()
path.parent.mkdir(exist_ok=True)
path.unlink(missing_ok=True)
initial = {'sections': [{'heading': 'Initial', 'blocks': [{'kind': 'equation', 'content': 'x=4'}]}]}
updated = {'sections': [{'heading': 'Updated', 'blocks': [{'kind': 'equation', 'content': 'y=17'}]}]}
append_notes(path, initial, session_id='test')
pythoncom.CoInitialize()
word = win32com.client.DispatchEx('Word.Application')
word.Visible = False
word.DisplayAlerts = 0
try:
    document = word.Documents.Open(str(path))
    document.Content.InsertAfter('Manual edit to preserve')
    from unittest.mock import patch
    from types import SimpleNamespace
    # Model file registration for this real test document, with an unrelated
    # active instance. The actual save, close, file lock, and replacement are real.
    moniker = SimpleNamespace(GetDisplayName=lambda *args: str(path))
    rot = SimpleNamespace(EnumRunning=lambda: [moniker], GetObject=lambda m: document._oleobj_)
    with patch('pythoncom.GetRunningObjectTable', return_value=rot), \
         patch('win32com.client.GetActiveObject', return_value=SimpleNamespace(Documents=[])):
        append_notes(path, updated, session_id='test')
    assert word.Documents.Count == 0, 'The document was not released for refresh'
    with ZipFile(path) as archive:
        xml = archive.read('word/document.xml').decode()
    assert 'Updated' in xml and 'Manual edit to preserve' in xml
    assert 'Initial' not in xml
    print('Exact document found across Word instances; edits saved, document closed, and notes updated.')
finally:
    word.Quit(SaveChanges=0)
    pythoncom.CoUninitialize()
