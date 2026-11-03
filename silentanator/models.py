"""Discover the signed-in Codex model catalog without starting a model turn."""
import json
import os
import queue
import subprocess
import tempfile
import threading
import time

from .core import find_codex, hidden_process, require_subscription


def image_models(entries):
    result, seen = [], set()
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        model = entry.get('model') or entry.get('id')
        if not isinstance(model, str) or not model or model in seen or entry.get('hidden'):
            continue
        # Older Codex catalogs omit inputModalities; the protocol defines these
        # entries as text+image compatible for backward compatibility.
        if 'image' not in entry.get('inputModalities', ['text', 'image']):
            continue
        seen.add(model)
        result.append({'model': model, 'name': entry.get('displayName') or model,
                       'default': bool(entry.get('isDefault'))})
    return result


def list_codex_models(configured='', cancel=None, timeout=30):
    executable = find_codex(configured)
    require_subscription(executable)
    env = os.environ.copy()
    for key in ('OPENAI_API_KEY', 'CODEX_API_KEY'):
        env.pop(key, None)
    messages = queue.Queue()
    with tempfile.TemporaryDirectory(prefix='silentanator-models-') as directory:
        process = hidden_process([executable, '-c', 'model_provider="openai"', 'app-server', '--listen', 'stdio://'],
                                 cwd=directory, env=env, stdin=subprocess.PIPE,
                                 stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                 text=True, encoding='utf-8', errors='replace', bufsize=1)
        def read():
            try:
                for line in process.stdout:
                    try:
                        messages.put(json.loads(line))
                    except ValueError:
                        continue
            finally:
                messages.put(None)
        reader = threading.Thread(target=read, daemon=True)
        reader.start()
        deadline = time.monotonic() + timeout

        def send(message):
            process.stdin.write(json.dumps(message) + '\n')
            process.stdin.flush()

        def response(request_id):
            while time.monotonic() < deadline:
                if cancel and cancel.is_set():
                    raise RuntimeError('Model discovery cancelled.')
                try:
                    message = messages.get(timeout=min(0.1, max(0.001, deadline-time.monotonic())))
                except queue.Empty:
                    continue
                if message is None:
                    raise RuntimeError('Codex closed before returning its models. Check connection and sign-in.')
                if message.get('id') != request_id:
                    continue
                if 'error' in message:
                    raise RuntimeError('Codex could not list models: ' + str(message['error'].get('message', 'unknown error')))
                if not isinstance(message.get('result'), dict):
                    raise RuntimeError('Codex returned an invalid model-list response.')
                return message['result']
            raise RuntimeError('Loading Codex models timed out. Try Refresh models.')

        try:
            send({'id': 0, 'method': 'initialize', 'params': {'clientInfo': {
                'name': 'silentanator', 'title': 'Silentanator Setup', 'version': '1.6.0'}}})
            response(0)
            send({'method': 'initialized', 'params': {}})
            entries, cursor, request_id, cursors = [], None, 1, set()
            while True:
                params = {'limit': 100, 'includeHidden': False}
                if cursor:
                    params['cursor'] = cursor
                send({'id': request_id, 'method': 'model/list', 'params': params})
                page = response(request_id)
                if not isinstance(page.get('data'), list):
                    raise RuntimeError('Codex returned an invalid model catalog.')
                entries.extend(page['data'])
                cursor = page.get('nextCursor')
                if not cursor:
                    break
                if cursor in cursors:
                    raise RuntimeError('Codex returned a repeated model-list page.')
                cursors.add(cursor)
                request_id += 1
            return image_models(entries)
        finally:
            try:
                process.stdin.close()
            except OSError:
                pass
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)
            reader.join(timeout=1)
            process.stdout.close()
