import os
import re
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
from linebot.v3.webhooks import FollowEvent, MessageEvent, TextMessageContent
from apscheduler.schedulers.background import BackgroundScheduler
import pytz

from db import (
    init_db, start_sleep, end_sleep, get_latest_record, get_today_records, get_week_records,
    set_alarm, get_alarm, delete_alarm, set_bedtime_reminder,
    get_bedtime_reminder, get_all_alarms, get_all_bedtime_reminders,
    set_pending, get_pending, clear_pending,
    increment_alarm_count, reset_alarm_count,
    reset_today_sleep, reset_all_settings, full_reset,
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
    "小睡": {"emoji": "💤", "label": "小睡（10-90分鐘）", "suggestion_hours": 0.5},
    "中睡": {"emoji": "😴", "label": "中睡（3-5小時）",   "suggestion_hours": 4},
    "大睡": {"emoji": "🛌", "label": "大睡（7-9小時）",   "suggestion_hours": 8},
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
    today = now.date().isoformat()
    for user_id, alarm_time, alarm_count, repeat_total, last_trigger_date in get_all_alarms():
        should_start_today = alarm_time == current_time and last_trigger_date != today
        should_continue = last_trigger_date == today and alarm_count > 0 and alarm_count < repeat_total
        if should_start_today or should_continue:
            if should_start_today:
                reset_alarm_count(user_id)
                alarm_count = 0
            msg_index = min(alarm_count, len(ALARM_MESSAGES) - 1)
            msg = ALARM_MESSAGES[msg_index].format(time=current_time)
            send_push(user_id, msg)
            increment_alarm_count(user_id)
        elif last_trigger_date != today and alarm_count > 0:
            reset_alarm_count(user_id)
    for user_id, reminder_time in get_all_bedtime_reminders():
        if reminder_time == current_time:
            send_push(user_id, f"🌙 睡前提醒！現在是 {current_time}\n準備放鬆一下，準備睡覺吧～ 😴")


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


def _welcome_text():
    return (
        "歡迎使用睡眠小幫手。\n\n"
        "輸入「說明」查看功能。\n"
        "電腦版可直接輸入：開始睡覺、起床、今日統計、週報告、鬧鐘、睡眠建議。"
    )


def _parse_time(text: str):
    """嘗試解析 HH:MM 或 HHMM 格式，成功回傳 HH:MM，失敗回傳 None"""
    text = text.strip()
    for fmt in ("%H:%M", "%H%M"):
        try:
            parsed = datetime.strptime(text, fmt)
            return parsed.strftime("%H:%M")
        except ValueError:
            pass
    return None


def _parse_clock_time(text: str):
    """解析常見時鐘格式：07:30、0730、7點、7點半、7點30分。"""
    compact = re.sub(r"\s+", "", text.strip())
    match = re.search(r"(\d{1,2}:\d{2})", compact)
    if match:
        return _parse_time(match.group(1))

    match = re.search(r"(?<!\d)(\d{3,4})(?!\d)", compact)
    if match:
        raw = match.group(1).zfill(4)
        return _parse_time(raw)

    match = re.search(r"(\d{1,2})點半", compact)
    if match:
        hour = int(match.group(1))
        if 0 <= hour <= 23:
            return f"{hour:02d}:30"

    match = re.search(r"(\d{1,2})點(?:(\d{1,2})分?)?", compact)
    if match:
        hour = int(match.group(1))
        minute = int(match.group(2) or 0)
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return f"{hour:02d}:{minute:02d}"

    return None


def _parse_sleep_until_request(text: str):
    """解析「現在睡到 07:30 起床」這類可睡時間試算。"""
    clean = text.strip()
    if not any(keyword in clean for keyword in ["起床", "醒來", "睡到", "可以睡"]):
        return None
    if not any(keyword in clean for keyword in ["現在", "睡", "起床", "醒來", "可以睡"]):
        return None
    return _parse_clock_time(clean)


def _parse_duration_to_minutes(text: str):
    """
    解析自然語言時長，回傳分鐘數（int）或 None。
    支援格式：
      10分 / 10分鐘 / 30min
      1小時 / 1hr / 1h
      1小時30分 / 1h30m / 1.5小時
      90分鐘
      我要睡10分鐘 / 睡1小時30分
    """
    text = text.strip()
    # 去掉前綴詞
    text = re.sub(r"^(我要|要|我想|想|我要睡|睡|幫我睡|設定)", "", text)
    text = text.strip()

    total = 0
    matched = False

    # 小時.分 小數格式：1.5小時
    m = re.search(r"(\d+\.?\d*)\s*(小時|hr|hour|h)", text)
    if m:
        total += float(m.group(1)) * 60
        matched = True

    # 分鐘
    m = re.search(r"(\d+)\s*(分鐘|分|min|m)", text)
    if m:
        total += int(m.group(1))
        matched = True

    # 純數字（若文字包含「分」意圖）
    if not matched:
        m = re.fullmatch(r"(\d+)", text.strip())
        if m:
            val = int(m.group(1))
            # 小於 24 視為小時，大於等於 24 視為分鐘
            if val < 24:
                total = val * 60
            else:
                total = val
            matched = True

    return int(total) if matched and total > 0 else None


def _parse_repeat_count(text: str):
    number_words = {
        "一": 1, "二": 2, "兩": 2, "三": 3, "四": 4, "五": 5,
        "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
    }
    m = re.search(r"(?:鬧鐘\s*)?(?:響|通知|提醒)?\s*(\d{1,2}|[一二兩三四五六七八九十])\s*次", text)
    if not m:
        return None
    raw_count = m.group(1)
    count = number_words.get(raw_count, int(raw_count) if raw_count.isdigit() else 1)
    return max(1, min(count, 10))


def _strip_repeat_text(text: str):
    return re.sub(r"(?:鬧鐘\s*)?(?:響|通知|提醒)?\s*(?:\d{1,2}|[一二兩三四五六七八九十])\s*次", "", text).strip()


def _is_alarm_repeat_command(text: str):
    return bool(re.fullmatch(r"(?:鬧鐘\s*)?(?:響|通知|提醒)\s*(?:\d{1,2}|[一二兩三四五六七八九十])\s*次", text.strip()))


def _parse_alarm_request(text: str, now: datetime):
    raw = text.strip()
    raw = re.sub(r"^(設定鬧鐘|鬧鐘|叫我|提醒我)\s*", "", raw).strip()
    repeat_total = _parse_repeat_count(raw) or 1
    target_text = _strip_repeat_text(raw)

    time_str = _parse_time(target_text)
    if time_str:
        return time_str, repeat_total

    minutes = _parse_duration_to_minutes(target_text)
    if minutes:
        _, _, alarm_dt = _calc_from_duration(now, minutes)
        return alarm_dt.strftime("%H:%M"), repeat_total

    return None, repeat_total


def _reply_alarm_repeat_choice(token, user_id, time_str):
    set_pending(user_id, "waiting_alarm_repeat", sleep_type=time_str)
    reply(token, TextMessage(text=(
        f"⏰ 鬧鐘時間：{time_str}\n"
        "請選擇通知幾次"
    ), quick_reply=_alarm_repeat_quick_reply()))


def _set_alarm_or_ask_repeat(token, user_id, time_str, repeat_total, original_text):
    if _parse_repeat_count(original_text):
        clear_pending(user_id)
        set_alarm(user_id, time_str, repeat_total)
        reply(token, TextMessage(text=f"⏰ 鬧鐘設定成功！{time_str} 會通知 {repeat_total} 次 💪"))
    else:
        _reply_alarm_repeat_choice(token, user_id, time_str)


def _calc_from_wake_time(now: datetime, wake_time_str: str):
    """從起床時間字串算出剩餘可睡時間"""
    wake = datetime.strptime(wake_time_str, "%H:%M").replace(
        year=now.year, month=now.month, day=now.day, tzinfo=TZ
    )
    if wake <= now:
        wake += timedelta(days=1)
    delta = wake - now
    total_min = int(delta.total_seconds() / 60)
    return total_min // 60, total_min % 60, wake


def _calc_from_duration(now: datetime, total_minutes: int):
    """從時長（分鐘）算出起床時間"""
    wake = now + timedelta(minutes=total_minutes)
    h = total_minutes // 60
    m = total_minutes % 60
    return h, m, wake


def _sleep_until_result_message(now: datetime, wake_dt: datetime, hours: int, minutes: int):
    total_min = hours * 60 + minutes
    sleep_type = _auto_sleep_type(total_min)
    s_info = SLEEP_TYPES[sleep_type]
    duration_text = f"{hours}小時{minutes:02d}分" if hours else f"{minutes}分鐘"
    return (
        f"現在是 {now.strftime('%H:%M')}。\n"
        f"如果 {wake_dt.strftime('%H:%M')} 起床，還可以睡 {duration_text}。\n\n"
        f"系統會歸類為{s_info['emoji']} {sleep_type}。"
    )


def _sleep_until_quick_reply(wake_dt: datetime):
    wake_text = wake_dt.strftime("%H:%M")
    return QuickReply(items=[
        QuickReplyItem(action=MessageAction(label="開始記錄", text=f"開始睡到 {wake_text} 起床")),
        QuickReplyItem(action=MessageAction(label="只設鬧鐘", text=f"鬧鐘 {wake_text}")),
        QuickReplyItem(action=MessageAction(label="選單", text="選單")),
    ])


def _parse_sleep_latency_minutes(text: str):
    match = re.search(r"(\d{1,2})\s*(?:分鐘|分|min)?(?:後)?(?:真正)?(?:入睡|睡著)", text)
    if match:
        return max(0, min(int(match.group(1)), 60))
    match = re.search(r"(?:入睡|睡著)\s*(\d{1,2})\s*(?:分鐘|分|min)?", text)
    if match:
        return max(0, min(int(match.group(1)), 60))
    return 15


def _parse_asleep_datetime(text: str, now: datetime):
    if "入睡" not in text:
        return None
    time_str = _parse_clock_time(text)
    if not time_str:
        return None
    asleep_at = datetime.strptime(time_str, "%H:%M").replace(
        year=now.year, month=now.month, day=now.day, tzinfo=TZ
    )
    if asleep_at <= now:
        asleep_at += timedelta(days=1)
    return asleep_at


def _sleep_cycle_message(now: datetime, latency_minutes: int = 15, asleep_at: datetime = None):
    asleep_at = asleep_at or (now + timedelta(minutes=latency_minutes))
    latency_minutes = max(int((asleep_at - now).total_seconds() // 60), 0)
    rows = []
    for cycles in range(4, 7):
        wake_dt = asleep_at + timedelta(minutes=90 * cycles)
        total_minutes = max(int((wake_dt - now).total_seconds() // 60), 0)
        hours = total_minutes // 60
        minutes = total_minutes % 60
        rows.append(f"{cycles} 個週期：{wake_dt.strftime('%H:%M')}（約 {hours}小時{minutes:02d}分）")
    return (
        f"現在是 {now.strftime('%H:%M')}。\n"
        f"預估 {latency_minutes} 分鐘後睡著，真正入睡時間：{asleep_at.strftime('%H:%M')}。\n"
        "這不是小睡 10 分鐘，是用來計算睡眠週期的入睡準備時間。\n\n"
        "建議起床時間：\n"
        + "\n".join(rows)
        + "\n\n可輸入「睡眠週期 10分鐘後睡著」或「睡眠週期 01:50入睡」調整。"
    )


def _sleep_cycle_quick_reply(now: datetime, latency_minutes: int = 15, asleep_at: datetime = None):
    asleep_at = asleep_at or (now + timedelta(minutes=latency_minutes))
    wake_4 = asleep_at + timedelta(minutes=90 * 4)
    wake_5 = asleep_at + timedelta(minutes=90 * 5)
    wake_6 = asleep_at + timedelta(minutes=90 * 6)
    return QuickReply(items=[
        QuickReplyItem(action=MessageAction(label=f"{wake_4.strftime('%H:%M')}起床", text=f"開始睡到 {wake_4.strftime('%H:%M')} 起床")),
        QuickReplyItem(action=MessageAction(label=f"{wake_5.strftime('%H:%M')}起床", text=f"開始睡到 {wake_5.strftime('%H:%M')} 起床")),
        QuickReplyItem(action=MessageAction(label=f"{wake_6.strftime('%H:%M')}起床", text=f"開始睡到 {wake_6.strftime('%H:%M')} 起床")),
    ])


def _auto_sleep_type(total_minutes: int) -> str:
    """根據實際睡眠時長自動判斷類型"""
    if total_minutes <= 90:
        return "小睡"
    elif total_minutes <= 300:
        return "中睡"
    else:
        return "大睡"


def _start_sleep_and_reply(token, user_id, now, sleep_type, hours, minutes, wake_dt):
    """統一的「開始睡眠＋建立回覆」邏輯，類型由實際時長自動決定"""
    # 永遠根據實際時長自動判斷類型
    total_min = hours * 60 + minutes
    sleep_type = _auto_sleep_type(total_min)
    s_info = SLEEP_TYPES[sleep_type]
    wake_str = wake_dt.strftime("%H:%M")
    start_sleep(user_id, now.isoformat(), sleep_type=sleep_type, target_wake=wake_str)
    set_alarm(user_id, wake_str, 1)
    flex = build_sleep_countdown(
        sleep_type=sleep_type,
        sleep_type_info=s_info,
        start_time=now,
        wake_time=wake_dt,
        hours=hours,
        minutes=minutes,
    )
    reply(token, [
        FlexMessage(
            alt_text=f"{s_info['emoji']} 已開始{sleep_type}（{hours}h{minutes:02d}m），{wake_str} 叫你起床",
            contents=FlexContainer.from_dict(flex),
        ),
        TextMessage(
            text=(
                f"⏰ {wake_str} 的鬧鐘要通知幾次？\n"
                "不選的話會先用預設 1 次。點卡片上的「響3次」或「響5次」可更改。"
            ),
        ),
    ])


def _set_wake_for_running_sleep_and_reply(token, user_id, now, sleep_type, hours, minutes, wake_dt):
    total_min = hours * 60 + minutes
    sleep_type = _auto_sleep_type(total_min)
    s_info = SLEEP_TYPES[sleep_type]
    wake_str = wake_dt.strftime("%H:%M")
    record = get_latest_record(user_id)
    if not record or record.get("sleep_end"):
        _start_sleep_and_reply(token, user_id, now, sleep_type, hours, minutes, wake_dt)
        return

    start_time = datetime.fromisoformat(record["sleep_start"]).astimezone(TZ)
    set_alarm(user_id, wake_str)
    flex = build_sleep_countdown(
        sleep_type=sleep_type,
        sleep_type_info=s_info,
        start_time=start_time,
        wake_time=wake_dt,
        hours=hours,
        minutes=minutes,
    )
    reply(token, [
        FlexMessage(
            alt_text=f"{s_info['emoji']} 已設定{sleep_type}鬧鐘，{wake_str} 叫你起床",
            contents=FlexContainer.from_dict(flex),
        ),
        TextMessage(text=(
            f"⏰ {wake_str} 的鬧鐘預設通知 1 次。\n"
            "可點卡片上的「響3次」或「響5次」更改。"
        )),
    ])


def _sleep_type_quick_reply():
    return QuickReply(items=[
        QuickReplyItem(action=MessageAction(label="💤 小睡", text="小睡")),
        QuickReplyItem(action=MessageAction(label="😴 中睡", text="中睡")),
        QuickReplyItem(action=MessageAction(label="🛌 大睡", text="大睡")),
    ])


def _duration_quick_reply(sleep_type=None, now=None):
    """依睡眠類型顯示不同時長快捷按鈕。"""
    if sleep_type == "小睡":
        items = [
            QuickReplyItem(action=MessageAction(label="⚡ 10分鐘", text="10分鐘")),
            QuickReplyItem(action=MessageAction(label="💤 20分鐘", text="20分鐘")),
            QuickReplyItem(action=MessageAction(label="😪 30分鐘", text="30分鐘")),
            QuickReplyItem(action=MessageAction(label="😴 45分鐘", text="45分鐘")),
            QuickReplyItem(action=MessageAction(label="🕐 60分鐘", text="60分鐘")),
            QuickReplyItem(action=MessageAction(label="💤 90分鐘", text="90分鐘")),
            QuickReplyItem(action=MessageAction(label="⏰ 指定起床時間", text="指定起床時間")),
        ]
    elif sleep_type == "中睡":
        items = [
            QuickReplyItem(action=MessageAction(label="😴 3小時", text="3小時")),
            QuickReplyItem(action=MessageAction(label="😴 4小時", text="4小時")),
            QuickReplyItem(action=MessageAction(label="😴 5小時", text="5小時")),
            QuickReplyItem(action=MessageAction(label="⏰ 指定起床時間", text="指定起床時間")),
        ]
    elif sleep_type == "大睡":
        items = [
            QuickReplyItem(action=MessageAction(label="🛌 7小時", text="7小時")),
            QuickReplyItem(action=MessageAction(label="🛌 8小時", text="8小時")),
            QuickReplyItem(action=MessageAction(label="🛌 9小時", text="9小時")),
            QuickReplyItem(action=MessageAction(label="⏰ 指定起床時間", text="指定起床時間")),
        ]
    else:
        items = [
            QuickReplyItem(action=MessageAction(label="💤 20分鐘", text="20分鐘")),
            QuickReplyItem(action=MessageAction(label="😪 30分鐘", text="30分鐘")),
            QuickReplyItem(action=MessageAction(label="😴 45分鐘", text="45分鐘")),
            QuickReplyItem(action=MessageAction(label="🛌 1小時", text="1小時")),
            QuickReplyItem(action=MessageAction(label="⏰ 指定起床時間", text="指定起床時間")),
        ]
    return QuickReply(items=items)


def _duration_prompt(sleep_type, now):
    if sleep_type == "小睡":
        options = "下方可選 10、20、30、45、60、90 分鐘"
    elif sleep_type == "中睡":
        options = "下方可選 3、4、5 小時"
    elif sleep_type == "大睡":
        options = "下方可選 7、8、9 小時"
    else:
        options = "也可以直接輸入想睡多久"
    return (
        f"🕐 現在是 {now.strftime('%H:%M')}\n\n"
        f"{options}\n"
        "或輸入起床時間，例如 07:30、0730"
    )


def _alarm_time_quick_reply():
    return QuickReply(items=[
        QuickReplyItem(action=MessageAction(label="⏱ 10分鐘後", text="10分鐘")),
        QuickReplyItem(action=MessageAction(label="⏱ 20分鐘後", text="20分鐘")),
        QuickReplyItem(action=MessageAction(label="⏱ 30分鐘後", text="30分鐘")),
        QuickReplyItem(action=MessageAction(label="⏱ 1小時後", text="1小時")),
        QuickReplyItem(action=MessageAction(label="⏱ 2小時後", text="2小時")),
        QuickReplyItem(action=MessageAction(label="🕒 指定時間", text="指定鬧鐘時間")),
        QuickReplyItem(action=MessageAction(label="❌ 取消鬧鐘", text="取消鬧鐘")),
    ])


def _alarm_repeat_quick_reply():
    return QuickReply(items=[
        QuickReplyItem(action=MessageAction(label="響1次", text="響1次")),
        QuickReplyItem(action=MessageAction(label="響3次", text="響3次")),
        QuickReplyItem(action=MessageAction(label="響5次", text="響5次")),
        QuickReplyItem(action=MessageAction(label="❌ 取消", text="取消鬧鐘")),
    ])


def _alarm_prompt(alarm=None):
    current = ""
    if alarm and alarm.get("alarm_time"):
        current = f"目前鬧鐘：{alarm['alarm_time']}，通知 {alarm.get('alarm_repeat_total') or 1} 次\n\n"
    return (
        f"⏰ {current}要多久後響？\n\n"
        "可以直接選下方：10分鐘後、20分鐘後、30分鐘後、1小時後\n"
        "也可以輸入：30分鐘、1小時30分、0730、07:30\n\n"
        "設定時間後會再讓你選通知幾次。"
    )


GLOBAL_COMMANDS = {
    "選單", "menu", "Menu", "開始", "start", "嗨", "hi", "Hi", "hello", "Hello",
    "開始睡覺", "我要開始睡覺", "睡覺", "小睡", "中睡", "大睡", "起床", "醒來", "起床了",
    "今日統計", "今天", "統計", "紀錄", "週報告", "本週", "週統計",
    "鬧鐘", "設定鬧鐘", "查看鬧鐘", "重新設定鬧鐘",
    "睡眠建議", "建議", "tips", "小知識", "算可睡多久", "睡眠週期", "狀態", "計時狀態",
    "說明", "幫助", "help", "Help", "指令", "重設", "重新設定", "reset",
}


def _clean_command_text(text):
    return re.sub(r"^[^\w\u4e00-\u9fff]+", "", text.strip()).strip()


def _is_global_command(text):
    clean = _clean_command_text(text)
    if clean in GLOBAL_COMMANDS:
        return True
    if clean.startswith(("鬧鐘 ", "設定鬧鐘 ", "睡前提醒 ", "就寢提醒 ")):
        return True
    return any(
        keyword in clean
        for keyword in [
            "開始睡覺", "今日統計", "週報告", "睡眠建議", "算可睡多久", "睡眠週期",
            "選單", "起床", "查看鬧鐘", "取消鬧鐘", "重新設定鬧鐘",
        ]
    )


def _should_leave_pending(pending_action, text):
    if not pending_action:
        return False
    return _is_global_command(text)


# ── Follow Handler ──────────────────────────────────────────────────────────

@handler.add(FollowEvent)
def handle_follow(event):
    reply(event.reply_token, TextMessage(text=_welcome_text()))


# ── Message Handler ─────────────────────────────────────────────────────────

@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    user_id = event.source.user_id
    text = event.message.text.strip()
    token = event.reply_token
    now = datetime.now(TZ)

    # ════════════════════════════════════════════════════
    # 優先處理 pending 狀態
    # ════════════════════════════════════════════════════
    pending_action, pending_sleep_type = get_pending(user_id)

    if _should_leave_pending(pending_action, text):
        clear_pending(user_id)
        pending_action, pending_sleep_type = None, None

    if pending_action and text in ["取消", "取消設定", "取消鬧鐘", "刪除鬧鐘"]:
        clear_pending(user_id)
        if text in ["取消鬧鐘", "刪除鬧鐘"]:
            delete_alarm(user_id)
            reply(token, TextMessage(text="⏰ 鬧鐘已取消！"))
        else:
            reply(token, TextMessage(text="✅ 已取消設定"))
        return



    # ── 等待輸入起床方式（時間 or 時長）──
    if pending_action == "waiting_wake_time":

        # 用戶選「指定起床時間」→ 切換狀態
        if text in ["指定起床時間", "指定時間", "幾點"]:
            set_pending(user_id, "waiting_exact_time", sleep_type=pending_sleep_type)
            reply(token, TextMessage(text=(
                "⏰ 請輸入起床時間（24小時制）\n\n"
                "例如：07:30　08:00　22:30"
            )))
            return

        # 嘗試解析時長
        minutes = _parse_duration_to_minutes(text)
        if minutes and minutes > 0:
            clear_pending(user_id)
            h, m, wake_dt = _calc_from_duration(now, minutes)
            _set_wake_for_running_sleep_and_reply(token, user_id, now, pending_sleep_type, h, m, wake_dt)
            return

        # 嘗試解析時間點
        time_str = _parse_time(text)
        if time_str:
            clear_pending(user_id)
            h, m, wake_dt = _calc_from_wake_time(now, time_str)
            _set_wake_for_running_sleep_and_reply(token, user_id, now, pending_sleep_type, h, m, wake_dt)
            return

    # pending waiting_wake_time 的錯誤提示也需要傳 now
        reply(token, TextMessage(
            text=(
                f"❌ 我沒看懂，現在是 {now.strftime('%H:%M')}\n\n"
                "可以這樣輸入：\n\n"
                "⏱ 睡多久（自動算起床時間）：\n"
                "「10分鐘」「30分鐘」「1小時30分」\n\n"
                "⏰ 幾點起床：\n"
                "「07:30」「08:00」\n\n"
                "或直接選下方快捷 👇"
            ),
            quick_reply=_duration_quick_reply(pending_sleep_type, now),
        ))
        return

    # ── 等待精確時間（HH:MM）──
    if pending_action == "waiting_exact_time":
        time_str = _parse_time(text)
        if time_str:
            clear_pending(user_id)
            h, m, wake_dt = _calc_from_wake_time(now, time_str)
            _set_wake_for_running_sleep_and_reply(token, user_id, now, pending_sleep_type, h, m, wake_dt)
            return

        minutes = _parse_duration_to_minutes(text)
        if minutes and minutes > 0:
            clear_pending(user_id)
            h, m, wake_dt = _calc_from_duration(now, minutes)
            _set_wake_for_running_sleep_and_reply(token, user_id, now, pending_sleep_type, h, m, wake_dt)
            return

        reply(token, TextMessage(
            text=(
                f"❌ 我沒看懂，現在是 {now.strftime('%H:%M')}\n\n"
                "可以輸入：\n"
                "「07:30」「0730」\n"
                "「30分鐘」「1小時30分」\n"
                "或按主選單功能離開設定"
            ),
            quick_reply=_duration_quick_reply(pending_sleep_type, now),
        ))
        return

    # ── 等待鬧鐘時間 ──
    if pending_action == "waiting_alarm_time":
        if text in ["指定鬧鐘時間", "指定時間", "輸入時間"]:
            reply(token, TextMessage(
                text=(
                    "請輸入鬧鐘時間\n"
                    "例如：07:30 或 0730\n\n"
                    "輸入「取消鬧鐘」可取消"
                ),
                quick_reply=QuickReply(items=[
                    QuickReplyItem(action=MessageAction(label="🌅 07:30", text="07:30")),
                    QuickReplyItem(action=MessageAction(label="🌙 22:30", text="22:30")),
                    QuickReplyItem(action=MessageAction(label="❌ 取消鬧鐘", text="取消鬧鐘")),
                ]),
            ))
            return

        time_str, repeat_total = _parse_alarm_request(text, now)
        if time_str:
            _set_alarm_or_ask_repeat(token, user_id, time_str, repeat_total, text)
        else:
            reply(token, TextMessage(
                text="❌ 我沒看懂鬧鐘時間\n\n" + _alarm_prompt(),
                quick_reply=_alarm_time_quick_reply(),
            ))
        return

    if pending_action == "waiting_alarm_repeat":
        repeat_total = _parse_repeat_count(text)
        if repeat_total:
            clear_pending(user_id)
            set_alarm(user_id, pending_sleep_type, repeat_total)
            reply(token, TextMessage(text=(
                f"⏰ 鬧鐘設定成功！\n"
                f"{pending_sleep_type} 會通知 {repeat_total} 次\n\n"
                "輸入「取消鬧鐘」可以刪除"
            )))
        else:
            reply(token, TextMessage(
                text="請選擇或輸入通知次數，例如：響3次",
                quick_reply=_alarm_repeat_quick_reply(),
            ))
        return

    # ── 等待睡前提醒時間 ──
    if pending_action == "waiting_bedtime_time":
        time_str = _parse_time(text)
        if time_str:
            clear_pending(user_id)
            set_bedtime_reminder(user_id, time_str)
            reply(token, TextMessage(text=(
                f"🌙 睡前提醒設定成功！\n"
                f"每天 {time_str} 會提醒你準備睡覺 😴"
            )))
        else:
            reply(token, TextMessage(text=(
                "❌ 我沒看懂提醒時間\n\n"
                "可以輸入 22:30 或 2230\n"
                "也可以直接按其他主選單功能離開"
            )))
        return

    if pending_action == "waiting_sleep_until_time":
        wake_time_str = _parse_clock_time(text)
        if wake_time_str:
            clear_pending(user_id)
            h, m, wake_dt = _calc_from_wake_time(now, wake_time_str)
            reply(token, TextMessage(
                text=_sleep_until_result_message(now, wake_dt, h, m),
                quick_reply=_sleep_until_quick_reply(wake_dt),
            ))
        else:
            reply(token, TextMessage(
                text=(
                    "請輸入你想幾點起床，例如：\n"
                    "07:30\n"
                    "0730\n"
                    "7點半"
                ),
                quick_reply=QuickReply(items=[
                    QuickReplyItem(action=MessageAction(label="07:30", text="07:30")),
                    QuickReplyItem(action=MessageAction(label="08:00", text="08:00")),
                    QuickReplyItem(action=MessageAction(label="取消", text="取消")),
                ]),
            ))
        return

    # ── 完全重設確認 ──
    if pending_action == "confirm_full_reset":
        if text in ["確認重設", "確認", "yes", "YES"]:
            clear_pending(user_id)
            full_reset(user_id)
            reply(token, TextMessage(text=(
                "💥 完全重設完成！\n\n"
                "所有睡眠紀錄和設定都已清除 🗑️\n"
                "輸入「選單」重新開始 😴"
            )))
        else:
            clear_pending(user_id)
            reply(token, TextMessage(text="✅ 已取消，資料保留完整！"))
        return

    # ════════════════════════════════════════════════════
    # 自然語言直接觸發睡眠（不需先選類型）
    # 例如：「我要睡10分鐘」「睡1小時30分」
    # ════════════════════════════════════════════════════
    sleep_trigger = re.match(
        r"^(我要睡|要睡|我想睡|想睡|睡)(.+)$", text
    )
    if sleep_trigger:
        duration_text = sleep_trigger.group(2).strip()
        minutes = _parse_duration_to_minutes(duration_text)
        if minutes and minutes > 0:
            # 根據時長自動判斷睡眠類型
            if minutes <= 90:
                sleep_type = "小睡"
            elif minutes <= 300:
                sleep_type = "中睡"
            else:
                sleep_type = "大睡"
            h, m, wake_dt = _calc_from_duration(now, minutes)
            _start_sleep_and_reply(token, user_id, now, sleep_type, h, m, wake_dt)
            return

    start_until_match = re.match(r"^(開始睡到|我要睡到|要睡到|睡到)\s*(.+)$", text)
    if start_until_match and "可以睡" not in text:
        wake_time_str = _parse_clock_time(start_until_match.group(2))
        if wake_time_str:
            h, m, wake_dt = _calc_from_wake_time(now, wake_time_str)
            total_min = h * 60 + m
            sleep_type = _auto_sleep_type(total_min)
            _start_sleep_and_reply(token, user_id, now, sleep_type, h, m, wake_dt)
            return

    wake_time_str = _parse_sleep_until_request(text)
    if wake_time_str:
        h, m, wake_dt = _calc_from_wake_time(now, wake_time_str)
        reply(token, TextMessage(
            text=_sleep_until_result_message(now, wake_dt, h, m),
            quick_reply=_sleep_until_quick_reply(wake_dt),
        ))
        return

    if (
        any(keyword in text for keyword in ["可以睡多久", "還能睡多久", "還可以睡多久"])
        or ("現在" in text and "睡" in text and "起床" in text)
    ):
        reply(token, TextMessage(
            text=(
                "請告訴我你想幾點起床，我會幫你算還可以睡多久。\n\n"
                "例如：\n"
                "現在睡 07:30 起床\n"
                "現在睡到 7點半\n"
                "07:30 起床可以睡多久"
            ),
            quick_reply=QuickReply(items=[
                QuickReplyItem(action=MessageAction(label="07:30起床", text="現在睡 07:30 起床")),
                QuickReplyItem(action=MessageAction(label="08:00起床", text="現在睡 08:00 起床")),
                QuickReplyItem(action=MessageAction(label="只設鬧鐘", text="鬧鐘")),
            ]),
        ))
        return

    if text.startswith("睡眠週期") or text.startswith("睡眠周期"):
        asleep_at = _parse_asleep_datetime(text, now)
        latency_minutes = _parse_sleep_latency_minutes(text)
        reply(token, TextMessage(
            text=_sleep_cycle_message(now, latency_minutes, asleep_at),
            quick_reply=_sleep_cycle_quick_reply(now, latency_minutes, asleep_at),
        ))
        return

    # ════════════════════════════════════════════════════
    # 標準指令
    # ════════════════════════════════════════════════════

    # ── 主選單 ──
    if text in ["選單", "menu", "Menu", "開始", "start", "嗨", "hi", "Hi", "hello", "Hello"]:
        reply(token, FlexMessage(
            alt_text="睡眠小幫手 主選單",
            contents=FlexContainer.from_dict(build_main_menu()),
        ))

    # ── 睡覺（選類型）──
    elif text in ["睡覺", "開始睡覺", "我要開始睡覺"]:
        alarm = get_alarm(user_id)
        if alarm and alarm.get("alarm_time"):
            reply(token, TextMessage(
                text=(
                    f"⏰ 目前已有鬧鐘行程\n"
                    f"時間：{alarm['alarm_time']}\n"
                    f"通知：{alarm.get('alarm_repeat_total') or 1} 次\n\n"
                    "要開始新的睡眠請按「開始睡覺」，新的起床時間會覆蓋目前鬧鐘。"
                ),
                quick_reply=QuickReply(items=[
                    QuickReplyItem(action=MessageAction(label="😴 開始睡覺", text="選擇睡眠類型")),
                    QuickReplyItem(action=MessageAction(label="🔄 重新設定鬧鐘", text="重新設定鬧鐘")),
                    QuickReplyItem(action=MessageAction(label="❌ 取消鬧鐘", text="取消鬧鐘")),
                ]),
            ))
        else:
            reply(token, TextMessage(
                text="你要睡哪種覺？😴",
                quick_reply=_sleep_type_quick_reply(),
            ))

    elif text == "選擇睡眠類型":
        reply(token, TextMessage(
            text="你要睡哪種覺？😴",
            quick_reply=_sleep_type_quick_reply(),
        ))

    # ── 三種睡眠類型 ──
    elif text in ["小睡", "中睡", "大睡"]:
        s_info = SLEEP_TYPES[text]
        record = get_latest_record(user_id)
        if not record or record.get("sleep_end"):
            start_sleep(user_id, now.isoformat(), sleep_type=text)
        set_pending(user_id, "waiting_wake_time", sleep_type=text)
        reply(token, TextMessage(
            text=(
                f"{s_info['emoji']} 【{s_info['label']}】\n\n"
                "已開始計時。\n"
                f"{_duration_prompt(text, now)}"
            ),
            quick_reply=_duration_quick_reply(text, now),
        ))

    # ── 起床 ──
    elif text in ["起床", "醒來", "起床了"]:
        record = get_latest_record(user_id)
        if not record or not record.get("sleep_start"):
            reply(token, TextMessage(text=(
                "❌ 你還沒有開始睡眠計時喔！\n\n"
                "點選單或說「我要睡X分鐘」開始記錄"
            )))
        elif record.get("sleep_end"):
            reply(token, TextMessage(text="✅ 你今天的睡眠已記錄完畢！\n輸入「統計」查看詳情"))
        else:
            sleep_start = datetime.fromisoformat(record["sleep_start"]).astimezone(TZ)
            delta = now - sleep_start
            total_min = int(delta.total_seconds() / 60)
            hours = total_min // 60
            minutes = total_min % 60
            sleep_type = _auto_sleep_type(total_min)
            s_info = SLEEP_TYPES.get(sleep_type, SLEEP_TYPES["大睡"])
            end_sleep(user_id, now.isoformat(), sleep_type=sleep_type)
            delete_alarm(user_id)

            if sleep_type == "大睡" and total_min >= 420:
                quality, q_emoji = "優良！繼續保持！", "🌟"
            elif sleep_type in ["中睡", "大睡"] and total_min >= 240:
                quality, q_emoji = "不錯，身體有充電到", "⚡"
            elif sleep_type == "小睡":
                quality, q_emoji = "小睡完成，短暫補眠已記錄", "😌"
            elif total_min >= 60:
                quality, q_emoji = "小憩一下，精神好一點了嗎？", "😌"
            else:
                quality, q_emoji = "快速補眠完成！", "💪"

            reply(token, TextMessage(text=(
                f"☀️ 起床囉！\n\n"
                f"📊 {sleep_type}報告\n"
                f"━━━━━━━━━━━━━━\n"
                f"{s_info['emoji']} 類型：{sleep_type}\n"
                f"🌙 入睡：{sleep_start.strftime('%H:%M')}\n"
                f"☀️ 起床：{now.strftime('%H:%M')}\n"
                f"⏱ 時長：{hours}小時{minutes:02d}分鐘\n"
                f"{q_emoji} 評估：{quality}\n\n"
                f"輸入「統計」或「週報告」查看更多"
            )))

    # ── 今日統計 ──
    elif text in ["今日統計", "今天", "統計", "紀錄"]:
        records = get_today_records(user_id)
        if not records:
            reply(token, TextMessage(text=(
                "📊 今天還沒有睡眠紀錄\n\n"
                "說「我要睡1小時」或點選單開始記錄 🌙"
            )))
        else:
            flex = build_sleep_stats(records, now)
            reply(token, FlexMessage(
                alt_text="今日睡眠統計",
                contents=FlexContainer.from_dict(flex),
            ))

    # ── 週報告 ──
    elif text in ["週報告", "本週", "週統計"]:
        records = get_week_records(user_id)
        flex = build_week_report(records, now)
        reply(token, FlexMessage(
            alt_text="本週睡眠報告",
            contents=FlexContainer.from_dict(flex),
        ))

    # ── 鬧鐘 ──
    elif text in ["設定鬧鐘", "重新設定鬧鐘"]:
        set_pending(user_id, "waiting_alarm_time")
        reply(token, TextMessage(
            text=_alarm_prompt(),
            quick_reply=_alarm_time_quick_reply(),
        ))

    elif text in ["鬧鐘", "查看鬧鐘"]:
        alarm = get_alarm(user_id)
        if alarm and alarm.get("alarm_time"):
            reply(token, TextMessage(
                text=(
                    f"⏰ 目前鬧鐘行程\n"
                    f"時間：{alarm['alarm_time']}\n"
                    f"通知：{alarm.get('alarm_repeat_total') or 1} 次\n\n"
                    "要更改請按「重新設定鬧鐘」，或按「取消鬧鐘」。"
                ),
                quick_reply=QuickReply(items=[
                    QuickReplyItem(action=MessageAction(label="🔄 重新設定", text="重新設定鬧鐘")),
                    QuickReplyItem(action=MessageAction(label="❌ 取消鬧鐘", text="取消鬧鐘")),
                ]),
            ))
        else:
            set_pending(user_id, "waiting_alarm_time")
            reply(token, TextMessage(
                text=_alarm_prompt(),
                quick_reply=_alarm_time_quick_reply(),
            ))

    elif _is_alarm_repeat_command(text):
        repeat_total = _parse_repeat_count(text)
        alarm = get_alarm(user_id)
        if alarm and alarm.get("alarm_time") and repeat_total:
            set_alarm(user_id, alarm["alarm_time"], repeat_total)
            reply(token, TextMessage(text=(
                f"好，{alarm['alarm_time']} 會響 {repeat_total} 次。"
            )))
        else:
            reply(token, TextMessage(
                text="目前還沒有鬧鐘，請先設定鬧鐘時間。",
                quick_reply=_alarm_time_quick_reply(),
            ))

    elif text.startswith("鬧鐘 ") or text.startswith("設定鬧鐘 "):
        time_str, repeat_total = _parse_alarm_request(text, now)
        if time_str:
            _set_alarm_or_ask_repeat(token, user_id, time_str, repeat_total, text)
        else:
            reply(token, TextMessage(text="❌ 格式錯誤，例如：鬧鐘 07:30 3次、鬧鐘 30分鐘"))

    elif text in ["取消鬧鐘", "刪除鬧鐘"]:
        delete_alarm(user_id)
        reply(token, TextMessage(text="⏰ 鬧鐘已取消！"))

    # ── 睡前提醒 ──
    elif text in ["睡前提醒", "就寢提醒", "設定提醒"]:
        set_pending(user_id, "waiting_bedtime_time")
        reply(token, TextMessage(text=(
            "🌙 請輸入睡前提醒時間\n"
            "例如：22:30 或 2230\n\n"
            "也可以直接按其他主選單功能離開"
        )))

    elif re.match(r"^(睡前提醒|就寢提醒)\s+\d{1,2}:\d{2}$", text):
        time_str = _parse_time(text.split()[-1])
        if time_str:
            set_bedtime_reminder(user_id, time_str)
            reply(token, TextMessage(text=f"🌙 睡前提醒設定成功！每天 {time_str} 提醒你 😴"))

    elif text in ["取消提醒", "刪除提醒"]:
        set_bedtime_reminder(user_id, None)
        reply(token, TextMessage(text="🌙 睡前提醒已取消！"))

    # ── 重設 ──
    elif text in ["重設", "重新設定", "reset"]:
        reply(token, TextMessage(
            text="🔄 你想重設什麼？",
            quick_reply=QuickReply(items=[
                QuickReplyItem(action=MessageAction(label="🔄 今日紀錄", text="重設今日")),
                QuickReplyItem(action=MessageAction(label="⏰ 鬧鐘",    text="取消鬧鐘")),
                QuickReplyItem(action=MessageAction(label="🌙 睡前提醒", text="取消提醒")),
                QuickReplyItem(action=MessageAction(label="⚙️ 所有設定", text="重設設定")),
                QuickReplyItem(action=MessageAction(label="💥 完全重設", text="完全重設")),
            ]),
        ))

    elif text in ["重設今日", "重設紀錄", "重新計時"]:
        reset_today_sleep(user_id)
        clear_pending(user_id)
        reply(token, TextMessage(text=(
            "🔄 今日睡眠紀錄已清除！\n\n"
            "說「我要睡X分鐘」或點選單重新開始 😴"
        )))

    elif text in ["重設設定", "清除設定"]:
        reset_all_settings(user_id)
        reply(token, TextMessage(text=(
            "⚙️ 所有設定已重設！\n\n"
            "✅ 已清除：鬧鐘、睡前提醒\n"
            "（睡眠紀錄保留）"
        )))

    elif text in ["完全重設", "清除所有", "全部重設"]:
        set_pending(user_id, "confirm_full_reset")
        reply(token, TextMessage(text=(
            "⚠️ 確定要完全重設嗎？\n\n"
            "這將刪除：\n"
            "• 所有睡眠歷史紀錄\n"
            "• 鬧鐘設定\n"
            "• 睡前提醒設定\n\n"
            "輸入「確認重設」執行，或任意其他文字取消。"
        )))

    # ── 睡眠建議 ──
    elif text in ["睡眠建議", "建議", "tips", "小知識"]:
        flex = build_sleep_tips()
        reply(token, [
            FlexMessage(
                alt_text="睡眠小知識",
                contents=FlexContainer.from_dict(flex),
            ),
            TextMessage(
                text="也可以計算現在睡到某個時間，還能睡多久，或用睡眠週期找適合的起床時間。",
                quick_reply=QuickReply(items=[
                    QuickReplyItem(action=MessageAction(label="睡眠週期", text="睡眠週期")),
                    QuickReplyItem(action=MessageAction(label="算可睡多久", text="算可睡多久")),
                    QuickReplyItem(action=MessageAction(label="07:30起床", text="現在睡 07:30 起床")),
                ]),
            ),
        ])

    elif text in ["算可睡多久", "計算可睡多久", "睡多久計算"]:
        set_pending(user_id, "waiting_sleep_until_time")
        reply(token, TextMessage(
            text=(
                "你想幾點起床？\n\n"
                "請輸入例如：07:30、0730、7點半"
            ),
            quick_reply=QuickReply(items=[
                QuickReplyItem(action=MessageAction(label="07:30", text="07:30")),
                QuickReplyItem(action=MessageAction(label="08:00", text="08:00")),
                QuickReplyItem(action=MessageAction(label="取消", text="取消")),
            ]),
        ))

    # ── 狀態 ──
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
            "🗣 直接說（最簡單！）\n"
            "「我要睡20分鐘」→ 直接開始計時\n"
            "「我要睡1小時30分」→ 自動算起床時間\n"
            "「我要睡8小時」→ 開始大睡\n\n"
            "🛌 選睡眠類型\n"
            "「小睡」/ 「中睡」/ 「大睡」\n"
            "→ 再選時長或輸入起床時間\n\n"
            "☀️ 起床\n"
            "「起床」→ 結束計時＋看報告\n\n"
            "📊 統計報告\n"
            "「統計」→ 今天\n"
            "「週報告」→ 本週趨勢\n\n"
            "⏰ 鬧鐘（預設響1次，可自選次數）\n"
            "「鬧鐘 07:30」→ 設定後選通知次數\n"
            "「鬧鐘 07:30 3次」→ 直接設定3次\n"
            "「鬧鐘 30分鐘」→ 30 分鐘後提醒\n"
            "「取消鬧鐘」→ 刪除\n\n"
            "🌙 睡前提醒\n"
            "「睡前提醒」→ 設定\n"
            "「取消提醒」→ 刪除\n\n"
            "🔄 重設\n"
            "「重設」→ 顯示重設選項\n\n"
            "💡 其他\n"
            "「睡眠建議」→ 睡眠小知識\n"
            "「算可睡多久」→ 計算睡到幾點還能睡多久\n"
            "「睡眠週期」→ 推薦完整週期起床時間\n"
            "「選單」→ 主選單\n\n"
            "💻 電腦版 LINE 可直接輸入\n"
            "開始睡覺 / 起床 / 今日統計 / 週報告\n"
            "鬧鐘 / 睡眠建議 / 算可睡多久 / 睡眠週期"
        )))

    # ── 預設回覆（嘗試解析時長）──
    else:
        # 最後嘗試：純時長輸入，視為大睡
        minutes = _parse_duration_to_minutes(text)
        if minutes and minutes > 0:
            if minutes <= 90:
                sleep_type = "小睡"
            elif minutes <= 300:
                sleep_type = "中睡"
            else:
                sleep_type = "大睡"
            h, m, wake_dt = _calc_from_duration(now, minutes)
            _start_sleep_and_reply(token, user_id, now, sleep_type, h, m, wake_dt)
        else:
            reply(token, TextMessage(
                text=(
                    "🌙 嗨！我是睡眠小幫手！\n\n"
                    "你可以直接說：\n"
                    "「我要睡20分鐘」\n"
                    "「我要睡1小時30分」\n\n"
                    "或輸入「選單」查看所有功能 😴"
                )
            ))


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
