from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass
from typing import Iterable, List, Optional, Sequence, Tuple

from .utils import collapse_whitespace


SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;

CREATE TABLE IF NOT EXISTS emails (
    id TEXT PRIMARY KEY,
    subject TEXT,
    from_name TEXT,
    from_email TEXT,
    to_emails TEXT,
    cc_emails TEXT,
    received_datetime TEXT,
    conversation_id TEXT,
    internet_message_id TEXT,
    body_preview TEXT,
    body_text TEXT,
    body_content_type TEXT,
    summary TEXT
);

-- Attempt to create FTS5; fallback handled in code if fails
CREATE VIRTUAL TABLE IF NOT EXISTS email_fts USING fts5(
    subject, body_text, summary, from_email, from_name, tokenize='porter'
);

CREATE INDEX IF NOT EXISTS idx_emails_received ON emails(received_datetime DESC);
"""


class Database:
    def __init__(self, path: str) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self._ensure_schema()
        self.use_fts = self._check_fts()

    def _ensure_schema(self) -> None:
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def _check_fts(self) -> bool:
        try:
            self.conn.execute("SELECT count(*) FROM email_fts")
            return True
        except sqlite3.Error:
            return False

    def upsert_email(
        self,
        *,
        id: str,
        subject: str,
        from_name: str,
        from_email: str,
        to_emails: List[str],
        cc_emails: List[str],
        received_datetime: str,
        conversation_id: Optional[str],
        internet_message_id: Optional[str],
        body_preview: Optional[str],
        body_text: str,
        body_content_type: str,
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO emails (
                id, subject, from_name, from_email, to_emails, cc_emails, received_datetime,
                conversation_id, internet_message_id, body_preview, body_text, body_content_type
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                subject=excluded.subject,
                from_name=excluded.from_name,
                from_email=excluded.from_email,
                to_emails=excluded.to_emails,
                cc_emails=excluded.cc_emails,
                received_datetime=excluded.received_datetime,
                conversation_id=excluded.conversation_id,
                internet_message_id=excluded.internet_message_id,
                body_preview=excluded.body_preview,
                body_text=excluded.body_text,
                body_content_type=excluded.body_content_type
            """,
            (
                id,
                subject,
                from_name,
                from_email,
                ", ".join(to_emails),
                ", ".join(cc_emails),
                received_datetime,
                conversation_id,
                internet_message_id,
                body_preview or "",
                body_text,
                body_content_type,
            ),
        )
        if self.use_fts:
            self.conn.execute(
                "DELETE FROM email_fts WHERE rowid = (SELECT rowid FROM emails WHERE id = ?)",
                (id,),
            )
            self.conn.execute(
                "INSERT INTO email_fts(rowid, subject, body_text, summary, from_email, from_name) SELECT rowid, subject, body_text, summary, from_email, from_name FROM emails WHERE id = ?",
                (id,),
            )
        self.conn.commit()

    def set_summary(self, message_id: str, summary: str) -> None:
        self.conn.execute("UPDATE emails SET summary = ? WHERE id = ?", (summary, message_id))
        if self.use_fts:
            self.conn.execute(
                "INSERT INTO email_fts(rowid, subject, body_text, summary, from_email, from_name) SELECT rowid, subject, body_text, summary, from_email, from_name FROM emails WHERE id = ?",
                (message_id,),
            )
        self.conn.commit()

    def get_email(self, message_id: str) -> Optional[sqlite3.Row]:
        cur = self.conn.execute("SELECT * FROM emails WHERE id = ?", (message_id,))
        return cur.fetchone()

    def search(self, query: str, limit: int = 5) -> List[sqlite3.Row]:
        if self.use_fts:
            cur = self.conn.execute(
                """
                SELECT e.* FROM email_fts f
                JOIN emails e ON e.rowid = f.rowid
                WHERE email_fts MATCH ?
                ORDER BY rank
                LIMIT ?
                """,
                (query, limit),
            )
        else:
            like = f"%{query}%"
            cur = self.conn.execute(
                """
                SELECT * FROM emails
                WHERE subject LIKE ? OR body_text LIKE ? OR summary LIKE ? OR from_email LIKE ? OR from_name LIKE ?
                ORDER BY received_datetime DESC
                LIMIT ?
                """,
                (like, like, like, like, like, limit),
            )
        return cur.fetchall()

    def iter_without_summary(self, limit: int = 100) -> Iterable[sqlite3.Row]:
        cur = self.conn.execute(
            "SELECT * FROM emails WHERE (summary IS NULL OR summary = '') ORDER BY received_datetime DESC LIMIT ?",
            (limit,),
        )
        for row in cur:
            yield row
