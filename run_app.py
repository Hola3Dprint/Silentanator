from silentanator.runner import main

if __name__ == '__main__':
    import sys
    if '--check-install' in sys.argv:
        import json
        from pathlib import Path
        from silentanator.core import find_codex
        import PIL, docx, latex2mathml, mathml2omml, pythoncom, win32com.client
        value = {'ok': True, 'codex': find_codex(), 'runtime': 'bundled'}
        if '--report' in sys.argv:
            Path(sys.argv[sys.argv.index('--report') + 1]).write_text(json.dumps(value), encoding='utf-8')
    else:
        main()
