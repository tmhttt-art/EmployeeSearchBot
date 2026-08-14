import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("DATA_DIR", BASE_DIR)).resolve()
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_NAME = DATA_DIR / "bot.db"
ADMIN_ID = 126659379


def get_connection():
    return sqlite3.connect(DB_NAME)


@contextmanager
def connection():
    conn = get_connection()
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def init_db():
    with connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users(
                telegram_id INTEGER PRIMARY KEY,
                username TEXT,
                full_name TEXT,
                role TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS join_requests(
                telegram_id INTEGER PRIMARY KEY,
                username TEXT,
                full_name TEXT,
                request_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS search_logs(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER,
                searched_name TEXT,
                search_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS settings(
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)
        conn.execute(
            "INSERT OR IGNORE INTO settings (key, value) VALUES ('bot_enabled', '1')"
        )


def ensure_admin():
    if get_user(ADMIN_ID) is None:
        add_user(ADMIN_ID, "tmhttt", "Taha Muslim", role="Admin", status="Active")


def get_user(telegram_id):
    with connection() as conn:
        return conn.execute(
            "SELECT telegram_id, username, full_name, role, status FROM users WHERE telegram_id=?",
            (telegram_id,),
        ).fetchone()


def add_user(telegram_id, username, full_name, role="User", status="Active"):
    with connection() as conn:
        conn.execute("""
            INSERT INTO users (telegram_id, username, full_name, role, status)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(telegram_id) DO UPDATE SET
                username=excluded.username,
                full_name=excluded.full_name,
                role=excluded.role,
                status=excluded.status
        """, (telegram_id, username, full_name, role, status))


def add_join_request(telegram_id, username, full_name):
    with connection() as conn:
        cursor = conn.execute("""
            INSERT OR IGNORE INTO join_requests (telegram_id, username, full_name)
            VALUES (?, ?, ?)
        """, (telegram_id, username, full_name))
        return cursor.rowcount == 1


def delete_join_request(telegram_id):
    with connection() as conn:
        return conn.execute(
            "DELETE FROM join_requests WHERE telegram_id=?", (telegram_id,)
        ).rowcount == 1


def get_join_request(telegram_id):
    with connection() as conn:
        return conn.execute(
            "SELECT telegram_id, username, full_name, request_date FROM join_requests WHERE telegram_id=?",
            (telegram_id,),
        ).fetchone()


def list_join_requests(limit=30):
    with connection() as conn:
        return conn.execute("""
            SELECT telegram_id, username, full_name,
                   datetime(request_date, '+3 hours')
            FROM join_requests
            ORDER BY request_date ASC
            LIMIT ?
        """, (limit,)).fetchall()


def log_search(telegram_id, searched_name):
    with connection() as conn:
        conn.execute(
            "INSERT INTO search_logs (telegram_id, searched_name) VALUES (?, ?)",
            (telegram_id, searched_name),
        )


def list_users(limit=30):
    with connection() as conn:
        return conn.execute("""
            SELECT telegram_id, username, full_name, role, status, created_at
            FROM users
            ORDER BY CASE WHEN role='Admin' THEN 0 ELSE 1 END, created_at DESC
            LIMIT ?
        """, (limit,)).fetchall()


def get_active_user_ids():
    with connection() as conn:
        return [row[0] for row in conn.execute("""
            SELECT u.telegram_id FROM users u
            WHERE u.role='User' AND u.status='Active'
              AND NOT EXISTS (
                  SELECT 1 FROM join_requests j WHERE j.telegram_id=u.telegram_id
              )
            ORDER BY u.telegram_id
        """).fetchall()]


def get_join_reviewer_ids():
    with connection() as conn:
        return [row[0] for row in conn.execute("""
            SELECT telegram_id FROM users
            WHERE role IN ('Admin', 'Approver') AND status='Active'
            ORDER BY CASE WHEN role='Admin' THEN 0 ELSE 1 END, telegram_id
        """).fetchall()]


def get_user_statistics(telegram_id):
    with connection() as conn:
        total = conn.execute(
            "SELECT COUNT(*) FROM search_logs WHERE telegram_id=?", (telegram_id,)
        ).fetchone()[0]
        today = conn.execute("""
            SELECT COUNT(*) FROM search_logs
            WHERE telegram_id=?
              AND date(search_time, '+3 hours')=date('now', '+3 hours')
        """, (telegram_id,)).fetchone()[0]
        last_search = conn.execute("""
            SELECT searched_name, datetime(search_time, '+3 hours')
            FROM search_logs WHERE telegram_id=?
            ORDER BY id DESC LIMIT 1
        """, (telegram_id,)).fetchone()
    return {"total": total, "today": today, "last_search": last_search}


def set_user_status(telegram_id, status):
    if status not in {"Active", "Inactive"}:
        raise ValueError("Invalid user status")
    with connection() as conn:
        return conn.execute(
            "UPDATE users SET status=? WHERE telegram_id=? AND role!='Admin'",
            (status, telegram_id),
        ).rowcount == 1


def set_user_role(telegram_id, role):
    if role not in {"User", "Approver"}:
        raise ValueError("Invalid user role")
    with connection() as conn:
        return conn.execute(
            "UPDATE users SET role=? WHERE telegram_id=? AND role!='Admin'",
            (role, telegram_id),
        ).rowcount == 1


def delete_user_completely(telegram_id):
    with connection() as conn:
        user = conn.execute(
            "SELECT role FROM users WHERE telegram_id=?", (telegram_id,)
        ).fetchone()
        if user is None or user[0] == "Admin":
            return False
        conn.execute("DELETE FROM join_requests WHERE telegram_id=?", (telegram_id,))
        conn.execute("DELETE FROM search_logs WHERE telegram_id=?", (telegram_id,))
        conn.execute("DELETE FROM users WHERE telegram_id=?", (telegram_id,))
        return True


def get_recent_searches(limit=20):
    with connection() as conn:
        return conn.execute("""
            SELECT l.telegram_id, COALESCE(u.full_name, '-'), l.searched_name,
                   datetime(l.search_time, '+3 hours')
            FROM search_logs l
            LEFT JOIN users u ON u.telegram_id=l.telegram_id
            ORDER BY l.id DESC
            LIMIT ?
        """, (limit,)).fetchall()


def get_statistics():
    with connection() as conn:
        active_users = conn.execute(
            "SELECT COUNT(*) FROM users WHERE status='Active'"
        ).fetchone()[0]
        inactive_users = conn.execute(
            "SELECT COUNT(*) FROM users WHERE status='Inactive'"
        ).fetchone()[0]
        pending_requests = conn.execute(
            "SELECT COUNT(*) FROM join_requests"
        ).fetchone()[0]
        total_searches = conn.execute(
            "SELECT COUNT(*) FROM search_logs"
        ).fetchone()[0]
        today_searches = conn.execute("""
            SELECT COUNT(*) FROM search_logs
            WHERE date(search_time, '+3 hours')=date('now', '+3 hours')
        """).fetchone()[0]
        unique_searchers = conn.execute(
            "SELECT COUNT(DISTINCT telegram_id) FROM search_logs"
        ).fetchone()[0]
        top_search = conn.execute("""
            SELECT searched_name, COUNT(*) AS total
            FROM search_logs
            GROUP BY searched_name
            ORDER BY total DESC, searched_name
            LIMIT 1
        """).fetchone()
    return {
        "active_users": active_users,
        "inactive_users": inactive_users,
        "pending_requests": pending_requests,
        "total_searches": total_searches,
        "today_searches": today_searches,
        "unique_searchers": unique_searchers,
        "top_search": top_search,
    }


def get_setting(key, default=None):
    with connection() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return row[0] if row else default


def set_setting(key, value):
    with connection() as conn:
        conn.execute("""
            INSERT INTO settings (key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value
        """, (key, str(value)))


def is_bot_enabled():
    return get_setting("bot_enabled", "1") == "1"


if __name__ == "__main__":
    init_db()
    ensure_admin()
    print("Database Ready")
