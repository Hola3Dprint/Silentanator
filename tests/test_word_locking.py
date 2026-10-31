from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import Mock, patch
import pythoncom
from silentanator.core import append_notes


class WordLockTests(unittest.TestCase):
    def test_failed_word_save_preserves_document_and_never_closes_it(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'Notes.docx'
            answer = {'sections': [{'heading': 'Notes', 'blocks': [{'kind': 'text', 'content': 'Original'}]}]}
            append_notes(path, answer)
            original = path.read_bytes()
            document = SimpleNamespace(FullName=str(path), Saved=False,
                Save=Mock(side_effect=pythoncom.com_error(-2147418111, 'Word busy', None, None)), Close=Mock())
            unrelated = SimpleNamespace(FullName=str(path.with_name('Other.docx')), Saved=False, Save=Mock(), Close=Mock())
            with patch('pythoncom.GetRunningObjectTable', return_value=SimpleNamespace(EnumRunning=lambda: [])), \
                 patch('win32com.client.GetActiveObject', return_value=SimpleNamespace(Documents=[unrelated, document])):
                with self.assertRaisesRegex(RuntimeError, 'could not save and close'):
                    append_notes(path, answer)
            self.assertEqual(path.read_bytes(), original)
            document.Close.assert_not_called()
            unrelated.Close.assert_not_called()
            unrelated.Save.assert_not_called()
