"""模擬 LINE 使用者對 webhook 施壓。

服務端要用 LINE_DRY_RUN=1 + Firestore emulator 啟動（見 run_local.sh），
不然回覆會打到真的 LINE API、資料會寫進正式 Firestore。

環境變數：
  LINE_CHANNEL_SECRET   簽 webhook 用，要和服務端一致（預設 loadtest-secret）
  LOADTEST_USERS        使用者 ID 池大小，要和 seed.py 一致（預設 50）
  LOADTEST_P95_MS       p95 超過就讓 locust 以 exit code 1 結束（預設 1000）
  LOADTEST_MAX_FAIL     失敗率上限（預設 0.01）
"""
import base64
import hashlib
import hmac
import itertools
import json
import os
import time
import uuid

from locust import HttpUser, between, constant, events, task

SECRET = os.environ.get("LINE_CHANNEL_SECRET", "loadtest-secret")
USER_POOL = int(os.environ.get("LOADTEST_USERS", "50"))
P95_MS = float(os.environ.get("LOADTEST_P95_MS", "1000"))
MAX_FAIL = float(os.environ.get("LOADTEST_MAX_FAIL", "0.01"))

_user_ids = itertools.count()


def seeded_user_id(index: int) -> str:
    return f"Uloadtest{index:05d}"


def _signed_event(user_id: str, text: str):
    body = json.dumps({
        "destination": "Uloadtestbot",
        "events": [{
            "type": "message",
            "mode": "active",
            "timestamp": int(time.time() * 1000),
            "webhookEventId": uuid.uuid4().hex,
            "deliveryContext": {"isRedelivery": False},
            "replyToken": uuid.uuid4().hex,
            "source": {"type": "user", "userId": user_id},
            "message": {"id": uuid.uuid4().hex, "type": "text", "quoteToken": "q", "text": text},
        }],
    }, ensure_ascii=False)
    signature = base64.b64encode(hmac.new(SECRET.encode(), body.encode(), hashlib.sha256).digest()).decode()
    return body.encode(), {"X-Line-Signature": signature, "Content-Type": "application/json"}


class LineUser(HttpUser):
    wait_time = between(1, 3)

    def on_start(self):
        self.user_id = seeded_user_id(next(_user_ids) % USER_POOL)

    def say(self, text: str, name: str):
        body, headers = _signed_event(self.user_id, text)
        self.client.post("/callback", data=body, headers=headers, name=f"webhook: {name}")

    @task(3)
    def sleep_session(self):
        self.say("我要睡20分鐘", "start sleep")
        self.say("狀態", "status")
        self.say("起床", "wake up")

    @task(3)
    def today_stats(self):
        self.say("今日統計", "today stats")

    @task(2)
    def week_report(self):
        self.say("週報告", "week report")

    @task(2)
    def menu(self):
        self.say("選單", "menu")

    @task(1)
    def alarm(self):
        self.say("鬧鐘 07:30 3次", "set alarm")
        self.say("取消鬧鐘", "cancel alarm")

    @task(1)
    def sleep_cycle(self):
        self.say("睡眠週期", "sleep cycle")


class AlarmScheduler(HttpUser):
    """Cloud Scheduler 每分鐘打一次；這裡加快頻率看鬧鐘掃描在壓力下的延遲。"""
    fixed_count = 1
    wait_time = constant(5)

    @task
    def check_alarms(self):
        self.client.post("/tasks/check-alarms", name="task: check-alarms")


@events.quitting.add_listener
def _enforce_thresholds(environment, **_kwargs):
    total = environment.stats.total
    p95 = total.get_response_time_percentile(0.95)
    problems = []
    if total.fail_ratio > MAX_FAIL:
        problems.append(f"failure ratio {total.fail_ratio:.2%} > {MAX_FAIL:.2%}")
    if p95 and p95 > P95_MS:
        problems.append(f"p95 {p95:.0f}ms > {P95_MS:.0f}ms")
    if problems:
        print("LOAD TEST FAILED: " + "; ".join(problems))
        environment.process_exit_code = 1
    else:
        # locust 預設只要有一個失敗就回 1；在門檻內就視為通過
        environment.process_exit_code = 0
        print(f"LOAD TEST PASSED: p95={p95:.0f}ms fail_ratio={total.fail_ratio:.2%}")
