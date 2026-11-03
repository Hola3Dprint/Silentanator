from silentanator.runner import main

if __name__ == '__main__':
    import sys
    if '--check-install' in sys.argv:
        import json
        from pathlib import Path
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
        if '--report' in sys.argv:
            Path(sys.argv[sys.argv.index('--report') + 1]).write_text(json.dumps(value), encoding='utf-8')
    else:
        main(update_now='--update' in sys.argv)
