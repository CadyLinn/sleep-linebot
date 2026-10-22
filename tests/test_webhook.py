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


SCHEDULER_SA = "alarm-scheduler@sleep-linebot.iam.gserviceaccount.com"
AUDIENCE = "https://sleep-linebot.example.run.app"


@pytest.fixture
def secured_task(client, monkeypatch):
    """開啟 OIDC 驗證；token 內容由 fake verifier 決定。"""
    monkeypatch.setattr(app, "TASKS_INVOKER_SA", SCHEDULER_SA)
    monkeypatch.setattr(app, "TASKS_AUDIENCE", AUDIENCE)
    checks = []
    monkeypatch.setattr(app, "check_alarms", lambda: checks.append(1))
    tokens = {
        "scheduler": {"email": SCHEDULER_SA, "email_verified": True},
        "other-sa": {"email": "someone@evil.iam.gserviceaccount.com", "email_verified": True},
    }

    def fake_verify(token, request, audience):
        assert audience == AUDIENCE
        if token not in tokens:
            raise ValueError("bad token")
        return tokens[token]

    monkeypatch.setattr(app.id_token, "verify_oauth2_token", fake_verify)
    client.checks = checks
    return client


@pytest.mark.parametrize("headers,expected", [
    ({}, 401),
    ({"Authorization": "Basic abc"}, 401),
    ({"Authorization": "Bearer forged"}, 401),
    ({"Authorization": "Bearer other-sa"}, 403),
])
def test_check_alarms_task_rejects_unauthorized(secured_task, headers, expected):
    assert secured_task.post("/tasks/check-alarms", headers=headers).status_code == expected
    assert secured_task.checks == []


def test_check_alarms_task_accepts_scheduler_token(secured_task):
    resp = secured_task.post("/tasks/check-alarms", headers={"Authorization": "Bearer scheduler"})
    assert resp.status_code == 200
    assert secured_task.checks == [1]
