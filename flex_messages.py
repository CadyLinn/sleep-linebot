"""
LINE Flex Message builders for the Sleep Bot.
All functions return a dict (JSON-serializable) compatible with
FlexContainer.from_dict().
"""
from datetime import datetime, timedelta
import pytz

TZ = pytz.timezone("Asia/Taipei")

# ── Color Palette ──────────────────────────────────────────────────────────
NAVY    = "#1A1A2E"
INDIGO  = "#16213E"
PURPLE  = "#7C3AED"
VIOLET  = "#A78BFA"
MINT    = "#34D399"
YELLOW  = "#FBBF24"
CORAL   = "#F87171"
WHITE   = "#FFFFFF"
GRAY    = "#94A3B8"
LIGHT   = "#E2E8F0"


def _header(title: str, subtitle: str = "", bg_color: str = NAVY):
    items = [
        {
            "type": "text",
            "text": title,
            "color": WHITE,
            "size": "xl",
            "weight": "bold",
        }
    ]
    if subtitle:
        items.append({
            "type": "text",
            "text": subtitle,
            "color": VIOLET,
            "size": "sm",
            "margin": "xs",
        })
    return {
        "type": "box",
        "layout": "vertical",
        "backgroundColor": bg_color,
        "paddingAll": "20px",
        "contents": items,
    }


def _btn(label: str, text: str, color: str = PURPLE):
    return {
        "type": "button",
        "style": "primary",
        "color": color,
        "height": "sm",
        "action": {
            "type": "message",
            "label": label,
            "text": text,
        },
    }


# ── Main Menu ──────────────────────────────────────────────────────────────

def build_main_menu():
    return {
        "type": "bubble",
        "size": "giga",
        "header": _header("😴 睡眠小幫手", "你的專屬睡眠管理助手"),
        "body": {
            "type": "box",
            "layout": "vertical",
            "backgroundColor": INDIGO,
            "paddingAll": "16px",
            "spacing": "md",
            "contents": [
                {
                    "type": "box",
                    "layout": "horizontal",
                    "spacing": "sm",
                    "contents": [
                        {
                            "type": "box",
                            "layout": "vertical",
                            "backgroundColor": "#0F172A",
                            "cornerRadius": "12px",
                            "paddingAll": "16px",
                            "flex": 1,
                            "contents": [
                                {"type": "text", "text": "🌙", "size": "xxl", "align": "center"},
                                {"type": "text", "text": "開始睡覺", "size": "sm", "color": WHITE,
                                 "align": "center", "weight": "bold", "margin": "sm"},
                                {"type": "button", "style": "primary", "color": PURPLE,
                                 "height": "sm", "margin": "sm",
                                 "action": {"type": "message", "label": "睡覺", "text": "睡覺"}},
                            ],
                        },
                        {
                            "type": "box",
                            "layout": "vertical",
                            "backgroundColor": "#0F172A",
                            "cornerRadius": "12px",
                            "paddingAll": "16px",
                            "flex": 1,
                            "contents": [
                                {"type": "text", "text": "☀️", "size": "xxl", "align": "center"},
                                {"type": "text", "text": "起床了", "size": "sm", "color": WHITE,
                                 "align": "center", "weight": "bold", "margin": "sm"},
                                {"type": "button", "style": "primary", "color": MINT,
                                 "height": "sm", "margin": "sm",
                                 "action": {"type": "message", "label": "起床", "text": "起床"}},
                            ],
                        },
                    ],
                },
                {
                    "type": "box",
                    "layout": "horizontal",
                    "spacing": "sm",
                    "contents": [
                        {
                            "type": "box",
                            "layout": "vertical",
                            "backgroundColor": "#0F172A",
                            "cornerRadius": "12px",
                            "paddingAll": "12px",
                            "flex": 1,
                            "contents": [
                                {"type": "text", "text": "📊 今日統計", "size": "sm",
                                 "color": YELLOW, "weight": "bold"},
                                {"type": "button", "style": "secondary", "height": "sm",
                                 "margin": "sm",
                                 "action": {"type": "message", "label": "查看", "text": "今日統計"}},
                            ],
                        },
                        {
                            "type": "box",
                            "layout": "vertical",
                            "backgroundColor": "#0F172A",
                            "cornerRadius": "12px",
                            "paddingAll": "12px",
                            "flex": 1,
                            "contents": [
                                {"type": "text", "text": "📈 週報告", "size": "sm",
                                 "color": VIOLET, "weight": "bold"},
                                {"type": "button", "style": "secondary", "height": "sm",
                                 "margin": "sm",
                                 "action": {"type": "message", "label": "查看", "text": "週報告"}},
                            ],
                        },
                    ],
                },
                {
                    "type": "box",
                    "layout": "horizontal",
                    "spacing": "sm",
                    "contents": [
                        {
                            "type": "box",
                            "layout": "vertical",
                            "backgroundColor": "#0F172A",
                            "cornerRadius": "12px",
                            "paddingAll": "12px",
                            "flex": 1,
                            "contents": [
                                {"type": "text", "text": "⏰ 鬧鐘", "size": "sm",
                                 "color": CORAL, "weight": "bold"},
                                {"type": "button", "style": "secondary", "height": "sm",
                                 "margin": "sm",
                                 "action": {"type": "message", "label": "查看", "text": "查看鬧鐘"}},
                            ],
                        },
                        {
                            "type": "box",
                            "layout": "vertical",
                            "backgroundColor": "#0F172A",
                            "cornerRadius": "12px",
                            "paddingAll": "12px",
                            "flex": 1,
                            "contents": [
                                {"type": "text", "text": "💡 睡眠建議", "size": "sm",
                                 "color": MINT, "weight": "bold"},
                                {"type": "button", "style": "secondary", "height": "sm",
                                 "margin": "sm",
                                 "action": {"type": "message", "label": "查看", "text": "睡眠建議"}},
                            ],
                        },
                    ],
                },
            ],
        },
        "footer": {
            "type": "box",
            "layout": "vertical",
            "backgroundColor": NAVY,
            "paddingAll": "12px",
            "contents": [
                {
                    "type": "text",
                    "text": "輸入「說明」查看完整指令列表",
                    "size": "xs",
                    "color": GRAY,
                    "align": "center",
                }
            ],
        },
    }


