# database.py
import sqlite3
import json
from datetime import datetime
from typing import Optional, List, Dict, Any
from config import Config

class Database:
    def __init__(self):
        self.db_path = Config.DATABASE_URL.replace('sqlite:///', '')
        self.init_db()
    
    def get_connection(self):
        return sqlite3.connect(self.db_path)
    
    def init_db(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Таблица пользователей
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    last_name TEXT,
                    is_admin INTEGER DEFAULT 0,
                    is_moder INTEGER DEFAULT 0,
                    is_banned INTEGER DEFAULT 0,
                    registered_date TIMESTAMP,
                    last_activity TIMESTAMP
                )
            ''')
            
            # Таблица мошенников
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS scammers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    scammer_id TEXT,
                    scammer_username TEXT,
                    scammer_name TEXT,
                    reason TEXT,
                    proofs TEXT,
                    status TEXT DEFAULT 'pending',
                    added_by INTEGER,
                    checked_by INTEGER,
                    created_at TIMESTAMP,
                    checked_at TIMESTAMP
                )
            ''')
            
            # Таблица для доказательств
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS proofs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    scammer_id INTEGER,
                    proof_type TEXT,
                    proof_data TEXT,
                    uploaded_at TIMESTAMP,
                    FOREIGN KEY (scammer_id) REFERENCES scammers (id)
                )
            ''')
            
            # Таблица для статистики
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS stats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    command TEXT,
                    user_id INTEGER,
                    search_query TEXT,
                    timestamp TIMESTAMP
                )
            ''')
            
            # Таблица для рассылок
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS mailings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    message TEXT,
                    sent_by INTEGER,
                    sent_at TIMESTAMP,
                    recipients_count INTEGER
                )
            ''')
            
            conn.commit()
    
    # ========== РАБОТА С ПОЛЬЗОВАТЕЛЯМИ ==========
    
    def add_user(self, user_id: int, username: str = None, first_name: str = None, last_name: str = None):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO users 
                (user_id, username, first_name, last_name, registered_date, last_activity)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                user_id, username, first_name, last_name,
                datetime.now(), datetime.now()
            ))
            conn.commit()
    
    def get_user(self, user_id: int) -> Optional[Dict]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
            row = cursor.fetchone()
            if row:
                columns = [description[0] for description in cursor.description]
                return dict(zip(columns, row))
            return None
    
    def get_all_users(self) -> List[Dict]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM users')
            rows = cursor.fetchall()
            columns = [description[0] for description in cursor.description]
            return [dict(zip(columns, row)) for row in rows]
    
    def set_admin(self, user_id: int, is_admin: bool = True):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('UPDATE users SET is_admin = ? WHERE user_id = ?', (1 if is_admin else 0, user_id))
            conn.commit()
    
    def set_moder(self, user_id: int, is_moder: bool = True):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('UPDATE users SET is_moder = ? WHERE user_id = ?', (1 if is_moder else 0, user_id))
            conn.commit()
    
    def ban_user(self, user_id: int, ban: bool = True):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('UPDATE users SET is_banned = ? WHERE user_id = ?', (1 if ban else 0, user_id))
            conn.commit()
    
    # ========== РАБОТА С МОШЕННИКАМИ ==========
    
    def add_scammer(self, scammer_id: str, scammer_username: str, scammer_name: str, 
                   reason: str, proofs: str, added_by: int) -> int:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO scammers 
                (scammer_id, scammer_username, scammer_name, reason, proofs, added_by, created_at, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                scammer_id, scammer_username, scammer_name, reason, proofs, added_by,
                datetime.now(), 'pending'
            ))
            conn.commit()
            return cursor.lastrowid
    
    def get_scammer(self, search_query: str) -> Optional[Dict]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            # Ищем по ID или username
            cursor.execute('''
                SELECT * FROM scammers 
                WHERE (scammer_id = ? OR LOWER(scammer_username) = LOWER(?) OR LOWER(scammer_name) = LOWER(?))
                AND status = 'approved'
            ''', (search_query, search_query.replace('@', ''), search_query))
            row = cursor.fetchone()
            if row:
                columns = [description[0] for description in cursor.description]
                return dict(zip(columns, row))
            return None
    
    def get_pending_scammers(self) -> List[Dict]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM scammers WHERE status = "pending" ORDER BY created_at DESC')
            rows = cursor.fetchall()
            columns = [description[0] for description in cursor.description]
            return [dict(zip(columns, row)) for row in rows]
    
    def get_approved_scammers(self) -> List[Dict]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM scammers WHERE status = "approved" ORDER BY created_at DESC')
            rows = cursor.fetchall()
            columns = [description[0] for description in cursor.description]
            return [dict(zip(columns, row)) for row in rows]
    
    def update_scammer_status(self, scammer_id: int, status: str, checked_by: int):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE scammers 
                SET status = ?, checked_by = ?, checked_at = ?
                WHERE id = ?
            ''', (status, checked_by, datetime.now(), scammer_id))
            conn.commit()
    
    def delete_scammer(self, scammer_id: int):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM scammers WHERE id = ?', (scammer_id,))
            conn.commit()
    
    # ========== СТАТИСТИКА ==========
    
    def add_stat(self, command: str, user_id: int, search_query: str = None):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO stats (command, user_id, search_query, timestamp)
                VALUES (?, ?, ?, ?)
            ''', (command, user_id, search_query, datetime.now()))
            conn.commit()
    
    def get_stats(self) -> Dict:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Общая статистика
            cursor.execute('SELECT COUNT(*) FROM users')
            total_users = cursor.fetchone()[0]
            
            cursor.execute('SELECT COUNT(*) FROM scammers')
            total_scammers = cursor.fetchone()[0]
            
            cursor.execute('SELECT COUNT(*) FROM scammers WHERE status = "approved"')
            approved_scammers = cursor.fetchone()[0]
            
            cursor.execute('SELECT COUNT(*) FROM scammers WHERE status = "pending"')
            pending_scammers = cursor.fetchone()[0]
            
            cursor.execute('SELECT COUNT(*) FROM stats WHERE command = "search"')
            total_searches = cursor.fetchone()[0]
            
            cursor.execute('SELECT COUNT(*) FROM stats WHERE DATE(timestamp) = DATE("now")')
            today_activity = cursor.fetchone()[0]
            
            return {
                'total_users': total_users,
                'total_scammers': total_scammers,
                'approved_scammers': approved_scammers,
                'pending_scammers': pending_scammers,
                'total_searches': total_searches,
                'today_activity': today_activity
            }
    
    # ========== РАССЫЛКИ ==========
    
    def add_mailing(self, message: str, sent_by: int, recipients_count: int):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO mailings (message, sent_by, sent_at, recipients_count)
                VALUES (?, ?, ?, ?)
            ''', (message, sent_by, datetime.now(), recipients_count))
            conn.commit()