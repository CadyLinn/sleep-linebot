#!/usr/bin/env bash
# 建立監控：log-based metrics、uptime check、儀表板、告警（寄 email）。重複執行無妨。
# 用法：ALERT_EMAIL=you@example.com ./ops/setup_monitoring.sh
set -euo pipefail
cd "$(dirname "$0")"

PROJECT_ID="${PROJECT_ID:-$(gcloud config get-value project 2>/dev/null)}"
REGION="${REGION:-asia-east1}"
SERVICE="${SERVICE:-sleep-linebot}"
ALERT_EMAIL="${ALERT_EMAIL:?set ALERT_EMAIL=you@example.com}"
G="gcloud --project $PROJECT_ID --quiet"

# 第一次用 beta 指令時 gcloud 會先安裝元件並印出雜訊，先裝好，免得被當成資源名稱抓進變數
gcloud components install beta --quiet > /dev/null 2>&1 || true
first_resource() { grep -m1 '^projects/' || true; }

render() {  # 把 JSON 範本中的佔位字換成實際值
  sed -e "s|__SERVICE__|$SERVICE|g" -e "s|__CHANNEL__|${CHANNEL:-}|g" -e "s|__CHECK_ID__|${CHECK_ID:-}|g" "$1"
}
tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT

echo "== Log-based metrics"
SVC_FILTER="resource.type=\"cloud_run_revision\" AND resource.labels.service_name=\"$SERVICE\""
create_metric() {
  $G logging metrics describe "$1" > /dev/null 2>&1 && { echo "exists: $1"; return; }
  $G logging metrics create "$1" --description "$2" --log-filter "$3"
}
create_metric sleepbot_alarm_check_runs "Completed /tasks/check-alarms runs" \
  "$SVC_FILTER AND jsonPayload.event=\"alarm_check_completed\""
create_metric sleepbot_errors "ERROR logs from sleep-linebot" \
  "$SVC_FILTER AND severity>=ERROR"

echo "== Notification channel ($ALERT_EMAIL)"
CHANNEL=$($G beta monitoring channels list --filter "type=\"email\" AND labels.email_address=\"$ALERT_EMAIL\"" \
  --format 'value(name)' | first_resource)
if [ -z "$CHANNEL" ]; then
  CHANNEL=$($G beta monitoring channels create --display-name "sleep-linebot alerts" --type email \
    --channel-labels "email_address=$ALERT_EMAIL" --format 'value(name)' | first_resource)
fi
[ -n "$CHANNEL" ] || { echo "Failed to find or create notification channel" >&2; exit 1; }
echo "$CHANNEL"

echo "== Uptime check"
URL=$($G run services describe "$SERVICE" --region "$REGION" --format 'value(status.url)')
HOST="${URL#https://}"
CHECK_NAME="$SERVICE-health"
CHECK=$($G monitoring uptime list-configs --filter "displayName=\"$CHECK_NAME\"" --format 'value(name)' | first_resource)
if [ -z "$CHECK" ]; then
  $G monitoring uptime create "$CHECK_NAME" --resource-type uptime-url \
    --resource-labels "host=$HOST,project_id=$PROJECT_ID" --protocol https --path / \
    --period 5 --timeout 10 --matcher-type contains-string --matcher-content running
  CHECK=$($G monitoring uptime list-configs --filter "displayName=\"$CHECK_NAME\"" --format 'value(name)' | first_resource)
fi
CHECK_ID="${CHECK##*/}"
echo "$CHECK_ID"

echo "== Alert policies"
for f in monitoring/*.json; do
  [ "$(basename "$f")" = dashboard.json ] && continue
  render "$f" > "$tmp/policy.json"
  name=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["displayName"])' "$tmp/policy.json")
  if [ -n "$($G monitoring policies list --filter "displayName=\"$name\"" --format 'value(name)')" ]; then
    echo "exists: $name"
  else
    $G monitoring policies create --policy-from-file "$tmp/policy.json" --format 'value(name)'
  fi
done

echo "== Dashboard"
if [ -z "$($G monitoring dashboards list --filter "displayName=\"$SERVICE\"" --format 'value(name)')" ]; then
  render monitoring/dashboard.json > "$tmp/dashboard.json"
  $G monitoring dashboards create --config-from-file "$tmp/dashboard.json" --format 'value(name)'
else
  echo "exists: $SERVICE"
fi

echo
echo "Done: https://console.cloud.google.com/monitoring/dashboards?project=$PROJECT_ID"
