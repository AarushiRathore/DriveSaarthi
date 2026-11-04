"""Driver accounts and report index: SQLite, PBKDF2 hashing, lockout after repeated failures."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import time
from contextlib import closing

DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "drivers.db")
ITERATIONS, MAX_FAILS, LOCK_SECS = 200_000, 5, 300
USERNAME_RE = re.compile(r"^[a-z0-9_.-]{3,32}$")
PHONE_RE = re.compile(r"^\+[1-9]\d{7,14}$")
EDITABLE = ("full_name", "email", "emergency_name", "emergency_phone", "vehicle_plate", "license_no")
SCHEMA = """
CREATE TABLE IF NOT EXISTS users(
  id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL, pw TEXT NOT NULL,
  full_name TEXT NOT NULL, email TEXT DEFAULT '', emergency_name TEXT NOT NULL,
  emergency_phone TEXT NOT NULL, vehicle_plate TEXT DEFAULT '', license_no TEXT DEFAULT '',
  failed INTEGER DEFAULT 0, locked_until REAL DEFAULT 0, created_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS reports(
  id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, window_start REAL, window_end REAL,
  csv_path TEXT, png_path TEXT, seconds_json TEXT);
"""


def _conn():
    os.makedirs(os.path.dirname(DB), exist_ok=True)
    c = sqlite3.connect(DB, timeout=10)
    c.row_factory = sqlite3.Row
    return c


def init_db():
    with closing(_conn()) as c:
        c.executescript(SCHEMA)


def _hash(pw: str, salt: bytes) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", pw.encode(), salt, ITERATIONS)


def _public(row) -> dict:
    d = dict(row)
    for k in ("pw", "failed", "locked_until"):
        d.pop(k)
    return d


def clean_phone(s: str) -> str:
    return re.sub(r"[\s()-]", "", s or "")


def _strong(pw: str) -> bool:
    return len(pw) >= 8 and bool(re.search(r"[A-Za-z]", pw)) and bool(re.search(r"\d", pw))


def register(full_name, username, password, emergency_name, emergency_phone,
             vehicle_plate="", license_no="", email="") -> tuple[bool, str]:
    username, phone = username.strip().lower(), clean_phone(emergency_phone)
    if not full_name.strip() or not emergency_name.strip():
        return False, "Your name and the emergency contact's name are required."
    if not USERNAME_RE.match(username):
        return False, "Username must be 3 to 32 characters: letters, digits, dot, dash or underscore."
    if not _strong(password):
        return False, "Password needs at least 8 characters, with letters and digits."
    if not PHONE_RE.match(phone):
        return False, "Emergency number needs the country code, for example +919810012345."
    salt = secrets.token_bytes(16)
    try:
        with closing(_conn()) as c, c:
            c.execute("INSERT INTO users(username,pw,full_name,email,emergency_name,emergency_phone,"
                      "vehicle_plate,license_no,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                      (username, f"{salt.hex()}${_hash(password, salt).hex()}", full_name.strip(), email.strip(),
                       emergency_name.strip(), phone, vehicle_plate.strip().upper(), license_no.strip(), time.time()))
    except sqlite3.IntegrityError:
        return False, "That username is already taken."
    return True, "Account created."


def login(username: str, password: str) -> tuple[dict | None, str]:
    with closing(_conn()) as c, c:
        row = c.execute("SELECT * FROM users WHERE username=?", (username.strip().lower(),)).fetchone()
        if row is None:
            _hash(password, b"\0" * 16)                      # equalise timing for unknown users
            return None, "Invalid username or password."
        if row["locked_until"] > time.time():
            return None, f"Too many attempts. Try again in {int((row['locked_until'] - time.time()) // 60) + 1} min."
        salt_hex, hash_hex = row["pw"].split("$")
        if hmac.compare_digest(_hash(password, bytes.fromhex(salt_hex)).hex(), hash_hex):
            c.execute("UPDATE users SET failed=0, locked_until=0 WHERE id=?", (row["id"],))
            return _public(row), "ok"
        fails = row["failed"] + 1
        lock = time.time() + LOCK_SECS if fails >= MAX_FAILS else 0
        c.execute("UPDATE users SET failed=?, locked_until=? WHERE id=?", (0 if lock else fails, lock, row["id"]))
        return None, "Invalid username or password."


def get_user(uid: int) -> dict | None:
    with closing(_conn()) as c:
        row = c.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    return _public(row) if row else None


def update_profile(uid: int, **fields) -> tuple[bool, str]:
    fields = {k: v.strip() for k, v in fields.items() if k in EDITABLE}
    if "emergency_phone" in fields:
        fields["emergency_phone"] = clean_phone(fields["emergency_phone"])
        if not PHONE_RE.match(fields["emergency_phone"]):
            return False, "Emergency number needs the country code, for example +919810012345."
    if not fields:
      return False, "No profile changes provided."
    if not fields.get("full_name", "x") or not fields.get("emergency_name", "x"):
        return False, "Names cannot be empty."
    if "vehicle_plate" in fields:
        fields["vehicle_plate"] = fields["vehicle_plate"].upper()
    with closing(_conn()) as c, c:
        c.execute(f"UPDATE users SET {', '.join(f'{k}=?' for k in fields)} WHERE id=?", (*fields.values(), uid))
    return True, "Profile saved."


def change_password(uid: int, old: str, new: str) -> tuple[bool, str]:
    with closing(_conn()) as c, c:
        row = c.execute("SELECT pw FROM users WHERE id=?", (uid,)).fetchone()
        if row is None:
         return False, "User account not found."
        salt_hex, hash_hex = row["pw"].split("$")
        if not hmac.compare_digest(_hash(old, bytes.fromhex(salt_hex)).hex(), hash_hex):
            return False, "Current password is incorrect."
        if not _strong(new):
            return False, "New password needs at least 8 characters, with letters and digits."
        salt = secrets.token_bytes(16)
        c.execute("UPDATE users SET pw=? WHERE id=?", (f"{salt.hex()}${_hash(new, salt).hex()}", uid))
    return True, "Password changed."


def save_report(uid: int, start: float, end: float, csv_path: str, png_path: str, seconds: dict):
    with closing(_conn()) as c, c:
        c.execute("INSERT INTO reports(user_id,window_start,window_end,csv_path,png_path,seconds_json) "
                  "VALUES(?,?,?,?,?,?)", (uid, start, end, csv_path, png_path, json.dumps(seconds)))
if __name__ == "__main__":
    init_db()
    print("Driver database initialized successfully.")