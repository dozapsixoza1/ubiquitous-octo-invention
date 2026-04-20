# database.py
import sqlite3
from datetime import datetime, date
from typing import Optional, List, Dict, Any
from config import Config


class Database:
    def __init__(self):
        self.db_path = Config.DATABASE_URL.replace('sqlite:///', '')
        self.init_db()

    def get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row          # dict-like доступ
        conn.execute("PRAGMA journal_mode=WAL") # надёжнее при параллельном доступе
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _row_to_dict(self, row) -> Optional[Dict]:
        return dict(row) if row else None

    def _rows_to_list(self, rows) -> List[Dict]:
        return [dict(r) for r in rows]

    # ══════════════════════════════════════════
    #               ИНИЦИАЛИЗАЦИЯ БД
    # ══════════════════════════════════════════

    def init_db(self):
        with self.get_connection() as conn:
            conn.executescript('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id         INTEGER PRIMARY KEY,
                    username        TEXT,
                    first_name      TEXT,
                    last_name       TEXT,
                    is_admin        INTEGER DEFAULT 0,
                    is_moder        INTEGER DEFAULT 0,
                    is_banned       INTEGER DEFAULT 0,
                    registered_date TEXT,
                    last_activity   TEXT
                );

                CREATE TABLE IF NOT EXISTS scammers (
                    id                INTEGER PRIMARY KEY AUTOINCREMENT,
                    scammer_id        TEXT,
                    scammer_username  TEXT,
                    scammer_name      TEXT,
                    reason            TEXT,
                    proofs            TEXT,
                    status            TEXT DEFAULT "pending",
                    added_by          INTEGER,
                    checked_by        INTEGER,
                    created_at        TEXT,
                    checked_at        TEXT,
                    FOREIGN KEY (added_by) REFERENCES users(user_id)
                );

                CREATE TABLE IF NOT EXISTS proofs (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    scammer_id  INTEGER,
                    proof_type  TEXT,
                    proof_data  TEXT,
                    uploaded_at TEXT,
                    FOREIGN KEY (scammer_id) REFERENCES scammers(id)
                );

                CREATE TABLE IF NOT EXISTS stats (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    command      TEXT,
                    user_id      INTEGER,
                    search_query TEXT,
                    timestamp    TEXT
                );

                CREATE TABLE IF NOT EXISTS mailings (
                    id               INTEGER PRIMARY KEY AUTOINCREMENT,
                    message          TEXT,
                    sent_by          INTEGER,
                    sent_at          TEXT,
                    recipients_count INTEGER DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS ban_list (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id    INTEGER UNIQUE,
                    reason     TEXT,
                    banned_by  INTEGER,
                    banned_at  TEXT
                );
            ''')

    # ══════════════════════════════════════════
    #                 ПОЛЬЗОВАТЕЛИ
    # ══════════════════════════════════════════

    def add_user(self, user_id: int, username: str = None,
                 first_name: str = None, last_name: str = None):
        now = datetime.now().isoformat()
        with self.get_connection() as conn:
            # Сохраняем is_admin/is_moder при повторном INSERT
            conn.execute('''
                INSERT INTO users (user_id, username, first_name, last_name,
                                   registered_date, last_activity)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    username      = excluded.username,
                    first_name    = excluded.first_name,
                    last_name     = excluded.last_name,
                    last_activity = excluded.last_activity
            ''', (user_id, username, first_name, last_name, now, now))

    def get_user(self, user_id: int) -> Optional[Dict]:
        with self.get_connection() as conn:
            row = conn.execute(
                'SELECT * FROM users WHERE user_id = ?', (user_id,)
            ).fetchone()
            return self._row_to_dict(row)

    def get_all_users(self) -> List[Dict]:
        with self.get_connection() as conn:
            rows = conn.execute('SELECT * FROM users').fetchall()
            return self._rows_to_list(rows)

    def get_all_users_not_banned(self) -> List[Dict]:
        with self.get_connection() as conn:
            rows = conn.execute(
                'SELECT * FROM users WHERE is_banned = 0'
            ).fetchall()
            return self._rows_to_list(rows)

    def set_admin(self, user_id: int, is_admin: bool = True):
        with self.get_connection() as conn:
            conn.execute(
                'UPDATE users SET is_admin = ? WHERE user_id = ?',
                (1 if is_admin else 0, user_id)
            )

    def set_moder(self, user_id: int, is_moder: bool = True):
        with self.get_connection() as conn:
            conn.execute(
                'UPDATE users SET is_moder = ? WHERE user_id = ?',
                (1 if is_moder else 0, user_id)
            )

    def ban_user(self, user_id: int, reason: str = '', banned_by: int = 0):
        now = datetime.now().isoformat()
        with self.get_connection() as conn:
            conn.execute(
                'UPDATE users SET is_banned = 1 WHERE user_id = ?', (user_id,)
            )
            conn.execute('''
                INSERT OR REPLACE INTO ban_list (user_id, reason, banned_by, banned_at)
                VALUES (?, ?, ?, ?)
            ''', (user_id, reason, banned_by, now))

    def unban_user(self, user_id: int):
        with self.get_connection() as conn:
            conn.execute(
                'UPDATE users SET is_banned = 0 WHERE user_id = ?', (user_id,)
            )
            conn.execute('DELETE FROM ban_list WHERE user_id = ?', (user_id,))

    def get_moderators(self) -> List[Dict]:
        with self.get_connection() as conn:
            rows = conn.execute(
                'SELECT * FROM users WHERE is_moder = 1'
            ).fetchall()
            return self._rows_to_list(rows)

    def is_banned(self, user_id: int) -> bool:
        user = self.get_user(user_id)
        return bool(user and user.get('is_banned'))

    def is_admin(self, user_id: int) -> bool:
        if user_id in Config.ADMIN_IDS:
            return True
        user = self.get_user(user_id)
        return bool(user and user.get('is_admin'))

    def is_moder(self, user_id: int) -> bool:
        user = self.get_user(user_id)
        return bool(user and (user.get('is_moder') or user.get('is_admin')))

    # ══════════════════════════════════════════
    #                 МОШЕННИКИ
    # ══════════════════════════════════════════

    def add_scammer(self, scammer_id: str, scammer_username: str,
                    scammer_name: str, reason: str, proofs: str,
                    added_by: int) -> int:
        now = datetime.now().isoformat()
        with self.get_connection() as conn:
            cur = conn.execute('''
                INSERT INTO scammers
                    (scammer_id, scammer_username, scammer_name,
                     reason, proofs, added_by, created_at, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, "pending")
            ''', (scammer_id, scammer_username, scammer_name,
                  reason, proofs, added_by, now))
            return cur.lastrowid

    def get_scammer(self, search_query: str) -> Optional[Dict]:
        q = search_query.lstrip('@')
        with self.get_connection() as conn:
            row = conn.execute('''
                SELECT * FROM scammers
                WHERE status = "approved"
                  AND (scammer_id = ?
                       OR LOWER(scammer_username) = LOWER(?)
                       OR LOWER(scammer_name)     = LOWER(?))
                LIMIT 1
            ''', (search_query, q, search_query)).fetchone()
            return self._row_to_dict(row)

    def get_pending_scammers(self) -> List[Dict]:
        with self.get_connection() as conn:
            rows = conn.execute(
                'SELECT * FROM scammers WHERE status = "pending" ORDER BY created_at DESC'
            ).fetchall()
            return self._rows_to_list(rows)

    def get_approved_scammers(self) -> List[Dict]:
        with self.get_connection() as conn:
            rows = conn.execute(
                'SELECT * FROM scammers WHERE status = "approved" ORDER BY created_at DESC'
            ).fetchall()
            return self._rows_to_list(rows)

    def count_pending_by_user(self, user_id: int) -> int:
        with self.get_connection() as conn:
            row = conn.execute(
                'SELECT COUNT(*) FROM scammers WHERE added_by = ? AND status = "pending"',
                (user_id,)
            ).fetchone()
            return row[0] if row else 0

    def update_scammer_status(self, scammer_id: int, status: str, checked_by: int):
        now = datetime.now().isoformat()
        with self.get_connection() as conn:
            conn.execute('''
                UPDATE scammers
                SET status = ?, checked_by = ?, checked_at = ?
                WHERE id = ?
            ''', (status, checked_by, now, scammer_id))

    def delete_scammer(self, scammer_id: int):
        with self.get_connection() as conn:
            conn.execute('DELETE FROM scammers WHERE id = ?', (scammer_id,))

    def search_scammers(self, query: str) -> List[Dict]:
        """Полнотекстовый поиск по одобренным записям"""
        q = f'%{query.lstrip("@")}%'
        with self.get_connection() as conn:
            rows = conn.execute('''
                SELECT * FROM scammers
                WHERE status = "approved"
                  AND (scammer_id       LIKE ?
                       OR scammer_username LIKE ?
                       OR scammer_name     LIKE ?
                       OR reason           LIKE ?)
                ORDER BY created_at DESC
                LIMIT 20
            ''', (q, q, q, q)).fetchall()
            return self._rows_to_list(rows)

    # ══════════════════════════════════════════
    #                 СТАТИСТИКА
    # ══════════════════════════════════════════

    def add_stat(self, command: str, user_id: int, search_query: str = None):
        with self.get_connection() as conn:
            conn.execute('''
                INSERT INTO stats (command, user_id, search_query, timestamp)
                VALUES (?, ?, ?, ?)
            ''', (command, user_id, search_query, datetime.now().isoformat()))

    def get_stats(self) -> Dict:
        with self.get_connection() as conn:
            today = date.today().isoformat()

            def q(sql, *args):
                return conn.execute(sql, args).fetchone()[0]

            return {
                'total_users':       q('SELECT COUNT(*) FROM users'),
                'total_scammers':    q('SELECT COUNT(*) FROM scammers'),
                'approved_scammers': q('SELECT COUNT(*) FROM scammers WHERE status="approved"'),
                'pending_scammers':  q('SELECT COUNT(*) FROM scammers WHERE status="pending"'),
                'rejected_scammers': q('SELECT COUNT(*) FROM scammers WHERE status="rejected"'),
                'total_searches':    q('SELECT COUNT(*) FROM stats WHERE command="search"'),
                'today_activity':    q('SELECT COUNT(*) FROM stats WHERE DATE(timestamp)=?', today),
                'today_searches':    q('SELECT COUNT(*) FROM stats WHERE command="search" AND DATE(timestamp)=?', today),
                'banned_users':      q('SELECT COUNT(*) FROM users WHERE is_banned=1'),
                'moderators':        q('SELECT COUNT(*) FROM users WHERE is_moder=1'),
            }

    # ══════════════════════════════════════════
    #                 РАССЫЛКИ
    # ══════════════════════════════════════════

    def add_mailing(self, message: str, sent_by: int, recipients_count: int):
        with self.get_connection() as conn:
            conn.execute('''
                INSERT INTO mailings (message, sent_by, sent_at, recipients_count)
                VALUES (?, ?, ?, ?)
            ''', (message, sent_by, datetime.now().isoformat(), recipients_count))

    def get_mailings(self, limit: int = 10) -> List[Dict]:
        with self.get_connection() as conn:
            rows = conn.execute(
                'SELECT * FROM mailings ORDER BY sent_at DESC LIMIT ?', (limit,)
            ).fetchall()
            return self._rows_to_list(rows)
