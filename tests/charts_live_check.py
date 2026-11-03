"""Live synthetic chart reading and generation; never captures the desktop."""
import json
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile

from silentanator import core
from silentanator.charts import render_chart

directory = Path('.qa/charts-live').resolve()
directory.mkdir(parents=True, exist_ok=True)
given = {'title': 'Velocity versus time', 'x_label': 'Time (s)', 'y_label': 'Velocity (m/s)',
         'x_scale': 'linear', 'y_scale': 'linear', 'x_limits': [0, 4], 'y_limits': [0, 8], 'invert_y': False,
         'series': [{'label': 'Velocity', 'kind': 'line', 'x': [0, 1, 2, 3, 4], 'y': [0, 2, 4, 6, 8],
                     'basis': 'provided', 'source': 'Synthetic test data'}], 'annotations': [], 'notes': ''}
image = render_chart(given, directory / 'input').image
settings = {**core.DEFAULTS, 'codex': str(Path('vendor/codex/codex.exe').resolve())}
answer = core.solve(image, settings, question='Read velocity at t=2.5 seconds, explain the interpolation, and generate a chart with that point marked. Label image-read coordinates as estimates.', on_progress=print)
(directory / 'reading-answer.json').write_text(json.dumps(answer, indent=2), encoding='utf-8')
blocks = [block for section in answer['sections'] for block in section['blocks']]
charts = [block['chart'] for block in blocks if block['kind'] == 'chart']
assert charts, 'The solver did not provide a chart'
points = [point for chart in charts for point in chart['annotations']]
assert any(abs(point['x']-2.5) < 0.1 and abs(point['y']-5) < 0.5 for point in points), 'Incorrect chart reading'
assert any(point['basis'] == 'estimated' for point in points), 'Image readings must be identified as estimates'
with patch.object(core, 'DATA', directory / 'app-data'):
    core.append_notes(directory / 'Chart notes.docx', answer, session_id='chart-live', on_progress=print)
with ZipFile(directory / 'Chart notes.docx') as archive:
    assert any(name.startswith('word/media/') for name in archive.namelist())
function = core.solve(None, settings, question='Generate a plot of y=sin(x) for 0<=x<=2*pi, and mark the maximum point (pi/2, 1). Include a chart in the notes.', new_image_count=0, on_progress=print)
(directory / 'function-answer.json').write_text(json.dumps(function, indent=2), encoding='utf-8')
assert any(block['kind'] == 'chart' for section in function['sections'] for block in section['blocks'])
with patch.object(core, 'DATA', directory / 'app-data'):
    core.append_notes(directory / 'Function notes.docx', function, on_progress=print)
print('Live chart reading, interpolation, highlighted point, function plotting, and Word chart embedding passed.')
