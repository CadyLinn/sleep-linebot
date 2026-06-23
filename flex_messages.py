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


def _fit_text(text, size="sm", color=WHITE, weight=None, align=None, flex=None, wrap=False):
    item = {
        "type": "text",
        "text": text,
        "size": size,
        "color": color,
        "adjustMode": "shrink-to-fit",
        "wrap": wrap,
    }
    if weight:
        item["weight"] = weight
    if align:
        item["align"] = align
    if flex is not None:
        item["flex"] = flex
    return item


def _duration_parts(start, end):
    total_min = max(int((end - start).total_seconds() // 60), 0)
    return total_min, total_min // 60, total_min % 60


def _duration_text(total_min):
    hours = total_min // 60
    minutes = total_min % 60
    if hours and minutes:
        return f"{hours}小時{minutes:02d}分"
    if hours:
        return f"{hours}小時"
    return f"{minutes}分鐘"


def _record_report_date(record):
    timestamp = record.get("sleep_end") or record.get("sleep_start")
    if not timestamp:
        return None
    return datetime.fromisoformat(timestamp).astimezone(TZ).date().isoformat()


def _info_row(label, value, value_color=WHITE):
    return {
        "type": "box",
        "layout": "horizontal",
        "spacing": "md",
        "contents": [
            _fit_text(label, "sm", GRAY, flex=4, wrap=True),
            _fit_text(value, "xl", value_color, "bold", "end", flex=6, wrap=False),
        ],
    }


# ── Main Menu ──────────────────────────────────────────────────────────────

def _menu_row(emoji, title, desc, btn_label, btn_text, color=PURPLE):
    """一列選單項目：emoji + 標題 + 說明 + 按鈕"""
    return {
        "type": "box",
        "layout": "horizontal",
        "backgroundColor": "#0F172A",
        "cornerRadius": "12px",
        "paddingAll": "14px",
        "spacing": "md",
        "contents": [
            # 左側 emoji
            {
                "type": "box",
                "layout": "vertical",
                "justifyContent": "center",
                "flex": 1,
                "contents": [
                    {"type": "text", "text": emoji, "size": "xxl", "align": "center"},
                ],
            },
            # 中間 標題＋說明
            {
                "type": "box",
                "layout": "vertical",
                "flex": 4,
                "justifyContent": "center",
                "contents": [
                    {"type": "text", "text": title, "size": "md",
                     "color": WHITE, "weight": "bold"},
                    {"type": "text", "text": desc, "size": "xs",
                     "color": GRAY, "wrap": True, "margin": "xs"},
                ],
            },
            # 右側 按鈕
            {
                "type": "box",
                "layout": "vertical",
                "flex": 2,
                "justifyContent": "center",
                "contents": [
                    {"type": "button", "style": "primary", "color": color,
                     "height": "sm",
                     "action": {"type": "message", "label": btn_label, "text": btn_text}},
                ],
            },
        ],
    }


# ── Main Menu ──────────────────────────────────────────────────────────────

def build_main_menu():
    return {
        "type": "bubble",
        "size": "giga",
        "header": {
            "type": "box",
            "layout": "vertical",
            "backgroundColor": NAVY,
            "paddingAll": "20px",
            "contents": [
                {"type": "text", "text": "😴 睡眠小幫手",
                 "color": WHITE, "size": "xl", "weight": "bold"},
                {"type": "text", "text": "常用功能都在這裡",
                 "color": VIOLET, "size": "sm", "margin": "xs"},
            ],
        },
        "body": {
            "type": "box",
            "layout": "vertical",
            "backgroundColor": INDIGO,
            "paddingAll": "14px",
            "spacing": "sm",
            "contents": [
                {"type": "text", "text": "⭐  常用",
                 "size": "xs", "color": VIOLET, "weight": "bold", "margin": "md"},

                _menu_row("😴", "開始睡覺", "選擇小睡、中睡、大睡或直接輸入分鐘", "開始", "睡覺", VIOLET),
                _menu_row("☀️", "起床", "結束目前計時並記錄睡眠", "起床", "起床", CORAL),
                _menu_row("📊", "今日統計", "加總今天每一次睡眠與小睡", "查看", "今日統計", PURPLE),
                _menu_row("📈", "週報告", "查看本週每天累計睡眠", "查看", "週報告", PURPLE),
                _menu_row("⏰", "鬧鐘設定", "可設定時間、倒數分鐘與通知次數", "設定", "鬧鐘", CORAL),
                _menu_row("💡", "睡眠建議", "改善睡眠品質的小知識", "查看", "睡眠建議", MINT),
            ],
        },
    }



# ── Sleep Countdown ────────────────────────────────────────────────────────

# ── Sleep Countdown ────────────────────────────────────────────────────────

def build_sleep_countdown(sleep_type, sleep_type_info, start_time, wake_time, hours, minutes):
    emoji = sleep_type_info["emoji"]
    total_minutes = hours * 60 + minutes
    suggestion_min = max(int(sleep_type_info["suggestion_hours"] * 60), 1)
    bar_pct = max(min(int(total_minutes / suggestion_min * 100), 100), 1)

    if total_minutes >= 420:
        quality_tip, color = "非常充足 🌟 好好享受！", MINT
    elif total_minutes >= 180:
        quality_tip, color = "補眠效果不錯 ⚡", YELLOW
    elif total_minutes >= 20:
        quality_tip, color = "短暫休息，恢復體力 😌", VIOLET
    else:
        quality_tip, color = "超短衝刺睡眠 ⚡", CORAL

    # 時長文字（10分鐘不顯示「0小時」）
    if hours > 0 and minutes > 0:
        dur_text = f"{hours}h {minutes}m"
    elif hours > 0:
        dur_text = f"{hours} 小時"
    else:
        dur_text = f"{minutes} 分鐘"

    return {
        "type": "bubble", "size": "mega",
        "header": {
            "type": "box", "layout": "vertical",
            "backgroundColor": NAVY, "paddingAll": "16px",
            "contents": [
                {"type": "text", "text": f"{emoji} 已開始{sleep_type}！",
                 "color": WHITE, "size": "lg", "weight": "bold"},
                {"type": "separator", "color": "#2D3748", "margin": "md"},
                {
                    "type": "box", "layout": "vertical",
                    "margin": "md", "spacing": "sm",
                    "contents": [
                        _info_row("🌙 入睡時間", start_time.strftime("%H:%M"), VIOLET),
                        _info_row("☀️ 預計起床", wake_time.strftime("%H:%M"), MINT),
                        _info_row("⏱ 可睡多久", dur_text, color),
                    ],
                },
            ],
        },
        "body": {
            "type": "box", "layout": "vertical",
            "backgroundColor": INDIGO, "paddingAll": "16px", "spacing": "md",
            "contents": [
                {"type": "text", "text": quality_tip,
                 "size": "sm", "color": color, "align": "center", "weight": "bold"},
                {
                    "type": "box", "layout": "horizontal", "margin": "sm",
                    "contents": [
                        {"type": "box", "layout": "vertical", "backgroundColor": color,
                         "height": "8px", "cornerRadius": "4px",
                         "flex": bar_pct, "contents": []},
                        {"type": "box", "layout": "vertical", "backgroundColor": "#2D3748",
                         "height": "8px", "cornerRadius": "4px",
                         "flex": max(100 - bar_pct, 1), "contents": []},
                    ],
                },
                {"type": "separator", "color": "#2D3748"},
                {"type": "text",
                 "text": f"⏰ 鬧鐘：{wake_time.strftime('%H:%M')} 預設通知 1 次",
                 "size": "xs", "color": GRAY, "align": "center"},
                {"type": "text", "text": "起床後輸入「起床」記錄睡眠 ☀️",
                 "size": "xs", "color": GRAY, "align": "center"},
            ],
        },
        "footer": {
            "type": "box", "layout": "vertical",
            "backgroundColor": NAVY, "paddingAll": "12px", "spacing": "sm",
            "contents": [
                {"type": "text", "text": "鬧鐘通知次數",
                 "size": "xs", "color": GRAY, "align": "center"},
                {
                    "type": "box", "layout": "horizontal", "spacing": "sm",
                    "contents": [
                        _msg_btn("響1次", "鬧鐘響1次", VIOLET),
                        _msg_btn("響3次", "鬧鐘響3次", PURPLE),
                        _msg_btn("響5次", "鬧鐘響5次", CORAL),
                    ],
                },
            ],
        },
    }




# ── Sleep Stats (Today) ────────────────────────────────────────────────────

def build_sleep_stats(records, now):
    if isinstance(records, dict):
        records = [records]

    completed = []
    running = None
    for record in records:
        if record.get("sleep_start") and record.get("sleep_end"):
            start = datetime.fromisoformat(record["sleep_start"]).astimezone(TZ)
            end = datetime.fromisoformat(record["sleep_end"]).astimezone(TZ)
            total_min, _, _ = _duration_parts(start, end)
            completed.append((record, start, end, total_min))
        elif record.get("sleep_start"):
            running = record

    if completed:
        first_start = min(item[1] for item in completed)
        last_end = max(item[2] for item in completed)
        total_min = sum(item[3] for item in completed)
        hours = total_min // 60
        minutes = total_min % 60
        dur_text = _duration_text(total_min)
        color = MINT if hours >= 7 else (YELLOW if hours >= 4 else CORAL)
        status = "🌟 已完成" if hours >= 7 else ("⚡ 普通" if hours >= 4 else "😌 已記錄")
        bar_pct = min(int(total_min / 480 * 100), 100)
        type_counts = {}
        for record, _, _, _ in completed:
            sleep_type = record.get("sleep_type", "睡眠")
            type_counts[sleep_type] = type_counts.get(sleep_type, 0) + 1
        type_text = "、".join(f"{name}{count}次" for name, count in type_counts.items())
        rows = [
            ("🛌 類型", type_text),
            ("🌙 首次入睡", first_start.strftime("%H:%M")),
            ("☀️ 最後起床", last_end.strftime("%H:%M")),
            ("⏱ 總時長", dur_text),
            ("📌 筆數", f"{len(completed)} 筆"),
        ]
    elif running:
        sleep_type = running.get("sleep_type", "大睡")
        target_wake = running.get("target_wake")
        start = datetime.fromisoformat(running["sleep_start"]).astimezone(TZ)
        elapsed = now - start
        total_min = max(int(elapsed.total_seconds() // 60), 0)
        dur_text = f"已睡 {_duration_text(total_min)}"
        color = VIOLET
        status = "😴 計時中"
        bar_pct = min(int(total_min / 480 * 100), 100)
        rows = [
            ("🛌 類型", sleep_type),
            ("🌙 入睡", start.strftime("%H:%M")),
            ("☀️ 起床", "睡眠中"),
            ("⏱ 時長", dur_text),
        ]
        if target_wake:
            rows.append(("⏰ 目標", target_wake))
    else:
        return {"type": "bubble", "body": {"type": "box", "layout": "vertical",
                "contents": [{"type": "text", "text": "今天還沒有記錄"}]}}

    detail_rows = [
        {"type": "box", "layout": "horizontal", "spacing": "sm", "contents": [
            _fit_text(label, "xs", GRAY, flex=3, wrap=True),
            _fit_text(value, "sm", color if label.startswith("⏱") else WHITE, "bold", "end", flex=5, wrap=True),
        ]}
        for label, value in rows
    ]

    return {
        "type": "bubble", "size": "mega",
        "header": _header("📊 今日睡眠統計", now.strftime("%Y/%m/%d")),
        "body": {
            "type": "box", "layout": "vertical",
            "backgroundColor": INDIGO, "paddingAll": "16px", "spacing": "md",
            "contents": [
                _fit_text(status, "lg", color, "bold", wrap=True),
                {"type": "separator", "color": "#2D3748"},
                *detail_rows,
                {"type": "separator", "color": "#2D3748"},
                _fit_text(f"目標進度 (8小時) - {min(bar_pct, 100)}%", "xs", GRAY, wrap=True),
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
    day_map = {}
    for record in records:
        report_date = _record_report_date(record)
        if report_date:
            day_map.setdefault(report_date, []).append(record)
    rows = []
    total_hours = 0
    count = 0

    for i in range(6, -1, -1):
        day = now.date() - timedelta(days=i)
        date_str = day.isoformat()
        weekday = ["一", "二", "三", "四", "五", "六", "日"][day.weekday()]
        day_records = day_map.get(date_str, [])

        completed = []
        type_counts = {}
        for record in day_records:
            if record.get("sleep_start") and record.get("sleep_end"):
                start = datetime.fromisoformat(record["sleep_start"]).astimezone(TZ)
                end = datetime.fromisoformat(record["sleep_end"]).astimezone(TZ)
                total_min, _, _ = _duration_parts(start, end)
                completed.append(total_min)
                sleep_type = record.get("sleep_type", "睡眠")
                type_counts[sleep_type] = type_counts.get(sleep_type, 0) + 1

        if completed:
            day_minutes = sum(completed)
            hours = day_minutes / 60
            total_hours += hours
            count += 1
            h, m = day_minutes // 60, day_minutes % 60
            dur = f"{h}h{m:02d}m"
            bar_w = min(int(hours / 9 * 100), 100)
            color = MINT if hours >= 7 else (YELLOW if hours >= 4 else CORAL)
            type_label = " " + "/".join(f"{name}{n}" for name, n in type_counts.items())
        else:
            dur, bar_w, color, type_label = "—", 0, GRAY, ""

        rows.append({
            "type": "box", "layout": "vertical", "margin": "sm",
            "contents": [
                {"type": "box", "layout": "horizontal", "contents": [
                    _fit_text(f"週{weekday} {day.strftime('%m/%d')}{type_label}", "xxs", GRAY, flex=5, wrap=True),
                    _fit_text(dur, "xs", color, "bold", "end", flex=2),
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
            "contents": [{"type": "text", "text": "🟢 ≥7h 大睡　🟡 3-5h 中睡　🔴 10-90m 小睡",
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
    ("💤 善用小睡", "10-90分鐘小睡可幫助恢復精神與專注力"),
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
