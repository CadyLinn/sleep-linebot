#!/usr/bin/env bash
# 一次性設定：讓 GitHub Actions 用 Workload Identity Federation（免金鑰）部署到 Cloud Run。
# 用法：PROJECT_ID=sleep-linebot ./ops/setup_github_deploy.sh
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-$(gcloud config get-value project 2>/dev/null)}"
REGION="${REGION:-asia-east1}"
SERVICE="${SERVICE:-sleep-linebot}"
GITHUB_REPO="${GITHUB_REPO:-CadyLinn/sleep-linebot}"
AR_REPO=sleep-linebot
POOL=github
PROVIDER=github
DEPLOY_SA="github-deployer@${PROJECT_ID}.iam.gserviceaccount.com"

PROJECT_NUMBER=$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')
echo "Project: $PROJECT_ID ($PROJECT_NUMBER), region: $REGION, repo: $GITHUB_REPO"

gcloud services enable --project "$PROJECT_ID" \
  run.googleapis.com artifactregistry.googleapis.com iam.googleapis.com \
  iamcredentials.googleapis.com sts.googleapis.com firestore.googleapis.com \
  monitoring.googleapis.com logging.googleapis.com

gcloud artifacts repositories describe "$AR_REPO" --location "$REGION" --project "$PROJECT_ID" > /dev/null 2>&1 ||
  gcloud artifacts repositories create "$AR_REPO" --repository-format=docker \
    --location "$REGION" --project "$PROJECT_ID" --description "sleep-linebot images"

gcloud iam service-accounts describe "$DEPLOY_SA" --project "$PROJECT_ID" > /dev/null 2>&1 ||
  gcloud iam service-accounts create github-deployer --project "$PROJECT_ID" \
    --display-name "GitHub Actions deployer"

for role in roles/run.developer roles/artifactregistry.writer; do
  gcloud projects add-iam-policy-binding "$PROJECT_ID" --quiet --condition=None \
    --member "serviceAccount:$DEPLOY_SA" --role "$role" > /dev/null
done

# 部署時要能「以 Cloud Run 執行身分」建立新 revision
RUNTIME_SA=$(gcloud run services describe "$SERVICE" --region "$REGION" --project "$PROJECT_ID" \
  --format='value(spec.template.spec.serviceAccountName)')
RUNTIME_SA="${RUNTIME_SA:-${PROJECT_NUMBER}-compute@developer.gserviceaccount.com}"
gcloud iam service-accounts add-iam-policy-binding "$RUNTIME_SA" --project "$PROJECT_ID" --quiet \
  --member "serviceAccount:$DEPLOY_SA" --role roles/iam.serviceAccountUser > /dev/null

gcloud iam workload-identity-pools describe "$POOL" --location global --project "$PROJECT_ID" > /dev/null 2>&1 ||
  gcloud iam workload-identity-pools create "$POOL" --location global --project "$PROJECT_ID" \
    --display-name "GitHub Actions"

# 只有這個 repo 的 main 分支能換到部署權限
gcloud iam workload-identity-pools providers describe "$PROVIDER" --workload-identity-pool "$POOL" \
  --location global --project "$PROJECT_ID" > /dev/null 2>&1 ||
  gcloud iam workload-identity-pools providers create-oidc "$PROVIDER" \
    --workload-identity-pool "$POOL" --location global --project "$PROJECT_ID" \
    --display-name "GitHub OIDC" \
    --issuer-uri "https://token.actions.githubusercontent.com" \
    --attribute-mapping "google.subject=assertion.sub,attribute.repository=assertion.repository,attribute.ref=assertion.ref" \
    --attribute-condition "assertion.repository=='${GITHUB_REPO}' && assertion.ref=='refs/heads/main'"

gcloud iam service-accounts add-iam-policy-binding "$DEPLOY_SA" --project "$PROJECT_ID" --quiet \
  --role roles/iam.workloadIdentityUser \
  --member "principalSet://iam.googleapis.com/projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/${POOL}/attribute.repository/${GITHUB_REPO}" > /dev/null

WIF_PROVIDER="projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/${POOL}/providers/${PROVIDER}"

echo
echo "Setting GitHub Actions variables on $GITHUB_REPO ..."
gh variable set GCP_PROJECT_ID   --repo "$GITHUB_REPO" --body "$PROJECT_ID"
gh variable set GCP_REGION       --repo "$GITHUB_REPO" --body "$REGION"
gh variable set GCP_WIF_PROVIDER --repo "$GITHUB_REPO" --body "$WIF_PROVIDER"
gh variable set GCP_DEPLOY_SA    --repo "$GITHUB_REPO" --body "$DEPLOY_SA"
echo "Done. Pushes to main will now deploy automatically."
