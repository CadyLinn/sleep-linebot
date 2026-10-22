"""
db.py — Firestore 版本
在 Cloud Run 上自動使用 ADC（Application Default Credentials），
不需要 Service Account key 檔案。
"""
import logging
from datetime import datetime, timedelta
from google.api_core.exceptions import FailedPrecondition
from google.cloud import firestore
import pytz

TZ = pytz.timezone("Asia/Taipei")
logger = logging.getLogger(__name__)

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


def _user_records(user_id: str):
    return _records_col().where("user_id", "==", user_id)


def _stream_or_scan(user_id: str, query):
    """執行需要複合索引的查詢；索引尚未建立時退回掃描該使用者全部紀錄。

    回傳 (docs, scanned)：scanned=True 代表結果未經過濾/排序，呼叫端要自行處理。
    """
    try:
        return list(query.stream()), False
    except FailedPrecondition:
        logger.warning("Firestore composite index missing, falling back to full scan user_id=%s", user_id)
        return list(_user_records(user_id).stream()), True


def _latest_doc(user_id: str):
    query = _user_records(user_id).order_by("sleep_start", direction=firestore.Query.DESCENDING).limit(1)
    docs, _ = _stream_or_scan(user_id, query)
    return max(docs, key=lambda doc: _record_start(doc.to_dict()), default=None)


def _latest_open_doc(user_id: str):
    doc = _latest_doc(user_id)
    if not doc:
        return None
    record = doc.to_dict()
    if record.get("sleep_start") and not record.get("sleep_end"):
        return doc
    return None


def _today_docs(user_id: str):
    today = datetime.now(TZ).date().isoformat()
    return list(_user_records(user_id).where("date", "==", today).stream())


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
    """結束最近一筆睡眠紀錄（若它還在進行中）"""
    latest_doc = _latest_open_doc(user_id)
    if latest_doc:
        fields = {"sleep_end": iso_time}
        if sleep_type:
            fields["sleep_type"] = sleep_type
        latest_doc.reference.update(fields)


def get_latest_record(user_id: str):
    """取得最近一筆睡眠紀錄"""
    doc = _latest_doc(user_id)
    return doc.to_dict() if doc else None


def get_today_records(user_id: str):
    """取得今天所有睡眠紀錄"""
    records = [doc.to_dict() for doc in _today_docs(user_id)]
    return sorted(records, key=_record_start)


def has_today_big_sleep(user_id: str, include_open: bool = True):
    """今天是否已有大睡紀錄。"""
    for record in get_today_records(user_id):
        if record.get("sleep_type") != "大睡":
            continue
        if include_open or record.get("sleep_end"):
            return True
    return False


def get_week_records(user_id: str):
    """取得最近 7 天的睡眠紀錄"""
    today = datetime.now(TZ).date()
    week_ago = (today - timedelta(days=6)).isoformat()
    docs, _ = _stream_or_scan(user_id, _user_records(user_id).where("date", ">=", week_ago))
    records = [doc.to_dict() for doc in docs]
    records = [r for r in records if r.get("date") and r["date"] >= week_ago]
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

def next_alarm_date(time_str: str, now: datetime = None) -> str:
    """鬧鐘是一次性的：還沒到的時間排今天，已過（含這一分鐘）排明天。"""
    now = now or datetime.now(TZ)
    day = now.date() if time_str > now.strftime("%H:%M") else now.date() + timedelta(days=1)
    return day.isoformat()


def set_alarm(user_id: str, time_str: str, repeat_total: int = 1):
    repeat_total = max(1, min(int(repeat_total or 1), 3))
    _set_fields(user_id, {
        "alarm_time": time_str,
        "alarm_date": next_alarm_date(time_str),
        "alarm_count": 0,
        "alarm_repeat_total": repeat_total,
        "alarm_last_trigger_date": None,
        "alarm_last_trigger_minute": None,
    })


