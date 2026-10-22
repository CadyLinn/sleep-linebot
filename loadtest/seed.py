"""在 Firestore emulator 灌入壓測用的歷史資料。

每位使用者有 RECORDS_PER_USER 筆過去的睡眠紀錄，用來反映長期使用者的查詢成本；
另外約 1/5 的使用者有鬧鐘，讓 /tasks/check-alarms 有東西可以掃。
"""
import os
import sys
from datetime import datetime, timedelta

from google.cloud import firestore
import pytz

if not os.environ.get("FIRESTORE_EMULATOR_HOST"):
    sys.exit("Refusing to seed: FIRESTORE_EMULATOR_HOST is not set (would write to a real project)")

TZ = pytz.timezone("Asia/Taipei")
USERS = int(os.environ.get("LOADTEST_USERS", "50"))
RECORDS_PER_USER = int(os.environ.get("RECORDS_PER_USER", "200"))


def seeded_user_id(index: int) -> str:
    # 要和 locustfile.seeded_user_id 一致（這裡不能 import locust，它會 monkey-patch gRPC）
    return f"Uloadtest{index:05d}"


def main():
    client = firestore.Client()
    now = datetime.now(TZ)
    batch, pending = client.batch(), 0

    def add(ref, data):
        nonlocal batch, pending
        batch.set(ref, data)
        pending += 1
        if pending == 500:
            batch.commit()
            batch, pending = client.batch(), 0

    for u in range(USERS):
        user_id = seeded_user_id(u)
        for i in range(RECORDS_PER_USER):
            start = now - timedelta(hours=12 * (i + 1))
            add(client.collection("sleep_records").document(), {
                "user_id": user_id,
                "date": start.strftime("%Y-%m-%d"),
                "sleep_type": "中睡",
                "sleep_start": start.isoformat(),
                "sleep_end": (start + timedelta(hours=4)).isoformat(),
                "target_wake": None,
            })
        if u % 5 == 0:
            alarm_at = now + timedelta(hours=1)
            add(client.collection("user_settings").document(user_id), {
                "alarm_time": alarm_at.strftime("%H:%M"),
                "alarm_date": alarm_at.strftime("%Y-%m-%d"),
                "alarm_count": 0,
                "alarm_repeat_total": 1,
            })
    if pending:
        batch.commit()
    print(f"Seeded {USERS} users x {RECORDS_PER_USER} records")


if __name__ == "__main__":
    main()
