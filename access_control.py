"""Local 24-hour activation. This is not a tamper-proof licensing server."""
from contextlib import closing
import hashlib
import hmac
import os
from pathlib import Path
import sqlite3
import sys
import time
import uuid
from activation_codes import verify


class AccessError(Exception):
    pass


class LicenseExpired(AccessError):
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
        self.permanent = False

    def _schema(self, db):
        db.execute('CREATE TABLE IF NOT EXISTS device (id INTEGER PRIMARY KEY, code TEXT)')
        db.execute('INSERT OR IGNORE INTO device VALUES (1, ?)', (uuid.uuid4().hex.upper(),))
        db.execute('CREATE TABLE IF NOT EXISTS renewals (id TEXT PRIMARY KEY, code TEXT, redeemed REAL)')
        return db.execute('SELECT code FROM device WHERE id=1').fetchone()[0]

    def machine_code(self):
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with closing(sqlite3.connect(self.path)) as db, db:
                return self._schema(db)
        except (OSError, sqlite3.Error) as exc:
            raise AccessError('无法读取机器码') from exc

    def _expiry(self, db, initial, machine):
        expires, permanent = initial, False
        for code, redeemed in db.execute('SELECT code, redeemed FROM renewals ORDER BY redeemed, rowid'):
            try:
                data = verify(code, machine)
            except Exception as exc:
                raise AccessError('续期授权记录无效') from exc
            if data['kind'] == 'permanent':
                permanent = True
            else:
                expires = max(expires, redeemed) + 86400
        return expires, permanent

    def redeem(self, code):
        machine = self.machine_code()
        try:
            data = verify(code, machine)
        except Exception as exc:
            raise AccessError('激活码无效，或不属于此机器码') from exc
        now = self.clock()
        try:
            with closing(sqlite3.connect(self.path)) as db, db:
                db.execute('BEGIN IMMEDIATE')
                self._schema(db)
                db.execute('CREATE TABLE IF NOT EXISTS activation (id INTEGER PRIMARY KEY, started REAL, expires REAL, last_seen REAL)')
                row = db.execute('SELECT started, expires, last_seen FROM activation WHERE id=1').fetchone()
                if row is None:
                    row = (now, now + 86400, now)
                    db.execute('INSERT INTO activation VALUES (1, ?, ?, ?)', row)
                if now < row[2] or row[1] != row[0] + 86400:
                    raise AccessError('系统时间或授权记录异常')
                if db.execute('SELECT 1 FROM renewals WHERE id=?', (data['id'],)).fetchone():
                    raise AccessError('此激活码已经使用，不能重复续期')
                _, permanent = self._expiry(db, row[1], machine)
                if permanent:
                    raise AccessError('已永久解锁，无需续期')
                db.execute('INSERT INTO renewals VALUES (?, ?, ?)', (data['id'], ''.join(code.split()), now))
                db.execute('UPDATE activation SET last_seen=? WHERE id=1', (now,))
        except sqlite3.Error as exc:
            raise AccessError('保存激活码失败') from exc
        self._check(activate=False)
        if self.deadline is not None:
            self.deadline = float('inf') if self.permanent else self.monotonic() + max(0, self.expires_at - self.clock())

    def login(self, account, password):
        if not verify_credentials(account, password):
            raise AccessError('账号或密码错误')
        self._check(activate=True)
        self.deadline = float('inf') if self.permanent else self.monotonic() + max(0, self.expires_at - self.clock())

    def check(self):
        if self.deadline is None:
            raise AccessError('请先登录')
        if self.monotonic() >= self.deadline:
            raise LicenseExpired('软件使用期限已到，请输入激活码续期或永久解锁')
        self._check(activate=False)

    def _check(self, activate):
        now = self.clock()
        try:
            if not activate and not self.path.exists():
                raise AccessError('授权记录缺失，无法继续使用')
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with closing(sqlite3.connect(self.path, timeout=10)) as db, db:
                db.execute('BEGIN IMMEDIATE')
                machine = self._schema(db)
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
                expires, permanent = self._expiry(db, expires, machine)
                if not permanent and now >= expires:
                    raise LicenseExpired('软件使用期限已到，请输入激活码续期或永久解锁')
                db.execute('UPDATE activation SET last_seen=? WHERE id=1', (now,))
                self.expires_at = expires
                self.permanent = permanent
        except (OSError, sqlite3.Error, TypeError, ValueError) as exc:
            raise AccessError('无法读取或保存授权记录，无法继续使用') from exc
