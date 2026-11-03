import json
from pathlib import Path
import sys


def check_install():
    from silentanator.core import find_codex
    import PIL, docx, latex2mathml, mathml2omml, pythoncom, win32com.client
    value = {'ok': True, 'codex': find_codex(), 'runtime': 'bundled'}
    if '--check-charts' in sys.argv:
        from silentanator.charts import render_chart
        directory = Path(sys.argv[sys.argv.index('--check-charts') + 1])
        chart = {'title': 'Installation chart check', 'x_label': 'x', 'y_label': 'y',
                 'x_scale': 'linear', 'y_scale': 'linear', 'x_limits': [], 'y_limits': [], 'invert_y': False,
                 'series': [{'label': 'y = x^2', 'kind': 'function', 'expression': 'x**2', 'x_min': 0,
                             'x_max': 4, 'basis': 'computed', 'source': 'Installation test equation'}],
                 'annotations': [{'x': 2, 'y': 4, 'label': '(2, 4)', 'basis': 'computed'}], 'notes': ''}
        value['chart'] = str(render_chart(chart, directory).image)
    if '--check-web' in sys.argv:
        from silentanator.core import DEFAULTS, solve
        directory = Path(sys.argv[sys.argv.index('--check-web') + 1])
        directory.mkdir(parents=True, exist_ok=True)
        progress = []
        result = solve(None, {**DEFAULTS, 'codex': value['codex']}, new_image_count=0,
                       question='Search the web for an authoritative value of standard gravity and compute the weight of a 2.00 kg mass step by step.',
                       on_progress=progress.append)
        if not any('Web research completed:' in message for message in progress):
            raise RuntimeError('The installation did not perform a verified web lookup.')
        visible = '\n'.join(section['heading'] + '\n' + '\n'.join(block['content'] for block in section['blocks'])
                            for section in result['sections'])
        if 'https://' in visible or 'http://' in visible or '\ue200cite' in visible:
            raise RuntimeError('Default notes unexpectedly included citations.')
        output = directory / 'web-check-answer.json'
        output.write_text(json.dumps(result), encoding='utf-8')
        value['web_answer'] = str(output)
        value['web_search_verified'] = True
    return value


if __name__ == '__main__':
    if '--check-install' in sys.argv:
        # Diagnostics must never activate a window, including on a failed check.
        try:
            value = check_install()
        except Exception as exc:
            value = {'ok': False, 'error': type(exc).__name__ + ': ' + str(exc)}
        if '--report' in sys.argv:
            Path(sys.argv[sys.argv.index('--report') + 1]).write_text(json.dumps(value), encoding='utf-8')
        sys.exit(0 if value['ok'] else 1)
    else:
        from silentanator.runner import main
        main(update_now='--update' in sys.argv)
