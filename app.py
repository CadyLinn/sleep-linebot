import os
import logging
from datetime import datetime, timedelta
from flask import Flask, request, abort
from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    Configuration, ApiClient, MessagingApi,
    ReplyMessageRequest, PushMessageRequest,
    TextMessage, FlexMessage, FlexContainer,
    QuickReply, QuickReplyItem, MessageAction,
)
from linebot.v3.webhooks import MessageEvent, TextMessageContent
from apscheduler.schedulers.background import BackgroundScheduler
import pytz

from db import (
    init_db, start_sleep, end_sleep, get_latest_record, get_week_records,
    set_alarm, get_alarm, delete_alarm, set_bedtime_reminder,
    get_bedtime_reminder, get_all_alarms, get_all_bedtime_reminders,
    set_pending, get_pending, clear_pending,
    increment_alarm_count, reset_alarm_count,
)
from flex_messages import (
    build_main_menu, build_sleep_stats, build_week_report,
    build_sleep_tips, build_timer_status, build_sleep_countdown,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# 初始化資料庫（gunicorn 啟動時也會執行）
init_db()

configuration = Configuration(access_token=os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", ""))
handler = WebhookHandler(os.environ.get("LINE_CHANNEL_SECRET", ""))
TZ = pytz.timezone("Asia/Taipei")

# 睡眠類型定義
SLEEP_TYPES = {
    "小睡": {"emoji": "💤", "label": "小睡（20-90分鐘）", "suggestion_hours": 0.5},
    "中睡": {"emoji": "😴", "label": "中睡（3-5小時）",  "suggestion_hours": 4},
    "大睡": {"emoji": "🛌", "label": "大睡（7-9小時）",  "suggestion_hours": 8},
}

ALARM_MESSAGES = [
    "⏰ 鬧鐘響了！該起床了！\n現在是 {time}，美好的一天開始了 💪",
    "⏰⏰ 還在睡嗎？快起床！\n已經 {time} 囉，別賴床～",
    "⏰⏰⏰ 最後一次提醒！！\n快起床！！！💥 今天的任務在等你！",
]

# ── Scheduler ──────────────────────────────────────────────────────────────

scheduler = BackgroundScheduler(timezone=TZ)


def send_push(user_id: str, text: str):
    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)
        line_bot_api.push_message(
            PushMessageRequest(to=user_id, messages=[TextMessage(text=text)])
        )


def check_alarms():
    now = datetime.now(TZ)
    current_time = now.strftime("%H:%M")

    for user_id, alarm_time, alarm_count in get_all_alarms():
        if alarm_time == current_time and alarm_count < 3:
            msg = ALARM_MESSAGES[alarm_count].format(time=current_time)
            send_push(user_id, msg)
            increment_alarm_count(user_id)
        # 過了鬧鐘時間後重置 count，讓隔天可以再響
        elif alarm_time != current_time and alarm_count > 0:
            # 只在整點後 5 分鐘重置，避免同分鐘重置
            reset_alarm_count(user_id)

    for user_id, reminder_time in get_all_bedtime_reminders():
        if reminder_time == current_time:
            send_push(
                user_id,
                f"🌙 睡前提醒！現在是 {current_time}\n準備放鬆一下，準備睡覺吧～ 😴",
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


# ── Helpers ─────────────────────────────────────────────────────────────────

def reply(reply_token, messages):
    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)
        if not isinstance(messages, list):
            messages = [messages]
        line_bot_api.reply_message(
            ReplyMessageRequest(reply_token=reply_token, messages=messages)
        )


def _parse_time(text: str):
    """嘗試解析 HH:MM 格式，成功回傳 time_str，失敗回傳 None"""
    text = text.strip()
    try:
        datetime.strptime(text, "%H:%M")
        return text
    except ValueError:
        return None


def _calc_sleep_hours(now: datetime, wake_time_str: str):
    """計算從現在到 wake_time_str 有多少小時可睡"""
    wake = datetime.strptime(wake_time_str, "%H:%M").replace(
        year=now.year, month=now.month, day=now.day, tzinfo=TZ
    )
    if wake <= now:
        wake += timedelta(days=1)
    delta = wake - now
    total_min = int(delta.total_seconds() / 60)
    h = total_min // 60
    m = total_min % 60
    return h, m, wake


def _sleep_type_quick_reply():
    return QuickReply(items=[
        QuickReplyItem(action=MessageAction(label="💤 小睡", text="小睡")),
        QuickReplyItem(action=MessageAction(label="😴 中睡", text="中睡")),
        QuickReplyItem(action=MessageAction(label="🛌 大睡", text="大睡")),
    ])


# ── Message Handler ─────────────────────────────────────────────────────────

@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    user_id = event.source.user_id
    text = event.message.text.strip()
    token = event.reply_token
    now = datetime.now(TZ)

    # ── 優先處理 pending 狀態（等待輸入起床時間）──
    pending_action, pending_sleep_type = get_pending(user_id)

    if pending_action == "waiting_wake_time":
        time_str = _parse_time(text)
        if time_str:
            clear_pending(user_id)
            h, m, wake_dt = _calc_sleep_hours(now, time_str)
            s_info = SLEEP_TYPES.get(pending_sleep_type, SLEEP_TYPES["大睡"])

            # 記錄睡眠
            start_sleep(user_id, now.isoformat(), sleep_type=pending_sleep_type, target_wake=time_str)

            # 自動設定鬧鐘
            set_alarm(user_id, time_str)

            flex = build_sleep_countdown(
                sleep_type=pending_sleep_type,
                sleep_type_info=s_info,
                start_time=now,
                wake_time=wake_dt,
                hours=h,
                minutes=m,
            )
            reply(token, FlexMessage(
                alt_text=f"{s_info['emoji']} 已開始{pending_sleep_type}，{time_str}叫你起床",
                contents=FlexContainer.from_dict(flex),
            ))
        else:
            reply(token, TextMessage(text=(
                "❌ 格式不對，請用 HH:MM\n\n"
                "例如：\n"
                "07:30\n"
                "08:00\n"
                "22:30"
            )))
        return

    if pending_action == "waiting_alarm_time":
        time_str = _parse_time(text)
        if time_str:
            clear_pending(user_id)
            set_alarm(user_id, time_str)
            reply(token, TextMessage(text=(
                f"⏰ 鬧鐘設定成功！\n"
                f"明天 {time_str} 會連響 3 次叫你起床 💪\n\n"
                "輸入「取消鬧鐘」可以刪除"
            )))
        else:
            reply(token, TextMessage(text="❌ 請輸入正確時間格式，例如：07:30"))
        return

    # ── 主選單 ──
    if text in ["選單", "menu", "Menu", "開始", "start", "嗨", "hi", "Hi", "hello", "Hello"]:
        reply(token, FlexMessage(
            alt_text="睡眠小幫手 主選單",
            contents=FlexContainer.from_dict(build_main_menu()),
        ))

    # ── 睡眠類型選擇 ──
    elif text in ["睡覺", "小睡", "中睡", "大睡"]:
        if text == "睡覺":
            # 問選哪種
            reply(token, TextMessage(
                text="你要睡哪種覺？😴",
                quick_reply=_sleep_type_quick_reply(),
            ))
        else:
            s_info = SLEEP_TYPES[text]
            set_pending(user_id, "waiting_wake_time", sleep_type=text)
            reply(token, TextMessage(text=(
                f"{s_info['emoji']} 選擇了【{s_info['label']}】\n\n"
                f"⏰ 你要幾點起床？\n"
                f"請輸入時間（24小時制）\n\n"
                f"例如：07:30"
            )))

    # ── 起床 ──
    elif text in ["起床", "醒來", "起床了"]:
        record = get_latest_record(user_id)
        if not record or not record.get("sleep_start"):
            reply(token, TextMessage(text="❌ 你還沒有開始睡眠計時喔！\n點選單的「小睡/中睡/大睡」開始記錄"))
        elif record.get("sleep_end"):
            reply(token, TextMessage(text="✅ 你今天的睡眠已記錄完畢！\n輸入「今日統計」查看詳情"))
        else:
            sleep_start = datetime.fromisoformat(record["sleep_start"]).astimezone(TZ)
            end_sleep(user_id, now.isoformat())
            delete_alarm(user_id)  # 起床後取消鬧鐘
            delta = now - sleep_start
            hours = int(delta.total_seconds() // 3600)
            minutes = int((delta.total_seconds() % 3600) // 60)
            sleep_type = record.get("sleep_type", "大睡")
            s_info = SLEEP_TYPES.get(sleep_type, SLEEP_TYPES["大睡"])

            if hours >= 7:
                quality, q_emoji = "優良！繼續保持！", "🌟"
            elif hours >= 4:
                quality, q_emoji = "不錯，身體有充電到", "⚡"
            elif hours >= 1:
                quality, q_emoji = "小憩一下，精神好一點了嗎？", "😌"
            else:
                quality, q_emoji = "睡太短了，有機會補眠吧", "⚠️"

            reply(token, TextMessage(text=(
                f"☀️ 早安！起床囉！\n\n"
                f"📊 {sleep_type}報告\n"
                f"━━━━━━━━━━━━━━\n"
                f"{s_info['emoji']} 類型：{sleep_type}\n"
                f"🌙 入睡：{sleep_start.strftime('%H:%M')}\n"
                f"☀️ 起床：{now.strftime('%H:%M')}\n"
                f"⏱ 時長：{hours} 小時 {minutes} 分鐘\n"
                f"{q_emoji} 評估：{quality}\n\n"
                f"輸入「今日統計」或「週報告」查看更多"
            )))

    # ── 今日統計 ──
    elif text in ["今日統計", "今天", "統計", "紀錄"]:
        record = get_latest_record(user_id)
        if not record or not record.get("sleep_start"):
            reply(token, TextMessage(text=(
                "📊 今天還沒有睡眠紀錄\n\n"
                "點選單選擇「小睡/中睡/大睡」開始記錄 🌙"
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
    elif text in ["鬧鐘", "設定鬧鐘", "查看鬧鐘"]:
        alarm = get_alarm(user_id)
        if alarm:
            reply(token, TextMessage(text=(
                f"⏰ 目前鬧鐘：{alarm}\n"
                f"到時間會連響 3 次！\n\n"
                "輸入「取消鬧鐘」可以刪除\n"
                "或輸入新時間重新設定，例如：鬧鐘 07:30"
            )))
        else:
            set_pending(user_id, "waiting_alarm_time")
            reply(token, TextMessage(text=(
                "⏰ 設定鬧鐘\n\n"
                "請輸入起床時間（24小時制）\n"
                "例如：07:30"
            )))

    elif text.startswith("鬧鐘 ") or text.startswith("設定鬧鐘 "):
        time_str = _parse_time(text.split()[-1])
        if time_str:
            set_alarm(user_id, time_str)
            reply(token, TextMessage(text=(
                f"⏰ 鬧鐘設定成功！\n"
                f"明天 {time_str} 會連響 3 次叫你起床 💪\n\n"
                "輸入「取消鬧鐘」可以刪除"
            )))
        else:
            reply(token, TextMessage(text="❌ 時間格式錯誤！例如：鬧鐘 07:30"))

    # ── 取消鬧鐘 ──
    elif text in ["取消鬧鐘", "刪除鬧鐘"]:
        delete_alarm(user_id)
        reply(token, TextMessage(text="⏰ 鬧鐘已取消！"))

    # ── 設定睡前提醒 ──
    elif text.startswith("睡前提醒 ") or text.startswith("就寢提醒 "):
        time_str = _parse_time(text.split()[-1])
        if time_str:
            set_bedtime_reminder(user_id, time_str)
            reply(token, TextMessage(text=(
                f"🌙 睡前提醒設定成功！\n"
                f"每天 {time_str} 會提醒你準備睡覺 😴\n\n"
                "輸入「取消提醒」可以刪除"
            )))
        else:
            reply(token, TextMessage(text="❌ 時間格式錯誤！例如：睡前提醒 22:30"))

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
        record = get_latest_record(user_id)
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
            "🛌 睡眠類型\n"
            "「小睡」→ 短暫休息 20-90 分\n"
            "「中睡」→ 補眠 3-5 小時\n"
            "「大睡」→ 完整睡眠 7-9 小時\n"
            "（選完後輸入起床時間）\n\n"
            "☀️ 起床\n"
            "「起床」→ 結束計時＋看報告\n\n"
            "📊 統計報告\n"
            "「統計」→ 今天睡眠資料\n"
            "「週報告」→ 本週睡眠趨勢\n\n"
            "⏰ 鬧鐘設定\n"
            "「鬧鐘 07:30」→ 設定鬧鐘\n"
            "（到時間連響 3 次）\n"
            "「取消鬧鐘」→ 刪除鬧鐘\n\n"
            "🌙 睡前提醒\n"
            "「睡前提醒 22:30」→ 設定提醒\n"
            "「取消提醒」→ 刪除提醒\n\n"
            "💡 其他\n"
            "「睡眠建議」→ 睡眠小知識\n"
            "「選單」→ 主選單"
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
