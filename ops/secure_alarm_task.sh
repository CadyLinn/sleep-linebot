#!/usr/bin/env bash
# 讓 /tasks/check-alarms 只接受 Cloud Scheduler 的 OIDC token。分兩階段，順序不能反：
#   ./ops/secure_alarm_task.sh scheduler  # 1. Scheduler 開始帶 token（舊程式會忽略，不影響鬧鐘）
#   （部署含驗證程式的版本）
#   ./ops/secure_alarm_task.sh enforce    # 2. 服務開始驗證 token
#   ./ops/secure_alarm_task.sh disable    # 緊急關閉驗證
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-$(gcloud config get-value project 2>/dev/null)}"
REGION="${REGION:-asia-east1}"
SERVICE="${SERVICE:-sleep-linebot}"
JOB="${JOB:-check-alarms-every-minute}"
SA_NAME=alarm-scheduler
SA="${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
G="gcloud --project $PROJECT_ID --quiet"

# 用 Scheduler 目前呼叫的網址當 audience（不含路徑），兩邊才會一致
JOB_URI=$($G scheduler jobs describe "$JOB" --location "$REGION" --format 'value(httpTarget.uri)')
AUDIENCE="${JOB_URI%%/tasks/*}"

case "${1:-}" in
  scheduler)
    $G iam service-accounts describe "$SA" > /dev/null 2>&1 ||
      $G iam service-accounts create "$SA_NAME" --display-name "Cloud Scheduler alarm caller"
    $G scheduler jobs update http "$JOB" --location "$REGION" \
      --oidc-service-account-email "$SA" --oidc-token-audience "$AUDIENCE"
    echo "Scheduler now sends OIDC tokens as $SA (audience $AUDIENCE)"
    ;;
  enforce)
    $G run services update "$SERVICE" --region "$REGION" \
      --update-env-vars "TASKS_INVOKER_SA=$SA,TASKS_AUDIENCE=$AUDIENCE"
    echo "Enforcing. Unauthenticated call now returns:"
    curl -s -o /dev/null -w '%{http_code}\n' -X POST "$JOB_URI"
    ;;
  disable)
    $G run services update "$SERVICE" --region "$REGION" --remove-env-vars TASKS_INVOKER_SA,TASKS_AUDIENCE
    ;;
  *)
    echo "usage: $0 scheduler|enforce|disable" >&2
    exit 1
    ;;
esac
