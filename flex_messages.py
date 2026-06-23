from datetime import datetime, timedelta
import pytz

TZ = pytz.timezone("Asia/Taipei")

NAVY   = "#1A1A2E"
INDIGO = "#16213E"
PURPLE = "#7C3AED"
VIOLET = "#A78BFA"
MINT   = "#34D399"
YELLOW = "#FBBF24"
CORAL  = "#F87171"
WHITE  = "#FFFFFF"
GRAY   = "#94A3B8"


def _header(title, subtitle="", bg=NAVY):
    items = [{"type": "text", "text": title, "color": WHITE, "size": "xl", "weight": "bold"}]
    if subtitle:
        items.append({"type": "text", "text": subtitle, "color": VIOLET, "size": "sm", "margin": "xs"})
    return {"type": "box", "layout": "vertical", "backgroundColor": bg, "paddingAll": "20px", "contents": items}


def _card(contents, flex=1):
    return {
        "type": "box", "layout": "vertical", "flex": flex,
        "backgroundColor": "#0F172A", "cornerRadius": "12px",
        "paddingAll": "14px", "contents": contents,
    }


def _msg_btn(label, text, color=PURPLE):
    return {"type": "button", "style": "primary", "color": color, "height": "sm",
            "action": {"type": "message", "label": label, "text": text}}


# ── Main Menu ──────────────────────────────────────────────────────────────

def build_main_menu():
    return {
        "type": "bubble", "size": "giga",
        "header": _header("😴 睡眠小幫手", "選擇你要的睡眠類型"),
        "body": {
            "type": "box", "layout": "vertical",
            "backgroundColor": INDIGO, "paddingAll": "16px", "spacing": "md",
            "contents": [
                # 睡眠類型 三個
                {
                    "type": "box", "layout": "horizontal", "spacing": "sm",
                    "contents": [
                        _card([
                            {"type": "text", "text": "💤", "size": "xxl", "align": "center"},
                            {"type": "text", "text": "小睡", "size": "md", "color": WHITE,
                             "align": "center", "weight": "bold", "margin": "sm"},
                            {"type": "text", "text": "20-90分鐘", "size": "xxs",
                             "color": GRAY, "align": "center"},
                            _msg_btn("小睡", "小睡", VIOLET),
                        ]),
                        _card([
                            {"type": "text", "text": "😴", "size": "xxl", "align": "center"},
                            {"type": "text", "text": "中睡", "size": "md", "color": WHITE,
                             "align": "center", "weight": "bold", "margin": "sm"},
                            {"type": "text", "text": "3-5小時", "size": "xxs",
                             "color": GRAY, "align": "center"},
                            _msg_btn("中睡", "中睡", YELLOW),
                        ]),
                        _card([
                            {"type": "text", "text": "🛌", "size": "xxl", "align": "center"},
                            {"type": "text", "text": "大睡", "size": "md", "color": WHITE,
                             "align": "center", "weight": "bold", "margin": "sm"},
                            {"type": "text", "text": "7-9小時", "size": "xxs",
                             "color": GRAY, "align": "center"},
                            _msg_btn("大睡", "大睡", MINT),
                        ]),
                    ],
                },
                # 起床
                {
                    "type": "box", "layout": "vertical",
                    "backgroundColor": "#0F172A", "cornerRadius": "12px", "paddingAll": "14px",
                    "contents": [
                        _msg_btn("☀️ 起床了！結束計時", "起床", CORAL),
                    ],
                },
                # 統計 / 鬧鐘
                {
                    "type": "box", "layout": "horizontal", "spacing": "sm",
                    "contents": [
                        _card([
                            {"type": "text", "text": "📊 今日統計", "size": "sm",
                             "color": YELLOW, "weight": "bold"},
                            _msg_btn("查看", "統計"),
                        ]),
                        _card([
                            {"type": "text", "text": "📈 週報告", "size": "sm",
                             "color": VIOLET, "weight": "bold"},
                            _msg_btn("查看", "週報告"),
                        ]),
                        _card([
                            {"type": "text", "text": "⏰ 鬧鐘", "size": "sm",
                             "color": CORAL, "weight": "bold"},
                            _msg_btn("設定", "鬧鐘"),
                        ]),
                    ],
                },
            ],
        },
        "footer": {
            "type": "box", "layout": "vertical", "backgroundColor": NAVY, "paddingAll": "10px",
            "contents": [{"type": "text", "text": "輸入「說明」查看完整指令",
                          "size": "xs", "color": GRAY, "align": "center"}],
        },
    }


