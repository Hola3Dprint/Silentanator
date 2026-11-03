import unittest
from silentanator.note_format import clean_text, citations_requested, without_citations
from tests.test_charts import fixture


class NoteFormatTests(unittest.TestCase):
    def test_inline_links_and_source_only_sentence_do_not_remove_known_values(self):
        text = ('Known: m = 2.00 kg. Standard gravity is 9.80665 m/s², exact by definition. '
                'The adopted value is recorded in [NIST Appendix 1](https://example.test/appendix-1).')
        self.assertEqual(clean_text(text), 'Known: m = 2.00 kg. Standard gravity is 9.80665 m/s², exact by definition.')
        self.assertEqual(clean_text('The value is listed in [a table](https://example.test/) as 9.80665 m/s².'),
                         'The value is listed in a table as 9.80665 m/s².')

    def test_native_markers_and_reference_lines_are_removed_without_changing_math(self):
        self.assertEqual(clean_text('Weight = 19.6 N. citeturn0search0\nSource: NIST https://example.test/'), 'Weight = 19.6 N.')
        self.assertEqual(clean_text('Coordinates [1, 2]. Source: 10 V battery.'), 'Coordinates [1, 2]. Source: 10 V battery.')
        self.assertEqual(clean_text('The value is 9.80665 m/s² (https://example.test/).'), 'The value is 9.80665 m/s².')
        self.assertEqual(clean_text('Weight = 19.6 N [1](https://example.test/).'), 'Weight = 19.6 N.')
        reference_work = {'sections': [{'heading': 'References', 'blocks': [{'kind': 'equation', 'content': 'V=10'}]}]}
        self.assertEqual(without_citations(reference_work), reference_work)

    def test_default_notes_hide_references_while_equations_and_chart_metadata_survive(self):
        chart = fixture()
        chart['series'][0]['source'] = 'https://example.test/data'
        chart['notes'] = 'These readings are estimates. citeturn0search0'
        answer = {'sections': [
            {'heading': 'Solution', 'blocks': [
                {'kind': 'equation', 'content': r'x=\frac{1}{2}'},
                {'kind': 'chart', 'content': 'Estimated points. citeturn0search0', 'chart': chart}]},
            {'heading': 'References', 'blocks': [{'kind': 'text', 'content': 'https://example.test/'}]}]}
        cleaned = without_citations(answer)
        self.assertEqual(len(cleaned['sections']), 1)
        blocks = cleaned['sections'][0]['blocks']
        self.assertEqual(blocks[0]['content'], r'x=\frac{1}{2}')
        self.assertEqual(blocks[1]['content'], 'Estimated points.')
        self.assertEqual(blocks[1]['chart']['series'][0]['source'], 'https://example.test/data')
        self.assertEqual(blocks[1]['chart']['notes'], 'These readings are estimates.')
        self.assertEqual(len(answer['sections']), 2)

    def test_citations_require_a_current_explicit_request(self):
        for text in (None, 'Look up an authoritative value.', 'No citations please.', "Don't need to cite.", 'Give a citation-free answer.'):
            self.assertFalse(citations_requested(text), text)
        for text in ('Cite the method.', 'Include citations.', 'Please show sources.'):
            self.assertTrue(citations_requested(text), text)
