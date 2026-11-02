"""User-triggered updates from the product's public GitHub release channel."""
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import queue
import re
import subprocess
import sys
import threading
import time
import urllib.request
import uuid

from .core import DATA

REPOSITORY = 'Hola3Dprint/Silentanator'
LATEST = f'https://api.github.com/repos/{REPOSITORY}/releases/latest'
PRODUCT_ID = 'f9334ef5-a351-4fba-a0a0-b563af7c6697'
MAX_INSTALLER = 2 * 1024 * 1024 * 1024


def version_tuple(value):
    match = re.fullmatch(r'v?(\d+)\.(\d+)\.(\d+)', value.strip())
    if not match:
        raise ValueError('GitHub returned an unsupported release version.')
    return tuple(int(part) for part in match.groups())


def app_directory():
    return Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent.parent


def current_version():
    return (app_directory() / 'VERSION').read_text(encoding='utf-8').strip()


class GitHubRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, new_url):
        from urllib.parse import urlsplit
        parsed = urlsplit(new_url)
        if parsed.scheme != 'https' or parsed.hostname not in {
                'github.com', 'api.github.com', 'release-assets.githubusercontent.com', 'objects.githubusercontent.com'}:
            raise ValueError('GitHub redirected the update to an unexpected location.')
        return super().redirect_request(request, fp, code, message, headers, new_url)


def open_url(url):
    request = urllib.request.Request(url, headers={'User-Agent': 'Silentanator-Updater',
                                                   'Accept': 'application/vnd.github+json' if url == LATEST else 'application/octet-stream'})
    return urllib.request.build_opener(GitHubRedirect()).open(request, timeout=30)


@dataclass(frozen=True)
class Release:
    version: str
    installer_url: str
    checksum_url: str
    size: int
    digest: str | None


def latest_release(installed):
    with open_url(LATEST) as response:
        raw = response.read(1024 * 1024 + 1)
    if len(raw) > 1024 * 1024:
        raise ValueError('GitHub release metadata is too large.')
    value = json.loads(raw)
    tag = value['tag_name']
    latest = version_tuple(tag)
    if value.get('draft') or value.get('prerelease'):
        raise ValueError('Only published stable releases can be installed.')
    if latest <= version_tuple(installed):
        return None
    assets = {asset['name']: asset for asset in value.get('assets', [])}
    installer, checksums = assets.get('Silentanator-Setup.exe'), assets.get('SHA256SUMS.txt')
    if not installer or not checksums:
        raise ValueError('The latest GitHub release does not have a complete Windows installer yet.')
    base = f'https://github.com/{REPOSITORY}/releases/download/{tag}/'
    if installer['browser_download_url'] != base + 'Silentanator-Setup.exe' or checksums['browser_download_url'] != base + 'SHA256SUMS.txt':
        raise ValueError('The release assets do not belong to the expected GitHub repository.')
    size = installer['size']
    if not isinstance(size, int) or not 0 < size <= MAX_INSTALLER:
        raise ValueError('GitHub returned an invalid installer size.')
    return Release('.'.join(map(str, latest)), installer['browser_download_url'], checksums['browser_download_url'],
                   size, installer.get('digest'))


def download_release(release, destination, cancel=None, progress=None):
    progress = progress or (lambda message: None)
    with open_url(release.checksum_url) as response:
        checksum_text = response.read(16385)
    if len(checksum_text) > 16384:
        raise ValueError('The published checksum file is too large.')
    matches = re.findall(r'^([0-9a-fA-F]{64})[ \t]+\*?Silentanator-Setup\.exe[ \t\r]*$', checksum_text.decode('ascii'), re.MULTILINE)
    if len(matches) != 1:
        raise ValueError('The published installer checksum is missing or ambiguous.')
    expected = matches[0].lower()
    if release.digest and release.digest.lower() != 'sha256:' + expected:
        raise ValueError('The GitHub asset digest and published checksum disagree.')
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    partial = destination / 'Silentanator-Setup.exe.part'
    target = destination / 'Silentanator-Setup.exe'
    digest, size, reported = hashlib.sha256(), 0, -1
    deadline = time.monotonic() + 900
    try:
        with open_url(release.installer_url) as response, partial.open('wb') as output:
            while True:
                if (cancel and cancel.is_set()) or time.monotonic() > deadline:
                    raise RuntimeError('Update download cancelled or timed out.')
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > release.size:
                    raise ValueError('The installer download exceeds its published size.')
                digest.update(chunk)
                output.write(chunk)
                percent = size * 100 // release.size
                if percent != reported:
                    progress(f'Downloading v{release.version}: {percent}%')
                    reported = percent
        if size != release.size or digest.hexdigest() != expected:
            raise ValueError('Installer verification failed. The current app has not been changed.')
        if cancel and cancel.is_set():
            raise RuntimeError('Update cancelled.')
        os.replace(partial, target)
        return target
    finally:
        if partial.exists():
            partial.unlink()


