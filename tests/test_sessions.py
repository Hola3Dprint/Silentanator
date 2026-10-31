from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from PIL import Image
from lxml import etree
from silentanator import core


def notes(heading, formula):
    return {'sections': [{'heading': heading, 'blocks': [{'kind': 'equation', 'content': formula}]}]}


def doc_xml(path):
    with ZipFile(path) as archive:
        return etree.fromstring(archive.read('word/document.xml'))


class SessionTests(unittest.TestCase):
    def test_update_replaces_own_session_and_preserves_other_notes(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'Notes.docx'
            core.append_notes(output, notes('Earlier notes', 'a=1'))
            core.append_notes(output, notes('First version', 'x=2'), session_id='one')
            core.append_notes(output, notes('Another session', 'y=3'), session_id='two')
            core.append_notes(output, notes('Updated version', r'x=\frac{8}{2}=4'), session_id='one')
            root = doc_xml(output)
            text = ''.join(root.itertext())
            self.assertIn('Earlier notes', text)
            self.assertIn('Another session', text)
            self.assertIn('Updated version', text)
            self.assertNotIn('First version', text)
            ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main',
                  'm': 'http://schemas.openxmlformats.org/officeDocument/2006/math'}
            self.assertEqual(len(root.findall('.//w:sdt', ns)), 2)
            self.assertEqual(len(root.findall('.//m:oMath', ns)), 3)
            self.assertEqual(len(root.findall('.//m:f', ns)), 1)

    def test_session_restores_images_answer_and_can_start_fresh(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(core, 'DATA', Path(directory)):
            output = Path(directory) / 'Notes.docx'
            first = core.StudySession(output)
            image = first.add_image(Image.new('RGB', (20, 20), 'white'))
            first.remember(notes('First', 'x=4'))
            restored = core.StudySession(output)
            self.assertEqual(restored.id, first.id)
            self.assertEqual(restored.images, [image])
            self.assertEqual(restored.answer, first.answer)
            second = restored.add_image(Image.new('RGB', (20, 20), 'black'))
            self.assertEqual(second.name, 'capture-0002.png')
            fresh = core.StudySession(output, fresh=True)
            self.assertNotEqual(fresh.id, first.id)
            self.assertEqual(fresh.images, [])
            self.assertIsNone(fresh.answer)
            self.assertTrue(image.exists())

    def test_recovery_uses_latest_session_snapshot_without_duplicates(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(core, 'DATA', Path(directory)):
            output = Path(directory) / 'Notes.docx'
            session = core.StudySession(output)
            first = notes('Old snapshot', 'x=2')
            updated = notes('Latest snapshot', 'x=4')
            session.remember(first)
            core.save_pending(first, session.id)
            session.remember(updated)
            core.save_pending(updated, session.id)
            self.assertEqual(core.retry_pending(output), 1)
            text = ''.join(doc_xml(output).itertext())
            self.assertIn('Latest snapshot', text)
            self.assertNotIn('Old snapshot', text)
            self.assertEqual(list((Path(directory) / 'pending').glob('*.json')), [])


if __name__ == '__main__':
    unittest.main()
