import os
import json
import logging
from datetime import datetime, timedelta
from flask import Flask, request, abort
from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    Configuration,
    ApiClient,
    MessagingApi,
    ReplyMessageRequest,
    PushMessageRequest,
    TextMessage,
    FlexMessage,
    FlexContainer,
)
from linebot.v3.webhooks import (
    MessageEvent,
    TextMessageContent,
    PostbackEvent,
)
from apscheduler.schedulers.background import BackgroundScheduler
import pytz

from db import (
    init_db,
    start_sleep,
    end_sleep,
    get_today_record,
    get_week_records,
    set_alarm,
    get_alarm,
    delete_alarm,
    set_bedtime_reminder,
    get_bedtime_reminder,
    get_all_alarms,
    get_all_bedtime_reminders,
)
from flex_messages import (
    build_main_menu,
    build_sleep_stats,
    build_week_report,
    build_sleep_tips,
    build_timer_status,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# 初始化資料庫（gunicorn 啟動時也會執行）
init_db()

configuration = Configuration(access_token=os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", ""))
handler = WebhookHandler(os.environ.get("LINE_CHANNEL_SECRET", ""))

TZ = pytz.timezone("Asia/Taipei")

# ── Scheduler ──────────────────────────────────────────────────────────────

scheduler = BackgroundScheduler(timezone=TZ)


def send_push(user_id: str, text: str):
    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)
        line_bot_api.push_message(
            PushMessageRequest(to=user_id, messages=[TextMessage(text=text)])
        )


def check_alarms():
    """每分鐘檢查是否有到期的鬧鐘/提醒"""
    now = datetime.now(TZ)
    current_time = now.strftime("%H:%M")

    for user_id, alarm_time in get_all_alarms():
        if alarm_time == current_time:
            send_push(
                user_id,
                f"⏰ 起床鬧鐘！\n現在是 {current_time}，該起床了！\n\n💪 美好的一天從現在開始！",
            )

    for user_id, reminder_time in get_all_bedtime_reminders():
        if reminder_time == current_time:
            send_push(
                user_id,
                f"🌙 睡前提醒！\n現在是 {current_time}，準備放鬆一下吧！\n\n😴 放下手機，讓身體休息～",
            )


scheduler.add_job(check_alarms, "cron", minute="*")
scheduler.start()

# ── Webhook ────────────────────────────────────────────────────────────────

@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers["X-Line-Signature"]
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return "OK"


@app.route("/", methods=["GET"])
def health():
    return "Sleep Bot is running! 😴"


# ── Message Handler ─────────────────────────────────────────────────────────

def reply(reply_token, messages):
    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)
        if not isinstance(messages, list):
            messages = [messages]
        line_bot_api.reply_message(
            ReplyMessageRequest(reply_token=reply_token, messages=messages)
        )


