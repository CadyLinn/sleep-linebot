"""
setup_rich_menu.py  ── 建立含文字的 6 格 Rich Menu
用法：LINE_CHANNEL_ACCESS_TOKEN=xxx python setup_rich_menu.py
"""
import os, sys, io, requests
from PIL import Image

TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "")
if not TOKEN:
    print("❌ 請先設定環境變數 LINE_CHANNEL_ACCESS_TOKEN")
    sys.exit(1)

HEADERS = {"Authorization": f"Bearer {TOKEN}"}

RICH_MENU = {
    "size": {"width": 2500, "height": 1686},
    "selected": True,
    "name": "睡眠小幫手選單 v2",
    "chatBarText": "😴 睡眠選單",
    "areas": [
        # 上排：開始睡覺 / 起床 / 今日統計
        {"bounds": {"x":    0, "y":   0, "width": 833, "height": 843},
         "action": {"type": "message", "label": "😴 開始睡覺", "text": "睡覺"}},
        {"bounds": {"x":  833, "y":   0, "width": 834, "height": 843},
         "action": {"type": "message", "label": "☀️ 起床", "text": "起床"}},
        {"bounds": {"x": 1667, "y":   0, "width": 833, "height": 843},
         "action": {"type": "message", "label": "📊 今日統計", "text": "今日統計"}},
        # 下排：週報告 / 鬧鐘 / 睡眠建議
        {"bounds": {"x":    0, "y": 843, "width": 833, "height": 843},
         "action": {"type": "message", "label": "📈 週報告", "text": "週報告"}},
        {"bounds": {"x":  833, "y": 843, "width": 834, "height": 843},
         "action": {"type": "message", "label": "⏰ 鬧鐘", "text": "鬧鐘"}},
        {"bounds": {"x": 1667, "y": 843, "width": 833, "height": 843},
         "action": {"type": "message", "label": "💡 睡眠建議", "text": "睡眠建議"}},
    ],
}

# Step 1: 建立選單
print("📋 Step 1: 建立 Rich Menu...")
r = requests.post("https://api.line.me/v2/bot/richmenu",
                  headers={**HEADERS, "Content-Type": "application/json"},
                  json=RICH_MENU)
if r.status_code != 200:
    print(f"❌ 失敗: {r.status_code} {r.text}"); sys.exit(1)
rich_menu_id = r.json()["richMenuId"]
print(f"✅ 建立成功：{rich_menu_id}")

# Step 2: 上傳圖片
IMAGE_PATH = "rich_menu.jpg"
if not os.path.exists(IMAGE_PATH):
    print(f"❌ 找不到圖片：{IMAGE_PATH}"); sys.exit(1)

print("🖼  Step 2: 調整尺寸並上傳圖片...")
img = Image.open(IMAGE_PATH).convert("RGB").resize((2500, 1686), Image.LANCZOS)
buf = io.BytesIO()
img.save(buf, format="JPEG", quality=95)
buf.seek(0)

r = requests.post(f"https://api-data.line.me/v2/bot/richmenu/{rich_menu_id}/content",
                  headers={**HEADERS, "Content-Type": "image/jpeg"},
                  data=buf.read())
if r.status_code != 200:
    print(f"❌ 上傳失敗: {r.status_code} {r.text}"); sys.exit(1)
print("✅ 圖片上傳成功")

# Step 3: 設為預設
print("⚙️  Step 3: 設為預設 Rich Menu...")
r = requests.post(f"https://api.line.me/v2/bot/user/all/richmenu/{rich_menu_id}",
                  headers=HEADERS)
if r.status_code != 200:
    print(f"❌ 設定失敗: {r.status_code} {r.text}"); sys.exit(1)
print("✅ 已設為所有用戶的預設選單")

print(f"""
🎉 Rich Menu 設定完成！ID: {rich_menu_id}

┌──────────┬──────────┬──────────┐
│ 😴 開始睡覺 │  ☀️ 起床  │ 📊 今日統計 │
├──────────┼──────────┼──────────┤
│ 📈 週報告 │  ⏰ 鬧鐘  │ 💡 睡眠建議 │
└──────────┴──────────┴──────────┘
""")