def get_alarm(user_id: str):
    s = _get_settings(user_id)
    if not s.get("alarm_time"):
        return None
    return {
        "alarm_time": s.get("alarm_time"),
        "alarm_date": s.get("alarm_date"),
        "alarm_count": s.get("alarm_count", 0),
        "alarm_repeat_total": s.get("alarm_repeat_total", 1),
        "alarm_last_trigger_date": s.get("alarm_last_trigger_date"),
        "alarm_last_trigger_minute": s.get("alarm_last_trigger_minute"),
    }


def get_alarm_settings(user_id: str):
    return get_alarm(user_id)


def set_alarm_repeat(user_id: str, repeat_total: int):
    repeat_total = max(1, min(int(repeat_total or 1), 3))
    s = _get_settings(user_id)
    if not s.get("alarm_time"):
        return False
    _set_fields(user_id, {
        "alarm_repeat_total": repeat_total,
        "alarm_count": 0,
        "alarm_last_trigger_date": None,
        "alarm_last_trigger_minute": None,
    })
    return True


def delete_alarm(user_id: str):
    _set_fields(user_id, {
        "alarm_time": None,
        "alarm_date": None,
        "alarm_count": 0,
        "alarm_last_trigger_date": None,
        "alarm_last_trigger_minute": None,
    })


def increment_alarm_count(user_id: str):
    now = datetime.now(TZ)
    today = now.date().isoformat()
    ref = _settings_ref(user_id)
    ref.update({
        "alarm_count": firestore.Increment(1),
        "alarm_last_trigger_date": today,
        "alarm_last_trigger_minute": now.strftime("%Y-%m-%d %H:%M"),
    })


def claim_alarm_trigger(user_id: str, trigger_minute: str):
    """用 transaction 確保同一位使用者同一分鐘只會觸發一次鬧鐘。"""
    transaction = _db.transaction()
    ref = _settings_ref(user_id)

    @firestore.transactional
    def _claim(tx):
        doc = ref.get(transaction=tx)
        data = doc.to_dict() if doc.exists else {}
        if data.get("alarm_last_trigger_minute") == trigger_minute:
            return False
        tx.update(ref, {
            "alarm_count": firestore.Increment(1),
            "alarm_last_trigger_date": trigger_minute.split(" ")[0],
            "alarm_last_trigger_minute": trigger_minute,
        })
        return True

    return _claim(transaction)


def reset_alarm_count(user_id: str):
    _set_fields(user_id, {"alarm_count": 0})


def get_all_alarms():
    """回傳所有有設定鬧鐘的 (user_id, alarm_time, alarm_date, alarm_count, repeat_total, last_trigger_date, last_trigger_minute)"""
    docs = _settings_col().where("alarm_time", "!=", None).stream()
    result = []
    for doc in docs:
        d = doc.to_dict()
        result.append((
            doc.id,
            d.get("alarm_time"),
            d.get("alarm_date"),
            d.get("alarm_count", 0),
            d.get("alarm_repeat_total", 1),
            d.get("alarm_last_trigger_date"),
            d.get("alarm_last_trigger_minute"),
        ))
    return result

# ── Bedtime Reminder ─────────────────────────────────────────────────────────

# ── Reset ────────────────────────────────────────────────────────────────────

def reset_today_sleep(user_id: str):
    """刪除最近一筆睡眠紀錄"""
    for doc in _today_docs(user_id):
        doc.reference.delete()


def delete_latest_open_sleep(user_id: str):
    """刪除目前進行中的最新睡眠紀錄。"""
    latest_doc = _latest_open_doc(user_id)
    if not latest_doc:
        return False
    latest_doc.reference.delete()
    return True


def reset_all_settings(user_id: str):
    """清除鬧鐘、互動狀態，並移除舊提醒欄位"""
    _set_fields(user_id, {
        "alarm_time": None,
        "alarm_date": None,
        "alarm_count": 0,
        "alarm_repeat_total": 1,
        "alarm_last_trigger_date": None,
        "alarm_last_trigger_minute": None,
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