@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    user_id = event.source.user_id
    text = event.message.text.strip()
    token = event.reply_token
    now = datetime.now(TZ)

    # ── 主選單 ──
    if text in ["選單", "menu", "Menu", "開始", "start", "Start", "hello", "Hello", "嗨", "hi", "Hi"]:
        reply(token, FlexMessage(
            alt_text="睡眠小幫手 主選單",
            contents=FlexContainer.from_dict(build_main_menu()),
        ))

    # ── 開始睡眠計時 ──
    elif text in ["睡覺", "開始睡覺", "入睡", "zzz", "ZZZ"]:
        record = get_today_record(user_id)
        if record and record.get("sleep_start") and not record.get("sleep_end"):
            reply(token, TextMessage(text=(
                f"😴 你已經在計時了！\n"
                f"入睡時間：{record['sleep_start']}\n\n"
                "輸入「起床」來結束計時"
            )))
        else:
            start_sleep(user_id, now.isoformat())
            reply(token, TextMessage(text=(
                f"🌙 已開始記錄睡眠\n"
                f"入睡時間：{now.strftime('%H:%M')}\n\n"
                "輸入「起床」來結束睡眠計時 ⏰"
            )))

    # ── 結束睡眠計時 ──
    elif text in ["起床", "醒來", "起床了"]:
        record = get_today_record(user_id)
        if not record or not record.get("sleep_start"):
            reply(token, TextMessage(text="❌ 你還沒有開始睡眠計時喔！\n輸入「睡覺」開始記錄"))
        elif record.get("sleep_end"):
            reply(token, TextMessage(text="✅ 你今天的睡眠已經記錄完畢了！\n輸入「今日統計」查看詳情"))
        else:
            sleep_start = datetime.fromisoformat(record["sleep_start"])
            end_sleep(user_id, now.isoformat())
            duration = now - sleep_start
            hours = int(duration.total_seconds() // 3600)
            minutes = int((duration.total_seconds() % 3600) // 60)

            # 睡眠品質評估
            if hours >= 7:
                quality = "😊 優良！繼續保持！"
                emoji = "🌟"
            elif hours >= 6:
                quality = "😐 還不錯，但建議多休息一小時"
                emoji = "⚡"
            else:
                quality = "😔 睡眠不足，注意休息！"
                emoji = "⚠️"

            reply(token, TextMessage(text=(
                f"☀️ 早安！起床囉！\n\n"
                f"📊 今日睡眠報告\n"
                f"━━━━━━━━━━━━━━\n"
                f"🌙 入睡：{sleep_start.strftime('%H:%M')}\n"
                f"☀️ 起床：{now.strftime('%H:%M')}\n"
                f"⏱ 時長：{hours} 小時 {minutes} 分鐘\n"
                f"{emoji} 評估：{quality}\n\n"
                f"輸入「今日統計」或「週報告」查看更多"
            )))

    # ── 今日統計 ──
    elif text in ["今日統計", "今天", "統計", "紀錄"]:
        record = get_today_record(user_id)
        if not record or not record.get("sleep_start"):
            reply(token, TextMessage(text=(
                "📊 今天還沒有睡眠紀錄\n\n"
                "輸入「睡覺」開始記錄 🌙"
            )))
        else:
            flex = build_sleep_stats(record, now)
            reply(token, FlexMessage(
                alt_text="今日睡眠統計",
                contents=FlexContainer.from_dict(flex),
            ))

    # ── 週報告 ──
    elif text in ["週報告", "本週", "週統計", "week"]:
        records = get_week_records(user_id)
        flex = build_week_report(records, now)
        reply(token, FlexMessage(
            alt_text="本週睡眠報告",
            contents=FlexContainer.from_dict(flex),
        ))

    # ── 設定鬧鐘 ──
    elif text.startswith("鬧鐘 ") or text.startswith("設定鬧鐘 "):
        parts = text.split()
        time_str = parts[-1]
        try:
            alarm_dt = datetime.strptime(time_str, "%H:%M")
            set_alarm(user_id, time_str)
            reply(token, TextMessage(text=(
                f"⏰ 鬧鐘設定成功！\n"
                f"明天 {time_str} 會叫你起床 💪\n\n"
                "輸入「取消鬧鐘」可以刪除"
            )))
        except ValueError:
            reply(token, TextMessage(text=(
                "❌ 時間格式錯誤！\n\n"
                "請用 24 小時制，例如：\n"
                "鬧鐘 07:30\n"
                "鬧鐘 08:00"
            )))

    # ── 查看鬧鐘 ──
    elif text in ["查看鬧鐘", "鬧鐘"]:
        alarm = get_alarm(user_id)
        if alarm:
            reply(token, TextMessage(text=f"⏰ 目前鬧鐘：{alarm}\n\n輸入「取消鬧鐘」可以刪除"))
        else:
            reply(token, TextMessage(text="⏰ 目前沒有設定鬧鐘\n\n輸入「鬧鐘 HH:MM」來設定"))

    # ── 取消鬧鐘 ──
    elif text in ["取消鬧鐘", "刪除鬧鐘"]:
        delete_alarm(user_id)
        reply(token, TextMessage(text="⏰ 鬧鐘已取消！"))

    # ── 設定睡前提醒 ──
    elif text.startswith("睡前提醒 ") or text.startswith("就寢提醒 "):
        parts = text.split()
        time_str = parts[-1]
        try:
            datetime.strptime(time_str, "%H:%M")
            set_bedtime_reminder(user_id, time_str)
            reply(token, TextMessage(text=(
                f"🌙 睡前提醒設定成功！\n"
                f"每天 {time_str} 會提醒你準備睡覺 😴\n\n"
                "輸入「取消提醒」可以刪除"
            )))
        except ValueError:
            reply(token, TextMessage(text=(
                "❌ 時間格式錯誤！\n\n"
                "請用 24 小時制，例如：\n"
                "睡前提醒 22:30\n"
                "睡前提醒 23:00"
            )))

    # ── 查看睡前提醒 ──
    elif text in ["查看提醒", "睡前提醒"]:
        reminder = get_bedtime_reminder(user_id)
        if reminder:
            reply(token, TextMessage(text=f"🌙 睡前提醒：每天 {reminder}\n\n輸入「取消提醒」可以刪除"))
        else:
            reply(token, TextMessage(text="🌙 目前沒有設定睡前提醒\n\n輸入「睡前提醒 HH:MM」來設定"))

    # ── 取消睡前提醒 ──
    elif text in ["取消提醒", "刪除提醒"]:
        set_bedtime_reminder(user_id, None)
        reply(token, TextMessage(text="🌙 睡前提醒已取消！"))

    # ── 睡眠建議 ──
    elif text in ["睡眠建議", "建議", "tips", "小知識"]:
        flex = build_sleep_tips()
        reply(token, FlexMessage(
            alt_text="睡眠小知識",
            contents=FlexContainer.from_dict(flex),
        ))

    # ── 計時狀態 ──
    elif text in ["狀態", "計時狀態"]:
        record = get_today_record(user_id)
        flex = build_timer_status(record, now)
        reply(token, FlexMessage(
            alt_text="計時狀態",
            contents=FlexContainer.from_dict(flex),
        ))

    # ── 說明 ──
    elif text in ["說明", "幫助", "help", "Help", "指令"]:
        reply(token, TextMessage(text=(
            "😴 睡眠小幫手 使用說明\n"
            "━━━━━━━━━━━━━━━━━\n\n"
            "📱 快速選單\n"
            "「選單」→ 顯示主選單\n\n"
            "⏱ 睡眠計時\n"
            "「睡覺」→ 開始睡眠計時\n"
            "「起床」→ 結束計時＋看報告\n"
            "「狀態」→ 查看計時狀態\n\n"
            "📊 統計報告\n"
            "「今日統計」→ 今天睡眠資料\n"
            "「週報告」→ 本週睡眠趨勢\n\n"
            "⏰ 鬧鐘設定\n"
            "「鬧鐘 07:30」→ 設定鬧鐘\n"
            "「查看鬧鐘」→ 目前鬧鐘\n"
            "「取消鬧鐘」→ 刪除鬧鐘\n\n"
            "🌙 睡前提醒\n"
            "「睡前提醒 22:30」→ 設定提醒\n"
            "「查看提醒」→ 目前提醒\n"
            "「取消提醒」→ 刪除提醒\n\n"
            "💡 其他\n"
            "「睡眠建議」→ 睡眠小知識"
        )))

    else:
        reply(token, TextMessage(text=(
            "🌙 嗨！我是睡眠小幫手！\n\n"
            "輸入「選單」查看所有功能\n"
            "輸入「說明」查看指令列表 😴"
        )))


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
