import base64
import hashlib
import hmac
import json
from unittest.mock import MagicMock

import pytest

import app

SECRET = "test-secret"


def sign(body: str) -> str:
    digest = hmac.new(SECRET.encode(), body.encode(), hashlib.sha256).digest()
    return base64.b64encode(digest).decode()


def text_event(text, user_id="U123"):
    return json.dumps({
        "destination": "Ubot",
        "events": [{
            "type": "message",
            "mode": "active",
            "timestamp": 1761100000000,
            "webhookEventId": "01HTEST",
            "deliveryContext": {"isRedelivery": False},
            "replyToken": "reply-token",
            "source": {"type": "user", "userId": user_id},
            "message": {"id": "1", "type": "text", "quoteToken": "q", "text": text},
        }],
    })


@pytest.fixture
def client(monkeypatch):
    replies = []
    monkeypatch.setattr(app, "reply", lambda token, messages: replies.append(messages))
    monkeypatch.setattr(app, "get_pending", lambda user_id: (None, None))
    test_client = app.app.test_client()
    test_client.replies = replies
    return test_client


def test_health(client):
    resp = client.get("/")
    assert resp.status_code == 200


def test_callback_without_signature_is_rejected(client):
    assert client.post("/callback", data="{}").status_code == 400


def test_callback_with_bad_signature_is_rejected(client):
    body = text_event("說明")
    resp = client.post("/callback", data=body, headers={"X-Line-Signature": "bad"})
    assert resp.status_code == 400
    assert client.replies == []


def test_help_command_replies(client):
    body = text_event("說明")
    resp = client.post("/callback", data=body, headers={"X-Line-Signature": sign(body)})
    assert resp.status_code == 200
    assert "使用說明" in client.replies[0].text


def test_sleep_for_duration_starts_record_and_alarm(client, monkeypatch):
    start_sleep, set_alarm = MagicMock(), MagicMock()
    monkeypatch.setattr(app, "start_sleep", start_sleep)
    monkeypatch.setattr(app, "set_alarm", set_alarm)
    monkeypatch.setattr(app, "has_today_big_sleep", lambda *a, **k: False)

    body = text_event("我要睡20分鐘")
    resp = client.post("/callback", data=body, headers={"X-Line-Signature": sign(body)})

    assert resp.status_code == 200
    assert start_sleep.call_args.kwargs["sleep_type"] == "小睡"
    assert set_alarm.call_args.args[2] == 1


def test_check_alarms_task(client, monkeypatch):
    monkeypatch.setattr(app, "get_all_alarms", lambda: [])
    assert client.post("/tasks/check-alarms").status_code == 200
