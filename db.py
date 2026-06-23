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
            sleep_type TEXT,
            sleep_start TEXT,
            sleep_end TEXT,
            target_wake TEXT,
            UNIQUE(user_id, date)
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS user_settings (
            user_id TEXT PRIMARY KEY,
            alarm_time TEXT,
            alarm_count INTEGER DEFAULT 0,
            bedtime_reminder TEXT,
            pending_action TEXT,
            pending_sleep_type TEXT
        )
    """)
    conn.commit()
    conn.close()


# ── Sleep Records ──────────────────────────────────────────────────────────

def _today_str():
    return datetime.now(TZ).strftime("%Y-%m-%d")


def start_sleep(user_id: str, iso_time: str, sleep_type: str = "大睡", target_wake: str = None):
    date = datetime.fromisoformat(iso_time).astimezone(TZ).strftime("%Y-%m-%d")
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        INSERT INTO sleep_records (user_id, date, sleep_type, sleep_start, target_wake)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(user_id, date)
        DO UPDATE SET
            sleep_type=excluded.sleep_type,
            sleep_start=excluded.sleep_start,
            target_wake=excluded.target_wake,
            sleep_end=NULL
    """, (user_id, date, sleep_type, iso_time, target_wake))
    conn.commit()
    conn.close()


def end_sleep(user_id: str, iso_time: str):
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        UPDATE sleep_records SET sleep_end=?
        WHERE user_id=? AND sleep_end IS NULL
        ORDER BY date DESC LIMIT 1
    """, (iso_time, user_id))
    conn.commit()
    conn.close()


def get_latest_record(user_id: str):
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        SELECT * FROM sleep_records
        WHERE user_id=?
        ORDER BY date DESC LIMIT 1
    """, (user_id,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None


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


def set_pending(user_id: str, action: str, sleep_type: str = None):
    conn = get_conn()
    c = conn.cursor()
    _ensure_settings(c, user_id)
    c.execute("""
        UPDATE user_settings SET pending_action=?, pending_sleep_type=? WHERE user_id=?
    """, (action, sleep_type, user_id))
    conn.commit()
    conn.close()


def get_pending(user_id: str):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT pending_action, pending_sleep_type FROM user_settings WHERE user_id=?", (user_id,))
    row = c.fetchone()
    conn.close()
    if row:
        return row["pending_action"], row["pending_sleep_type"]
    return None, None


def clear_pending(user_id: str):
    conn = get_conn()
    c = conn.cursor()
    c.execute("UPDATE user_settings SET pending_action=NULL, pending_sleep_type=NULL WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()


def set_alarm(user_id: str, time_str: str):
    conn = get_conn()
    c = conn.cursor()
    _ensure_settings(c, user_id)
    c.execute("UPDATE user_settings SET alarm_time=?, alarm_count=0 WHERE user_id=?", (time_str, user_id))
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
    c.execute("UPDATE user_settings SET alarm_time=NULL, alarm_count=0 WHERE user_id=?", (user_id,))
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
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT user_id, alarm_time, alarm_count FROM user_settings WHERE alarm_time IS NOT NULL")
    rows = c.fetchall()
    conn.close()
    return [(r["user_id"], r["alarm_time"], r["alarm_count"]) for r in rows]


def increment_alarm_count(user_id: str):
    conn = get_conn()
    c = conn.cursor()
    c.execute("UPDATE user_settings SET alarm_count = alarm_count + 1 WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()


def reset_alarm_count(user_id: str):
    conn = get_conn()
    c = conn.cursor()
    c.execute("UPDATE user_settings SET alarm_count=0 WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()


def get_all_bedtime_reminders():
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT user_id, bedtime_reminder FROM user_settings WHERE bedtime_reminder IS NOT NULL")
    rows = c.fetchall()
    conn.close()
    return [(r["user_id"], r["bedtime_reminder"]) for r in rows]


# ── Reset Functions ────────────────────────────────────────────────────────

def reset_today_sleep(user_id: str):
    """清除今天（或最近未結束）的睡眠紀錄"""
    conn = get_conn()
    c = conn.cursor()
    # 刪除最近一筆未結束或今天的紀錄
    c.execute("""
        DELETE FROM sleep_records
        WHERE user_id=? AND id = (
            SELECT id FROM sleep_records WHERE user_id=? ORDER BY date DESC LIMIT 1
        )
    """, (user_id, user_id))
    conn.commit()
    conn.close()


def reset_all_settings(user_id: str):
    """清除鬧鐘、睡前提醒、pending 狀態"""
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        UPDATE user_settings
        SET alarm_time=NULL, alarm_count=0,
            bedtime_reminder=NULL,
            pending_action=NULL, pending_sleep_type=NULL
        WHERE user_id=?
    """, (user_id,))
    conn.commit()
    conn.close()


def full_reset(user_id: str):
    """完全重設：刪除所有睡眠紀錄＋所有設定"""
    conn = get_conn()
    c = conn.cursor()
    c.execute("DELETE FROM sleep_records WHERE user_id=?", (user_id,))
    c.execute("DELETE FROM user_settings WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()