# ── Sleep Countdown ────────────────────────────────────────────────────────

def build_sleep_countdown(sleep_type, sleep_type_info, start_time, wake_time, hours, minutes):
    emoji = sleep_type_info["emoji"]
    bar_pct = min(int((hours / (sleep_type_info["suggestion_hours"] or 8)) * 100), 100)
    bar_pct = max(bar_pct, 1)

    if hours >= 7:
        quality_tip = "非常充足 🌟 好好享受！"
        color = MINT
    elif hours >= 4:
        quality_tip = "補眠效果不錯 ⚡"
        color = YELLOW
    elif hours >= 1:
        quality_tip = "短暫休息，恢復體力 😌"
        color = VIOLET
    else:
        quality_tip = "時間很短，善用小睡！"
        color = CORAL

    return {
        "type": "bubble", "size": "mega",
        "header": _header(f"{emoji} 已開始{sleep_type}！", start_time.strftime("%H:%M 入睡")),
        "body": {
            "type": "box", "layout": "vertical",
            "backgroundColor": INDIGO, "paddingAll": "16px", "spacing": "md",
            "contents": [
                {
                    "type": "box", "layout": "horizontal",
                    "contents": [
                        {"type": "text", "text": "⏰ 起床時間", "size": "sm", "color": GRAY, "flex": 2},
                        {"type": "text", "text": wake_time.strftime("%H:%M"), "size": "xl",
                         "color": WHITE, "weight": "bold", "align": "end", "flex": 3},
                    ],
                },
                {
                    "type": "box", "layout": "horizontal",
                    "contents": [
                        {"type": "text", "text": "💤 可睡時間", "size": "sm", "color": GRAY, "flex": 2},
                        {"type": "text", "text": f"{hours} 小時 {minutes} 分鐘",
                         "size": "lg", "color": color, "weight": "bold", "align": "end", "flex": 3},
                    ],
                },
                {"type": "separator", "color": "#2D3748"},
                {"type": "text", "text": quality_tip, "size": "sm", "color": color, "align": "center"},
                {
                    "type": "box", "layout": "horizontal", "margin": "sm",
                    "contents": [
                        {"type": "box", "layout": "vertical", "backgroundColor": color,
                         "height": "8px", "cornerRadius": "4px", "flex": bar_pct, "contents": []},
                        {"type": "box", "layout": "vertical", "backgroundColor": "#2D3748",
                         "height": "8px", "cornerRadius": "4px", "flex": max(100 - bar_pct, 1), "contents": []},
                    ],
                },
                {"type": "separator", "color": "#2D3748"},
                {"type": "text", "text": f"⏰ 鬧鐘已設定：{wake_time.strftime('%H:%M')} 連響 3 次",
                 "size": "xs", "color": GRAY, "align": "center"},
                {"type": "text", "text": "起床時輸入「起床」記錄睡眠 ☀️",
                 "size": "xs", "color": GRAY, "align": "center"},
            ],
        },
    }


# ── Sleep Stats (Today) ────────────────────────────────────────────────────