def launch_update(installer, restart_setup=False):
    directory = app_directory()
    marker = directory / '.silentanator-install'
    if not getattr(sys, 'frozen', False) or not marker.is_file() or marker.read_text(encoding='utf-8').strip() != PRODUCT_ID:
        raise RuntimeError('Apply updates from the installed Windows app.')
    from .windows import runner_running
    restart_runner = not restart_setup or runner_running()
    report = DATA / 'updates' / 'last-update.json'
    report.parent.mkdir(parents=True, exist_ok=True)
    args = [str(installer), '--apply-update', '--dir', str(directory), '--wait-pid', str(os.getpid()),
            '--update-report', str(report)]
    if restart_runner:
        args.append('--restart-runner')
    if restart_setup:
        args.append('--restart-setup')
    # Only the installer escapes our child job; solver subprocesses remain contained.
    return subprocess.Popen(args, close_fds=True, creationflags=0x01000000 | 0x08000000 | 0x00000200)


class UpdateControl:
    def __init__(self, root, parent, on_request, restart_setup=False):
        from tkinter import ttk
        from .windows import UpdateRequest
        self.root, self.on_request, self.restart_setup = root, on_request, restart_setup
        self.request = UpdateRequest()
        self.cancel = threading.Event()
        self.events = queue.Queue()
        self.busy = False
        self.guard = None
        self.requested = False
        self.frame = ttk.Frame(parent)
        self.button = ttk.Button(self.frame, text='Update from GitHub', command=self.start)
        self.button.pack(side='right')
        self.label = ttk.Label(self.frame, text='v' + current_version(), wraplength=310)
        self.label.pack(side='right', padx=8)
        try:
            result = json.loads((DATA / 'updates' / 'last-update.json').read_text(encoding='utf-8'))
            if result.get('state') == 'failed':
                self.label.configure(text='Last update failed; the previous app was retained.')
        except (OSError, ValueError):
            pass
        self.root.after(100, self.poll)

    def start(self):
        if self.busy or self.requested:
            return
        from .windows import SingleInstance
        try:
            self.guard = SingleInstance('Local\\SilentanatorUpdateDownload')
        except RuntimeError:
            self.label.configure(text='Another update is already in progress.')
            return
        self.busy = True
        self.button.configure(state='disabled')
        self.label.configure(text='Checking GitHub…')
        def work():
            try:
                release = latest_release(current_version())
                if not release:
                    self.events.put(('done', 'Already up to date (v' + current_version() + ').'))
                    return
                destination = DATA / 'updates' / (release.version + '-' + uuid.uuid4().hex)
                installer = download_release(release, destination, self.cancel,
                                             lambda message: self.events.put(('progress', message)))
                if not self.cancel.is_set():
                    self.events.put(('install', installer))
            except Exception as exc:
                self.events.put(('error', 'Update failed: ' + str(exc)))
        threading.Thread(target=work, daemon=True).start()

    def poll(self):
        while not self.events.empty():
            kind, value = self.events.get_nowait()
            if kind == 'install':
                try:
                    if self.cancel.is_set():
                        continue
                    launch_update(value, self.restart_setup)
                    self.label.configure(text='Installing update; waiting for open work to finish…')
                    self.request.signal()
                except Exception as exc:
                    kind, value = 'error', 'Update could not start: ' + str(exc)
            if kind in ('done', 'error'):
                self.busy = False
                if self.guard:
                    self.guard.close()
                    self.guard = None
                self.button.configure(state='normal')
                self.label.configure(text=value)
            elif kind == 'progress':
                self.label.configure(text=value)
        if not self.requested and self.request.is_set():
            self.requested = True
            self.button.configure(state='disabled')
            self.label.configure(text='Update ready; finishing open work…')
            self.on_request()
        if not self.cancel.is_set():
            self.root.after(100, self.poll)

    def close(self):
        self.cancel.set()
        if self.guard:
            self.guard.close()
            self.guard = None
        self.request.close()
