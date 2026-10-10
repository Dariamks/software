import json
from pathlib import Path
import tempfile
import unittest
import uuid
from unittest.mock import patch
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from activation_codes import encode
from access_control import LocalLicense, AccessError


class RenewalTests(unittest.TestCase):
    def test_universal_codes_work_on_multiple_installations(self):
        key = Ed25519PrivateKey.generate()
        def issue(kind):
            raw = json.dumps({'v': 1, 'id': uuid.uuid4().hex, 'machine': '*', 'kind': kind}).encode()
            return encode(raw) + '.' + encode(key.sign(raw))
        day, permanent = issue('day'), issue('permanent')
        with tempfile.TemporaryDirectory() as directory, patch('activation_codes.PUBLIC_KEY_HEX', key.public_key().public_bytes_raw().hex()), patch('access_control.verify_credentials', return_value=True):
            machines = []
            for index in range(3):
                license = LocalLicense(Path(directory) / f'{index}.db', lambda: 100000.0)
                license.login('test', 'test')
                machines.append(license.machine_code())
                original = license.expires_at
                license.redeem(day)
                self.assertEqual(license.expires_at, original + 86400)
                with self.assertRaises(AccessError):
                    license.redeem(day)
                license.redeem(permanent)
                restarted = LocalLicense(license.path, lambda: 100000.0 + 86400 * 365)
                restarted.login('test', 'test')
                self.assertTrue(restarted.permanent)
            self.assertEqual(len(set(machines)), 3)

    def test_renewal_permanent_replay_and_binding(self):
        key = Ed25519PrivateKey.generate()
        with tempfile.TemporaryDirectory() as d, patch('activation_codes.PUBLIC_KEY_HEX', key.public_key().public_bytes_raw().hex()), patch('access_control.verify_credentials', return_value=True):
            now = [100000.0]
            license = LocalLicense(Path(d)/'one.db', lambda: now[0])
            license.login('test', 'test')
            initial = license.expires_at
            def issue(kind):
                raw = json.dumps({'v':1,'id':uuid.uuid4().hex,'machine':license.machine_code(),'kind':kind}).encode()
                return encode(raw)+'.'+encode(key.sign(raw))
            day = issue('day')
            other = LocalLicense(Path(d)/'other.db', lambda: now[0])
            with self.assertRaises(AccessError): other.redeem(day)
            with self.assertRaises(AccessError): license.redeem('invalid')
            license.redeem(day)
            self.assertEqual(license.expires_at, initial+86400)
            with self.assertRaises(AccessError): license.redeem(day)
            now[0] = license.expires_at+10
            license.redeem(issue('day'))
            self.assertEqual(license.expires_at, now[0]+86400)
            permanent = issue('permanent')
            license.redeem(permanent)
            self.assertTrue(license.permanent)
            now[0] += 86400*365
            restarted = LocalLicense(license.path, lambda: now[0])
            restarted.login('test', 'test')
            restarted.check()
            self.assertTrue(restarted.permanent)
            with self.assertRaises(AccessError): restarted.redeem(permanent)
