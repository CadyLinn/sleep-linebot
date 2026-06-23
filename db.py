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
    _migrate_sleep_records_table(c)
    c.execute("""
        CREATE TABLE IF NOT EXISTS user_settings (
            user_id TEXT PRIMARY KEY,
            alarm_time TEXT,
            alarm_count INTEGER DEFAULT 0,
            alarm_repeat_total INTEGER DEFAULT 3,
            alarm_last_trigger_date TEXT,
            bedtime_reminder TEXT,
            pending_action TEXT,
            pending_sleep_type TEXT
        )
    """)
    _ensure_column(c, "user_settings", "alarm_repeat_total", "INTEGER DEFAULT 3")
    _ensure_column(c, "user_settings", "alarm_last_trigger_date", "TEXT")
    conn.commit()
    conn.close()


def _ensure_column(cursor, table, column, definition):
    cursor.execute(f"PRAGMA table_info({table})")
    columns = {row[1] for row in cursor.fetchall()}
    if column not in columns:
        cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def _migrate_sleep_records_table(cursor):
    """Remove the old one-record-per-day constraint while preserving records."""
    cursor.execute("PRAGMA index_list(sleep_records)")
    has_unique_index = any(row[2] for row in cursor.fetchall())
    if not has_unique_index:
        return

    cursor.execute("ALTER TABLE sleep_records RENAME TO sleep_records_old")
    cursor.execute("""
        CREATE TABLE sleep_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            date TEXT NOT NULL,
            sleep_type TEXT,
            sleep_start TEXT,
            sleep_end TEXT,
            target_wake TEXT
        )
    """)
    cursor.execute("""
        INSERT INTO sleep_records (id, user_id, date, sleep_type, sleep_start, sleep_end, target_wake)
        SELECT id, user_id, date, sleep_type, sleep_start, sleep_end, target_wake
        FROM sleep_records_old
    """)
    cursor.execute("DROP TABLE sleep_records_old")


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
    """, (user_id, date, sleep_type, iso_time, target_wake))
    conn.commit()
    conn.close()


def end_sleep(user_id: str, iso_time: str):
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        UPDATE sleep_records SET sleep_end=?
        WHERE id = (
            SELECT id FROM sleep_records
            WHERE user_id=? AND sleep_end IS NULL
            ORDER BY sleep_start DESC, id DESC LIMIT 1
        )
    """, (iso_time, user_id))
    conn.commit()
    conn.close()


def get_latest_record(user_id: str):
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        SELECT * FROM sleep_records
        WHERE user_id=?
        ORDER BY sleep_start DESC, id DESC LIMIT 1
    """, (user_id,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None


def get_today_records(user_id: str):
    conn = get_conn()
    c = conn.cursor()
    today = datetime.now(TZ).date()
    since = today - timedelta(days=1)
    c.execute("""
        SELECT * FROM sleep_records
        WHERE user_id=? AND date >= ?
        ORDER BY sleep_start ASC, id ASC
    """, (user_id, since.isoformat()))
    rows = c.fetchall()
    conn.close()
    records = [dict(r) for r in rows]
    return [
        record for record in records
        if _record_report_date(record) == today
        or _record_start_date(record) == today
    ]


def get_week_records(user_id: str):
    conn = get_conn()
    c = conn.cursor()
    today = datetime.now(TZ).date()
    week_ago = today - timedelta(days=6)
    fetch_from = week_ago - timedelta(days=1)
    c.execute("""
        SELECT * FROM sleep_records
        WHERE user_id=? AND date >= ?
        ORDER BY date ASC
    """, (user_id, fetch_from.isoformat()))
    rows = c.fetchall()
    conn.close()
    records = [dict(r) for r in rows]
    return [
        record for record in records
        if week_ago <= _record_report_date(record) <= today
    ]


def _record_start_date(record):
    if not record.get("sleep_start"):
        return None
    return datetime.fromisoformat(record["sleep_start"]).astimezone(TZ).date()


def _record_report_date(record):
    """Completed sleeps are reported on wake date; running sleeps stay on start date."""
    timestamp = record.get("sleep_end") or record.get("sleep_start")
    if not timestamp:
        return None
    return datetime.fromisoformat(timestamp).astimezone(TZ).date()


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


def set_alarm(user_id: str, time_str: str, repeat_total: int = 3):
    repeat_total = max(1, min(int(repeat_total or 3), 10))
    conn = get_conn()
    c = conn.cursor()
    _ensure_settings(c, user_id)
    c.execute("""
        UPDATE user_settings
        SET alarm_time=?, alarm_count=0, alarm_repeat_total=?, alarm_last_trigger_date=NULL
        WHERE user_id=?
    """, (time_str, repeat_total, user_id))
    conn.commit()
    conn.close()


def get_alarm(user_id: str):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT alarm_time FROM user_settings WHERE user_id=?", (user_id,))
    row = c.fetchone()
    conn.close()
    return row["alarm_time"] if row else None


def get_alarm_settings(user_id: str):
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        SELECT alarm_time, alarm_count, alarm_repeat_total, alarm_last_trigger_date
        FROM user_settings WHERE user_id=?
    """, (user_id,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None


def delete_alarm(user_id: str):
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        UPDATE user_settings
        SET alarm_time=NULL, alarm_count=0, alarm_last_trigger_date=NULL
        WHERE user_id=?
    """, (user_id,))
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
    c.execute("""
        SELECT user_id, alarm_time, alarm_count, alarm_repeat_total, alarm_last_trigger_date
        FROM user_settings WHERE alarm_time IS NOT NULL
    """)
    rows = c.fetchall()
    conn.close()
    return [
        (
            r["user_id"],
            r["alarm_time"],
            r["alarm_count"],
            r["alarm_repeat_total"] or 3,
            r["alarm_last_trigger_date"],
        )
        for r in rows
    ]


def increment_alarm_count(user_id: str):
    conn = get_conn()
    c = conn.cursor()
    today = datetime.now(TZ).date().isoformat()
    c.execute("""
        UPDATE user_settings
        SET alarm_count = alarm_count + 1, alarm_last_trigger_date=?
        WHERE user_id=?
    """, (today, user_id))
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
