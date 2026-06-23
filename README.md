# Sleep Line Bot

Sleep Line Bot is a LINE Messaging API bot for recording sleep, setting wake-up alarms, and reviewing daily or weekly sleep summaries. It is built with Flask, deployed on Google Cloud Run, and stores user records in Firestore.

## Features

- Start sleep tracking by sleep type: nap, medium sleep, or long sleep
- Automatically classify sleep type by actual duration when the user wakes up
- Set wake-up alarms by exact time or duration, with configurable notification count
- Cancel or update existing alarms
- Track multiple sleep sessions in the same day
- View daily sleep statistics and weekly reports
- Calculate how long the user can sleep until a target wake-up time
- Recommend wake-up times based on 90-minute sleep cycles
- Show sleep tips and a text-based command guide for desktop LINE users
- Send a short welcome message when a user adds the bot

## Tech Stack

- Python
- Flask
- LINE Messaging API
- Google Cloud Run
- Google Firestore
- APScheduler

## Project Structure

```text
app.py              # Flask app, LINE webhook handlers, alarm scheduler
db.py               # Firestore data access layer
flex_messages.py    # LINE Flex Message templates
setup_rich_menu.py  # Rich menu setup script
rich_menu.jpg       # LINE rich menu image
requirements.txt    # Python dependencies
Dockerfile          # Cloud Run container build
```

## LINE Bot Commands

Users can type these commands in mobile or desktop LINE:

```text
開始睡覺
起床
今日統計
週報告
鬧鐘
睡眠建議
算可睡多久
睡眠週期
說明
```

Example inputs:

```text
我要睡20分鐘
鬧鐘 07:30 3次
現在睡 07:30 起床
睡眠週期
睡眠週期 10分鐘後睡著
```

## Firestore Collections

```text
sleep_records   # Sleep tracking records
user_settings   # Alarms, bedtime reminders, and pending interaction state
```

## Environment Variables

Set these variables before running the bot:

```text
LINE_CHANNEL_ACCESS_TOKEN
LINE_CHANNEL_SECRET
```

On Cloud Run, Firestore uses Google Application Default Credentials. The Cloud Run service account must have permission to read and write Firestore.

## Local Development

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python app.py
```

The webhook endpoint is:

```text
/callback
```

## Deploy to Cloud Run

```bash
gcloud run deploy sleep-linebot \
  --source . \
  --region asia-east1 \
  --allow-unauthenticated
```

After deployment, set the LINE Developers webhook URL to:

```text
https://YOUR_CLOUD_RUN_URL/callback
```

## GitHub About

Recommended repository description:

```text
A LINE bot for sleep tracking, wake-up alarms, sleep cycle suggestions, and daily or weekly sleep reports.
```
