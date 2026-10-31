"""Bundle dependency license texts with the installed application."""
from importlib import metadata
from pathlib import Path
import sys

destination = Path(sys.argv[1])
destination.mkdir(parents=True, exist_ok=True)
index = ['Third-party components bundled with Silentanator', '']
for distribution in metadata.distributions():
    name = distribution.metadata.get('Name', 'unknown')
    index.append(f'{name} {distribution.version}')
    for item in distribution.files or []:
        if any(word in item.name.lower() for word in ('license', 'copying', 'notice')):
            source = Path(distribution.locate_file(item))
            if source.is_file() and source.suffix.lower() not in ('.py', '.pyc', '.exe', '.dll'):
                target = destination / name / str(item).replace('../', '').replace('\\', '/')
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(source.read_bytes())
for source in (Path(sys.base_prefix) / 'LICENSE.txt',
               Path(sys.base_prefix) / 'tcl/tcl8.6/license.terms',
               Path(sys.base_prefix) / 'tcl/tk8.6/license.terms'):
    if source.is_file():
        (destination / (source.parent.name + '-' + source.name)).write_bytes(source.read_bytes())
(destination / 'INDEX.txt').write_text('\n'.join(index), encoding='utf-8')
