import json
import shutil
import uuid
from pathlib import Path
from datetime import datetime
from typing import Optional, Any
from .internal.encryption import EncryptionManager
from .internal.database import DatabaseManager


class Storage:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(Storage, cls).__new__(cls)
        return cls._instance

    def __init__(self, db_path: str = "~/.opendev/data.db"):
        if hasattr(self, "_initialized"):
            return
        self.db_path = Path(db_path).expanduser()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._migrate_legacy_storage()
        key_file = self.db_path.parent / ".enc_key"

        self.db = DatabaseManager(self.db_path)
        self.encryption = EncryptionManager(key_file)
        self._initialized = True

    def _migrate_legacy_storage(self) -> None:
        new_dir = self.db_path.parent
        old_dir = Path.home() / ".opendev_cli"
        if not old_dir.exists() or old_dir == new_dir:
            return

        old_db = old_dir / "data.db"
        new_db = new_dir / "data.db"
        if old_db.exists() and not new_db.exists():
            shutil.copy2(old_db, new_db)

        old_key = old_dir / ".enc_key"
        new_key = new_dir / ".enc_key"
        if old_key.exists() and not new_key.exists():
            shutil.copy2(old_key, new_key)

        old_sessions = old_dir / "sessions"
        new_sessions = new_dir / "sessions"
        if old_sessions.exists():
            new_sessions.mkdir(parents=True, exist_ok=True)
            for session_file in old_sessions.iterdir():
                target = new_sessions / session_file.name
                if session_file.is_file() and not target.exists():
                    shutil.copy2(session_file, target)

    async def shutdown(self):
        await self.db.shutdown()

    async def save_api_key(self, provider: str, api_key: str):
        encrypted = self.encryption.encrypt(api_key)
        await self.db.execute(
            "INSERT OR REPLACE INTO api_keys (provider, encrypted_key) VALUES (?, ?)",
            (provider, encrypted),
        )

    async def get_api_key(self, provider: str) -> Optional[str]:
        row = await self.db.fetchone(
            "SELECT encrypted_key FROM api_keys WHERE provider = ?", (provider,)
        )
        return self.encryption.decrypt(row[0]) if row else None

    async def create_conversation(self, conversation_id: str, title: str):
        now = datetime.now().isoformat()
        await self.db.execute(
            "INSERT INTO conversations (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (conversation_id, title, now, now),
        )

    async def update_conversation_title(self, conversation_id: str, title: str):
        await self.db.execute(
            "UPDATE conversations SET title = ?, updated_at = ? WHERE id = ?",
            (title, datetime.now().isoformat(), conversation_id),
        )

    async def save_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        tool_calls: Optional[list[dict]] = None,
        reasoning: Optional[str] = None,
    ):
        await self.db.execute(
            "INSERT INTO messages (conversation_id, role, content, tool_calls, reasoning, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
            (
                conversation_id,
                role,
                content,
                json.dumps(tool_calls) if tool_calls else None,
                reasoning,
                datetime.now().isoformat(),
            ),
        )
        await self.db.execute(
            "UPDATE conversations SET updated_at = ? WHERE id = ?",
            (datetime.now().isoformat(), conversation_id),
        )

    async def get_messages(self, conversation_id: str) -> list[dict[str, Any]]:
        rows = await self.db.fetchall(
            "SELECT role, content, tool_calls, reasoning FROM messages WHERE conversation_id = ? ORDER BY id ASC",
            (conversation_id,),
        )
        messages = []
        for row in rows:
            msg = {"role": row[0], "content": row[1]}
            if row[2]:
                msg["tool_calls"] = json.loads(row[2])
            if row[3]:
                msg["reasoning"] = row[3]
            messages.append(msg)
        return messages

    async def list_conversations(self) -> list[dict[str, Any]]:
        rows = await self.db.fetchall(
            "SELECT id, title, updated_at FROM conversations ORDER BY updated_at DESC"
        )
        return [{"id": row[0], "title": row[1], "updated_at": row[2]} for row in rows]

    async def delete_all_conversations(self) -> None:
        await self.db.execute("DELETE FROM messages")
        await self.db.execute("DELETE FROM conversations")

    async def delete_conversations_except(self, keep_conversation_id: Optional[str]) -> None:
        if keep_conversation_id:
            await self.db.execute(
                "DELETE FROM messages WHERE conversation_id != ?",
                (keep_conversation_id,),
            )
            await self.db.execute(
                "DELETE FROM conversations WHERE id != ?",
                (keep_conversation_id,),
            )
        else:
            await self.delete_all_conversations()

    async def save_setting(self, key: str, value: str):
        await self.db.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value)
        )

    async def get_all_settings(self) -> dict[str, Any]:
        defaults = {"max_tokens": "4096", "temperature": "0.5", "top_p": "1.0"}
        rows = await self.db.fetchall("SELECT key, value FROM settings")
        for row in rows:
            defaults[row[0]] = row[1]
        return defaults


class SessionLogger:
    def __init__(self, session_id: Optional[str] = None):
        self.session_id = session_id or str(uuid.uuid4())
        self.log_dir = Path("~/.opendev/sessions").expanduser()
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.log_file = self.log_dir / f"{self.session_id}.log"

    def log(
        self,
        role: str,
        content: str,
        reasoning: Optional[str] = None,
        tools: Optional[list] = None,
    ):
        entry = {
            "timestamp": datetime.now().isoformat(),
            "role": role,
            "content": content,
            "reasoning": reasoning,
            "tools": tools,
        }
        with open(self.log_file, "a") as f:
            f.write(json.dumps(entry) + "\n")

    def get_session_id(self) -> str:
        return self.session_id
