"""Read Codex event metadata without exposing queries, reasoning, or answer text."""
import json


class RequestProgress:
    def __init__(self, progress):
        self.progress = progress
        self.pending = b''
        self.phase = 'Waiting for Codex'
        self.web_steps = 0
        self.completed = set()
        self.last_error = None

    def drain(self, reader, final=False):
        while chunk := reader.read(65536):
            self.pending += chunk
            while b'\n' in self.pending:
                line, self.pending = self.pending.split(b'\n', 1)
                self.consume(line)
        if final and self.pending:
            self.consume(self.pending)
            self.pending = b''

    def consume(self, line):
        try:
            event = json.loads(line)
        except (ValueError, UnicodeDecodeError):
            return
        if not isinstance(event, dict):
            return
        kind = event.get('type')
        item = event.get('item') or {}
        if not isinstance(item, dict):
            item = {}
        phase = None
        if kind == 'turn.started':
            phase = 'Codex accepted the request; working on the solution'
        elif kind in ('item.started', 'item.updated') and item.get('type') == 'web_search':
            phase = 'Codex is searching or reading web sources'
        elif kind == 'item.completed' and item.get('type') == 'web_search':
            if item.get('status') not in ('failed', 'cancelled'):
                identity = item.get('id')
                if not isinstance(identity, str):
                    identity = None
                if identity is None or identity not in self.completed:
                    self.web_steps += 1
                    if identity is not None:
                        self.completed.add(identity)
                    self.progress(f'Web lookup completed: {self.web_steps} search/browse step(s).')
            phase = 'Codex is working on calculations and notes'
        elif kind in ('item.started', 'item.completed') and item.get('type') == 'agent_message':
            phase = 'Codex response activity; waiting for the finished notes'
        elif kind == 'turn.completed':
            phase = 'Codex finished; receiving the notes'
        elif kind in ('error', 'turn.failed'):
            error = event.get('error') or {}
            message = event.get('message') or (error.get('message') if isinstance(error, dict) else '') or ''
            message = str(message).lower()
            if any(word in message for word in ('rate limit', 'usage limit', 'quota')):
                self.last_error = 'Codex reported a usage or rate limit. Check your Codex allowance and try again later.'
            elif any(word in message for word in ('authentication', 'unauthorized', 'sign in', 'login')):
                self.last_error = 'Codex reported a sign-in error. Sign in again from Setup, then retry the saved request.'
            elif any(word in message for word in ('network', 'connection', 'stream', 'reconnect', 'timed out')):
                self.last_error = 'Codex reported a connection error. Check connectivity, then retry the saved request.'
            phase = 'Codex reported an error; waiting for its final status'
        if phase and phase != self.phase:
            self.phase = phase
            self.progress(phase + '…')
