from __future__ import annotations

import hashlib
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


# 从环境变量读取数据库路径，默认值为当前目录下的 data.sqlite3
DB_PATH = Path(os.getenv("DB_PATH", Path(__file__).resolve().parents[1] / "data.sqlite3"))


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _now_str() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")


def _hash_password(password: str, salt: str) -> str:
    raw = f"{salt}:{password}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def init_user_store() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                display_name TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                salt TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'viewer',
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.commit()
    ensure_admin_account()


def ensure_admin_account() -> None:
    now = _now_str()
    with _conn() as conn:
        row = conn.execute("SELECT id FROM users WHERE username = ?", ("admin",)).fetchone()
        if row:
            return
        salt = os.urandom(16).hex()
        pw_hash = _hash_password("admin123", salt)
        conn.execute(
            """
            INSERT INTO users (username, display_name, password_hash, salt, role, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("admin", "系统管理员", pw_hash, salt, "admin", "approved", now, now),
        )
        conn.commit()


def create_user(username: str, password: str, display_name: str, role: str = "viewer", status: str = "pending") -> int:
    now = _now_str()
    salt = os.urandom(16).hex()
    pw_hash = _hash_password(password, salt)
    with _conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO users (username, display_name, password_hash, salt, role, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (username, display_name, pw_hash, salt, role, status, now, now),
        )
        conn.commit()
        return int(cur.lastrowid)


def get_user_by_username(username: str) -> Optional[Dict[str, Any]]:
    with _conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        return dict(row) if row else None


def get_user_by_id(user_id: int) -> Optional[Dict[str, Any]]:
    with _conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return dict(row) if row else None


def verify_user(username: str, password: str) -> Optional[Dict[str, Any]]:
    user = get_user_by_username(username)
    if not user:
        return None
    hashed = _hash_password(password, user["salt"])
    if hashed != user["password_hash"]:
        return None
    return user


def list_users() -> List[Dict[str, Any]]:
    with _conn() as conn:
        rows = conn.execute(
            """
            SELECT id, username, display_name, role, status, created_at, updated_at
            FROM users
            ORDER BY id DESC
            """
        ).fetchall()
        return [dict(r) for r in rows]


def update_user_status(user_id: int, status: str) -> bool:
    now = _now_str()
    with _conn() as conn:
        cur = conn.execute(
            "UPDATE users SET status = ?, updated_at = ? WHERE id = ?",
            (status, now, user_id),
        )
        conn.commit()
        return cur.rowcount > 0


def update_user_role(user_id: int, role: str) -> bool:
    now = _now_str()
    with _conn() as conn:
        cur = conn.execute(
            "UPDATE users SET role = ?, updated_at = ? WHERE id = ?",
            (role, now, user_id),
        )
        conn.commit()
        return cur.rowcount > 0
