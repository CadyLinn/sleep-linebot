"""db.py 測試。

test_*_emulator 需要 Firestore emulator（CI 會啟動；本機見 README）：
    gcloud emulators firestore start --host-port=localhost:8681
    FIRESTORE_EMULATOR_HOST=localhost:8681 pytest
"""
import uuid
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest
from google.api_core.exceptions import FailedPrecondition

import db
from conftest import REAL_EMULATOR

emulator = pytest.mark.skipif(not REAL_EMULATOR, reason="需要 FIRESTORE_EMULATOR_HOST")


def test_index_missing_falls_back_to_full_scan(monkeypatch):
    query = MagicMock()
    query.stream.side_effect = FailedPrecondition("The query requires an index")
    scan = MagicMock()
    scan.stream.return_value = iter(["doc"])
    monkeypatch.setattr(db, "_user_records", lambda user_id: scan)

    assert db._stream_or_scan("u1", query) == (["doc"], True)


@pytest.fixture
def user_id():
    uid = f"test-{uuid.uuid4().hex}"
    yield uid
    db.full_reset(uid)


@emulator
def test_latest_record_and_end_sleep_emulator(user_id):
    now = datetime.now(db.TZ)
    db.start_sleep(user_id, (now - timedelta(hours=30)).isoformat(), "大睡")
    db.end_sleep(user_id, (now - timedelta(hours=22)).isoformat())
    db.start_sleep(user_id, (now - timedelta(minutes=20)).isoformat(), "小睡")

    latest = db.get_latest_record(user_id)
    assert latest["sleep_type"] == "小睡" and latest["sleep_end"] is None

    db.end_sleep(user_id, now.isoformat(), sleep_type="小睡")
    assert db.get_latest_record(user_id)["sleep_end"] == now.isoformat()
    assert not db.delete_latest_open_sleep(user_id)


@emulator
def test_today_and_week_records_emulator(user_id):
    now = datetime.now(db.TZ)
    for days in (0, 3, 10):
        db.start_sleep(user_id, (now - timedelta(days=days)).isoformat(), "中睡")

    assert len(db.get_today_records(user_id)) == 1
    assert len(db.get_week_records(user_id)) == 2

    db.reset_today_sleep(user_id)
    assert db.get_today_records(user_id) == []


@emulator
def test_alarm_roundtrip_emulator(user_id):
    db.set_alarm(user_id, "07:30", 3)
    alarm = db.get_alarm(user_id)
    assert alarm["alarm_date"] == db.next_alarm_date("07:30")
    assert alarm["alarm_repeat_total"] == 3

    minute = f"{alarm['alarm_date']} 07:30"
    assert db.claim_alarm_trigger(user_id, minute)
    assert not db.claim_alarm_trigger(user_id, minute)

    db.delete_alarm(user_id)
    assert db.get_alarm(user_id) is None
    assert user_id not in [row[0] for row in db.get_all_alarms()]
