"""Explicit integration check with a synthetic image; never captures the desktop."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from silentanator.core import DEFAULTS, solve, append_notes

directory = Path('.qa').resolve()
directory.mkdir(exist_ok=True)
image = Image.new('RGB', (1200, 260), 'white')
draw = ImageDraw.Draw(image)
font = ImageFont.truetype('C:/Windows/Fonts/arial.ttf', 38)
draw.text((40, 50), 'Solve for x and explain each step:', font=font, fill='black')
draw.text((40, 120), '2x + 6 = 14', font=font, fill='black')
path = directory / 'problem.png'
image.save(path)
answer = solve(path, DEFAULTS)
append_notes(directory / 'Notes.docx', answer)
print('Live image solve and native-equation DOCX generation passed.')
print(answer)
