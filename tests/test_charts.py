import copy
import csv
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile
from PIL import Image

from silentanator import core
from silentanator.charts import expression_tree, evaluate, render_chart, series_points, validate_chart


def fixture():
    return {'title': 'Position versus time', 'x_label': 'Time (s)', 'y_label': 'Position (m)',
            'x_scale': 'linear', 'y_scale': 'linear', 'x_limits': [], 'y_limits': [], 'invert_y': False,
            'series': [{'label': 'Computed curve', 'kind': 'function', 'expression': 'x**2',
                        'x_min': 0, 'x_max': 4, 'basis': 'computed', 'source': 'Given equation y = x^2'},
                       {'label': 'Read points', 'kind': 'scatter', 'x': [1, 2, 3], 'y': [1, 4, 9],
                        'basis': 'estimated', 'source': 'Illustrative screenshot readings'}],
            'annotations': [{'x': 2, 'y': 4, 'label': 'Requested point (2, 4)', 'basis': 'computed'}],
            'notes': 'Scatter points are approximate image readings; the curve is computed from the equation.'}


class ChartTests(unittest.TestCase):
    def test_safe_math_and_invalid_or_executable_expressions(self):
        self.assertAlmostEqual(evaluate(expression_tree('sin(pi*x)+sqrt(x)'), 4), 2)
        for expression in ["__import__('os').system('echo unsafe')", 'x.__class__', '[x for x in range(3)]',
                           'open(1)', '2**(2**1000000)', 'True', 'lambda:1']:
            if expression == '2**(2**1000000)':
                chart = fixture()
                chart['series'][0]['expression'] = expression
                with self.assertRaises(ValueError):
                    validate_chart(chart)
            else:
                with self.assertRaises(ValueError):
                    expression_tree(expression)

    def test_function_samples_real_values_and_keeps_domain_gaps(self):
        chart = fixture()
        xs, ys = series_points(chart['series'][0], 'linear')
        self.assertEqual((xs[200], ys[200]), (2, 4))
        series = {**chart['series'][0], 'expression': '1/x', 'x_min': -1, 'x_max': 1}
        xs, ys = series_points(series, 'linear')
        self.assertIsNone(ys[200])

    def test_bad_coordinates_scales_and_lengths_are_rejected(self):
        for mutation in ('length', 'nan', 'log', 'limits'):
            chart = fixture()
            if mutation == 'length':
                chart['series'][1]['y'].pop()
            elif mutation == 'nan':
                chart['series'][1]['x'][0] = float('nan')
            elif mutation == 'log':
                chart['x_scale'] = 'log'
            else:
                chart['y_limits'] = [10, 0]
            with self.assertRaises(ValueError):
                validate_chart(chart)

    def test_chart_exports_png_csv_and_reproducible_spec(self):
        with tempfile.TemporaryDirectory() as directory:
            chart = fixture()
            chart['series'][1]['source'] = '=dangerous-formula'
            asset = render_chart(chart, directory)
            with Image.open(asset.image) as image:
                self.assertGreater(image.width, 1200)
                self.assertGreater(image.height, 700)
            self.assertTrue(asset.spec.exists())
            with asset.data.open(encoding='utf-8-sig') as source:
                rows = list(csv.DictReader(source))
            self.assertIn({'series': 'Computed curve', 'x': '2.0', 'y': '4.0', 'basis': 'computed',
                           'source': 'Given equation y = x^2'}, rows)
            self.assertTrue(next(row for row in rows if row['series'] == 'Read points')['source'].startswith("'="))

    def test_word_embeds_chart_points_and_preserves_existing_content(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(core, 'DATA', Path(directory)):
            path = Path(directory) / 'Notes.docx'
            old = {'sections': [{'heading': 'Original notes', 'blocks': [{'kind': 'text', 'content': 'Keep this.'}]}]}
            core.append_notes(path, old)
            answer = {'sections': [{'heading': 'Chart solution', 'blocks': [
                {'kind': 'chart', 'content': 'Calculated curve and approximate readings.', 'chart': fixture()}]}]}
            core.append_notes(path, answer, session_id='graph-session')
            core.append_notes(path, answer, session_id='graph-session')
            with ZipFile(path) as archive:
                xml = archive.read('word/document.xml').decode()
                self.assertIn('Original notes', xml)
                self.assertEqual(xml.count('Chart solution'), 1)
                self.assertIn('Highlighted point', xml)
                self.assertIn('approximate', xml)
                self.assertEqual(xml.count('<pic:pic>'), 1)
                self.assertTrue(any(name.startswith('word/media/') for name in archive.namelist()))
            self.assertEqual(len(list((Path(directory) / 'charts').rglob('*.png'))), 1)

    def test_invalid_chart_does_not_close_word_or_change_notes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'Notes.docx'
            path.write_bytes(b'original')
            chart = fixture()
            chart['series'][0]['expression'] = 'open(x)'
            answer = {'sections': [{'heading': 'Bad chart', 'blocks': [{'kind': 'chart', 'content': '', 'chart': chart}]}]}
            with patch.object(core, 'close_saved_word_document') as close:
                with self.assertRaises(ValueError):
                    core.append_notes(path, answer)
                close.assert_not_called()
            self.assertEqual(path.read_bytes(), b'original')