def build_sleep_stats(record, now):
    sleep_type = record.get("sleep_type", "大睡")
    target_wake = record.get("target_wake")

    if record.get("sleep_start") and record.get("sleep_end"):
        start = datetime.fromisoformat(record["sleep_start"]).astimezone(TZ)
        end = datetime.fromisoformat(record["sleep_end"]).astimezone(TZ)
        delta = end - start
        hours = int(delta.total_seconds() // 3600)
        minutes = int((delta.total_seconds() % 3600) // 60)
        end_text = end.strftime("%H:%M")
        dur_text = f"{hours} 小時 {minutes} 分鐘"
        color = MINT if hours >= 7 else (YELLOW if hours >= 4 else CORAL)
        status = "🌟 已完成" if hours >= 7 else ("⚡ 普通" if hours >= 4 else "⚠️ 偏短")
        bar_pct = min(int(hours / 8 * 100), 100)
    elif record.get("sleep_start"):
        start = datetime.fromisoformat(record["sleep_start"]).astimezone(TZ)
        elapsed = now - start
        eh = int(elapsed.total_seconds() // 3600)
        em = int((elapsed.total_seconds() % 3600) // 60)
        end_text = "睡眠中..."
        dur_text = f"已睡 {eh}h {em:02d}m"
        color = VIOLET
        status = "😴 計時中"
        hours = eh
        bar_pct = min(int(eh / 8 * 100), 100)
    else:
        return {"type": "bubble", "body": {"type": "box", "layout": "vertical",
                "contents": [{"type": "text", "text": "今天還沒有記錄"}]}}

    return {
        "type": "bubble", "size": "mega",
        "header": _header("📊 今日睡眠統計", now.strftime("%Y/%m/%d")),
        "body": {
            "type": "box", "layout": "vertical",
            "backgroundColor": INDIGO, "paddingAll": "16px", "spacing": "md",
            "contents": [
                {"type": "text", "text": status, "size": "lg", "color": color, "weight": "bold"},
                {"type": "separator", "color": "#2D3748"},
                {"type": "box", "layout": "horizontal", "contents": [
                    {"type": "text", "text": "🛌 類型", "size": "sm", "color": GRAY, "flex": 2},
                    {"type": "text", "text": sleep_type, "size": "sm", "color": WHITE,
                     "weight": "bold", "align": "end", "flex": 3},
                ]},
                {"type": "box", "layout": "horizontal", "contents": [
                    {"type": "text", "text": "🌙 入睡", "size": "sm", "color": GRAY, "flex": 2},
                    {"type": "text", "text": start.strftime("%H:%M"), "size": "sm",
                     "color": WHITE, "weight": "bold", "align": "end", "flex": 3},
                ]},
                {"type": "box", "layout": "horizontal", "contents": [
                    {"type": "text", "text": "☀️ 起床", "size": "sm", "color": GRAY, "flex": 2},
                    {"type": "text", "text": end_text, "size": "sm", "color": WHITE,
                     "weight": "bold", "align": "end", "flex": 3},
                ]},
                {"type": "box", "layout": "horizontal", "contents": [
                    {"type": "text", "text": "⏱ 時長", "size": "sm", "color": GRAY, "flex": 2},
                    {"type": "text", "text": dur_text, "size": "sm", "color": color,
                     "weight": "bold", "align": "end", "flex": 3},
                ]},
                *([] if not target_wake else [
                    {"type": "box", "layout": "horizontal", "contents": [
                        {"type": "text", "text": "⏰ 目標", "size": "sm", "color": GRAY, "flex": 2},
                        {"type": "text", "text": target_wake, "size": "sm", "color": VIOLET,
                         "weight": "bold", "align": "end", "flex": 3},
                    ]},
                ]),
                {"type": "separator", "color": "#2D3748"},
                {"type": "text", "text": f"目標進度 (8小時) — {min(bar_pct, 100)}%",
                 "size": "xs", "color": GRAY},
                {"type": "box", "layout": "horizontal", "margin": "sm", "contents": [
                    {"type": "box", "layout": "vertical", "backgroundColor": color,
                     "height": "8px", "cornerRadius": "4px", "flex": bar_pct if bar_pct > 0 else 1, "contents": []},
                    {"type": "box", "layout": "vertical", "backgroundColor": "#2D3748",
                     "height": "8px", "cornerRadius": "4px", "flex": max(100 - bar_pct, 1), "contents": []},
                ]},
            ],
        },
    }


# ── Week Report ────────────────────────────────────────────────────────────

def build_week_report(records, now):
    day_map = {r["date"]: r for r in records}
    rows = []
    total_hours = 0
    count = 0

    for i in range(6, -1, -1):
        day = now.date() - timedelta(days=i)
        date_str = day.isoformat()
        weekday = ["一", "二", "三", "四", "五", "六", "日"][day.weekday()]
        record = day_map.get(date_str)
        sleep_type = record.get("sleep_type", "") if record else ""

        if record and record.get("sleep_start") and record.get("sleep_end"):
            start = datetime.fromisoformat(record["sleep_start"]).astimezone(TZ)
            end = datetime.fromisoformat(record["sleep_end"]).astimezone(TZ)
            hours = (end - start).total_seconds() / 3600
            total_hours += hours
            count += 1
            h, m = int(hours), int((hours % 1) * 60)
            dur = f"{h}h{m:02d}m"
            bar_w = min(int(hours / 9 * 100), 100)
            color = MINT if hours >= 7 else (YELLOW if hours >= 4 else CORAL)
            type_label = f" ({sleep_type})" if sleep_type else ""
        else:
            dur, bar_w, color, type_label = "—", 0, GRAY, ""

        rows.append({
            "type": "box", "layout": "vertical", "margin": "sm",
            "contents": [
                {"type": "box", "layout": "horizontal", "contents": [
                    {"type": "text", "text": f"週{weekday} {day.strftime('%m/%d')}{type_label}",
                     "size": "xs", "color": GRAY, "flex": 4},
                    {"type": "text", "text": dur, "size": "xs", "color": color,
                     "weight": "bold", "align": "end", "flex": 2},
                ]},
                {"type": "box", "layout": "horizontal", "margin": "xs", "contents": [
                    {"type": "box", "layout": "vertical", "backgroundColor": color if bar_w > 0 else GRAY,
                     "height": "6px", "cornerRadius": "3px", "flex": bar_w if bar_w > 0 else 1, "contents": []},
                    {"type": "box", "layout": "vertical", "backgroundColor": "#2D3748",
                     "height": "6px", "cornerRadius": "3px", "flex": max(100 - bar_w, 1), "contents": []},
                ]},
            ],
        })

    avg = f"{total_hours/count:.1f} 小時" if count else "無資料"
    return {
        "type": "bubble", "size": "mega",
        "header": _header("📈 本週睡眠報告", f"平均睡眠：{avg}"),
        "body": {
            "type": "box", "layout": "vertical",
            "backgroundColor": INDIGO, "paddingAll": "16px", "spacing": "sm",
            "contents": rows,
        },
        "footer": {
            "type": "box", "layout": "vertical", "backgroundColor": NAVY, "paddingAll": "10px",
            "contents": [{"type": "text", "text": "🟢 ≥7h 大睡　🟡 4-7h 中睡　🔴 <4h 小睡",
                          "size": "xxs", "color": GRAY, "align": "center", "wrap": True}],
        },
    }


# ── Sleep Tips ─────────────────────────────────────────────────────────────

TIPS = [
    ("🌡️ 保持涼爽環境", "理想睡眠溫度約 18-22°C，涼爽有助入睡"),
    ("📵 睡前放下手機", "藍光抑制褪黑激素，睡前1小時遠離螢幕"),
    ("☕ 下午後避免咖啡因", "咖啡因在身體留存約 6-8 小時"),
    ("🧘 建立睡前儀式", "洗澡、冥想、閱讀，讓身體準備好睡覺"),
    ("⏰ 固定作息時間", "每天同一時間起床，建立穩定生理時鐘"),
    ("💤 善用小睡", "20分鐘小睡可大幅提升下午的專注力"),
]


def build_sleep_tips():
    return {
        "type": "carousel",
        "contents": [
            {
                "type": "bubble", "size": "micro",
                "body": {
                    "type": "box", "layout": "vertical",
                    "backgroundColor": INDIGO, "paddingAll": "16px",
                    "contents": [
                        {"type": "text", "text": f"Tip {i+1}/{len(TIPS)}", "size": "xxs", "color": VIOLET},
                        {"type": "text", "text": title, "size": "sm", "color": WHITE,
                         "weight": "bold", "margin": "sm", "wrap": True},
                        {"type": "separator", "margin": "sm", "color": "#2D3748"},
                        {"type": "text", "text": desc, "size": "xs", "color": GRAY,
                         "margin": "sm", "wrap": True},
                    ],
                },
            }
            for i, (title, desc) in enumerate(TIPS)
        ],
    }


# ── Timer Status ───────────────────────────────────────────────────────────

def build_timer_status(record, now):
    if not record or not record.get("sleep_start"):
        return {
            "type": "bubble", "size": "kilo",
            "body": {"type": "box", "layout": "vertical", "backgroundColor": INDIGO, "paddingAll": "20px",
                     "contents": [
                         {"type": "text", "text": "💤", "size": "5xl", "align": "center"},
                         {"type": "text", "text": "未開始", "size": "xl", "color": GRAY,
                          "weight": "bold", "align": "center", "margin": "md"},
                         {"type": "text", "text": "點選單選擇睡眠類型開始記錄", "size": "sm",
                          "color": GRAY, "wrap": True, "align": "center", "margin": "sm"},
                     ]},
        }
    elif not record.get("sleep_end"):
        start = datetime.fromisoformat(record["sleep_start"]).astimezone(TZ)
        elapsed = now - start
        h = int(elapsed.total_seconds() // 3600)
        m = int((elapsed.total_seconds() % 3600) // 60)
        sleep_type = record.get("sleep_type", "大睡")
        target = record.get("target_wake", "")
        return {
            "type": "bubble", "size": "kilo",
            "body": {"type": "box", "layout": "vertical", "backgroundColor": INDIGO, "paddingAll": "20px",
                     "contents": [
                         {"type": "text", "text": "😴", "size": "5xl", "align": "center"},
                         {"type": "text", "text": f"{sleep_type} 計時中", "size": "xl", "color": VIOLET,
                          "weight": "bold", "align": "center", "margin": "md"},
                         {"type": "text", "text": f"入睡：{start.strftime('%H:%M')}，已睡 {h}h {m:02d}m",
                          "size": "sm", "color": GRAY, "wrap": True, "align": "center", "margin": "sm"},
                         *([] if not target else [
                             {"type": "text", "text": f"⏰ 鬧鐘：{target}", "size": "sm",
                              "color": MINT, "align": "center"}
                         ]),
                     ]},
        }
    else:
        start = datetime.fromisoformat(record["sleep_start"]).astimezone(TZ)
        end = datetime.fromisoformat(record["sleep_end"]).astimezone(TZ)
        h = int((end - start).total_seconds() // 3600)
        m = int(((end - start).total_seconds() % 3600) // 60)
        return {
            "type": "bubble", "size": "kilo",
            "body": {"type": "box", "layout": "vertical", "backgroundColor": INDIGO, "paddingAll": "20px",
                     "contents": [
                         {"type": "text", "text": "✅", "size": "5xl", "align": "center"},
                         {"type": "text", "text": "已完成", "size": "xl", "color": MINT,
                          "weight": "bold", "align": "center", "margin": "md"},
                         {"type": "text", "text": f"{start.strftime('%H:%M')} → {end.strftime('%H:%M')}，共 {h}h {m:02d}m",
                          "size": "sm", "color": GRAY, "wrap": True, "align": "center", "margin": "sm"},
                     ]},
        }
