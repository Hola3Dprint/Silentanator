import hashlib
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
import uuid

from silentanator import updater
from silentanator.windows import UpdateRequest


class UpdateTests(unittest.TestCase):
    def release(self, data=b'verified-test-installer'):
        digest = hashlib.sha256(data).hexdigest()
        return updater.Release('9.1.0', 'https://github.com/Hola3Dprint/Silentanator/releases/download/v9.1.0/Silentanator-Setup.exe',
                               'https://github.com/Hola3Dprint/Silentanator/releases/download/v9.1.0/SHA256SUMS.txt',
                               len(data), 'sha256:' + digest)

    def metadata(self):
        release = self.release()
        return {'tag_name': 'v9.1.0', 'draft': False, 'prerelease': False, 'assets': [
            {'name': 'Silentanator-Setup.exe', 'browser_download_url': release.installer_url,
             'size': release.size, 'digest': release.digest},
            {'name': 'SHA256SUMS.txt', 'browser_download_url': release.checksum_url}]}

    def test_newer_stable_release_is_selected_but_same_and_older_are_not(self):
        with patch.object(updater, 'open_url', side_effect=lambda url: io.BytesIO(json.dumps(self.metadata()).encode())):
            self.assertEqual(updater.latest_release('1.3.0').version, '9.1.0')
            self.assertIsNone(updater.latest_release('9.1.0'))
            self.assertIsNone(updater.latest_release('10.0.0'))

    def test_foreign_asset_or_prerelease_never_downloads(self):
        for change in ('foreign', 'prerelease', 'missing'):
            value = self.metadata()
            if change == 'foreign':
                value['assets'][0]['browser_download_url'] = 'https://example.com/not-the-installer.exe'
            elif change == 'prerelease':
                value['prerelease'] = True
            else:
                value['assets'] = []
            with self.subTest(change=change), patch.object(updater, 'open_url', return_value=io.BytesIO(json.dumps(value).encode())):
                with self.assertRaises(ValueError):
                    updater.latest_release('1.0.0')

    def test_streamed_download_verifies_hash_and_size_before_final_file_appears(self):
        data = b'verified-test-installer'
        release = self.release(data)
        checksum = (hashlib.sha256(data).hexdigest() + '  Silentanator-Setup.exe\n').encode()
        with tempfile.TemporaryDirectory() as directory, patch.object(updater, 'open_url',
                side_effect=lambda url: io.BytesIO(checksum if url == release.checksum_url else data)):
            path = updater.download_release(release, directory)
            self.assertEqual(path.read_bytes(), data)
            self.assertFalse(path.with_suffix('.exe.part').exists())

    def test_corrupted_or_truncated_download_never_becomes_executable(self):
        release = self.release()
        checksum = (release.digest[7:] + '  Silentanator-Setup.exe\n').encode()
        for bad_data in (b'broken', b'x' * release.size, b'x' * (release.size + 1)):
            with self.subTest(size=len(bad_data)), tempfile.TemporaryDirectory() as directory, \
                 patch.object(updater, 'open_url', side_effect=lambda url: io.BytesIO(checksum if url == release.checksum_url else bad_data)):
                with self.assertRaises(ValueError):
                    updater.download_release(release, directory)
                self.assertEqual(list(Path(directory).iterdir()), [])

    def test_digest_mismatch_and_cancel_leave_app_untouched(self):
        release = self.release()
        bad_checksum = ('0' * 64 + '  Silentanator-Setup.exe\n').encode()
        with tempfile.TemporaryDirectory() as directory, patch.object(updater, 'open_url', return_value=io.BytesIO(bad_checksum)):
            with self.assertRaises(ValueError):
                updater.download_release(release, directory)
            self.assertFalse(any(Path(directory).iterdir()))
        cancel = threading.Event()
        cancel.set()
        checksum = (release.digest[7:] + '  Silentanator-Setup.exe\n').encode()
        with tempfile.TemporaryDirectory() as directory, patch.object(updater, 'open_url',
                side_effect=lambda url: io.BytesIO(checksum if url == release.checksum_url else b'x')):
            with self.assertRaises(RuntimeError):
                updater.download_release(release, directory, cancel)
            self.assertFalse(any(Path(directory).iterdir()))

    def test_redirects_must_remain_on_https_github_asset_hosts(self):
        redirect = updater.GitHubRedirect()
        for url in ('http://github.com/asset', 'https://example.com/asset'):
            with self.assertRaises(ValueError):
                redirect.redirect_request(None, None, 302, '', {}, url)

    def test_update_event_is_shared_and_closes_cleanly(self):
        name = 'Local\\Silentanator-QA-' + uuid.uuid4().hex
        first, second = UpdateRequest(name), UpdateRequest(name)
        try:
            self.assertFalse(first.is_set())
            first.signal()
            self.assertTrue(second.is_set())
        finally:
            first.close()
            second.close()
        fresh = UpdateRequest(name)
        try:
            self.assertFalse(fresh.is_set())
        finally:
            fresh.close()


if __name__ == '__main__':
    unittest.main()
