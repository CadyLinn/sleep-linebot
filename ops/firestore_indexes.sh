#!/usr/bin/env bash
# 建立 db.py 查詢用的 Firestore 複合索引（重複執行無妨）。
# 索引還沒建好之前，db.py 會自動退回全量掃描，所以不會壞，只是比較慢。
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-$(gcloud config get-value project 2>/dev/null)}"

create_index() {
  local out
  if out=$(gcloud firestore indexes composite create --project "$PROJECT_ID" --async \
      --collection-group=sleep_records --query-scope=COLLECTION "$@" 2>&1); then
    echo "Creating index: $*"
  elif grep -qi "already exists" <<< "$out"; then
    echo "Index exists: $*"
  else
    echo "$out" >&2
    return 1
  fi
}

# get_latest_record：where user_id == ? order by sleep_start desc limit 1
create_index --field-config=field-path=user_id,order=ascending \
             --field-config=field-path=sleep_start,order=descending
# get_week_records：where user_id == ? and date >= ?
create_index --field-config=field-path=user_id,order=ascending \
             --field-config=field-path=date,order=ascending

echo
gcloud firestore indexes composite list --project "$PROJECT_ID" \
  --format="table(name.basename(), state, fields[].fieldPath.list())"
