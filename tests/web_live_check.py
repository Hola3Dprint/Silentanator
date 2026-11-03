"""Synthetic public-data lookup and method research through the real ChatGPT login."""
import json
from pathlib import Path
import re
from unittest.mock import patch
from zipfile import ZipFile

from silentanator import core


directory = Path('.qa/web-live').resolve()
directory.mkdir(parents=True, exist_ok=True)
settings = {**core.DEFAULTS, 'codex': str(Path('vendor/codex/codex.exe').resolve())}
progress = []
def report(message):
    progress.append(message)
    print(message, flush=True)

question = ('A 2.00 kg object is at standard gravity. The value of standard gravity is not supplied. '
            'Find its weight step by step, with an authoritative source for the missing constant. '
            'Also plot weight versus mass from 0 to 3 kg and highlight the 2 kg point.')
answer = core.solve(None, settings, question=question, new_image_count=0, on_progress=report)
(directory / 'data-answer.json').write_text(json.dumps(answer, indent=2), encoding='utf-8')
text = json.dumps(answer)
assert any('Web research completed:' in message for message in progress), 'No actual web search was observed'
assert '9.80665' in text, 'Incorrect standard gravity'
assert re.search(r'https://[^\s"\\]*(nist\.gov|bipm\.org)', text), 'No authoritative source URL'
charts = [block['chart'] for section in answer['sections'] for block in section['blocks'] if block['kind'] == 'chart']
assert charts and any(abs(point['x']-2)<.001 and abs(point['y']-19.6133)<.1
                      for chart in charts for point in chart['annotations']), 'Incorrect weight plot'
with patch.object(core, 'DATA', directory / 'app-data'):
    core.append_notes(directory / 'Research notes.docx', answer, session_id='web-check', on_progress=report)
with ZipFile(directory / 'Research notes.docx') as archive:
    assert 'https://' in archive.read('word/document.xml').decode()
    assert any(name.startswith('word/media/') for name in archive.namelist())

progress.clear()
method = core.solve(None, settings, question=(
    'Use a university source to find the bisection method and cite its source URL. Apply it to '
    'cos(x)-x=0 on [0,1], showing actual iterations until bracket width <0.01. '
    'In a separate part, a rectangle has length 5 m but its width is omitted and no identifying '
    'source is provided. Explain whether internet research can uniquely determine that width '
    'and give the appropriate area expression without inventing a numerical width.'),
    new_image_count=0, on_progress=report)
(directory / 'method-answer.json').write_text(json.dumps(method, indent=2), encoding='utf-8')
text = json.dumps(method)
assert any('Web research completed:' in message for message in progress), 'No method research was observed'
assert 'https://' in text and ('0.73' in text or '0.74' in text), 'Missing source or incorrect bisection root'
with patch.object(core, 'DATA', directory / 'app-data'):
    core.append_notes(directory / 'Method notes.docx', method, on_progress=report)
print('Live external constant lookup, cited method, generated plot, Word output, and unresolved-input checks completed.', flush=True)
