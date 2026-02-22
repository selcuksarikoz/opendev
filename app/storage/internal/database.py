import json
import sqlite3
import aiosqlite
from pathlib import Path
from datetime import datetime
from typing import Optional, Any

class DatabaseManager:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._db = None
        self._init_db_sync()

    async def get_db(self):
        if self._db is None:
            self._db = await aiosqlite.connect(self.db_path)
            self._db.row_factory = aiosqlite.Row
        return self._db

    async def shutdown(self):
        if self._db:
            await self._db.close()
            self._db = None

    async def _reopen_after_closed(self):
        self._db = None
        return await self.get_db()

    def _init_db_sync(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS api_keys (
                    provider TEXT PRIMARY KEY,
                    encrypted_key TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY, title TEXT NOT NULL,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id TEXT NOT NULL, role TEXT NOT NULL,
                    content TEXT NOT NULL, tool_calls TEXT,
                    reasoning TEXT, timestamp TEXT NOT NULL,
                    FOREIGN KEY(conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
                )
            """)
            try: conn.execute("ALTER TABLE messages ADD COLUMN reasoning TEXT")
            except sqlite3.OperationalError: pass
            conn.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            conn.commit()

    async def execute(self, sql: str, params: tuple = ()):
        db = await self.get_db()
        try:
            await db.execute(sql, params)
            await db.commit()
        except (aiosqlite.ProgrammingError, sqlite3.ProgrammingError) as exc:
            if "closed" not in str(exc).lower():
                raise
            db = await self._reopen_after_closed()
            await db.execute(sql, params)
            await db.commit()

    async def fetchall(self, sql: str, params: tuple = ()):
        db = await self.get_db()
        try:
            async with db.execute(sql, params) as cursor:
                return await cursor.fetchall()
        except (aiosqlite.ProgrammingError, sqlite3.ProgrammingError) as exc:
            if "closed" not in str(exc).lower():
                raise
            db = await self._reopen_after_closed()
            async with db.execute(sql, params) as cursor:
                return await cursor.fetchall()

    async def fetchone(self, sql: str, params: tuple = ()):
        db = await self.get_db()
        try:
            async with db.execute(sql, params) as cursor:
                return await cursor.fetchone()
        except (aiosqlite.ProgrammingError, sqlite3.ProgrammingError) as exc:
            if "closed" not in str(exc).lower():
                raise
            db = await self._reopen_after_closed()
            async with db.execute(sql, params) as cursor:
                return await cursor.fetchone()
