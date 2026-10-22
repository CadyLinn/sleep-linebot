# 維運：CI/CD、監控、效能、壓力測試

## 流程總覽

```text
PR / push ─▶ Lint & test（ruff + pytest + Firestore emulator）
          ─▶ Docker build
          ─▶ Load test（PR 上跑 60 秒，p95 > 1s 或失敗率 > 1% 就失敗）
push main ─▶ Deploy：build image → 部署新 revision（0% 流量）→ smoke test
                     → 通過才切 100% 流量；沒通過時正式流量完全不受影響
```

## 一次性設定（照順序）

```bash
# 1. GitHub Actions 免金鑰部署（Workload Identity Federation），並寫入 repo variables
PROJECT_ID=sleep-linebot ./ops/setup_github_deploy.sh

# 2. Firestore 複合索引（查詢加速用；沒建好也能動，只是退回全量掃描）
./ops/firestore_indexes.sh

# 3. 監控與告警（email 通知）
ALERT_EMAIL=you@example.com ./ops/setup_monitoring.sh
```

第 1 步完成前，CI 的 `Deploy` job 會自動略過。可在 GitHub → Settings → Environments → `production` 加上「需要核准」，部署前就會停下來等你按確認。

## 監控項目

| 告警 | 條件 | 代表什麼 |
| --- | --- | --- |
| 鬧鐘排程停止 | 10 分鐘內沒有 `alarm_check_completed` log | Cloud Scheduler 停了，**所有鬧鐘都不會響** |
| 5xx 錯誤 | 5 分鐘內 > 5 個 | 程式錯誤或部署壞掉 |
| 回應變慢 | p95 > 2s 持續 10 分鐘 | Firestore 索引缺失、冷啟動、LINE API 變慢 |
| 錯誤 log | 任何 `severity>=ERROR` | 例如某位使用者鬧鐘推播失敗 |
| 服務無法連線 | uptime check 失敗 | 服務掛掉，LINE webhook 也收不到 |

儀表板「sleep-linebot」：請求數（依狀態碼）、p50/p95/p99 延遲、instance 數、CPU、每分鐘鬧鐘檢查次數、錯誤 log 數。

Cloud Run 上 log 是 JSON 格式（`severity`、`event` 等欄位），可在 Logs Explorer 直接篩選，例如：

```text
resource.labels.service_name="sleep-linebot" jsonPayload.event="alarm_check_completed"
```

## 回滾

```bash
gcloud run revisions list --service sleep-linebot --region asia-east1
gcloud run services update-traffic sleep-linebot --region asia-east1 --to-revisions=<REVISION>=100
```

## 壓力測試

全部在本機跑：Firestore emulator + `LINE_DRY_RUN=1`（不呼叫 LINE API），不會碰到正式資料。

```bash
pip install -r requirements.txt -r loadtest/requirements.txt
USERS=50 DURATION=2m RECORDS_PER_USER=200 ./loadtest/run_local.sh
open loadtest/out/report.html
```

情境：模擬使用者以不同比例呼叫開始睡覺 → 狀態 → 起床、今日統計、週報告、選單、設定/取消鬧鐘、睡眠週期，另有一個模擬 Cloud Scheduler 每 5 秒打 `/tasks/check-alarms`。每位使用者預先灌入 `RECORDS_PER_USER` 筆歷史紀錄，模擬長期使用者。

門檻（環境變數）：`LOADTEST_P95_MS`（預設 1000）、`LOADTEST_MAX_FAIL`（預設 0.01）。GitHub Actions → Load test → Run workflow 可指定人數與時間。

> 不要對正式服務跑壓測：會用假的 reply token 呼叫 LINE API，並把測試資料寫進正式 Firestore。
