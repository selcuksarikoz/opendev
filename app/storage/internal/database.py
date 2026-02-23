import json
import sqlite3
import aiosqlite
import asyncio
import time
from pathlib import Path
from datetime import datetime
from typing import Optional, Any

class DatabaseManager:
    LOCK_RETRIES = 20

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._db = None
        self._init_db_sync()

    async def get_db(self):
        if self._db is None:
            self._db = await aiosqlite.connect(self.db_path)
            self._db.row_factory = aiosqlite.Row
            await self._apply_connection_pragmas()
        return self._db

    async def shutdown(self):
        if self._db:
            await self._db.close()
            self._db = None

    async def _reopen_after_closed(self):
        self._db = None
        return await self.get_db()

    def _init_db_sync(self):
        retries = self.LOCK_RETRIES
        for attempt in range(retries):
            try:
                with sqlite3.connect(self.db_path, timeout=30) as conn:
                    conn.execute("PRAGMA busy_timeout = 5000")
                    try:
                        conn.execute("PRAGMA journal_mode = WAL")
                    except sqlite3.OperationalError as exc:
                        if not self._is_locked_error(exc):
                            raise
                    try:
                        conn.execute("PRAGMA synchronous = NORMAL")
                    except sqlite3.OperationalError as exc:
                        if not self._is_locked_error(exc):
                            raise
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
                    conn.execute("""
                        CREATE TABLE IF NOT EXISTS history (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            conversation_id TEXT NOT NULL,
                            content TEXT NOT NULL,
                            timestamp TEXT NOT NULL,
                            FOREIGN KEY(conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
                        )
                    """)
                    try:
                        conn.execute("ALTER TABLE messages ADD COLUMN reasoning TEXT")
                    except sqlite3.OperationalError:
                        pass
                    history_cols = {
                        row[1]
                        for row in conn.execute("PRAGMA table_info(history)").fetchall()
                    }
                    if "conversation_id" not in history_cols:
                        try:
                            conn.execute(
                                "ALTER TABLE history ADD COLUMN conversation_id TEXT NOT NULL DEFAULT ''"
                            )
                        except sqlite3.OperationalError:
                            pass
                    if "content" not in history_cols:
                        try:
                            conn.execute(
                                "ALTER TABLE history ADD COLUMN content TEXT NOT NULL DEFAULT ''"
                            )
                        except sqlite3.OperationalError:
                            pass
                    history_cols = {
                        row[1]
                        for row in conn.execute("PRAGMA table_info(history)").fetchall()
                    }
                    if "prompt" in history_cols and "content" in history_cols:
                        try:
                            conn.execute(
                                "UPDATE history SET content = prompt WHERE (content = '' OR content IS NULL) AND prompt IS NOT NULL"
                            )
                        except sqlite3.OperationalError:
                            pass
                    if "conversation_id" in history_cols:
                        try:
                            conn.execute(
                                "CREATE INDEX IF NOT EXISTS idx_history_conversation_id ON history(conversation_id)"
                            )
                        except sqlite3.OperationalError:
                            pass
                    conn.execute(
                        "CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
                    )
                    conn.commit()
                    return
            except sqlite3.OperationalError as exc:
                if not self._is_locked_error(exc):
                    raise
                if attempt == retries - 1:
                    return
                time.sleep(min(0.05 * (attempt + 1), 1.0))

    @staticmethod
    def _is_locked_error(exc: Exception) -> bool:
        return "locked" in str(exc).lower() or "busy" in str(exc).lower()

    async def _apply_connection_pragmas(self) -> None:
        if self._db is None:
            return

        try:
            await self._db.execute("PRAGMA busy_timeout = 5000")
        except Exception:
            pass

        retries = self.LOCK_RETRIES
        for attempt in range(retries):
            try:
                await self._db.execute("PRAGMA journal_mode = WAL")
                break
            except (aiosqlite.OperationalError, sqlite3.OperationalError) as exc:
                if not self._is_locked_error(exc):
                    break
                if attempt == retries - 1:
                    # WAL switch failed under lock; continue with default mode.
                    break
                await asyncio.sleep(min(0.05 * (attempt + 1), 1.0))

        try:
            await self._db.execute("PRAGMA synchronous = NORMAL")
        except Exception:
            pass

        try:
            await self._db.commit()
        except Exception:
            pass

    async def execute(self, sql: str, params: tuple = ()):
        retries = self.LOCK_RETRIES
        for attempt in range(retries):
            db = await self.get_db()
            try:
                await db.execute(sql, params)
                await db.commit()
                return
            except (aiosqlite.ProgrammingError, sqlite3.ProgrammingError) as exc:
                if "closed" not in str(exc).lower():
                    raise
                await self._reopen_after_closed()
                continue
            except (aiosqlite.OperationalError, sqlite3.OperationalError) as exc:
                if not self._is_locked_error(exc):
                    raise
                if attempt == retries - 1:
                    raise
                await asyncio.sleep(min(0.05 * (attempt + 1), 1.0))

    async def fetchall(self, sql: str, params: tuple = ()):
        retries = self.LOCK_RETRIES
        for attempt in range(retries):
            db = await self.get_db()
            try:
                async with db.execute(sql, params) as cursor:
                    return await cursor.fetchall()
            except (aiosqlite.ProgrammingError, sqlite3.ProgrammingError) as exc:
                if "closed" not in str(exc).lower():
                    raise
                await self._reopen_after_closed()
                continue
            except (aiosqlite.OperationalError, sqlite3.OperationalError) as exc:
                if not self._is_locked_error(exc):
                    raise
                if attempt == retries - 1:
                    raise
                await asyncio.sleep(min(0.05 * (attempt + 1), 1.0))
        return []

    async def fetchone(self, sql: str, params: tuple = ()):
        retries = self.LOCK_RETRIES
        for attempt in range(retries):
            db = await self.get_db()
            try:
                async with db.execute(sql, params) as cursor:
                    return await cursor.fetchone()
            except (aiosqlite.ProgrammingError, sqlite3.ProgrammingError) as exc:
                if "closed" not in str(exc).lower():
                    raise
                await self._reopen_after_closed()
                continue
            except (aiosqlite.OperationalError, sqlite3.OperationalError) as exc:
                if not self._is_locked_error(exc):
                    raise
                if attempt == retries - 1:
                    raise
                await asyncio.sleep(min(0.05 * (attempt + 1), 1.0))
        return None
