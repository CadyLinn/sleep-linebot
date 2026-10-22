import os

# 只有在外部真的啟動 Firestore emulator 時，才跑 tests/test_db_emulator.py
REAL_EMULATOR = bool(os.environ.get("FIRESTORE_EMULATOR_HOST"))

os.environ.setdefault("LINE_CHANNEL_SECRET", "test-secret")
os.environ.setdefault("LINE_CHANNEL_ACCESS_TOKEN", "test-token")
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "demo-sleep-bot")
# 指向 emulator 讓 firestore.Client() 不需要 GCP 憑證；單元測試不會真的連線
os.environ.setdefault("FIRESTORE_EMULATOR_HOST", "localhost:65535")
