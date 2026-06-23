"""
db.py — Firestore 版本
在 Cloud Run 上自動使用 ADC（Application Default Credentials），
不需要 Service Account key 檔案。
"""
from datetime import datetime, timedelta
from google.cloud import firestore
import pytz

TZ = pytz.timezone("Asia/Taipei")

# Cloud Run 上自動使用 ADC，不需傳入 credentials
_db = firestore.Client()

# ── Collection refs ──────────────────────────────────────────────────────────

def _records_col():
    return _db.collection("sleep_records")

def _settings_col():
    return _db.collection("user_settings")

# ── Compat：init_db 保留空實作讓 app.py 不需改動 ────────────────────────────

def init_db():
    """Firestore 不需初始化，保留此函式維持介面相容"""
    pass

# ── Sleep Records ────────────────────────────────────────────────────────────

def _record_start(record: dict):
    try:
        return datetime.fromisoformat(record.get("sleep_start")).astimezone(TZ)
    except (TypeError, ValueError):
        return datetime.min.replace(tzinfo=TZ)


def start_sleep(user_id: str, iso_time: str, sleep_type: str = "大睡", target_wake: str = None):
    dt = datetime.fromisoformat(iso_time).astimezone(TZ)
    date = dt.strftime("%Y-%m-%d")
    doc_ref = _records_col().document()
    doc_ref.set({
        "user_id": user_id,
        "date": date,
        "sleep_type": sleep_type,
        "sleep_start": iso_time,
        "sleep_end": None,
        "target_wake": target_wake,
    })


def end_sleep(user_id: str, iso_time: str, sleep_type: str = None):
    """結束最近一筆未結束的睡眠紀錄"""
    open_docs = []
    for doc in _records_col().where("user_id", "==", user_id).stream():
        record = doc.to_dict()
        if record.get("sleep_start") and not record.get("sleep_end"):
            open_docs.append((doc, record))
    if open_docs:
        latest_doc, _ = max(open_docs, key=lambda item: _record_start(item[1]))
        fields = {"sleep_end": iso_time}
        if sleep_type:
            fields["sleep_type"] = sleep_type
        latest_doc.reference.update(fields)


def get_latest_record(user_id: str):
    """取得最近一筆睡眠紀錄"""
    records = [doc.to_dict() for doc in _records_col().where("user_id", "==", user_id).stream()]
    if not records:
        return None
    return max(records, key=_record_start)


def get_today_records(user_id: str):
    """取得今天所有睡眠紀錄"""
    today = datetime.now(TZ).date().isoformat()
    records = []
    for doc in _records_col().where("user_id", "==", user_id).stream():
        record = doc.to_dict()
        if record.get("date") == today:
            records.append(record)
    return sorted(records, key=_record_start)


def get_week_records(user_id: str):
    """取得最近 7 天的睡眠紀錄"""
    today = datetime.now(TZ).date()
    week_ago = (today - timedelta(days=6)).isoformat()
    records = []
    for doc in _records_col().where("user_id", "==", user_id).stream():
        record = doc.to_dict()
        if record.get("date") and record.get("date") >= week_ago:
            records.append(record)
    return sorted(records, key=_record_start)

# ── User Settings ────────────────────────────────────────────────────────────

def _settings_ref(user_id: str):
    return _settings_col().document(user_id)


def _get_settings(user_id: str) -> dict:
    doc = _settings_ref(user_id).get()
    return doc.to_dict() if doc.exists else {}


def _set_fields(user_id: str, fields: dict):
    _settings_ref(user_id).set(fields, merge=True)

# ── Pending State ────────────────────────────────────────────────────────────

def set_pending(user_id: str, action: str, sleep_type: str = None):
    _set_fields(user_id, {
        "pending_action": action,
        "pending_sleep_type": sleep_type,
    })


def get_pending(user_id: str):
    s = _get_settings(user_id)
    return s.get("pending_action"), s.get("pending_sleep_type")


def clear_pending(user_id: str):
    _set_fields(user_id, {
        "pending_action": None,
        "pending_sleep_type": None,
    })

