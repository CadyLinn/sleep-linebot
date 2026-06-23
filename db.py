import sqlite3
import os
from datetime import datetime, timedelta
import pytz

DB_PATH = os.environ.get("DB_PATH", "sleep_bot.db")
TZ = pytz.timezone("Asia/Taipei")


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS sleep_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            date TEXT NOT NULL,
            sleep_start TEXT,
            sleep_end TEXT,
            UNIQUE(user_id, date)
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS user_settings (
            user_id TEXT PRIMARY KEY,
            alarm_time TEXT,
            bedtime_reminder TEXT
        )
    """)
    conn.commit()
    conn.close()


# ── Sleep Records ──────────────────────────────────────────────────────────

def _today_str():
    return datetime.now(TZ).strftime("%Y-%m-%d")


def start_sleep(user_id: str, iso_time: str):
    date = datetime.fromisoformat(iso_time).astimezone(TZ).strftime("%Y-%m-%d")
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        INSERT INTO sleep_records (user_id, date, sleep_start)
        VALUES (?, ?, ?)
        ON CONFLICT(user_id, date)
        DO UPDATE SET sleep_start=excluded.sleep_start, sleep_end=NULL
    """, (user_id, date, iso_time))
    conn.commit()
    conn.close()


def end_sleep(user_id: str, iso_time: str):
    date = _today_str()
    # If sleeping after midnight, the record might be from yesterday
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        UPDATE sleep_records SET sleep_end=?
        WHERE user_id=? AND sleep_end IS NULL
        ORDER BY date DESC LIMIT 1
    """, (iso_time, user_id))
    conn.commit()
    conn.close()


def get_today_record(user_id: str):
    conn = get_conn()
    c = conn.cursor()
    # Get the most recent unfinished OR today's record
    c.execute("""
        SELECT * FROM sleep_records
        WHERE user_id=?
        ORDER BY date DESC LIMIT 1
    """, (user_id,))
    row = c.fetchone()
    conn.close()
    if row:
        return dict(row)
    return None


def get_week_records(user_id: str):
    conn = get_conn()
    c = conn.cursor()
    today = datetime.now(TZ).date()
    week_ago = today - timedelta(days=6)
    c.execute("""
        SELECT * FROM sleep_records
        WHERE user_id=? AND date >= ?
        ORDER BY date ASC
    """, (user_id, week_ago.isoformat()))
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── User Settings ──────────────────────────────────────────────────────────

def _ensure_settings(cursor, user_id):
    cursor.execute("""
        INSERT OR IGNORE INTO user_settings (user_id) VALUES (?)
    """, (user_id,))


def set_alarm(user_id: str, time_str: str):
    conn = get_conn()
    c = conn.cursor()
    _ensure_settings(c, user_id)
    c.execute("UPDATE user_settings SET alarm_time=? WHERE user_id=?", (time_str, user_id))
    conn.commit()
    conn.close()


def get_alarm(user_id: str):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT alarm_time FROM user_settings WHERE user_id=?", (user_id,))
    row = c.fetchone()
    conn.close()
    return row["alarm_time"] if row else None


def delete_alarm(user_id: str):
    conn = get_conn()
    c = conn.cursor()
    c.execute("UPDATE user_settings SET alarm_time=NULL WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()


def set_bedtime_reminder(user_id: str, time_str):
    conn = get_conn()
    c = conn.cursor()
    _ensure_settings(c, user_id)
    c.execute("UPDATE user_settings SET bedtime_reminder=? WHERE user_id=?", (time_str, user_id))
    conn.commit()
    conn.close()


def get_bedtime_reminder(user_id: str):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT bedtime_reminder FROM user_settings WHERE user_id=?", (user_id,))
    row = c.fetchone()
    conn.close()
    return row["bedtime_reminder"] if row else None


def get_all_alarms():
    """Return list of (user_id, alarm_time) for all users with alarm set"""
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT user_id, alarm_time FROM user_settings WHERE alarm_time IS NOT NULL")
    rows = c.fetchall()
    conn.close()
    return [(r["user_id"], r["alarm_time"]) for r in rows]


def get_all_bedtime_reminders():
    """Return list of (user_id, bedtime_reminder) for all users with reminder set"""
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT user_id, bedtime_reminder FROM user_settings WHERE bedtime_reminder IS NOT NULL")
    rows = c.fetchall()
    conn.close()
    return [(r["user_id"], r["bedtime_reminder"]) for r in rows]
