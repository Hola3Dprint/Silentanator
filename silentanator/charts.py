"""Validated chart specifications and local plotting; model output is never executed."""
import ast
import csv
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import textwrap


def object_schema(properties):
    return {'type': 'object', 'additionalProperties': False,
            'properties': properties, 'required': list(properties)}


TEXT = {'type': 'string'}
NUMBERS = {'type': 'array', 'items': {'type': 'number'}}
BASIS = {'type': 'string', 'enum': ['provided', 'computed', 'estimated']}
SERIES_SCHEMA = {'anyOf': [
    object_schema({'label': TEXT, 'kind': {'type': 'string', 'enum': ['line', 'scatter', 'bar']},
                   'x': NUMBERS, 'y': NUMBERS, 'basis': BASIS, 'source': TEXT}),
    object_schema({'label': TEXT, 'kind': {'type': 'string', 'enum': ['function']},
                   'expression': TEXT, 'x_min': {'type': 'number'}, 'x_max': {'type': 'number'},
                   'basis': {'type': 'string', 'enum': ['computed']}, 'source': TEXT}),
]}
CHART_SCHEMA = object_schema({
    'title': TEXT, 'x_label': TEXT, 'y_label': TEXT,
    'x_scale': {'type': 'string', 'enum': ['linear', 'log']},
    'y_scale': {'type': 'string', 'enum': ['linear', 'log']},
    'x_limits': NUMBERS, 'y_limits': NUMBERS, 'invert_y': {'type': 'boolean'},
    'series': {'type': 'array', 'items': SERIES_SCHEMA},
    'annotations': {'type': 'array', 'items': object_schema({
        'x': {'type': 'number'}, 'y': {'type': 'number'}, 'label': TEXT, 'basis': BASIS})},
    'notes': TEXT,
})

FUNCTIONS = {name: getattr(math, name) for name in (
    'sin', 'cos', 'tan', 'asin', 'acos', 'atan', 'sinh', 'cosh', 'tanh',
    'exp', 'log', 'log10', 'sqrt')}
FUNCTIONS['abs'] = abs
CONSTANTS = {'pi': math.pi, 'e': math.e}


def number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError('Chart coordinates must be finite numbers.')
    return float(value)


def expression_tree(expression):
    if not isinstance(expression, str) or not expression or len(expression) > 300:
        raise ValueError('Use a short mathematical expression in x for the chart.')
    try:
        tree = ast.parse(expression, mode='eval')
    except (SyntaxError, RecursionError) as exc:
        raise ValueError('The chart function is not a supported mathematical expression.') from exc
    nodes = list(ast.walk(tree))
    if len(nodes) > 80:
        raise ValueError('The chart function is too complex.')
    allowed = (ast.Expression, ast.BinOp, ast.UnaryOp, ast.Add, ast.Sub, ast.Mult,
               ast.Div, ast.Pow, ast.UAdd, ast.USub, ast.Constant, ast.Name, ast.Load, ast.Call)
    for node in nodes:
        if not isinstance(node, allowed):
            raise ValueError('Only arithmetic and approved math functions are allowed in charts.')
        if isinstance(node, ast.Constant):
            number(node.value)
        if isinstance(node, ast.Name) and node.id not in {'x', *CONSTANTS, *FUNCTIONS}:
            raise ValueError('Unknown name in chart expression: ' + node.id)
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id not in FUNCTIONS or node.keywords or len(node.args) != 1:
                raise ValueError('Chart functions must be approved one-argument math functions.')
    return tree.body


def evaluate(node, x):
    if isinstance(node, ast.Constant):
        return float(node.value)
    if isinstance(node, ast.Name):
        return x if node.id == 'x' else CONSTANTS[node.id]
    if isinstance(node, ast.Call):
        return FUNCTIONS[node.func.id](evaluate(node.args[0], x))
    if isinstance(node, ast.UnaryOp):
        value = evaluate(node.operand, x)
        return -value if isinstance(node.op, ast.USub) else value
    left, right = evaluate(node.left, x), evaluate(node.right, x)
    if isinstance(node.op, ast.Add):
        return left + right
    if isinstance(node.op, ast.Sub):
        return left - right
    if isinstance(node.op, ast.Mult):
        return left * right
    if isinstance(node.op, ast.Div):
        return left / right
    return left ** right


def series_points(series, x_scale):
    if series['kind'] != 'function':
        return list(series['x']), list(series['y'])
    tree = expression_tree(series['expression'])
    start, end = number(series['x_min']), number(series['x_max'])
    xs, ys = [], []
    for index in range(401):
        ratio = index / 400
        x = math.exp(math.log(start) + ratio * (math.log(end) - math.log(start))) if x_scale == 'log' else start + ratio * (end - start)
        try:
            y = number(evaluate(tree, x))
        except (ValueError, ZeroDivisionError, OverflowError, TypeError, KeyError):
            y = None
        xs.append(x)
        ys.append(y)
    if sum(value is not None for value in ys) < 2:
        raise ValueError('The chart function has no usable values over the specified range.')
    return xs, ys