# ── Alarm ────────────────────────────────────────────────────────────────────

def set_alarm(user_id: str, time_str: str, repeat_total: int = 1):
    repeat_total = max(1, min(int(repeat_total or 1), 10))
    _set_fields(user_id, {
        "alarm_time": time_str,
        "alarm_count": 0,
        "alarm_repeat_total": repeat_total,
        "alarm_last_trigger_date": None,
    })


def get_alarm(user_id: str):
    s = _get_settings(user_id)
    if not s.get("alarm_time"):
        return None
    return {
        "alarm_time": s.get("alarm_time"),
        "alarm_count": s.get("alarm_count", 0),
        "alarm_repeat_total": s.get("alarm_repeat_total", 1),
        "alarm_last_trigger_date": s.get("alarm_last_trigger_date"),
    }


def get_alarm_settings(user_id: str):
    return get_alarm(user_id)


def set_alarm_repeat(user_id: str, repeat_total: int):
    repeat_total = max(1, min(int(repeat_total or 1), 10))
    s = _get_settings(user_id)
    if not s.get("alarm_time"):
        return False
    _set_fields(user_id, {
        "alarm_repeat_total": repeat_total,
        "alarm_count": 0,
        "alarm_last_trigger_date": None,
    })
    return True


def delete_alarm(user_id: str):
    _set_fields(user_id, {
        "alarm_time": None,
        "alarm_count": 0,
        "alarm_last_trigger_date": None,
    })


def increment_alarm_count(user_id: str):
    today = datetime.now(TZ).date().isoformat()
    ref = _settings_ref(user_id)
    ref.update({
        "alarm_count": firestore.Increment(1),
        "alarm_last_trigger_date": today,
    })


def reset_alarm_count(user_id: str):
    _set_fields(user_id, {"alarm_count": 0})


def get_all_alarms():
    """回傳所有有設定鬧鐘的 (user_id, alarm_time, alarm_count, repeat_total, last_trigger_date)"""
    docs = _settings_col().where("alarm_time", "!=", None).stream()
    result = []
    for doc in docs:
        d = doc.to_dict()
        result.append((
            doc.id,
            d.get("alarm_time"),
            d.get("alarm_count", 0),
            d.get("alarm_repeat_total", 1),
            d.get("alarm_last_trigger_date"),
        ))
    return result

# ── Bedtime Reminder ─────────────────────────────────────────────────────────

def set_bedtime_reminder(user_id: str, time_str):
    _set_fields(user_id, {"bedtime_reminder": time_str})


def get_bedtime_reminder(user_id: str):
    return _get_settings(user_id).get("bedtime_reminder")


def get_all_bedtime_reminders():
    """回傳所有有設定睡前提醒的 (user_id, bedtime_reminder)"""
    docs = _settings_col().where("bedtime_reminder", "!=", None).stream()
    result = []
    for doc in docs:
        d = doc.to_dict()
        result.append((doc.id, d.get("bedtime_reminder")))
    return result

# ── Reset ────────────────────────────────────────────────────────────────────

def reset_today_sleep(user_id: str):
    """刪除最近一筆睡眠紀錄"""
    docs = []
    for doc in _records_col().where("user_id", "==", user_id).stream():
        record = doc.to_dict()
        if record.get("date") == datetime.now(TZ).date().isoformat():
            docs.append((doc, record))
    for doc, _ in docs:
        doc.reference.delete()


def reset_all_settings(user_id: str):
    """清除鬧鐘、睡前提醒、pending 狀態"""
    _set_fields(user_id, {
        "alarm_time": None,
        "alarm_count": 0,
        "alarm_repeat_total": 1,
        "alarm_last_trigger_date": None,
        "bedtime_reminder": None,
        "pending_action": None,
        "pending_sleep_type": None,
    })


def full_reset(user_id: str):
    """完全重設：刪除所有睡眠紀錄 + 設定"""
    # 刪除所有睡眠紀錄
    docs = _records_col().where("user_id", "==", user_id).stream()
    for doc in docs:
        doc.reference.delete()
    # 刪除設定文件
    _settings_ref(user_id).delete()
