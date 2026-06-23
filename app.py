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
from linebot.v3.webhooks import MessageEvent, TextMessageContent
from apscheduler.schedulers.background import BackgroundScheduler
import pytz

from db import (
    init_db, start_sleep, end_sleep, get_latest_record, get_week_records,
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
    "小睡": {"emoji": "💤", "label": "小睡（20-90分鐘）", "suggestion_hours": 0.5},
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
    for user_id, alarm_time, alarm_count in get_all_alarms():
        if alarm_time == current_time and alarm_count < 3:
            msg = ALARM_MESSAGES[alarm_count].format(time=current_time)
            send_push(user_id, msg)
            increment_alarm_count(user_id)
        elif alarm_time != current_time and alarm_count > 0:
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


def _parse_time(text: str):
    """嘗試解析 HH:MM 格式，成功回傳 time_str，失敗回傳 None"""
    text = text.strip()
    try:
        datetime.strptime(text, "%H:%M")
        return text
    except ValueError:
        return None


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


def _start_sleep_and_reply(token, user_id, now, sleep_type, hours, minutes, wake_dt):
    """統一的「開始睡眠＋建立回覆」邏輯"""
    s_info = SLEEP_TYPES.get(sleep_type, SLEEP_TYPES["大睡"])
    wake_str = wake_dt.strftime("%H:%M")
    start_sleep(user_id, now.isoformat(), sleep_type=sleep_type, target_wake=wake_str)
    set_alarm(user_id, wake_str)
    flex = build_sleep_countdown(
        sleep_type=sleep_type,
        sleep_type_info=s_info,
        start_time=now,
        wake_time=wake_dt,
        hours=hours,
        minutes=minutes,
    )
    reply(token, FlexMessage(
        alt_text=f"{s_info['emoji']} 已開始{sleep_type}，{wake_str} 叫你起床",
        contents=FlexContainer.from_dict(flex),
    ))


def _sleep_type_quick_reply():
    return QuickReply(items=[
        QuickReplyItem(action=MessageAction(label="💤 小睡", text="小睡")),
        QuickReplyItem(action=MessageAction(label="😴 中睡", text="中睡")),
        QuickReplyItem(action=MessageAction(label="🛌 大睡", text="大睡")),
    ])


def _duration_quick_reply(now=None):
    """快捷按鈕：分鐘選項 + 指定時間"""
    now_str = f"（現在 {now.strftime('%H:%M')}）" if now else ""
    items = [
        QuickReplyItem(action=MessageAction(label="⚡ 10分鐘",  text="10分鐘")),
        QuickReplyItem(action=MessageAction(label="💤 20分鐘",  text="20分鐘")),
        QuickReplyItem(action=MessageAction(label="😪 30分鐘",  text="30分鐘")),
        QuickReplyItem(action=MessageAction(label="😴 45分鐘",  text="45分鐘")),
        QuickReplyItem(action=MessageAction(label="🛌 1小時",   text="1小時")),
        QuickReplyItem(action=MessageAction(label="🛌 1.5小時", text="1.5小時")),
        QuickReplyItem(action=MessageAction(label="🛌 2小時",   text="2小時")),
        QuickReplyItem(action=MessageAction(label="⏰ 指定起床時間", text="指定起床時間")),
    ]
    return QuickReply(items=items)


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
            _start_sleep_and_reply(token, user_id, now, pending_sleep_type, h, m, wake_dt)
            return

        # 嘗試解析時間點
        time_str = _parse_time(text)
        if time_str:
            clear_pending(user_id)
            h, m, wake_dt = _calc_from_wake_time(now, time_str)
            _start_sleep_and_reply(token, user_id, now, pending_sleep_type, h, m, wake_dt)
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
            quick_reply=_duration_quick_reply(now),
        ))
        return

    # ── 等待精確時間（HH:MM）──
    if pending_action == "waiting_exact_time":
        time_str = _parse_time(text)
        if time_str:
            clear_pending(user_id)
            h, m, wake_dt = _calc_from_wake_time(now, time_str)
            _start_sleep_and_reply(token, user_id, now, pending_sleep_type, h, m, wake_dt)
        else:
            reply(token, TextMessage(text="❌ 請輸入 HH:MM 格式，例如：07:30"))
        return

    # ── 等待鬧鐘時間 ──
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
            reply(token, TextMessage(text="❌ 請輸入 HH:MM 格式，例如：07:30"))
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
            reply(token, TextMessage(text="❌ 請輸入 HH:MM 格式，例如：22:30"))
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
    elif text == "睡覺":
        reply(token, TextMessage(
            text="你要睡哪種覺？😴",
            quick_reply=_sleep_type_quick_reply(),
        ))

    # ── 三種睡眠類型 ──
    elif text in ["小睡", "中睡", "大睡"]:
        s_info = SLEEP_TYPES[text]
        set_pending(user_id, "waiting_wake_time", sleep_type=text)
        reply(token, TextMessage(
            text=(
                f"{s_info['emoji']} 【{s_info['label']}】\n\n"
                f"🕐 現在是 {now.strftime('%H:%M')}\n\n"
                "想睡多久？或幾點起床？👇"
            ),
            quick_reply=_duration_quick_reply(now),
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
            end_sleep(user_id, now.isoformat())
            delete_alarm(user_id)
            delta = now - sleep_start
            total_min = int(delta.total_seconds() / 60)
            hours = total_min // 60
            minutes = total_min % 60
            sleep_type = record.get("sleep_type", "大睡")
            s_info = SLEEP_TYPES.get(sleep_type, SLEEP_TYPES["大睡"])

            if total_min >= 420:
                quality, q_emoji = "優良！繼續保持！", "🌟"
            elif total_min >= 240:
                quality, q_emoji = "不錯，身體有充電到", "⚡"
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
        record = get_latest_record(user_id)
        if not record or not record.get("sleep_start"):
            reply(token, TextMessage(text=(
                "📊 今天還沒有睡眠紀錄\n\n"
                "說「我要睡1小時」或點選單開始記錄 🌙"
            )))
        else:
            flex = build_sleep_stats(record, now)
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
    elif text in ["鬧鐘", "設定鬧鐘", "查看鬧鐘"]:
        alarm = get_alarm(user_id)
        if alarm:
            reply(token, TextMessage(text=(
                f"⏰ 目前鬧鐘：{alarm}\n"
                f"到時間會連響 3 次！\n\n"
                "輸入新時間可重設，例如：鬧鐘 07:30\n"
                "輸入「取消鬧鐘」刪除"
            )))
        else:
            set_pending(user_id, "waiting_alarm_time")
            reply(token, TextMessage(text="⏰ 請輸入起床時間（HH:MM）\n例如：07:30"))

    elif text.startswith("鬧鐘 ") or text.startswith("設定鬧鐘 "):
        time_str = _parse_time(text.split()[-1])
        if time_str:
            set_alarm(user_id, time_str)
            reply(token, TextMessage(text=f"⏰ 鬧鐘設定成功！{time_str} 連響 3 次 💪"))
        else:
            reply(token, TextMessage(text="❌ 格式錯誤，例如：鬧鐘 07:30"))

    elif text in ["取消鬧鐘", "刪除鬧鐘"]:
        delete_alarm(user_id)
        reply(token, TextMessage(text="⏰ 鬧鐘已取消！"))

    # ── 睡前提醒 ──
    elif text in ["睡前提醒", "就寢提醒", "設定提醒"]:
        set_pending(user_id, "waiting_bedtime_time")
        reply(token, TextMessage(text="🌙 請輸入睡前提醒時間（HH:MM）\n例如：22:30"))

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
        reply(token, FlexMessage(
            alt_text="睡眠小知識",
            contents=FlexContainer.from_dict(flex),
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
            "⏰ 鬧鐘（連響3次）\n"
            "「鬧鐘 07:30」→ 設定\n"
            "「取消鬧鐘」→ 刪除\n\n"
            "🌙 睡前提醒\n"
            "「睡前提醒」→ 設定\n"
            "「取消提醒」→ 刪除\n\n"
            "🔄 重設\n"
            "「重設」→ 顯示重設選項\n\n"
            "💡 其他\n"
            "「睡眠建議」→ 睡眠小知識\n"
            "「選單」→ 主選單"
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
