"""鬧鐘排程測試：鬧鐘是一次性的，響完不能隔天同一時間又響。"""
from datetime import datetime, timedelta

import pytest

import app
import db
from app import TZ


class FakeAlarmStore:
    """模擬 db.py 裡鬧鐘相關欄位的行為。"""

    def __init__(self):
        self.users = {}
        self.pushes = []

    def set_alarm(self, user_id, time_str, repeat_total=1, now=None, alarm_date="auto"):
        self.users[user_id] = {
            "alarm_time": time_str,
            "alarm_date": db.next_alarm_date(time_str, now) if alarm_date == "auto" else alarm_date,
            "alarm_count": 0,
            "alarm_repeat_total": repeat_total,
            "alarm_last_trigger_date": None,
            "alarm_last_trigger_minute": None,
        }

    def get_all_alarms(self):
        return [
            (uid, d["alarm_time"], d.get("alarm_date"), d["alarm_count"], d["alarm_repeat_total"],
             d["alarm_last_trigger_date"], d["alarm_last_trigger_minute"])
            for uid, d in self.users.items() if d.get("alarm_time")
        ]

    def delete_alarm(self, user_id):
        self.users[user_id].update(alarm_time=None, alarm_date=None, alarm_count=0)

    def claim_alarm_trigger(self, user_id, minute):
        d = self.users[user_id]
        if d["alarm_last_trigger_minute"] == minute:
            return False
        d["alarm_count"] += 1
        d["alarm_last_trigger_date"] = minute.split(" ")[0]
        d["alarm_last_trigger_minute"] = minute
        return True

    def send_push(self, user_id, text, quick_reply=None):
        self.pushes.append((user_id, text))


@pytest.fixture
def store(monkeypatch):
    s = FakeAlarmStore()
    for name in ("get_all_alarms", "delete_alarm", "claim_alarm_trigger", "send_push"):
        monkeypatch.setattr(app, name, getattr(s, name))
    return s


def at(text):
    return TZ.localize(datetime.strptime(text, "%Y-%m-%d %H:%M"))


def run_minutes(start, minutes):
    for i in range(minutes):
        app.check_alarms(start + timedelta(minutes=i))


def test_alarm_rings_once_and_not_again_next_day(store):
    store.set_alarm("u1", "07:30", 1, now=at("2026-10-21 23:00"))
    run_minutes(at("2026-10-22 07:28"), 5)
    assert len(store.pushes) == 1
    assert store.users["u1"]["alarm_time"] is None

    # 隔天、後天同一時間都不能再響
    run_minutes(at("2026-10-23 07:28"), 5)
    run_minutes(at("2026-10-24 07:28"), 5)
    assert len(store.pushes) == 1


def test_repeat_three_times_then_cleared(store):
    store.set_alarm("u1", "07:30", 3, now=at("2026-10-22 06:00"))
    run_minutes(at("2026-10-22 07:29"), 6)
    assert [t.split("\n")[0] for _, t in store.pushes] == [
        "⏰ 鬧鐘響了！該起床了！", "⏰⏰ 還在睡嗎？快起床！", "⏰⏰⏰ 最後一次提醒！！",
    ]
    run_minutes(at("2026-10-23 07:29"), 6)
    assert len(store.pushes) == 3


def test_alarm_for_tomorrow_does_not_ring_today(store):
    # 晚上 08:00 設 07:30 的鬧鐘 → 是明天早上，不是今天
    store.set_alarm("u1", "07:30", 1, now=at("2026-10-22 08:00"))
    assert store.users["u1"]["alarm_date"] == "2026-10-23"
    run_minutes(at("2026-10-22 08:00"), 3)
    assert store.pushes == []
    app.check_alarms(at("2026-10-23 07:30"))
    assert len(store.pushes) == 1


def test_repeat_across_midnight(store):
    store.set_alarm("u1", "23:59", 3, now=at("2026-10-22 22:00"))
    run_minutes(at("2026-10-22 23:58"), 5)
    assert len(store.pushes) == 3


def test_missed_first_minute_still_rings(store):
    store.set_alarm("u1", "07:30", 3, now=at("2026-10-22 06:00"))
    app.check_alarms(at("2026-10-22 07:31"))  # 07:30 那次排程沒跑到
    assert len(store.pushes) == 1


def test_fully_missed_alarm_expires_instead_of_ringing_tomorrow(store):
    store.set_alarm("u1", "07:30", 1, now=at("2026-10-22 06:00"))
    app.check_alarms(at("2026-10-22 09:00"))  # 排程整段停掉後恢復
    assert store.pushes == []
    assert store.users["u1"]["alarm_time"] is None
    app.check_alarms(at("2026-10-23 07:30"))
    assert store.pushes == []


def test_same_minute_runs_twice_rings_once(store):
    store.set_alarm("u1", "07:30", 3, now=at("2026-10-22 06:00"))
    app.check_alarms(at("2026-10-22 07:30"))
    app.check_alarms(at("2026-10-22 07:30"))
    assert len(store.pushes) == 1


def test_legacy_leftover_alarm_is_removed_without_ringing(store):
    # 修 bug 前留下的鬧鐘：沒有 alarm_date，而且昨天已經響過
    store.set_alarm("u1", "07:30", 1, alarm_date=None)
    store.users["u1"].update(alarm_count=1, alarm_last_trigger_date="2026-10-21",
                             alarm_last_trigger_minute="2026-10-21 07:30")
    app.check_alarms(at("2026-10-22 07:30"))
    assert store.pushes == []
    assert store.users["u1"]["alarm_time"] is None


def test_legacy_pending_alarm_still_rings_once(store):
    # 舊資料、還沒響過、時間在今天稍晚 → 照常響一次，之後清掉
    store.set_alarm("u1", "07:30", 1, alarm_date=None)
    app.check_alarms(at("2026-10-22 06:00"))
    assert store.users["u1"]["alarm_time"] == "07:30"
    app.check_alarms(at("2026-10-22 07:30"))
    assert len(store.pushes) == 1
    app.check_alarms(at("2026-10-23 07:30"))
    assert len(store.pushes) == 1


def test_one_failing_push_does_not_block_other_users(store, monkeypatch):
    store.set_alarm("bad", "07:30", 1, now=at("2026-10-22 06:00"))
    store.set_alarm("good", "07:30", 1, now=at("2026-10-22 06:00"))

    def flaky_push(user_id, text, quick_reply=None):
        if user_id == "bad":
            raise RuntimeError("LINE API down")
        store.pushes.append((user_id, text))

    monkeypatch.setattr(app, "send_push", flaky_push)
    result = app.check_alarms(at("2026-10-22 07:30"))
    assert result == {"active": 2, "triggered": 1, "failed": 1}
    assert [u for u, _ in store.pushes] == ["good"]


@pytest.mark.parametrize("time_str,now,expected", [
    ("07:30", "2026-10-22 06:00", "2026-10-22"),
    ("07:30", "2026-10-22 07:29", "2026-10-22"),
    ("07:30", "2026-10-22 07:30", "2026-10-23"),
    ("07:30", "2026-10-22 23:00", "2026-10-23"),
    ("00:10", "2026-12-31 23:50", "2027-01-01"),
])
def test_next_alarm_date(time_str, now, expected):
    assert db.next_alarm_date(time_str, at(now)) == expected
