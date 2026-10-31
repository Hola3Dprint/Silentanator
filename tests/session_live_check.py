"""Synthetic two-image session; no desktop capture or real notes are used."""
from pathlib import Path
from unittest.mock import patch
from PIL import Image, ImageDraw, ImageFont
from silentanator import core

directory = Path('.qa/session-live').resolve()
directory.mkdir(parents=True, exist_ok=True)
font = ImageFont.truetype('C:/Windows/Fonts/arial.ttf', 36)
output = directory / 'Notes.docx'
with patch.object(core, 'DATA', directory):
    session = core.StudySession(output, fresh=True)
    for problem in ['Solve for x: 2x + 6 = 14', 'Using x from the previous image, find y = x^2 + 1.']:
        image = Image.new('RGB', (1400, 200), 'white')
        ImageDraw.Draw(image).text((30, 60), problem, font=font, fill='black')
        path = session.add_image(image)
        answer = core.solve(path, core.DEFAULTS, on_progress=print,
                            history=session.images[:-1], previous_answer=session.answer)
        session.remember(answer)
        core.append_notes(output, answer, session_id=session.id)
    from zipfile import ZipFile
    from lxml import etree
    with ZipFile(output) as archive:
        root = etree.fromstring(archive.read('word/document.xml'))
    text = ''.join(root.itertext())
    assert '17' in text, 'Second image did not use the previous x value'
    assert len(root.findall('.//{http://schemas.openxmlformats.org/wordprocessingml/2006/main}sdt')) == 1
    restored = core.StudySession(output)
    assert len(restored.images) == 2 and restored.answer == answer
    print('Two-image context, cumulative document update, and restart recovery passed.')
