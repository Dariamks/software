"""Local 24-hour activation. This is not a tamper-proof licensing server."""
import hashlib
import hmac
import os
from pathlib import Path
import sqlite3
import sys
import time


class AccessError(Exception):
    pass


def verify_credentials(account, password):
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), b'single-payment-login-v1', 240000).hex()
    return account.strip() == '13713533367' and hmac.compare_digest(
        digest, 'b4ba27a7cab12b7b62674bb0c1e30837857ed84fcf1fe7682dc55de2a87cf847')


def license_path():
    if sys.platform == 'win32':
        base = Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData/Local'))
    elif sys.platform == 'darwin':
        base = Path.home() / 'Library/Application Support'
    else:
        base = Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local/share'))
    return base / 'SinglePaymentTool' / 'activation.sqlite3'


class LocalLicense:
    def __init__(self, path=None, clock=time.time, monotonic=time.monotonic):
        self.path = Path(path) if path else license_path()
        self.clock, self.monotonic = clock, monotonic
        self.deadline = None
        self.expires_at = None

    def login(self, account, password):
        if not verify_credentials(account, password):
            raise AccessError('账号或密码错误')
        self._check(activate=True)
        self.deadline = self.monotonic() + max(0, self.expires_at - self.clock())

    def check(self):
        if self.deadline is None:
            raise AccessError('请先登录')
        if self.monotonic() >= self.deadline:
            raise AccessError('软件的一天使用期限已到，无法继续使用')
        self._check(activate=False)

    def _check(self, activate):
        now = self.clock()
        try:
            if not activate and not self.path.exists():
                raise AccessError('授权记录缺失，无法继续使用')
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(self.path, timeout=10) as db:
                db.execute('BEGIN IMMEDIATE')
                db.execute('CREATE TABLE IF NOT EXISTS activation (id INTEGER PRIMARY KEY, started REAL, expires REAL, last_seen REAL)')
                row = db.execute('SELECT started, expires, last_seen FROM activation WHERE id=1').fetchone()
                if row is None:
                    if not activate:
                        raise AccessError('授权记录缺失，无法继续使用')
                    row = (now, now + 86400, now)
                    db.execute('INSERT INTO activation VALUES (1, ?, ?, ?)', row)
                started, expires, last_seen = row
                if expires != started + 86400 or now < last_seen:
                    raise AccessError('系统时间或授权记录异常，无法继续使用')
                if now >= expires:
                    raise AccessError('软件的一天使用期限已到，无法继续使用')
                db.execute('UPDATE activation SET last_seen=? WHERE id=1', (now,))
                self.expires_at = expires
        except (OSError, sqlite3.Error, TypeError, ValueError) as exc:
            raise AccessError('无法读取或保存授权记录，无法继续使用') from exc