def validate_chart(chart):
    if not isinstance(chart, dict):
        raise ValueError('A chart specification is missing.')
    for key in ('title', 'x_label', 'y_label', 'notes'):
        if not isinstance(chart.get(key), str) or len(chart[key]) > (3000 if key == 'notes' else 180):
            raise ValueError('Chart title, axes, and notes must be readable text.')
    if not chart['x_label'].strip() or not chart['y_label'].strip():
        raise ValueError('Both chart axes need labels and units when applicable.')
    for axis in ('x', 'y'):
        if chart.get(axis + '_scale') not in ('linear', 'log'):
            raise ValueError('Chart axes must use linear or log scales.')
        limits = chart.get(axis + '_limits')
        if not isinstance(limits, list) or len(limits) not in (0, 2):
            raise ValueError('Chart limits must be empty or contain a minimum and maximum.')
        if limits and (number(limits[0]) >= number(limits[1]) or (chart[axis + '_scale'] == 'log' and limits[0] <= 0)):
            raise ValueError('Chart limits must be increasing and positive for log scales.')
    if not isinstance(chart.get('invert_y'), bool):
        raise ValueError('Chart axis direction must be specified.')
    if not isinstance(chart.get('series'), list) or not 1 <= len(chart['series']) <= 6:
        raise ValueError('A chart needs one to six data series.')
    for series in chart['series']:
        if not isinstance(series, dict) or series.get('kind') not in ('line', 'scatter', 'bar', 'function'):
            raise ValueError('Unsupported chart series type.')
        if not isinstance(series.get('label'), str) or not isinstance(series.get('source'), str):
            raise ValueError('Each chart series needs a label and source.')
        if len(series['label']) > 140 or len(series['source']) > 1000:
            raise ValueError('Chart labels and sources are too long.')
        if series.get('basis') not in ('provided', 'computed', 'estimated'):
            raise ValueError('Chart data must identify whether values are provided, computed, or estimated.')
        if series['kind'] == 'function':
            if not all(key in series for key in ('expression', 'x_min', 'x_max')):
                raise ValueError('Chart functions need an expression and range.')
            if series['basis'] != 'computed' or number(series['x_min']) >= number(series['x_max']):
                raise ValueError('Chart functions need an increasing range and computed provenance.')
            if chart['x_scale'] == 'log' and series['x_min'] <= 0:
                raise ValueError('A logarithmic x axis requires a positive function range.')
        else:
            if not all(isinstance(series.get(key), list) for key in ('x', 'y')) or not 1 <= len(series['x']) <= 3000 or len(series['x']) != len(series['y']):
                raise ValueError('Chart x and y coordinates must have equal, nonzero lengths (maximum 3000).')
            for coordinate in series['x'] + series['y']:
                number(coordinate)
            if series['kind'] == 'bar':
                if chart['x_scale'] == 'log' or len(set(series['x'])) != len(series['x']):
                    raise ValueError('Bar charts need distinct x positions on a linear x axis.')
        xs, ys = series_points(series, chart['x_scale'])
        for values, axis in ((xs, 'x'), (ys, 'y')):
            if chart[axis + '_scale'] == 'log' and any(value is not None and value <= 0 for value in values):
                raise ValueError('Non-positive data cannot be plotted on a logarithmic ' + axis + ' axis.')
    annotations = chart.get('annotations')
    if not isinstance(annotations, list) or len(annotations) > 20:
        raise ValueError('A chart can highlight up to 20 labeled points.')
    for point in annotations:
        if not isinstance(point, dict) or not isinstance(point.get('label'), str) or len(point['label']) > 140 or point.get('basis') not in ('provided', 'computed', 'estimated'):
            raise ValueError('Highlighted points need labels and value provenance.')
        for axis in ('x', 'y'):
            coordinate = number(point.get(axis))
            if chart[axis + '_scale'] == 'log' and coordinate <= 0:
                raise ValueError('Highlighted points must be positive on logarithmic axes.')


@dataclass
class ChartAsset:
    image: Path
    data: Path
    spec: Path
    notes: str


