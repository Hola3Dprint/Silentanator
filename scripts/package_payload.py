"""Create a complete payload without user settings or credentials."""
from pathlib import Path
import hashlib
import json
import sys
import zipfile

source, output, manifest = map(lambda value: Path(value).resolve(), sys.argv[1:])
required = ['Silentanator.exe', 'SilentanatorSetup.exe', 'vendor/codex/codex.exe']
for name in required:
    if not (source / name).is_file():
        raise SystemExit('Missing application component: ' + name)
files = sorted(path for path in source.rglob('*') if path.is_file())
for path in files:
    if path.name.lower() in ('auth.json', 'settings.json', 'state.json', 'capture.png'):
        raise SystemExit('Refusing to package user data: ' + str(path))
output.parent.mkdir(parents=True, exist_ok=True)
with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
    for path in files:
        archive.write(path, path.relative_to(source).as_posix())
digest = hashlib.file_digest(output.open('rb'), 'sha256').hexdigest()
manifest.write_text(json.dumps({'Sha256': digest, 'Files': len(files)}), encoding='utf-8')
print(f'Packaged {len(files)} application files; SHA256 {digest}')
