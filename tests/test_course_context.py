import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from silentanator import core
from silentanator.course_context import build_index, reference_folder, retrieve, reference_prompt


class CourseTests(unittest.TestCase):
    def test_refresh_removes_deleted_sources_and_updates_changed_content(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            course = root / 'Mechanics'
            course.mkdir()
            source = course / 'Lecture.md'
            source.write_text('Beam bending stress and second moment of area.', encoding='utf-8')
            index = build_index(course, root / 'cache')
            self.assertTrue(retrieve(index, 'beam bending stress'))
            source.write_text('Ideal gas law pressure volume temperature.', encoding='utf-8')
            index = build_index(course, root / 'cache')
            self.assertFalse(retrieve(index, 'bending'))
            self.assertTrue(retrieve(index, 'pressure temperature'))
            source.unlink()
            self.assertEqual(build_index(course, root / 'cache')['files'], {})

    def test_selection_isolates_courses_and_ignores_generated_workspaces(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ('Aero', 'Mech Comp', 'Workspaces'):
                (root / name).mkdir()
                (root / name / 'notes.md').write_text(name + ' characteristic unique content', encoding='utf-8')
            index = build_index(root / 'Aero', root / 'cache')
            self.assertEqual(index['course'], 'Aero')
            self.assertNotIn('Mech Comp', json.dumps(index))
            self.assertEqual(len(index['files']), 1)
            combined = build_index(root, root / 'cache')
            self.assertEqual(len(combined['files']), 2)
            self.assertNotIn('Workspaces/notes.md', combined['files'])

    def test_pasted_folder_quotes_spaces_blank_and_invalid_path(self):
        with tempfile.TemporaryDirectory(prefix='references with spaces ') as directory:
            self.assertEqual(reference_folder('  "' + directory + '"  '), str(Path(directory).resolve()))
            self.assertIsNone(reference_folder('  '))
            with self.assertRaises(ValueError):
                reference_folder(str(Path(directory) / 'missing'))

    def test_source_citations_and_unreadable_file_warning(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            course = root / 'Course'
            course.mkdir()
            (course / 'broken.pdf').write_bytes(b'not a PDF')
            (course / 'lecture.md').write_text('Use nodal analysis and Kirchhoff current law.', encoding='utf-8')
            index = build_index(course, root / 'cache')
            excerpts = retrieve(index, 'nodal Kirchhoff circuit')
            prompt = reference_prompt(index, excerpts)
            self.assertIn('lecture.md', prompt)
            self.assertIn('broken.pdf', prompt)
            self.assertIn('UNTRUSTED', prompt)
            self.assertEqual(excerpts[0]['location'], 'text')

    def test_session_course_survives_restart_and_fresh_session(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(core, 'DATA', Path(directory)):
            course = Path(directory) / 'Aero'
            session = core.StudySession(Path(directory) / 'notes.docx', course=course)
            restored = core.StudySession(session.output)
            self.assertEqual(restored.course, str(course.resolve()))
            fresh = core.StudySession(session.output, fresh=True, course=Path(directory) / 'Mech Comp')
            self.assertNotEqual(fresh.id, session.id)
            self.assertNotEqual(fresh.course, session.course)

    def test_solver_searches_course_then_supplies_cited_excerpts(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(core, 'DATA', Path(directory)):
            course = Path(directory) / 'Aero'
            course.mkdir()
            (course / 'Lecture 3.md').write_text('Lift equals dynamic pressure times wing area times lift coefficient.', encoding='utf-8')
            answer = {'sections': [{'heading': 'Lift', 'blocks': [{'kind': 'text', 'content': 'Answer'}]}]}
            with patch.object(core, '_solve_request', side_effect=[{'query': 'lift coefficient wing area'}, answer]) as request:
                self.assertEqual(core.solve(Path('problem.png'), core.DEFAULTS, course=course), answer)
            self.assertEqual(request.call_count, 2)
            final = request.call_args.kwargs['base_prompt']
            self.assertIn('Lecture 3.md', final)
            self.assertIn('dynamic pressure', final)
            self.assertIn('Do not use tools', final)


if __name__ == '__main__':
    unittest.main()