def render_chart(chart, directory):
    validate_chart(chart)
    import matplotlib
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_agg import FigureCanvasAgg

    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(chart, sort_keys=True, ensure_ascii=False)
    stem = 'chart-' + hashlib.sha256(encoded.encode('utf-8')).hexdigest()[:20]
    asset = ChartAsset(directory / (stem + '.png'), directory / (stem + '.csv'),
                       directory / (stem + '.json'), chart['notes'])
    palette = ['#2463A6', '#C87624', '#6C7D35', '#7E589B', '#687587', '#B95A86']
    samples = []
    with matplotlib.rc_context({'font.family': 'DejaVu Sans', 'font.size': 10,
                                'text.usetex': False, 'text.parse_math': False}):
        figure = Figure(figsize=(7.0, 4.8), dpi=240)
        FigureCanvasAgg(figure)
        axes = figure.subplots()
        figure.subplots_adjust(left=0.14, right=0.96, bottom=0.19, top=0.82)
        bar_series = [series for series in chart['series'] if series['kind'] == 'bar']
        bar_positions = sorted({x for series in bar_series for x in series['x']})
        spacings = [right-left for left, right in zip(bar_positions, bar_positions[1:])]
        bar_width = 0.8 * (min(spacings) if spacings else 1) / max(1, len(bar_series))
        bar_index = 0
        for index, series in enumerate(chart['series']):
            xs, ys = series_points(series, chart['x_scale'])
            samples.append((series, xs, ys))
            label = series['label'] + (' (estimated)' if series['basis'] == 'estimated' else '')
            color = palette[index]
            if series['kind'] == 'bar':
                offset = (bar_index - (len(bar_series)-1)/2) * bar_width
                axes.bar([x+offset for x in xs], ys, width=bar_width, label=label, color=color, alpha=0.85)
                bar_index += 1
            elif series['kind'] == 'scatter':
                axes.scatter(xs, ys, label=label, color=color, marker=['o', 's', '^', 'D', 'v', 'X'][index], s=28)
            else:
                axes.plot(xs, [math.nan if y is None else y for y in ys], label=label,
                          color=color, linewidth=1.6, linestyle=['-', '--', ':', '-.'][index % 4],
                          marker='o' if series['kind'] == 'line' and len(xs) <= 25 else None, markersize=3)
        axes.set_xscale(chart['x_scale'])
        axes.set_yscale(chart['y_scale'])
        if bar_positions and len(bar_positions) <= 15:
            axes.set_xticks(bar_positions)
        if chart['x_limits']:
            axes.set_xlim(*chart['x_limits'])
        if chart['y_limits']:
            axes.set_ylim(*chart['y_limits'])
        if any(series['kind'] == 'bar' for series in chart['series']) and chart['y_scale'] == 'linear' and not chart['y_limits']:
            low, high = axes.get_ylim()
            axes.set_ylim(min(0, low), max(0, high))
        if chart['invert_y']:
            axes.invert_yaxis()
        axes.set_xlabel(textwrap.fill(chart['x_label'], 65))
        axes.set_ylabel(textwrap.fill(chart['y_label'], 55))
        figure.suptitle(textwrap.fill(chart['title'], 80), fontsize=12, fontweight='bold', y=0.98)
        axes.grid(True, alpha=0.22, linewidth=0.6)
        axes.set_axisbelow(True)
        axes.spines[['top', 'right']].set_visible(False)
        for index, point in enumerate(chart['annotations']):
            label = ('≈ ' if point['basis'] == 'estimated' else '') + point['label']
            axes.scatter([point['x']], [point['y']], color='#26323E', marker='D', s=24, zorder=5)
            axes.annotate(textwrap.fill(label, 28), xy=(point['x'], point['y']),
                          xytext=[(12, 14), (12, -26), (-85, 14), (-85, -26)][index % 4],
                          textcoords='offset points', fontsize=9,
                          arrowprops={'arrowstyle': '-', 'color': '#4A5560', 'lw': 0.7})
        axes.legend(loc='lower left', bbox_to_anchor=(0, 1.01), ncol=2, fontsize=8,
                    frameon=False, borderaxespad=0)
        estimated = any(s['basis'] == 'estimated' for s in chart['series']) or any(p['basis'] == 'estimated' for p in chart['annotations'])
        if estimated:
            figure.text(0.14, 0.025, 'Estimated readings from image; see notes for source and precision.', fontsize=8)
        if any(y is None for _, _, ys in samples for y in ys):
            asset.notes += '\nThe function is undefined at some sampled values; those points are omitted and the line is broken.'
        figure.savefig(asset.image, format='png', dpi=240, bbox_inches='tight', facecolor='white')
        figure.clear()
    with asset.data.open('w', newline='', encoding='utf-8-sig') as output:
        writer = csv.writer(output)
        writer.writerow(['series', 'x', 'y', 'basis', 'source'])
        for series, xs, ys in samples:
            for x, y in zip(xs, ys):
                writer.writerow([csv_text(series['label']), x, '' if y is None else y, series['basis'], csv_text(series['source'])])
        for point in chart['annotations']:
            writer.writerow([csv_text('Highlighted: ' + point['label']), point['x'], point['y'], point['basis'], 'Chart annotation'])
    asset.spec.write_text(encoded, encoding='utf-8')
    return asset


def csv_text(value):
    # Text exported from model output must not become a spreadsheet formula.
    return "'" + value if value.lstrip().startswith(('=', '+', '-', '@')) else value