# ── Sleep Stats (Today) ────────────────────────────────────────────────────

def _duration_str(record):
    if not record.get("sleep_start") or not record.get("sleep_end"):
        return None, None, None
    start = datetime.fromisoformat(record["sleep_start"]).astimezone(TZ)
    end = datetime.fromisoformat(record["sleep_end"]).astimezone(TZ)
    delta = end - start
    hours = int(delta.total_seconds() // 3600)
    minutes = int((delta.total_seconds() % 3600) // 60)
    return start, end, (hours, minutes)


def build_sleep_stats(record, now):
    start, end, duration = _duration_str(record)

    if not start:
        # Still sleeping
        start = datetime.fromisoformat(record["sleep_start"]).astimezone(TZ)
        elapsed = now - start
        eh = int(elapsed.total_seconds() // 3600)
        em = int((elapsed.total_seconds() % 3600) // 60)
        status_text = f"😴 睡眠中... 已 {eh}h {em}m"
        status_color = VIOLET
        dur_text = "計時中"
        end_text = "未起床"
        quality_text = "計時中"
        bar_pct = min(int((eh / 8) * 100), 100)
    else:
        hours, minutes = duration
        if hours >= 7:
            status_text = "🌟 睡眠充足"
            status_color = MINT
            quality_text = "優良"
        elif hours >= 6:
            status_text = "⚡ 睡眠稍短"
            status_color = YELLOW
            quality_text = "普通"
        else:
            status_text = "⚠️ 睡眠不足"
            status_color = CORAL
            quality_text = "不足"
        dur_text = f"{hours} 小時 {minutes} 分鐘"
        end_text = end.strftime("%H:%M")
        bar_pct = min(int((hours / 8) * 100), 100)

    return {
        "type": "bubble",
        "size": "mega",
        "header": _header("📊 今日睡眠統計", now.strftime("%Y/%m/%d")),
        "body": {
            "type": "box",
            "layout": "vertical",
            "backgroundColor": INDIGO,
            "paddingAll": "16px",
            "spacing": "md",
            "contents": [
                {
                    "type": "text",
                    "text": status_text,
                    "size": "lg",
                    "color": status_color,
                    "weight": "bold",
                },
                {"type": "separator", "color": "#2D3748"},
                {
                    "type": "box",
                    "layout": "horizontal",
                    "contents": [
                        {"type": "text", "text": "🌙 入睡", "size": "sm", "color": GRAY, "flex": 2},
                        {"type": "text", "text": start.strftime("%H:%M"), "size": "sm",
                         "color": WHITE, "weight": "bold", "align": "end", "flex": 3},
                    ],
                },
                {
                    "type": "box",
                    "layout": "horizontal",
                    "contents": [
                        {"type": "text", "text": "☀️ 起床", "size": "sm", "color": GRAY, "flex": 2},
                        {"type": "text", "text": end_text if end else "計時中", "size": "sm",
                         "color": WHITE, "weight": "bold", "align": "end", "flex": 3},
                    ],
                },
                {
                    "type": "box",
                    "layout": "horizontal",
                    "contents": [
                        {"type": "text", "text": "⏱ 時長", "size": "sm", "color": GRAY, "flex": 2},
                        {"type": "text", "text": dur_text, "size": "sm",
                         "color": VIOLET, "weight": "bold", "align": "end", "flex": 3},
                    ],
                },
                {
                    "type": "box",
                    "layout": "horizontal",
                    "contents": [
                        {"type": "text", "text": "💤 品質", "size": "sm", "color": GRAY, "flex": 2},
                        {"type": "text", "text": quality_text, "size": "sm",
                         "color": status_color, "weight": "bold", "align": "end", "flex": 3},
                    ],
                },
                {"type": "separator", "color": "#2D3748"},
                # Progress bar
                {
                    "type": "box",
                    "layout": "vertical",
                    "contents": [
                        {"type": "text", "text": f"目標進度 (8小時) — {bar_pct}%",
                         "size": "xs", "color": GRAY},
                        {
                            "type": "box",
                            "layout": "horizontal",
                            "margin": "sm",
                            "contents": [
                                {
                                    "type": "box",
                                    "layout": "vertical",
                                    "backgroundColor": PURPLE,
                                    "height": "8px",
                                    "cornerRadius": "4px",
                                    "flex": bar_pct if bar_pct > 0 else 1,
                                    "contents": [],
                                },
                                {
                                    "type": "box",
                                    "layout": "vertical",
                                    "backgroundColor": "#2D3748",
                                    "height": "8px",
                                    "cornerRadius": "4px",
                                    "flex": max(100 - bar_pct, 1),
                                    "contents": [],
                                },
                            ],
                        },
                    ],
                },
            ],
        },
    }


# ── Week Report ────────────────────────────────────────────────────────────

def build_week_report(records, now):
    rows = []
    total_hours = 0
    count = 0

    # Build 7-day map
    day_map = {}
    for r in records:
        day_map[r["date"]] = r

    for i in range(6, -1, -1):
        day = (now.date() - timedelta(days=i)
               if hasattr(now, "date") else
               (now - timedelta(days=i)).date())
        date_str = day.isoformat()
        weekday = ["一", "二", "三", "四", "五", "六", "日"][day.weekday()]
        record = day_map.get(date_str)

        if record and record.get("sleep_start") and record.get("sleep_end"):
            start = datetime.fromisoformat(record["sleep_start"]).astimezone(TZ)
            end = datetime.fromisoformat(record["sleep_end"]).astimezone(TZ)
            delta = end - start
            hours = delta.total_seconds() / 3600
            total_hours += hours
            count += 1
            h = int(hours)
            m = int((hours - h) * 60)
            dur = f"{h}h{m:02d}m"
            bar_w = min(int(hours / 9 * 100), 100)
            color = MINT if hours >= 7 else (YELLOW if hours >= 6 else CORAL)
        else:
            dur = "—"
            bar_w = 0
            color = GRAY

        rows.append({
            "type": "box",
            "layout": "vertical",
            "margin": "sm",
            "contents": [
                {
                    "type": "box",
                    "layout": "horizontal",
                    "contents": [
                        {"type": "text", "text": f"週{weekday} {day.strftime('%m/%d')}",
                         "size": "xs", "color": GRAY, "flex": 3},
                        {"type": "text", "text": dur, "size": "xs",
                         "color": color, "weight": "bold", "align": "end", "flex": 2},
                    ],
                },
                {
                    "type": "box",
                    "layout": "horizontal",
                    "margin": "xs",
                    "contents": [
                        {
                            "type": "box",
                            "layout": "vertical",
                            "backgroundColor": color if bar_w > 0 else GRAY,
                            "height": "6px",
                            "cornerRadius": "3px",
                            "flex": bar_w if bar_w > 0 else 1,
                            "contents": [],
                        },
                        {
                            "type": "box",
                            "layout": "vertical",
                            "backgroundColor": "#2D3748",
                            "height": "6px",
                            "cornerRadius": "3px",
                            "flex": max(100 - bar_w, 1),
                            "contents": [],
                        },
                    ],
                },
            ],
        })

    avg_text = f"{total_hours/count:.1f} 小時" if count > 0 else "無資料"

    return {
        "type": "bubble",
        "size": "mega",
        "header": _header("📈 本週睡眠報告", f"平均睡眠：{avg_text}"),
        "body": {
            "type": "box",
            "layout": "vertical",
            "backgroundColor": INDIGO,
            "paddingAll": "16px",
            "spacing": "sm",
            "contents": rows,
        },
        "footer": {
            "type": "box",
            "layout": "vertical",
            "backgroundColor": NAVY,
            "paddingAll": "12px",
            "contents": [
                {"type": "text", "text": "🟢 ≥7h 充足　🟡 6-7h 普通　🔴 <6h 不足",
                 "size": "xxs", "color": GRAY, "align": "center", "wrap": True},
            ],
        },
    }


# ── Sleep Tips ─────────────────────────────────────────────────────────────

TIPS = [
    ("🌡️ 保持涼爽環境", "理想睡眠溫度約 18-22°C，涼爽環境有助於快速入睡"),
    ("📵 睡前放下手機", "藍光會抑制褪黑激素分泌，睡前1小時遠離螢幕"),
    ("☕ 下午後避免咖啡因", "咖啡、茶、可樂在身體中留存約6-8小時"),
    ("🧘 建立睡前儀式", "洗澡、冥想、閱讀紙本書，讓身體知道要睡覺了"),
    ("⏰ 固定作息時間", "每天同一時間起床，週末也不例外，建立生理時鐘"),
    ("🚶 白天適度運動", "規律運動改善睡眠品質，但避免睡前3小時激烈運動"),
]


def build_sleep_tips():
    bubbles = []
    for i, (title, desc) in enumerate(TIPS):
        bubbles.append({
            "type": "bubble",
            "size": "micro",
            "body": {
                "type": "box",
                "layout": "vertical",
                "backgroundColor": INDIGO,
                "paddingAll": "16px",
                "contents": [
                    {"type": "text", "text": f"Tip {i+1}/{len(TIPS)}", "size": "xxs", "color": VIOLET},
                    {"type": "text", "text": title, "size": "sm", "color": WHITE,
                     "weight": "bold", "margin": "sm", "wrap": True},
                    {"type": "separator", "margin": "sm", "color": "#2D3748"},
                    {"type": "text", "text": desc, "size": "xs", "color": GRAY,
                     "margin": "sm", "wrap": True},
                ],
            },
        })

    return {
        "type": "carousel",
        "contents": bubbles,
    }


# ── Timer Status ───────────────────────────────────────────────────────────

def build_timer_status(record, now):
    if not record or not record.get("sleep_start"):
        status = "未開始"
        detail = "輸入「睡覺」開始記錄"
        color = GRAY
        emoji = "💤"
    elif not record.get("sleep_end"):
        start = datetime.fromisoformat(record["sleep_start"]).astimezone(TZ)
        elapsed = now - start
        h = int(elapsed.total_seconds() // 3600)
        m = int((elapsed.total_seconds() % 3600) // 60)
        status = "計時中"
        detail = f"入睡：{start.strftime('%H:%M')}，已睡 {h}h {m:02d}m"
        color = VIOLET
        emoji = "😴"
    else:
        start = datetime.fromisoformat(record["sleep_start"]).astimezone(TZ)
        end = datetime.fromisoformat(record["sleep_end"]).astimezone(TZ)
        delta = end - start
        h = int(delta.total_seconds() // 3600)
        m = int((delta.total_seconds() % 3600) // 60)
        status = "已完成"
        detail = f"{start.strftime('%H:%M')} → {end.strftime('%H:%M')}，共 {h}h {m:02d}m"
        color = MINT
        emoji = "✅"

    return {
        "type": "bubble",
        "size": "kilo",
        "body": {
            "type": "box",
            "layout": "vertical",
            "backgroundColor": INDIGO,
            "paddingAll": "20px",
            "contents": [
                {"type": "text", "text": emoji, "size": "5xl", "align": "center"},
                {"type": "text", "text": status, "size": "xl", "color": color,
                 "weight": "bold", "align": "center", "margin": "md"},
                {"type": "text", "text": detail, "size": "sm", "color": GRAY,
                 "wrap": True, "align": "center", "margin": "sm"},
            ],
        },
    }
