from datetime import datetime

import pytest

import app
from app import TZ


@pytest.mark.parametrize("text,expected", [
    ("10分鐘", 10),
    ("30min", 30),
    ("1小時", 60),
    ("1小時30分", 90),
    ("1.5小時", 90),
    ("我要睡20分鐘", 20),
    ("8", 480),
    ("90", 90),
    ("你好", None),
])
def test_parse_duration_to_minutes(text, expected):
    assert app._parse_duration_to_minutes(text) == expected


@pytest.mark.parametrize("text,sleep_type,expected", [
    ("10", "小睡", 10),
    ("4", "中睡", 240),
    ("8", "大睡", 480),
    ("30分鐘", "大睡", 30),
])
def test_parse_duration_for_sleep_type(text, sleep_type, expected):
    assert app._parse_duration_for_sleep_type(text, sleep_type) == expected


@pytest.mark.parametrize("text,expected", [
    ("07:30", "07:30"),
    ("0730", "07:30"),
    ("7點半", "07:30"),
    ("7點15分", "07:15"),
    ("現在睡 08:00 起床", "08:00"),
    ("沒有時間", None),
])
def test_parse_clock_time(text, expected):
    assert app._parse_clock_time(text) == expected


def test_parse_alarm_request_with_repeat():
    now = TZ.localize(datetime(2026, 10, 22, 23, 0))
    assert app._parse_alarm_request("鬧鐘 07:30 3次", now) == ("07:30", 3)
    assert app._parse_alarm_request("鬧鐘 30分鐘", now) == ("23:30", 1)


@pytest.mark.parametrize("minutes,expected", [(20, "小睡"), (90, "小睡"), (240, "中睡"), (480, "大睡")])
def test_auto_sleep_type(minutes, expected):
    assert app._auto_sleep_type(minutes) == expected


def test_calc_from_wake_time_rolls_to_tomorrow():
    now = TZ.localize(datetime(2026, 10, 22, 23, 0))
    hours, minutes, wake = app._calc_from_wake_time(now, "07:30")
    assert (hours, minutes) == (8, 30)
    assert wake.date().isoformat() == "2026-10-23"
