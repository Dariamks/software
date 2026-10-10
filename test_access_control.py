import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from access_control import LocalLicense, AccessError


class LicenseTests(unittest.TestCase):
    def test_persistent_expiry_and_clock_rollback(self):
        with tempfile.TemporaryDirectory() as directory, patch('access_control.verify_credentials', return_value=True):
            now = [100000.0]
            path = Path(directory) / 'license.db'
            first = LocalLicense(path, lambda: now[0])
            first.login('test', 'test')
            now[0] += 100
            second = LocalLicense(path, lambda: now[0])
            second.login('test', 'test')
            self.assertEqual(first.expires_at, second.expires_at)
            now[0] -= 1
            with self.assertRaises(AccessError):
                second.check()
            now[0] = first.expires_at
            with self.assertRaises(AccessError):
                second.check()
            with self.assertRaises(AccessError):
                second.login('test', 'test')

    def test_wrong_credentials_do_not_activate(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'license.db'
            with self.assertRaises(AccessError):
                LocalLicense(path).login('invalid', 'invalid')
            self.assertFalse(path.exists())

    def test_corrupt_record_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory, patch('access_control.verify_credentials', return_value=True):
            path = Path(directory) / 'license.db'
            path.write_text('corrupted')
            with self.assertRaises(AccessError):
                LocalLicense(path).login('test', 'test')
