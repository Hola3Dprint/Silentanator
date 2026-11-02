import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from lxml import etree
from silentanator import core
from silentanator.windows import Hotkeys, parse_hotkey

ANSWER = {'sections': [{'heading': 'Quadratic formula', 'blocks': [
    {'kind': 'text', 'content': '1. Substitute the coefficients.'},
    {'kind': 'equation', 'content': r'x=\frac{-b\pm\sqrt{b^2-4ac}}{2a}'},
    {'kind': 'equation', 'content': r'\int_0^1 x^2\,dx=\frac{1}{3}'},
]}]}


class NotesTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        patcher = patch.object(core, 'DATA', Path(directory.name))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_equations_are_editable_and_append_preserves_notes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'Notes.docx'
            core.append_notes(path, ANSWER)
            core.append_notes(path, ANSWER)
            with ZipFile(path) as archive:
                root = etree.fromstring(archive.read('word/document.xml'))
                ns = {'m': 'http://schemas.openxmlformats.org/officeDocument/2006/math',
                      'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
                self.assertEqual(len(root.findall('.//m:oMath', ns)), 4)
                self.assertEqual(len(root.findall('.//m:f', ns)), 4)
                self.assertEqual(len(root.findall('.//m:rad', ns)), 2)
                self.assertEqual(len(root.findall('.//m:sSup', ns)), 4)
                self.assertIn('Notes', ''.join(root.itertext()))

    def test_failed_write_keeps_original_intact(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'Notes.docx'
            core.append_notes(path, ANSWER)
            original = path.read_bytes()
            with patch('silentanator.core.os.replace', side_effect=PermissionError('locked')):
                with self.assertRaises(PermissionError):
                    core.append_notes(path, ANSWER)
            self.assertEqual(path.read_bytes(), original)
            self.assertEqual(list(Path(directory).glob('.*.docx')), [])

    def test_pending_survives_failure_and_is_removed_on_success(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(core, 'DATA', Path(directory)):
            item = core.save_pending(ANSWER)
            output = Path(directory) / 'Notes.docx'
            with patch.object(core, 'append_notes', side_effect=PermissionError('locked')):
                with self.assertRaises(PermissionError):
                    core.retry_pending(output)
            self.assertTrue(item.exists())
            self.assertEqual(core.retry_pending(output), 1)
            self.assertFalse(item.exists())
            self.assertTrue(output.exists())

    def test_validation_rejects_empty_or_malformed_answers(self):
        for value in ({}, {'sections': []}, {'sections': [{'heading': 'h', 'blocks': [{'kind': 'bad', 'content': ''}]}]}):
            with self.assertRaises(ValueError):
                core.validate_answer(value)

    def test_hotkey_registration_conflict_releases_partial_registration(self):
        keys = Hotkeys(['Ctrl+Alt+F23'])
        try:
            with self.assertRaises(RuntimeError):
                Hotkeys(['Ctrl+Alt+F24', 'Ctrl+Alt+F23'])
            released = Hotkeys(['Ctrl+Alt+F24'])
            released.close()
        finally:
            keys.close()

    def test_parse_hotkeys(self):
        self.assertEqual(parse_hotkey('Control+0'), parse_hotkey('Ctrl+0'))
        for value in ('0', 'Ctrl+', 'Ctrl+F25', 'banana+0'):
            with self.assertRaises(ValueError):
                parse_hotkey(value)


if __name__ == '__main__':
    unittest.main()
